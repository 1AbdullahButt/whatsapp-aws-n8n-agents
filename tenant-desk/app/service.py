"""The business logic: what happens when a tenant message arrives.

handle_message steps, in order:
    1. dedupe       repo.mark_seen(id); if seen before, stop (Meta retries deliveries)
    2. voice note   download the audio, save it under media_dir, transcribe it
    3. classify     category + urgent flag from the text
    4. ticket       reuse the tenant's open ticket, or create a new one
    5. store        save the inbound message on the ticket
    6. reply        if a person has taken over (mode "human"): no auto reply.
                    otherwise reply with the ticket number (+ urgent notice).

How we choose send_text vs send_template (the 24-hour window)
------------------------------------------------------------
WhatsApp allows free-form text only within 24 hours of the tenant's
LATEST inbound message. We always store the inbound message first and
then ask repo.last_inbound_time(phone). So for an auto reply the window
is measured from the message we just received: a tenant who last wrote
3 days ago and writes again today has just reopened the window, and
gets a normal text reply. (Checking the window BEFORE storing would use
the old 3-day-old message and wrongly force a template.)

The realistic template case is send_update(): staff or the bot sends an
update later (e.g. "plumber booked for Tuesday") when the tenant has not
written for over 24 hours. Then we must use the template "ticket_update".
That template would need to be created and approved in Meta's WhatsApp
Manager first; in this prototype the template send is only simulated.
"""
import re
from dataclasses import dataclass
from pathlib import Path

from app.classifier import classify
from app.window import inside_24h

UPDATE_TEMPLATE = "ticket_update"  # body: "Update on ticket {{1}}: {{2}}"


@dataclass
class HandleResult:
    status: str  # "duplicate", "replied", "stored_no_reply"
    ticket_id: str = None


def handle_message(msg, repo, wa_client, transcriber, media_dir, now, media_saver=None):
    """Process one IncomingMessage. `now` is passed in so tests control time.

    media_saver(wa_client, msg) -> path or URL of the stored audio. The local
    server saves to media_dir; the AWS worker passes one that saves to S3.
    """
    # 1. Dedupe first, so a repeated delivery never creates a ticket or a reply.
    # Trade-off: if we crash after this line, Meta's retry is ignored too.
    if not repo.mark_seen(msg.wa_message_id):
        return HandleResult("duplicate")

    # 2. Voice note -> text.
    text = msg.text
    media_path = None
    if msg.kind == "audio":
        if media_saver is None:
            media_path = save_media(wa_client, msg, media_dir)
        else:
            media_path = media_saver(wa_client, msg)
        text = transcriber.transcribe(media_path)

    # 3. Classify. The month matters for "no heating" (urgent only in winter).
    result = classify(text, now.month)

    # 4. One open ticket per tenant phone.
    ticket = repo.get_open_ticket(msg.from_phone)
    is_new = ticket is None
    if is_new:
        ticket = repo.create_ticket(msg.from_phone, result.category, result.urgent)
    elif result.urgent and not ticket.urgent:
        # A later message can raise an existing ticket to urgent (e.g. "now I smell gas").
        # It never lowers it: once urgent, staff decide.
        repo.mark_urgent(ticket.id)
        ticket = repo.get_ticket(ticket.id)

    # 5. Store the inbound message (this also moves the 24h window forward).
    repo.add_message(ticket.id, "in", text, msg.timestamp,
                     wa_message_id=msg.wa_message_id, media_path=media_path)

    # 6. Reply, unless a person is handling this ticket.
    if ticket.mode == "human":
        return HandleResult("stored_no_reply", ticket.id)
    reply = build_reply(ticket, is_new, result.urgent)
    send_update(repo, wa_client, ticket, reply, now)
    return HandleResult("replied", ticket.id)


def build_reply(ticket, is_new, urgent):
    if is_new:
        text = f"Thanks, we have logged your request as ticket {ticket.id} ({ticket.category})."
    else:
        text = f"Thanks, we have added your message to ticket {ticket.id}."
    if urgent:
        text += (" This looks URGENT, so staff will see it first."
                 " If anyone is in danger, leave the property and call the emergency services.")
    return text


def send_update(repo, wa_client, ticket, text, now, direction="out"):
    """Send a message to the tenant on a ticket, respecting the 24h window.

    Inside the window: free-form send_text.
    Outside: send_template("ticket_update", [ticket id, text]).
    The message is stored on the ticket either way. Returns the method used.
    """
    last_inbound = repo.last_inbound_time(ticket.phone)
    if inside_24h(last_inbound, now):
        wa_client.send_text(ticket.phone, text)
        method = "send_text"
    else:
        wa_client.send_template(ticket.phone, UPDATE_TEMPLATE, [ticket.id, text])
        method = "send_template"
    repo.add_message(ticket.id, direction, text, now)
    return method


def save_media(wa_client, msg, media_dir):
    """Download a voice note and save it as <media_dir>/<message id>.ogg."""
    audio = wa_client.download_media(msg.media_id)
    folder = Path(media_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{safe_filename(msg.wa_message_id)}.ogg"
    path.write_bytes(audio)
    return str(path)


def safe_filename(name):
    """WhatsApp ids can contain characters like '=' or '/'; keep letters, digits, - _ ."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)
