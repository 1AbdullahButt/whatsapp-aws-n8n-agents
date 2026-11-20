"""WhatsApp's 24-hour customer service window.

After a tenant messages us, we may send free-form replies for 24 hours.
After that, WhatsApp only allows pre-approved template messages until
the tenant writes again.
"""
from datetime import timedelta

WINDOW = timedelta(hours=24)


def inside_24h(last_inbound_ts, now):
    """True if `now` is less than 24 hours after the tenant's last inbound message."""
    if last_inbound_ts is None:
        return False
    return now - last_inbound_ts < WINDOW
