# src/claude_mesh/cli.py
"""Main CLI dispatcher for claude-mesh."""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="claude-mesh",
        description="FTAI-structured shared knowledge layer for Claude Code sessions.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Print mesh status for current context")

    p_init = sub.add_parser("init", help="Scaffold a .claude-mesh config")
    p_init.add_argument("--peer", type=str, help="Peer name (defaults to project dirname)")

    p_send = sub.add_parser("send", help="Append an event to the peer inbox / team log")
    p_send.add_argument("text", type=str, help="The message body")
    p_send.add_argument(
        "--kind", type=str, default="message",
        choices=["message", "decision", "note"],
        help="Event kind",
    )
    p_send.add_argument("--to", type=str, default=None, help="Target peer (standalone mode)")

    p_notify = sub.add_parser("notify-change", help="Append a @file_change event")
    p_notify.add_argument("path", type=str)
    p_notify.add_argument("tool", type=str)

    p_drain = sub.add_parser("drain", help="Print unread events since last-read marker")
    p_drain.add_argument("--format", choices=["ftai", "prompt"], default="ftai")
    sub.add_parser("mark-read", help="Advance the last-read marker to now")
    sub.add_parser("doctor", help="Run diagnostic checks")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Dispatch — each subcommand handler returns int exit code
    if args.command == "status":
        from claude_mesh.commands.status import run as run_status
        return run_status()
    if args.command == "init":
        from claude_mesh.commands.init import run as run_init
        return run_init(peer=args.peer)
    if args.command == "send":
        from claude_mesh.commands.send import run as run_send
        return run_send(text=args.text, kind=args.kind, to=args.to)
    if args.command == "notify-change":
        from claude_mesh.commands.notify_change import run as run_notify
        return run_notify(path=args.path, tool=args.tool)
    if args.command == "drain":
        from claude_mesh.commands.drain import run as run_drain
        return run_drain(fmt=args.format)
    if args.command == "mark-read":
        from claude_mesh.commands.mark_read import run as run_mark
        return run_mark()
    if args.command == "doctor":
        from claude_mesh.commands.doctor import run as run_doctor
        return run_doctor()

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
