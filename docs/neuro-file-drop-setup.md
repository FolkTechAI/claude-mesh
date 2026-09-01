# Neuro Setup: File-Drop Transport to Mac Hub

This guide explains how to configure **Neuro** (running on Cursor's Grok Bot Linux box) to coordinate with Claude Code, Hermes, Codex, and other agents on Mike's Mac mini via file-drop transport.

**No SSH required.** Neuro uses Grok Bot's registered-computer tools to copy files to/from the Mac hub.

---

## Topology

- **Mac mini** (`Michaels-Mac-mini.local`) is the mesh hub
  - User: `michaelfolk`
  - Home: `/Users/michaelfolk`
  - Mesh directory: `/Users/michaelfolk/.claude-mesh/groups/{group}/`
  - Agents: Claude Code, Hermes, Codex, Grok Build (all same-machine peers)

- **Grok Bot Linux box** (Cursor-managed) runs Neuro
  - User: `box`
  - Home: `/home/box`
  - Hostname: `cursor`
  - **NOT on Mike's LAN** — uses registered-computer tools when Grok Bot app is open on Mac

- **Existing Mac reach**:
  - `/Users/michaelfolk/bin/neuro` — notes, calendar, iMessage commands
  - Grok Bot registered-computer tools: Shell, Read, Write files on Mac

---

## How It Works

**Hub model**: Mac mini is the source of truth. Neuro's FTAI inbox lives on the Mac at:
```
/Users/michaelfolk/.claude-mesh/groups/mac-neuro-mesh/neuro-grokbot.ftai
```

**File-drop transport**:
1. **Neuro publishes**: Writes event to staging dir on Grok Bot box → copies to Mac hub
2. **Neuro drains**: Copies inbox from Mac hub → reads from staging dir on Grok Bot box

**No daemon needed** on Mac — existing PostToolUse hooks handle same-machine peers.

---

## One-Time Setup

### Step 1: Install claude-mesh on Mac

On **Mac mini** (as user `michaelfolk`):

```bash
pip3 install claude-mesh
# Or if using plugin:
/plugin install claude-mesh@folktechai
```

**Verify**:
```bash
claude-mesh --version
```

### Step 2: Configure Mesh on Mac

In your project directory on **Mac mini**, create or update `.claude-mesh`:

```yaml
mesh_group: mac-neuro-mesh
mesh_peer: claude-mac
mesh_peers:
  - claude-mac
  - hermes-mac
  - neuro-grokbot
cross_cutting_paths:
  - src/**
  - api/**
```

**Key points**:
- `neuro-grokbot` is listed as a peer
- No `remote_peers` section needed (Neuro is not SSH; it's file-drop)

**Hub directory will be created at**:
```
/Users/michaelfolk/.claude-mesh/groups/mac-neuro-mesh/
```

### Step 3: Install Mac-Side Wrapper (Optional)

On **Mac mini**, install the wrapper script:

```bash
# Copy the wrapper
cp scripts/neuro-mesh-wrapper.sh /Users/michaelfolk/bin/neuro-mesh
chmod +x /Users/michaelfolk/bin/neuro-mesh

# Or integrate into existing ~/bin/neuro if preferred
```

This allows Neuro to run commands like:
```bash
# From Grok Bot box, via registered-computer Shell on Mac:
Shell(command='neuro-mesh send --message "Task claimed" --to claude-mac')
```

### Step 4: Create Staging Directories on Grok Bot Box

On **Grok Bot box** (user `box`), create staging directories:

```bash
mkdir -p /home/box/.claude-mesh-staging/outgoing
mkdir -p /home/box/.claude-mesh-staging/incoming
chmod 700 /home/box/.claude-mesh-staging
```

---

## Usage

### Neuro Publishing an Event

From **Grok Bot box**, Neuro publishes via staging + copy:

**Option A: Use Python file_drop module**

```python
from pathlib import Path
from claude_mesh.file_drop import publish_to_staging, get_copy_instructions
from claude_mesh.events import MessageEvent
from claude_mesh.identity import utc_now, new_event_id

# Create event
event = MessageEvent(
    from_="neuro-grokbot",
    timestamp=utc_now(),
    body="Task claimed: backend auth refactor",
    to="claude-mac",
    event_id=new_event_id(),
)

# Write to staging
staging_root = Path("/home/box/.claude-mesh-staging")
staging_file = publish_to_staging(
    event,
    target_peer="claude-mac",
    staging_root=staging_root,
    group_name="mac-neuro-mesh",
    participants=["claude-mac", "hermes-mac", "neuro-grokbot"],
)

# Get copy instructions
instructions = get_copy_instructions(
    "publish",
    peer_name="claude-mac",
    group_name="mac-neuro-mesh",
    staging_root=staging_root,
)

# Copy to Mac using registered-computer Write tool
# Source: instructions["source"] = /home/box/.claude-mesh-staging/outgoing/claude-mac.ftai
# Dest:   instructions["dest"] = /Users/michaelfolk/.claude-mesh/groups/mac-neuro-mesh/claude-mac.ftai
Write(path=instructions["dest"], contents=staging_file.read_text())
```

**Option B: Use Mac-side wrapper via Shell**

```python
# From Grok Bot box, invoke Mac-side claude-mesh via registered-computer Shell:
Shell(command='neuro-mesh send --message "Task claimed: backend auth refactor" --to claude-mac')
```

The wrapper runs `claude-mesh` on Mac as the `neuro-grokbot` peer.

### Neuro Draining Unread Events

From **Grok Bot box**, Neuro drains via copy + read:

**Option A: Use Python file_drop module**

```python
from pathlib import Path
from claude_mesh.file_drop import prepare_inbox_fetch, read_inbox_from_staging, get_copy_instructions

staging_root = Path("/home/box/.claude-mesh-staging")

# Get copy instructions
instructions = get_copy_instructions(
    "fetch",
    peer_name="neuro-grokbot",
    group_name="mac-neuro-mesh",
    staging_root=staging_root,
)

# Copy inbox from Mac using registered-computer Read tool
# Source: instructions["source"] = /Users/michaelfolk/.claude-mesh/groups/mac-neuro-mesh/neuro-grokbot.ftai
# Dest:   instructions["dest"] = /home/box/.claude-mesh-staging/incoming/neuro-grokbot.ftai
inbox_content = Read(path=instructions["source"])
Path(instructions["dest"]).write_text(inbox_content)

# Read unread events
events = read_inbox_from_staging(
    peer_name="neuro-grokbot",
    staging_root=staging_root,
    last_read_marker=None,  # Or timestamp from previous drain
)

for event in events:
    print(f"@{event['tag']} from {event.get('from')}: {event.get('body', event.get('summary'))}")
```

**Option B: Use Mac-side wrapper via Shell**

```python
# From Grok Bot box, invoke Mac-side claude-mesh via registered-computer Shell:
result = Shell(command='neuro-mesh drain --format=ftai')
# Parse result.output to get FTAI events
```

---

## Copy Contract for Grok Bot Implementation

**For Grok Bot registered-computer tools** (no SSH, no claude-mesh on Grok Bot box):

### Publish Operation (Neuro → Mac)

| Step | Action |
|---|---|
| 1 | Neuro writes event to `/home/box/.claude-mesh-staging/outgoing/{peer}.ftai` on Grok Bot box |
| 2 | Copy using **Write** tool: |
|   | Source: `/home/box/.claude-mesh-staging/outgoing/{peer}.ftai` |
|   | Dest: `/Users/michaelfolk/.claude-mesh/groups/{group}/{peer}.ftai` |
| 3 | Mac PostToolUse hooks handle fanout to other Mac peers automatically |

### Fetch Operation (Mac → Neuro)

| Step | Action |
|---|---|
| 1 | Copy using **Read** tool: |
|   | Source: `/Users/michaelfolk/.claude-mesh/groups/{group}/neuro-grokbot.ftai` |
|   | Dest: `/home/box/.claude-mesh-staging/incoming/neuro-grokbot.ftai` |
| 2 | Neuro reads from staging on Grok Bot box |
| 3 | Neuro updates local read-marker (timestamp) to avoid re-reading |

**File operations**:
- **Write**: Append-only or replace (Mac file may exist)
- **Read**: Copy entire file (read-only from Mac perspective)

---

## Validation

### Test Mac Setup

On **Mac mini**:

```bash
cd /path/to/your/project
claude-mesh status
```

Expected output:
```
Mesh peer: claude-mac
Mesh group: mac-neuro-mesh
Participants: claude-mac, hermes-mac, neuro-grokbot
Unread events: 0
```

### Test Staging Setup

On **Grok Bot box**:

```bash
ls -ld /home/box/.claude-mesh-staging
# Should show: drwx------ ... /home/box/.claude-mesh-staging
```

### Test File Copy (Mac)

From **Grok Bot box**, test registered-computer Write:

```python
from grok_bot_tools import Write  # Hypothetical registered-computer API

# Test write to Mac
test_content = "@message\nfrom: neuro-grokbot\ntimestamp: 2026-09-01T16:00:00Z\nbody: Test message\n"
Write(
    path="/Users/michaelfolk/.claude-mesh/groups/mac-neuro-mesh/test.ftai",
    contents=test_content,
)
```

On **Mac mini**, verify:
```bash
cat /Users/michaelfolk/.claude-mesh/groups/mac-neuro-mesh/test.ftai
# Should show: @message from neuro-grokbot...
```

---

## Troubleshooting

### "Grok Bot app not open on Mac"

- **Cause**: Registered-computer tools require Grok Bot app running on Mac
- **Fix**: Open Grok Bot desktop app on Mac mini

### "Permission denied" when copying to Mac

- **Cause**: macOS may prompt for Allow
- **Fix**: Grant Grok Bot app permission to access files (one-time OS Allow tap)

### "Hub directory doesn't exist"

- **Cause**: `.claude-mesh` config not initialized on Mac
- **Fix**: Run `claude-mesh init` or create config manually (Step 2 above)

### Neuro sees old events repeatedly

- **Cause**: Read-marker not persisted between drains
- **Fix**: Store `last_read_marker` (highest timestamp seen) and pass to `read_inbox_from_staging()`

---

## Security Notes

### Trust Model

- **Same as same-machine mesh**: Mac mini is trusted, content is untrusted
- **Transport**: Grok Bot registered-computer tools (not network, not SSH)
- **Access control**: macOS prompts user for Allow (one-time)
- **Content sanitization**: All existing sanitizers apply (CAT 1-5)

### What We Don't Defend Against

- Compromised Grok Bot box (same as compromised Mac — content is untrusted)
- Malicious Grok Bot app (registered-computer tools are trusted)
- OS-level compromise on Mac (filesystem security fails at that point)

---

## Example Workflow

**Scenario**: Neuro claims a task, Claude implements it on Mac.

1. **Neuro** (Grok Bot box) claims task:
   ```python
   # Publish via staging + copy
   publish_to_staging(event, "claude-mac", ...)
   Write(dest="/Users/michaelfolk/.claude-mesh/groups/.../claude-mac.ftai", ...)
   ```

2. **Claude** (Mac mini) sees task in next prompt:
   ```bash
   # Auto-drained via UserPromptSubmit hook
   # Claude sees: @task_claim from neuro-grokbot
   ```

3. **Claude** completes task, publishes file change:
   ```bash
   # Auto-published via PostToolUse hook
   # Writes to: /Users/michaelfolk/.claude-mesh/groups/.../neuro-grokbot.ftai
   ```

4. **Neuro** (Grok Bot box) drains update:
   ```python
   # Copy from Mac + read staging
   inbox = Read(path="/Users/michaelfolk/.claude-mesh/groups/.../neuro-grokbot.ftai")
   events = read_inbox_from_staging("neuro-grokbot", ...)
   # Neuro sees: @file_change from claude-mac
   ```

---

## Next Steps

- **Test end-to-end**: Neuro publish → Claude drain → Claude publish → Neuro drain
- **Automate**: Add copy operations to Neuro's task loop
- **Monitor**: Check staging dirs and Mac hub for stale files

---

## References

- [SPEC-003: Cross-Machine Mesh via Hub + File-Drop](../specs/SPEC-003-remote-peer-sync.md)
- [Security Posture](../security-posture.md)
- [Operations Guide](../operations.md)

For issues or questions, open an issue at [github.com/FolkTechAI/claude-mesh](https://github.com/FolkTechAI/claude-mesh).
