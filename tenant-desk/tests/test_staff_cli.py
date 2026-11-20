import io
from datetime import timedelta

import staff_cli
from app.service import handle_message
from tests.helpers import NOW, incoming_text


def run(argv, repo, wa, now=NOW):
    out = io.StringIO()
    code = staff_cli.run(argv, repo, wa, now, out=out)
    return code, out.getvalue()


def test_cli_list_takeover_reply_show(repo, wa, transcriber, media_dir):
    handle_message(incoming_text("My sink is leaking"), repo, wa, transcriber, media_dir, NOW)

    code, text = run(["list"], repo, wa)
    assert code == 0 and "TD-0001" in text

    run(["takeover", "TD-0001"], repo, wa)
    assert repo.get_ticket("TD-0001").mode == "human"

    code, text = run(["reply", "TD-0001", "Plumber booked for Tuesday"], repo, wa)
    assert "send_text" in text
    assert repo.get_history("TD-0001")[-1].direction == "staff"

    code, text = run(["show", "TD-0001"], repo, wa)
    assert "Plumber booked for Tuesday" in text

    run(["release", "TD-0001"], repo, wa)
    assert repo.get_ticket("TD-0001").mode == "bot"


def test_cli_reply_outside_window_uses_template(repo, wa, transcriber, media_dir):
    handle_message(incoming_text("My sink is leaking"), repo, wa, transcriber, media_dir, NOW)
    code, text = run(["reply", "TD-0001", "Any update?"], repo, wa, now=NOW + timedelta(days=2))
    assert "send_template" in text
    assert wa.sent()[-1]["method"] == "send_template"


def test_cli_unknown_ticket(repo, wa):
    code, text = run(["show", "TD-0042"], repo, wa)
    assert code == 1
