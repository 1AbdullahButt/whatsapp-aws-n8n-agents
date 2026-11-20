"""Service-level tests: handoff, urgent routing, 24h window, voice notes."""
from datetime import timedelta
from pathlib import Path

from app.parser import IncomingMessage
from app.service import UPDATE_TEMPLATE, handle_message, send_update
from app.window import inside_24h
from tests.helpers import NOW, TENANT_PHONE, incoming_text


def handle(msg, repo, wa, transcriber, media_dir, now=NOW):
    return handle_message(msg, repo, wa, transcriber, media_dir, now)


def test_new_message_creates_ticket_and_replies(repo, wa, transcriber, media_dir):
    result = handle(incoming_text("My sink is leaking"), repo, wa, transcriber, media_dir)
    assert result.status == "replied"
    assert result.ticket_id == "TD-0001"
    [sent] = wa.sent()
    assert sent["method"] == "send_text"
    assert "TD-0001" in sent["text"]
    assert repo.get_ticket("TD-0001").category == "plumbing"


def test_second_message_goes_to_same_open_ticket(repo, wa, transcriber, media_dir):
    handle(incoming_text("My sink is leaking", wa_id="wamid.1"), repo, wa, transcriber, media_dir)
    result = handle(incoming_text("It is getting worse", wa_id="wamid.2"),
                    repo, wa, transcriber, media_dir)
    assert result.ticket_id == "TD-0001"
    assert len(repo.list_tickets()) == 1


def test_handoff_no_auto_reply_and_full_history(repo, wa, transcriber, media_dir):
    handle(incoming_text("My sink is leaking", wa_id="wamid.1"), repo, wa, transcriber, media_dir)
    repo.set_mode("TD-0001", "human")

    result = handle(incoming_text("Hello? Anyone there?", wa_id="wamid.2"),
                    repo, wa, transcriber, media_dir)
    handle(incoming_text("Water on the floor now", wa_id="wamid.3"),
           repo, wa, transcriber, media_dir)

    assert result.status == "stored_no_reply"
    assert len(wa.sent()) == 1  # only the first auto reply, before takeover
    assert len(repo.list_tickets()) == 1
    history = repo.get_history("TD-0001")
    assert [m.direction for m in history] == ["in", "out", "in", "in"]
    assert history[-1].text == "Water on the floor now"

    # Release back to the bot: auto replies start again.
    repo.set_mode("TD-0001", "bot")
    handle(incoming_text("Thanks", wa_id="wamid.4"), repo, wa, transcriber, media_dir)
    assert len(wa.sent()) == 2


def test_urgent_gas_reply_mentions_urgent(repo, wa, transcriber, media_dir):
    handle(incoming_text("I can smell gas in the kitchen"), repo, wa, transcriber, media_dir)
    ticket = repo.get_ticket("TD-0001")
    assert ticket.urgent
    assert ticket.category == "heating"
    assert "URGENT" in wa.sent()[0]["text"]


def test_later_urgent_message_escalates_open_ticket(repo, wa, transcriber, media_dir):
    handle(incoming_text("The kitchen tap drips", wa_id="wamid.1"), repo, wa, transcriber, media_dir)
    assert not repo.get_ticket("TD-0001").urgent
    handle(incoming_text("Now there is flooding under the sink", wa_id="wamid.2"),
           repo, wa, transcriber, media_dir)
    assert repo.get_ticket("TD-0001").urgent
    assert len(repo.list_tickets()) == 1
    assert "URGENT" in wa.sent()[-1]["text"]


def test_non_urgent_reply_has_no_urgent_notice(repo, wa, transcriber, media_dir):
    handle(incoming_text("The kitchen tap drips"), repo, wa, transcriber, media_dir)
    assert "URGENT" not in wa.sent()[0]["text"]


# --- 24-hour window -------------------------------------------------------

def test_inside_24h_function():
    assert inside_24h(NOW - timedelta(hours=23), NOW)
    assert not inside_24h(NOW - timedelta(hours=25), NOW)
    assert not inside_24h(None, NOW)


def test_send_update_inside_window_uses_text(repo, wa, transcriber, media_dir):
    handle(incoming_text("My sink is leaking"), repo, wa, transcriber, media_dir)
    ticket = repo.get_ticket("TD-0001")
    method = send_update(repo, wa, ticket, "Plumber booked for Tuesday", NOW + timedelta(hours=2))
    assert method == "send_text"
    assert wa.sent()[-1] == {"method": "send_text", "to": TENANT_PHONE,
                             "text": "Plumber booked for Tuesday"}


def test_send_update_outside_window_uses_template(repo, wa, transcriber, media_dir):
    handle(incoming_text("My sink is leaking"), repo, wa, transcriber, media_dir)
    ticket = repo.get_ticket("TD-0001")
    later = NOW + timedelta(hours=30)
    method = send_update(repo, wa, ticket, "Plumber booked for Tuesday", later)
    assert method == "send_template"
    last = wa.sent()[-1]
    assert last["name"] == UPDATE_TEMPLATE
    assert last["params"] == ["TD-0001", "Plumber booked for Tuesday"]
    # The update is still stored on the ticket.
    assert repo.get_history("TD-0001")[-1].text == "Plumber booked for Tuesday"


def test_new_inbound_reopens_window_after_long_silence(repo, wa, transcriber, media_dir):
    # Tenant wrote 3 days ago, then writes again now. The new message opens
    # the window, so the auto reply is free-form text, not a template.
    three_days_ago = NOW - timedelta(days=3)
    handle(incoming_text("My sink is leaking", wa_id="wamid.old", at=three_days_ago),
           repo, wa, transcriber, media_dir, now=three_days_ago + timedelta(minutes=1))
    handle(incoming_text("Still leaking", wa_id="wamid.new"), repo, wa, transcriber, media_dir)
    assert [c["method"] for c in wa.sent()] == ["send_text", "send_text"]


# --- voice notes ------------------------------------------------------------

def test_voice_note_saved_transcribed_and_classified(repo, wa, transcriber, media_dir):
    wa.media_bytes = b"OggS-fake-voice-note"
    msg = IncomingMessage(wa_message_id="wamid.AUDIO=1", from_phone=TENANT_PHONE,
                          timestamp=NOW - timedelta(minutes=1), kind="audio", media_id="MEDIA001")

    result = handle(msg, repo, wa, transcriber, media_dir)

    assert {"method": "download_media", "media_id": "MEDIA001"} in wa.calls
    saved = Path(media_dir) / "wamid.AUDIO_1.ogg"
    assert saved.read_bytes() == b"OggS-fake-voice-note"
    assert transcriber.paths == [str(saved)]
    assert repo.get_ticket(result.ticket_id).category == "heating"
    [stored] = repo.get_history(result.ticket_id)[:1]
    assert stored.text == "the boiler is broken"
    assert stored.media_path == str(saved)
