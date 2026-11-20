"""DynamoDB version of the repository (for the AWS milestone).

Single-table design. Every item has a partition key `pk` and sort key `sk`:

    pk                     sk            what it holds
    ---------------------  ------------  ------------------------------------
    COUNTER                TICKET        value = last ticket number used
    WAMSG#<wa_message_id>  SEEN          dedupe marker for one WhatsApp message
    TICKET#<TD-0001>       META          phone, category, urgent, mode, status,
                                         created_at, msg_count
    TICKET#<TD-0001>       MSG#000001    one message (direction, text, at, ...)
    PHONE#<phone>          PROFILE       open_ticket, last_inbound

- Dedupe: put the WAMSG item with ConditionExpression
  attribute_not_exists(pk). A second put for the same id fails, so we
  know it is a duplicate. Safe even with two servers at once.
- Ticket numbers: one atomic `ADD value :one` on the COUNTER item.
- Messages for a ticket sort by sk, so one Query returns the history in order.
- list_tickets uses a Scan. Fine for a prototype with a few tickets; a
  bigger setup would add an index instead.
"""
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from app.repository import (Repository, StoredMessage, Ticket, check_direction,
                            check_mode, from_iso, ticket_number, to_iso)


class DynamoRepository(Repository):
    def __init__(self, table_name, region="us-east-1"):
        self.table = boto3.resource("dynamodb", region_name=region).Table(table_name)

    def mark_seen(self, wa_message_id):
        try:
            self.table.put_item(
                Item={"pk": f"WAMSG#{wa_message_id}", "sk": "SEEN",
                      "seen_at": to_iso(datetime.now(timezone.utc))},
                ConditionExpression="attribute_not_exists(pk)",
            )
            return True
        except ClientError as error:
            if _is_condition_failure(error):
                return False
            raise

    def create_ticket(self, phone, category, urgent):
        ticket_id = ticket_number(self._next_ticket_number())
        created_at = datetime.now(timezone.utc).replace(microsecond=0)
        self.table.put_item(Item={
            "pk": f"TICKET#{ticket_id}", "sk": "META",
            "id": ticket_id, "phone": phone, "category": category,
            "urgent": bool(urgent), "mode": "bot", "status": "open",
            "created_at": to_iso(created_at), "msg_count": 0,
        })
        self.table.update_item(
            Key={"pk": f"PHONE#{phone}", "sk": "PROFILE"},
            UpdateExpression="SET open_ticket = :t",
            ExpressionAttributeValues={":t": ticket_id},
        )
        return Ticket(ticket_id, phone, category, bool(urgent), "bot", "open", created_at)

    def _next_ticket_number(self):
        """Atomically add 1 to the counter and return the new value."""
        response = self.table.update_item(
            Key={"pk": "COUNTER", "sk": "TICKET"},
            UpdateExpression="ADD #v :one",
            ExpressionAttributeNames={"#v": "value"},
            ExpressionAttributeValues={":one": 1},
            ReturnValues="UPDATED_NEW",
        )
        return int(response["Attributes"]["value"])

    def get_ticket(self, ticket_id):
        item = self.table.get_item(Key={"pk": f"TICKET#{ticket_id}", "sk": "META"}).get("Item")
        return _item_to_ticket(item) if item else None

    def get_open_ticket(self, phone):
        profile = self._get_profile(phone)
        if not profile or "open_ticket" not in profile:
            return None
        ticket = self.get_ticket(profile["open_ticket"])
        if ticket and ticket.status == "open":
            return ticket
        return None

    def _get_profile(self, phone):
        return self.table.get_item(Key={"pk": f"PHONE#{phone}", "sk": "PROFILE"}).get("Item")

    def set_mode(self, ticket_id, mode):
        check_mode(mode)
        self.table.update_item(
            Key={"pk": f"TICKET#{ticket_id}", "sk": "META"},
            UpdateExpression="SET #m = :m",
            ExpressionAttributeNames={"#m": "mode"},
            ExpressionAttributeValues={":m": mode},
        )

    def mark_urgent(self, ticket_id):
        self.table.update_item(
            Key={"pk": f"TICKET#{ticket_id}", "sk": "META"},
            UpdateExpression="SET urgent = :u",
            ExpressionAttributeValues={":u": True},
        )

    def add_message(self, ticket_id, direction, text, at, wa_message_id=None, media_path=None):
        check_direction(direction)
        # Atomic per-ticket counter gives each message a sort key in arrival order.
        response = self.table.update_item(
            Key={"pk": f"TICKET#{ticket_id}", "sk": "META"},
            UpdateExpression="ADD msg_count :one",
            ExpressionAttributeValues={":one": 1},
            ReturnValues="ALL_NEW",
        )
        meta = response["Attributes"]
        seq = int(meta["msg_count"])
        item = {"pk": f"TICKET#{ticket_id}", "sk": f"MSG#{seq:06d}",
                "ticket_id": ticket_id, "direction": direction, "text": text, "at": to_iso(at)}
        if wa_message_id:
            item["wa_message_id"] = wa_message_id
        if media_path:
            item["media_path"] = media_path
        self.table.put_item(Item=item)
        if direction == "in":
            self._update_last_inbound(meta["phone"], at)

    def _update_last_inbound(self, phone, at):
        """Keep the newest inbound time on the phone profile (never move it backwards)."""
        try:
            self.table.update_item(
                Key={"pk": f"PHONE#{phone}", "sk": "PROFILE"},
                UpdateExpression="SET last_inbound = :t",
                ConditionExpression="attribute_not_exists(last_inbound) OR last_inbound < :t",
                ExpressionAttributeValues={":t": to_iso(at)},
            )
        except ClientError as error:
            if not _is_condition_failure(error):
                raise

    def get_history(self, ticket_id):
        response = self.table.query(
            KeyConditionExpression="pk = :pk AND begins_with(sk, :msg)",
            ExpressionAttributeValues={":pk": f"TICKET#{ticket_id}", ":msg": "MSG#"},
        )
        return [_item_to_message(item) for item in response["Items"]]

    def list_tickets(self):
        response = self.table.scan(
            FilterExpression="sk = :meta",
            ExpressionAttributeValues={":meta": "META"},
        )
        tickets = [_item_to_ticket(item) for item in response["Items"]]
        return sorted(tickets, key=lambda t: t.id)

    def last_inbound_time(self, phone):
        profile = self._get_profile(phone)
        if not profile or "last_inbound" not in profile:
            return None
        return from_iso(profile["last_inbound"])


def _is_condition_failure(error):
    return error.response["Error"]["Code"] == "ConditionalCheckFailedException"


def _item_to_ticket(item):
    return Ticket(
        id=item["id"],
        phone=item["phone"],
        category=item["category"],
        urgent=bool(item["urgent"]),
        mode=item["mode"],
        status=item["status"],
        created_at=from_iso(item["created_at"]),
    )


def _item_to_message(item):
    return StoredMessage(
        ticket_id=item["ticket_id"],
        direction=item["direction"],
        text=item["text"],
        at=from_iso(item["at"]),
        wa_message_id=item.get("wa_message_id"),
        media_path=item.get("media_path"),
    )
