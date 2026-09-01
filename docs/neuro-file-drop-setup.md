# Neuro Setup: File-Drop Transport to Mac Hub

This guide explains how to configure **Neuro** (running on Cursor's Grok Bot Linux box) to coordinate with Claude Code, Hermes, Codex, and other agents on Mike's Mac mini via file-drop transport.

**No SSH required.** Neuro uses Grok Bot's registered-computer Shell tool to run Mac-side CLI commands.

---

## Topology

- **Mac mini** (`Michaels-Mac-mini.local`) is the mesh hub
  - User: `michaelfolk`
  - Home: `/Users/michaelfolk`
  - Existing claude-mesh: `/opt/homebrew/bin/claude-mesh` (v0.3.2)
  - Existing groups: serena-myelin, folktech-supervisor, groklive, etc.
  - Agents: Claude Code, Hermes, Codex, Grok Build (all same-machine peers)

- **Grok Bot Linux box** (Cursor-managed) runs Neuro
  - User: `box`
  - Home: `/home/box`
  - Hostname: `cursor`
  - **NOT on Mike's LAN** — uses registered-computer tools when Grok Bot app is open on Mac

- **Existing Mac reach**:
  - `/Users/michaelfolk/bin/neuro` — notes, calendar, iMessage commands
  - Grok Bot registered-computer Shell tool

---

## How It Works

**Hub model**: Mac mini is the source of truth. Neuro's FTAI inbox lives on the Mac at:
```
/Users/michaelfolk/.claude-mesh/groups/mac-neuro-mesh/neuro-grokbot.ftai
```

**Default transport (RECOMMENDED)**:
- Neuro runs Mac-side CLI via registered-computer Shell: `neuro-mesh send|drain|task`
- The `neuro-mesh` wrapper runs `/opt/homebrew/bin/claude-mesh` with `CLAUDE_MESH_PEER=neuro-grokbot`
- Mac's claude-mesh handles all FTAI file operations (append-only, atomic)

**No daemon needed** on Mac — existing PostToolUse hooks handle same-machine peers.

---

## Prerequisites

### On Mac Mini

- **claude-mesh already installed**: `/opt/homebrew/bin/claude-mesh` (v0.3.2)
- **Existing groups**: serena-myelin, folktech-supervisor, groklive, etc.
- **New group for Neuro**: `mac-neuro-mesh` (DO NOT add Neuro to existing groups)

### On Grok Bot Box

- Grok Bot app open on Mac (for registered-computer tools)
- No installation needed on Grok Bot box

---

## One-Time Setup

### Step 1: Create Dedicated Mesh Group on Mac

⚠️ **CRITICAL**: Neuro needs its own dedicated group. Do NOT add `neuro-grokbot` to existing groups (serena-myelin, folktech-supervisor, groklive, etc.).

On **Mac mini**, create a new project directory or use existing project:

```bash
cd /Users/michaelfolk/Developer/your-project
```

Create `.claude-mesh`:

```yaml
mesh_group: mac-neuro-mesh
mesh_peer: claude-mac
mesh_peers:
  - claude-mac
  - neuro-grokbot
cross_cutting_paths:
  - src/**
  - api/**
```

**Key points**:
- **New group**: `mac-neuro-mesh` (NOT serena-myelin, etc.)
- `neuro-grokbot` listed as peer
- No `remote_peers` section (Neuro uses file-drop, not SSH)

**Hub directory will be created at**:
```
/Users/michaelfolk/.claude-mesh/groups/mac-neuro-mesh/
```

### Step 2: Install Mac-Side Wrapper

On **Mac mini**, create the wrapper as a sibling to existing `neuro`:

```bash
cat > /Users/michaelfolk/bin/neuro-mesh << 'EOF'
#!/bin/bash
# neuro-mesh: Wrapper for Neuro to run claude-mesh on Mac as neuro-grokbot peer

export CLAUDE_MESH_PEER=neuro-grokbot

# Use existing claude-mesh binary
exec /opt/homebrew/bin/claude-mesh "$@"
EOF

chmod +x /Users/michaelfolk/bin/neuro-mesh
```

**Verify**:
```bash
/Users/michaelfolk/bin/neuro-mesh --version
# Should show: claude-mesh 0.3.2
```

⚠️ **Do NOT overwrite** `/Users/michaelfolk/bin/neuro` (existing notes/calendar/imessage script).

### Step 3: Verify Grok Bot App is Open

On **Mac mini**, ensure Grok Bot desktop app is running (required for registered-computer tools).

Grant OS Allow if prompted (one-time macOS permission).

---

## Usage (Recommended Method)

### Neuro Publishing an Event

From **Grok Bot box**, use registered-computer Shell on Mac:

```python
from grok_bot_tools import Shell  # Hypothetical registered-computer API

# Publish a message
Shell(command='neuro-mesh send --message "Task claimed: backend auth refactor" --to claude-mac')

# Publish a decision
Shell(command='neuro-mesh send --decision "Switching to Ed25519 keys"')

# Claim a task
Shell(command='neuro-mesh task claim --id BACKEND-42 --lease-seconds 1800')
```

The wrapper runs claude-mesh on Mac, which handles append-only FTAI writes atomically.

### Neuro Draining Unread Events

From **Grok Bot box**, use registered-computer Shell on Mac:

```python
result = Shell(command='neuro-mesh drain --format=ftai')

# Parse result.output (FTAI format):
# <mesh_context>
# @message
# from: claude-mac
# timestamp: 2026-09-01T14:23:11Z
# body: Task completed
# </mesh_context>

# Or if your Shell tool returns structured output:
for line in result.output.splitlines():
    if line.startswith('@message'):
        # Parse FTAI event...
```

**Read-marker**: Automatically maintained by claude-mesh on Mac (at `~/.claude-mesh/groups/mac-neuro-mesh/neuro-grokbot.ftai.neuro-grokbot.read`).

---

## Validation

### Test Mac Setup

On **Mac mini**:

```bash
cd /Users/michaelfolk/Developer/your-project
/opt/homebrew/bin/claude-mesh status
```

Expected output:
```
Mesh peer: claude-mac
Mesh group: mac-neuro-mesh
Participants: claude-mac, neuro-grokbot
Unread events: 0
```

### Test Wrapper

From **Grok Bot box**, test Shell invocation:

```python
Shell(command='neuro-mesh --version')
# Should output: claude-mesh 0.3.2
```

### Test End-to-End

1. **Neuro publishes**:
   ```python
   Shell(command='neuro-mesh send --message "Test from Neuro" --to claude-mac')
   ```

2. **Claude drains** (on Mac):
   ```bash
   cd /Users/michaelfolk/Developer/your-project
   /opt/homebrew/bin/claude-mesh drain
   # Should show: @message from neuro-grokbot: Test from Neuro
   ```

---

## Troubleshooting

### "Grok Bot app not open on Mac"

- **Cause**: Registered-computer tools require Grok Bot app running
- **Fix**: Open Grok Bot desktop app on Mac mini

### "Permission denied" when running neuro-mesh

- **Cause**: macOS permission prompt or script not executable
- **Fix**: 
  1. Grant Grok Bot app permission (one-time Allow)
  2. `chmod +x /Users/michaelfolk/bin/neuro-mesh`

### "Mesh group not found"

- **Cause**: `.claude-mesh` config not in project directory
- **Fix**: Create config (Step 1 above)

### Neuro joins wrong group

- **Cause**: Using existing group (serena-myelin, etc.)
- **Fix**: Create dedicated `mac-neuro-mesh` group, leave existing groups alone

---

## Installation Notes

### If This Branch Must Be Installed

⚠️ **Do NOT** use pip (claude-mesh is not on PyPI).

**Current stable**: v0.3.2 at `/opt/homebrew/bin/claude-mesh` works for Neuro. No upgrade needed.

**If Mike approves merging this branch** and you need features from it:

```bash
cd /Users/michaelfolk/Developer/claude-mesh
git checkout main
git pull origin main
pip3 install -e .
```

Do NOT git pull onto the local checkout unless Mike asks.

---

## Security Notes

### Hub Model

- **Trust**: Mac mini hub (same user, filesystem ACLs)
- **Transport**: Grok Bot registered-computer Shell (not network)
- **Content**: Still untrusted (all sanitizers apply)
- **Access**: macOS permission prompt (one-time Allow)

### Append-Only Safety

- **Why it matters**: claude-mesh uses append-only writes; never replace inbox files
- **Protection**: neuro-mesh wrapper uses claude-mesh's atomic append operations
- **Group isolation**: Dedicated mac-neuro-mesh group prevents cross-contamination

---

## Example Workflow

**Scenario**: Neuro claims a task, Claude implements it on Mac.

1. **Neuro** (Grok Bot box) claims task:
   ```python
   Shell(command='neuro-mesh task claim --id BACKEND-42 --lease-seconds 1800')
   Shell(command='neuro-mesh send --message "Claimed BACKEND-42" --to claude-mac')
   ```

2. **Claude** (Mac mini) sees task:
   ```bash
   # Auto-drained via UserPromptSubmit hook
   # Claude sees: @task_claim and @message from neuro-grokbot
   ```

3. **Claude** completes task:
   ```bash
   # Auto-published via PostToolUse hook
   # Writes to: /Users/michaelfolk/.claude-mesh/groups/mac-neuro-mesh/neuro-grokbot.ftai
   ```

4. **Neuro** (Grok Bot box) drains update:
   ```python
   result = Shell(command='neuro-mesh drain')
   # Neuro sees: @file_change from claude-mac
   ```

---

## References

- Spec: [SPEC-003: Cross-Machine Mesh](../specs/SPEC-003-remote-peer-sync.md)
- SSH (optional LAN): [ssh-transport-optional.md](ssh-transport-optional.md)
- Security: [security-posture.md](../security-posture.md)

For issues, open an issue at [github.com/FolkTechAI/claude-mesh](https://github.com/FolkTechAI/claude-mesh).
