# Grok Build adapter

Run Grok Build as a mesh peer alongside Claude Code sessions — same mailbox, same
FTAI files, same CLI. Only the harness adapter differs.

## Install

```bash
scripts/install_grok_adapter.sh            # install
scripts/install_grok_adapter.sh --uninstall
```

Writes two things:

| Path | Purpose |
|---|---|
| `~/.grok/hooks/claude-mesh.json` | Hook registration |
| `~/.grok/skills/claude-mesh/SKILL.md` | On-demand drain/send skill |

Installed **globally** on purpose: per grok's docs, hooks in `~/.grok/hooks/` are
always trusted, while project-level hooks additionally require `/hooks-trust` per
repo — easy to forget, and it fails silently.

## Then add the peer to a group

```yaml
# .claude-mesh in the Grok project
mesh_group: serena-myelin
mesh_peer: grok
mesh_peers:
  - serena
  - myelin
  - grok
cross_cutting_paths:
  - src/**
```

Every peer in the group needs `grok` in its own `mesh_peers` roster too, or mail
won't fan out to it.

## What's wired

| Grok event | Action | Notes |
|---|---|---|
| `PostToolUse` | `notify-change` → `@file_change` to every other peer | matcher covers `search_replace`, `write_file`, `create_file`, `edit_file`, `apply_patch`, `str_replace`, `multi_edit` |
| `Stop` / `SubagentStop` | drain unread → `additionalContext` | the only injection surface grok exposes |

## Why drain happens at Stop, not UserPromptSubmit

Claude Code injects mesh context by returning `{"modified_prompt": ...}` from
`UserPromptSubmit`. **Grok cannot do this.** Its `UserPromptSubmit` is a passive
event, and passive events' stdout is discarded
(`~/.grok/docs/user-guide/10-hooks.md` § *Passive Hooks*). Only `PreToolUse`
(allow/deny) and `Stop`/`SubagentStop` (`hookSpecificOutput.additionalContext`)
can put text in front of the model.

So mail lands at the **end** of a turn and the agent keeps working with it,
rather than arriving before the turn starts. Guards keep that bounded:

- fires only when `reason == "end_turn"` — skips the observe-only session-end Stop
- fires only when `stopHookActive` is false — **at most one injection per turn**,
  well inside grok's 8-continuation cap
- fires only when there is actually unread mail
- `CLAUDE_MESH_GROK_STOP_DRAIN=0` disables it without unregistering

For start-of-task drains, use the installed skill (`claude-mesh drain --format=prompt`).

## Field mapping

Grok's envelope differs from Claude's; the adapter normalizes it:

| Concern | Claude Code | Grok Build |
|---|---|---|
| envelope keys | snake_case (`tool_name`, `tool_input`) | **camelCase** (`toolName`, `toolInput`) |
| tool output | `tool_response` | `toolResult` |
| project root | `cwd` | `workspaceRoot` (preferred), `cwd` |
| edit tools | `Edit` / `Write` / `NotebookEdit` | `search_replace` et al. |
| hook config | `.claude/settings.json` | `.grok/settings.json`, `~/.grok/hooks/*.json` |

The tool name is written into the event verbatim, so a drained `@file_change`
shows `tool: search_replace` and you can tell which harness made the edit.

## Troubleshooting

```bash
claude-mesh doctor          # from the project directory
tail ~/.claude-mesh/errors.log   # adapter failures land here, prefixed [grok]
```

Hooks always exit 0 and never block a turn. A misconfigured mesh degrades to
"no mail", never to a stalled agent.
