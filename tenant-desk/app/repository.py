"""Storage interface for tickets and messages.

The service only talks to this interface, so the same logic runs on
SQLite (local) and DynamoDB (AWS later). Both are checked by the same
contract tests in tests/test_repository_contract.py.

Methods:
    mark_seen(wa_message_id) -> bool
        Record a WhatsApp message id. Returns False if it was seen before.
        This is the dedupe step and runs first, before any ticket work.
    create_ticket(phone, category, urgent) -> Ticket   (number like "TD-0001")
    get_ticket(ticket_id) -> Ticket or None
    get_open_ticket(phone) -> Ticket or None
    set_mode(ticket_id, mode)        mode is "bot" or "human"
    add_message(ticket_id, direction, text, at, wa_message_id=None, media_path=None)
        direction is "in" (tenant), "out" (bot) or "staff" (a person).
    get_history(ticket_id) -> list of StoredMessage, oldest first
    list_tickets() -> list of Ticket, oldest first
    last_inbound_time(phone) -> datetime or None
        Time of the newest "in" message from this phone, on any ticket.

The ticket id IS the human-friendly number ("TD-0001"), to keep one id.
All times are timezone-aware UTC datetimes.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

MODES = ("bot", "human")
DIRECTIONS = ("in", "out", "staff")


@dataclass
class Ticket:
    id: str  # e.g. "TD-0001"
    phone: str
    category: str
    urgent: bool
    mode: str  # "bot" or "human"
    status: str  # "open" or "closed" (staff close it; the tenant's next message opens a new one)
    created_at: datetime


@dataclass
class StoredMessage:
    ticket_id: str
    direction: str
    text: str
    at: datetime
    wa_message_id: str = None
    media_path: str = None


def ticket_number(n):
    """1 -> "TD-0001"."""
    return f"TD-{n:04d}"


def to_iso(dt):
    """Store times as fixed-format UTC text, so text order equals time order."""
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def from_iso(text):
    return datetime.fromisoformat(text)


class Repository(ABC):
    @abstractmethod
    def mark_seen(self, wa_message_id): ...

    @abstractmethod
    def create_ticket(self, phone, category, urgent): ...

    @abstractmethod
    def get_ticket(self, ticket_id): ...

    @abstractmethod
    def get_open_ticket(self, phone): ...

    @abstractmethod
    def set_mode(self, ticket_id, mode): ...

    @abstractmethod
    def mark_urgent(self, ticket_id): ...

    @abstractmethod
    def close_ticket(self, ticket_id): ...

    @abstractmethod
    def add_message(self, ticket_id, direction, text, at, wa_message_id=None, media_path=None): ...

    @abstractmethod
    def get_history(self, ticket_id): ...

    @abstractmethod
    def list_tickets(self): ...

    @abstractmethod
    def last_inbound_time(self, phone): ...


def check_mode(mode):
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")


def check_direction(direction):
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {DIRECTIONS}, got {direction!r}")
