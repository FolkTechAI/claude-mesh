# src/claude_mesh/cli.py
"""Main CLI dispatcher for claude-mesh."""

from __future__ import annotations

import argparse
import sys

from claude_mesh import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="claude-mesh",
        description="FTAI-structured shared knowledge layer for Claude Code sessions.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Print mesh status for current context")

    p_init = sub.add_parser("init", help="Scaffold a .claude-mesh config")
    p_init.add_argument("--peer", type=str, help="Peer name (defaults to project dirname)")
    p_init.add_argument(
        "--other",
        type=str,
        help="Other peer this session coordinates with (default 'peer')",
    )
    p_init.add_argument("--group", type=str, help="Mesh group name (default {peer}-{other})")

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

    p_task = sub.add_parser("task-event", help="Append a @task event to the peer knowledge file")
    p_task.add_argument("--id", dest="task_id", type=str, required=True, help="Task ID")
    p_task.add_argument("--subject", type=str, required=True, help="Task subject/title")
    p_task.add_argument("--to", type=str, help="Target peer (broadcast when omitted)")
    p_task.add_argument("--description", type=str, help="Task details or completion evidence")
    p_task.add_argument(
        "--status", type=str, required=True,
        choices=[
            "pending",
            "accepted",
            "in-progress",
            "blocked",
            "completed",
            "failed",
            "cancelled",
            "verified",
            "rejected",
        ],
        help="Task status",
    )

    sub.add_parser("subagent-turn", help="Auto-log a teammate turn summary from SubagentStop")

    # Sync and remote peer commands
    p_sync = sub.add_parser("sync", help="Sync inbox files with remote peers")
    p_sync.add_argument("--peer", help="Sync with a specific peer (default: all remote peers)")
    p_sync.add_argument("--watch", action="store_true", help="Keep running and sync periodically")
    p_sync.add_argument("--interval", type=int, default=30, help="Seconds between syncs in watch mode (default: 30)")
    
    sub.add_parser("remote-doctor", help="Test SSH connectivity to remote peers")

    p_work = sub.add_parser(
        "task",
        help="Reliable task ledger: ownership, leases, retries, and verification",
    )
    p_work.add_argument(
        "action",
        choices=["create", "claim", "start", "complete", "fail", "verify", "list", "sweep"],
    )
    p_work.add_argument("--id", dest="task_id")
    p_work.add_argument("--subject")
    p_work.add_argument("--description", default="")
    p_work.add_argument("--to", help="Assignee for create")
    p_work.add_argument("--priority", choices=["low", "normal", "high", "urgent"], default="normal")
    p_work.add_argument(
        "--risk",
        choices=["low", "medium", "high", "critical"],
        default="low",
    )
    p_work.add_argument("--max-attempts", type=int, default=3)
    p_work.add_argument("--idempotency-key")
    p_work.add_argument("--lease-seconds", type=int, default=900)
    p_work.add_argument("--evidence")
    p_work.add_argument("--error")
    p_work.add_argument("--verdict", choices=["pass", "fail"])
    p_work.add_argument("--status", action="append", dest="statuses")
    p_work.add_argument("--json", action="store_true", dest="as_json")
    p_work.add_argument("--workspace", default="")
    p_work.add_argument("--capability", default="coding")
    p_work.add_argument("--acceptance-criteria", default="")
    p_work.add_argument(
        "--no-approval-required",
        action="store_false",
        dest="approval_required",
        help="Allow policy to auto-run this task when its risk is eligible",
    )

    p_verify = sub.add_parser(
        "verification",
        help="Publish an independent verification receipt",
    )
    p_verify.add_argument("--id", dest="record_id", required=True)
    p_verify.add_argument("--task-id", required=True)
    p_verify.add_argument("--verdict", choices=["pass", "fail"], required=True)
    p_verify.add_argument("--evidence", required=True)
    p_verify.add_argument("--checks")
    p_verify.add_argument("--to")

    p_experience = sub.add_parser(
        "experience",
        help="Publish a verified outcome for a learning-system adapter",
    )
    p_experience.add_argument("--id", dest="record_id", required=True)
    p_experience.add_argument("--task-id", required=True)
    p_experience.add_argument("--outcome", required=True)
    p_experience.add_argument("--lesson", required=True)
    p_experience.add_argument("--evidence", required=True)
    p_experience.add_argument("--verified-by", required=True)
    p_experience.add_argument("--tag", action="append", dest="tags")
    p_experience.add_argument("--to")

    p_capability = sub.add_parser(
        "capability",
        help="Advertise an agent capability and its constraints",
    )
    p_capability.add_argument("--name", required=True)
    p_capability.add_argument("--description", required=True)
    p_capability.add_argument(
        "--risk",
        choices=["low", "medium", "high", "critical"],
        required=True,
    )
    p_capability.add_argument(
        "--status",
        choices=["available", "busy", "degraded", "disabled"],
        required=True,
    )
    p_capability.add_argument("--constraints")

    p_heartbeat = sub.add_parser("heartbeat", help="Publish token-free agent presence")
    p_heartbeat.add_argument(
        "--state",
        choices=["idle", "busy", "degraded", "offline"],
        required=True,
    )
    p_heartbeat.add_argument("--task-id")

    p_watch = sub.add_parser(
        "watch",
        help="Wait for unread mail without polling a model or consuming events",
    )
    p_watch.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Seconds to wait; 0 waits indefinitely",
    )
    p_watch.add_argument("--interval", type=float, default=0.25)
    p_watch.add_argument("--json", action="store_true", dest="as_json")

    p_supervisor = sub.add_parser(
        "supervisor",
        help="Run the approval-gated adversarial agent supervisor",
    )
    p_supervisor.add_argument(
        "action",
        choices=[
            "init",
            "submit",
            "plan",
            "run",
            "approve",
            "execute",
            "once",
            "serve",
            "recover",
            "list",
            "artifacts",
        ],
    )
    p_supervisor.add_argument("--config", type=str, dest="config_path")
    p_supervisor.add_argument("--group")
    p_supervisor.add_argument("--operator")
    p_supervisor.add_argument("--workspace-root", type=str)
    p_supervisor.add_argument("--task-id")
    p_supervisor.add_argument("--subject")
    p_supervisor.add_argument("--description", default="")
    p_supervisor.add_argument("--workspace")
    p_supervisor.add_argument("--acceptance-criteria", default="")
    p_supervisor.add_argument(
        "--risk", choices=["low", "medium", "high", "critical"], default="low"
    )
    p_supervisor.add_argument("--capability", default="coding")
    p_supervisor.add_argument("--worker")
    p_supervisor.add_argument("--idempotency-key")
    p_supervisor.add_argument(
        "--no-approval-required",
        action="store_false",
        dest="approval_required",
    )
    p_supervisor.add_argument("--run-id")
    p_supervisor.add_argument("--by", dest="approved_by")
    p_supervisor.add_argument("--stop-after", type=float)
    p_supervisor.add_argument("--json", action="store_true", dest="as_json")

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
        return run_init(peer=args.peer, group=args.group, other=args.other)
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
    if args.command == "sync":
        from claude_mesh.commands.sync import run_sync
        return run_sync(peer=args.peer, watch=args.watch, interval=args.interval)
    if args.command == "remote-doctor":
        from claude_mesh.commands.remote_doctor import run_remote_doctor
        return run_remote_doctor()
    if args.command == "task-event":
        from claude_mesh.commands.task_event import run as run_task_event
        return run_task_event(
            task_id=args.task_id,
            subject=args.subject,
            status=args.status,
            to=args.to,
            description=args.description,
        )
    if args.command == "subagent-turn":
        from claude_mesh.commands.subagent_turn import run as run_subagent_turn
        return run_subagent_turn()
    if args.command == "task":
        from claude_mesh.commands.task import run as run_task
        return run_task(
            args.action,
            task_id=args.task_id,
            subject=args.subject,
            description=args.description,
            to=args.to,
            priority=args.priority,
            risk=args.risk,
            max_attempts=args.max_attempts,
            idempotency_key=args.idempotency_key,
            lease_seconds=args.lease_seconds,
            evidence=args.evidence,
            error=args.error,
            verdict=args.verdict,
            statuses=args.statuses,
            as_json=args.as_json,
            workspace=args.workspace,
            capability=args.capability,
            acceptance_criteria=args.acceptance_criteria,
            approval_required=args.approval_required,
        )
    if args.command in {"verification", "experience", "capability", "heartbeat"}:
        from claude_mesh.commands.control import run as run_control
        return run_control(
            args.command,
            to=getattr(args, "to", None),
            record_id=getattr(args, "record_id", None),
            task_id=getattr(args, "task_id", None),
            verdict=getattr(args, "verdict", None),
            evidence=getattr(args, "evidence", None),
            checks=getattr(args, "checks", None),
            outcome=getattr(args, "outcome", None),
            lesson=getattr(args, "lesson", None),
            verified_by=getattr(args, "verified_by", None),
            tags=getattr(args, "tags", None),
            name=getattr(args, "name", None),
            description=getattr(args, "description", None),
            risk=getattr(args, "risk", None),
            status=getattr(args, "status", None),
            constraints=getattr(args, "constraints", None),
            state=getattr(args, "state", None),
        )
    if args.command == "watch":
        from claude_mesh.commands.watch import run as run_watch
        return run_watch(
            timeout=args.timeout,
            interval=args.interval,
            as_json=args.as_json,
        )
    if args.command == "supervisor":
        from pathlib import Path

        from claude_mesh.commands.supervisor import run as run_supervisor

        return run_supervisor(
            args.action,
            config_path=Path(args.config_path).expanduser() if args.config_path else None,
            group=args.group,
            workspace_root=(
                Path(args.workspace_root).expanduser() if args.workspace_root else None
            ),
            task_id=args.task_id,
            run_id=args.run_id,
            approved_by=args.approved_by,
            operator=args.operator,
            subject=args.subject,
            description=args.description,
            workspace=args.workspace,
            acceptance_criteria=args.acceptance_criteria,
            risk=args.risk,
            capability=args.capability,
            worker=args.worker,
            idempotency_key=args.idempotency_key,
            approval_required=args.approval_required,
            stop_after=args.stop_after,
            as_json=args.as_json,
        )

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
