# SPEC-003: Cross-Machine Mesh via Hub + File-Drop Transport

| Field | Value |
|---|---|
| **Status** | Draft — SSH optional LAN, Neuro uses file-drop |
| **Author** | Cloud Agent (for Mike Folk / FolkTech AI) |
| **Created** | 2026-09-01 |
| **Target release** | v0.4.0 |
| **Supersedes** | SPEC-001 Section 2 "Out of scope: Cross-machine topology" |

---

## 1. Problem Statement

Neuro (Mike's Grok Bot Chief of Staff) runs on a Cursor-managed Linux Grok Bot box, while other agents (Claude Code, Hermes, Codex, Grok Build) run on Mike's Mac mini. The existing FTAI mesh is same-machine only. Neuro cannot currently coordinate work with Mac-based agents.

**Topology**:
- **Mac mini** (user `michaelfolk`, home `/Users/michaelfolk`, hostname `Michaels-Mac-mini.local`) is the mesh hub
- **Grok Bot Linux box** (user `box`, home `/home/box`, hostname `cursor`) runs Neuro but is NOT on Mike's LAN
- **Existing Mac reach**: Grok Bot registered-computer tools (Shell/Read/Write files on Mac) when Grok Bot app is open on Mac
- **Existing Neuro bridge**: `/Users/michaelfolk/bin/neuro` on Mac for notes/calendar/iMessage

**Goal**: Enable Neuro to publish and consume mesh events via the Mac hub without SSH.

---

## 2. Scope

### In Scope

- **Hub model**: Mac is source of truth; Neuro's FTAI files live on Mac
- **File-drop transport**: Neuro writes to local staging dir, copies to/from Mac via registered-computer tools
- **Mac-side CLI wrapper**: Optional `neuro mesh send` / `drain` that runs `claude-mesh` on Mac as neuro-grokbot peer
- **Copy contract documentation**: Exact file paths and operations for Grok Bot registered-computer tools
- **SSH as optional LAN transport**: Keep for two SSH-enabled user-owned machines, NOT for Neuro

### Out of Scope

- SSH setup for Neuro (wrong transport)
- Neuro running claude-mesh directly on Grok Bot box (Mac is hub)
- Real-time daemon on Mac (PostToolUse hooks already handle same-machine)
- Installing claude-mesh on Grok Bot box (not needed)

---

## 3. Architecture

### 3.1 Hub Model

**Source of truth**: `/Users/michaelfolk/.claude-mesh/groups/{group}/` on Mac mini.

**Peers**:
- `claude-mac` (Claude Code on Mac) — same-machine
- `hermes-mac` (Hermes on Mac) — same-machine
- `neuro-grokbot` (Neuro on Grok Bot box) — **file-drop peer**

**Neuro's inbox**: `/Users/michaelfolk/.claude-mesh/groups/{group}/neuro-grokbot.ftai` (lives on Mac)

### 3.2 File-Drop Transport

Neuro operates via **staging directory** + **copy operations**:

1. **Neuro publishes**:
   - Neuro writes event to `/home/box/.claude-mesh-staging/outgoing/{peer}.ftai` on Grok Bot box
   - Copies file to Mac: `/Users/michaelfolk/.claude-mesh/groups/{group}/{peer}.ftai`
   - Uses Grok Bot registered-computer Write/Shell tools

2. **Neuro drains**:
   - Copies Neuro's inbox from Mac: `/Users/michaelfolk/.claude-mesh/groups/{group}/neuro-grokbot.ftai`
   - Reads from `/home/box/.claude-mesh-staging/incoming/neuro-grokbot.ftai` on Grok Bot box
   - Uses Grok Bot registered-computer Read tools

3. **Mac-based agents**: Continue using existing same-machine hooks (no change)

### 3.3 Copy Contract

**For Grok Bot registered-computer tools implementation** (no SSH, no claude-mesh on box):

| Operation | Source (Grok Bot box) | Destination (Mac) |
|---|---|---|
| Publish to peer | `/home/box/.claude-mesh-staging/outgoing/{peer}.ftai` | `/Users/michaelfolk/.claude-mesh/groups/{group}/{peer}.ftai` |
| Fetch own inbox | `/Users/michaelfolk/.claude-mesh/groups/{group}/neuro-grokbot.ftai` | `/home/box/.claude-mesh-staging/incoming/neuro-grokbot.ftai` |

**File operations**:
- **Publish**: Append-only write (existing Mac file may exist, append or replace)
- **Fetch**: Copy entire file (read-only from Mac perspective)

**No daemons needed**: Neuro calls copy operations explicitly when publishing/draining.

### 3.4 Mac-Side CLI Wrapper (Optional)

Add to `/Users/michaelfolk/bin/neuro` (or separate script):

```bash
#!/bin/bash
# neuro mesh send "message text"
# Runs claude-mesh on Mac as neuro-grokbot peer

case "$1" in
  mesh)
    shift
    CLAUDE_MESH_PEER=neuro-grokbot claude-mesh "$@"
    ;;
  *)
    # Existing neuro commands (notes, calendar, etc.)
    ;;
esac
```

**Usage from Grok Bot box**:
```bash
# Neuro invokes via registered-computer Shell on Mac:
Shell(command='neuro mesh send --message "Task claimed" --to claude-mac')
Shell(command='neuro mesh drain --format=ftai > /tmp/neuro-inbox.ftai')
```

Then copy results back to Grok Bot box if needed.

### 3.5 SSH Transport (Optional LAN)

**Kept for general use** between two SSH-enabled user-owned machines on same LAN.

**NOT used by Neuro**. SSH code remains in `remote.py` with `remote_peers` config, but Neuro docs do NOT mention it.

---

## 4. Configuration

### On Mac Mini

`.claude-mesh` in project directory:

```yaml
mesh_group: mac-neuro-mesh
mesh_peer: claude-mac
mesh_peers:
  - claude-mac
  - hermes-mac
  - neuro-grokbot
cross_cutting_paths:
  - src/**
# No remote_peers for file-drop peers (Neuro is local to Mac filesystem)
```

**Hub directory**: `/Users/michaelfolk/.claude-mesh/groups/mac-neuro-mesh/`

**Files**:
- `claude-mac.ftai` — Claude's inbox (written by other peers)
- `hermes-mac.ftai` — Hermes's inbox
- `neuro-grokbot.ftai` — Neuro's inbox (written by Mac peers, read by Neuro via copy)

### On Grok Bot Box

**No `.claude-mesh` config needed** (Neuro is not running claude-mesh locally).

**Staging directories**:
- `/home/box/.claude-mesh-staging/outgoing/` — Neuro writes events here before copying to Mac
- `/home/box/.claude-mesh-staging/incoming/` — Neuro copies inbox from Mac here before reading

---

## 5. Implementation

### 5.1 File-Drop Helper (New)

Create `src/claude_mesh/file_drop.py`:

```python
"""File-drop transport for peers without direct filesystem access to hub.

Used by Neuro on Grok Bot box to publish/drain via staging + copy to Mac hub.
"""

def publish_via_staging(event_ftai: str, target_peer: str, staging_dir: Path):
    """Write event to staging/outgoing/{peer}.ftai for later copy to Mac hub."""
    
def fetch_inbox_to_staging(peer_name: str, staging_dir: Path):
    """Prepare to copy peer's inbox from Mac hub to staging/incoming/."""
```

### 5.2 Mac-Side CLI Wrapper

Add `scripts/neuro-mesh-wrapper.sh`:

```bash
#!/bin/bash
# Wrapper for neuro to run claude-mesh commands on Mac as neuro-grokbot peer
export CLAUDE_MESH_PEER=neuro-grokbot
exec claude-mesh "$@"
```

Install to `/Users/michaelfolk/bin/neuro-mesh` or integrate into existing `~/bin/neuro`.

### 5.3 Documentation

**Update**:
- `docs/specs/SPEC-003-*` → Rename to emphasize hub model, not SSH
- `docs/remote-peer-setup.md` → Split into:
  - `docs/file-drop-setup.md` — Neuro setup (default, no SSH)
  - `docs/ssh-transport.md` — Optional SSH for LAN machines

**Remove**:
- All Neuro + SSH instructions (ssh-keygen, ssh-copy-id, grokbot.local)
- `/home/mike` paths (wrong user)
- pip install on Grok Bot box (not needed)

**Add**:
- Real paths: `/Users/michaelfolk`, `user box`, `/home/box`, `hostname cursor`
- Grok Bot app open on Mac (one Allow tap if prompted)
- Copy contract for registered-computer tools
- Mac hub as source of truth

---

## 6. Success Criteria

- [ ] Neuro can publish event via staging + copy to Mac hub
- [ ] Neuro can drain inbox via copy from Mac hub + read staging
- [ ] Mac-based agents see Neuro's events (same as current same-machine)
- [ ] No SSH setup required for Neuro
- [ ] Setup: Grok Bot app open on Mac + one OS Allow tap
- [ ] Tests for file-drop transport
- [ ] SSH tests clearly labeled as optional LAN transport
- [ ] Docs reflect real topology (no grokbot.local, no mike user on box)
- [ ] PR marked draft, "do not merge until Mike approves"

---

## 7. Open Questions

1. **Staging dir location**: `/home/box/.claude-mesh-staging/` or `/tmp/neuro-mesh-staging/`?
2. **Copy timing**: Should Neuro copy after every publish, or batch N events?
3. **Read-marker**: Store on Mac (source of truth) or Grok Bot box (local state)?

---

**END OF SPEC-003 (Updated for Hub Model).**
