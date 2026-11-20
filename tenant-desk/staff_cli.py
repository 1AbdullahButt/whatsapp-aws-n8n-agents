"""Staff command line for the tenant desk.

    .venv\\Scripts\\python staff_cli.py list
    .venv\\Scripts\\python staff_cli.py show TD-0001
    .venv\\Scripts\\python staff_cli.py takeover TD-0001   # bot stops auto replying
    .venv\\Scripts\\python staff_cli.py release TD-0001    # bot replies again
    .venv\\Scripts\\python staff_cli.py reply TD-0001 "Plumber booked for Tuesday 9am"

`reply` stores the text as a "staff" message and sends it to the tenant,
as free text inside the 24h window or as the ticket_update template outside it.
"""
import argparse
import sys
from datetime import datetime, timezone

import app  # noqa: F401  (adds the shared/ folder to sys.path)
from app.service import send_update


def cmd_list(repo, out):
    tickets = repo.list_tickets()
    if not tickets:
        print("No tickets yet.", file=out)
    for t in tickets:
        flag = "URGENT" if t.urgent else ""
        print(f"{t.id}  {t.phone}  {t.category:<10} {t.mode:<5} {t.status:<6} {flag}", file=out)


def cmd_show(repo, ticket, out):
    print(f"{ticket.id}  phone {ticket.phone}  {ticket.category}  mode={ticket.mode}"
          f"  urgent={ticket.urgent}", file=out)
    for m in repo.get_history(ticket.id):
        extra = f"  [audio: {m.media_path}]" if m.media_path else ""
        print(f"  {m.at:%Y-%m-%d %H:%M}  {m.direction:<5} {m.text}{extra}", file=out)


def cmd_set_mode(repo, ticket, mode, out):
    repo.set_mode(ticket.id, mode)
    print(f"{ticket.id} is now in {mode} mode.", file=out)


def cmd_reply(repo, wa_client, ticket, text, now, out):
    method = send_update(repo, wa_client, ticket, text, now, direction="staff")
    print(f"Sent to {ticket.phone} via {method}.", file=out)


def build_parser():
    parser = argparse.ArgumentParser(description="Tenant desk staff tools")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list all tickets")
    for name in ("show", "takeover", "release"):
        sub.add_parser(name).add_argument("ticket")
    reply = sub.add_parser("reply", help="send a staff message to the tenant")
    reply.add_argument("ticket")
    reply.add_argument("text")
    return parser


def run(argv, repo, wa_client, now, out=sys.stdout):
    """Run one command. Takes its dependencies so tests can pass fakes."""
    args = build_parser().parse_args(argv)
    if args.command == "list":
        cmd_list(repo, out)
        return 0
    ticket = repo.get_ticket(args.ticket)
    if ticket is None:
        print(f"No ticket {args.ticket}", file=out)
        return 1
    if args.command == "show":
        cmd_show(repo, ticket, out)
    elif args.command == "takeover":
        cmd_set_mode(repo, ticket, "human", out)
    elif args.command == "release":
        cmd_set_mode(repo, ticket, "bot", out)
    elif args.command == "reply":
        cmd_reply(repo, wa_client, ticket, args.text, now, out)
    return 0


def main():
    from app.webhook import build_deps, load_settings
    deps = build_deps(load_settings())
    return run(sys.argv[1:], deps.repo, deps.wa_client, datetime.now(timezone.utc))


if __name__ == "__main__":
    sys.exit(main())
