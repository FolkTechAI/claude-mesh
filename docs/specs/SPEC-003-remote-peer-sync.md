# SPEC-003: Remote Peer Sync for Cross-Machine Mesh

| Field | Value |
|---|---|
| **Status** | Draft |
| **Author** | Cloud Agent (for Mike Folk / FolkTech AI) |
| **Created** | 2026-09-01 |
| **Target release** | v0.4.0 |
| **Supersedes** | SPEC-001 Section 2 "Out of scope: Cross-machine topology" |

---

## 1. Problem Statement

Neuro (Mike's Grok Bot Chief of Staff) runs on a separate Linux Grok Bot machine, while other agents (Claude Code, Hermes, Codex, Grok Build) run on Mike's Mac mini. The existing FTAI mesh is same-machine only. Neuro cannot currently coordinate work with Mac-based agents without ad-hoc chat pings.

**Goal**: Enable Neuro to publish and consume mesh events as a first-class peer, coordinating with agents on Mike's Mac without a cloud message bus.

---

## 2. Scope

### In Scope

- **Cross-machine peer registration**: Declare a peer as "remote" in `.claude-mesh` config
- **Bidirectional inbox sync**: Push local writes to remote peer inboxes; pull remote writes to local inbox
- **SSH/rsync transport**: Use SSH over local network (user-owned machines only)
- **Manual and periodic sync**: `claude-mesh sync` command plus optional watch mode
- **Neuro-specific adapter docs**: How Neuro publishes/drains via the bridge
- **Security update**: Extend threat model to cover cross-machine trust

### Out of Scope

- Real-time sync daemon (v1 is pull-based; Neuro polls periodically)
- Cloud relay services (must be local-only)
- Multi-hop routing (direct Mac ↔ Grok Bot only)
- Windows support (Mac and Linux only)
- Automatic conflict resolution (last-write-wins via rsync)

---

## 3. Architecture

### 3.1 Config Extension

Add optional `remote_peers` map to `.claude-mesh`:

```yaml
mesh_group: neuro-claude-mesh
mesh_peer: claude-mac
mesh_peers:
  - claude-mac
  - neuro-grokbot
  - hermes-mac
remote_peers:
  neuro-grokbot:
    host: grokbot.local  # or IP address
    user: mike
    inbox_path: /home/mike/.claude-mesh/groups/neuro-claude-mesh
```

**Remote peer contract**:
- `host`: SSH hostname or IP (must be reachable on local network)
- `user`: SSH username (passwordless key auth required)
- `inbox_path`: Absolute path to the mesh group directory on remote machine

### 3.2 Sync Mechanism

**Bidirectional rsync**:

1. **Push** (after local publish):
   - When this peer writes to a remote peer's inbox, sync that inbox file to the remote machine
   - Command: `rsync -az ~/.claude-mesh/groups/{group}/{remote-peer}.ftai {user}@{host}:{inbox_path}/{remote-peer}.ftai`

2. **Pull** (before local drain):
   - Fetch this peer's own inbox from all remote peers who might have written to it
   - Command: `rsync -az {user}@{host}:{inbox_path}/{local-peer}.ftai ~/.claude-mesh/groups/{group}/{local-peer}.ftai`

3. **Read-marker sync**:
   - Each peer's read-marker stays local (never synced)
   - Remote writes append to the local inbox copy; local drain advances local read-marker

### 3.3 CLI Commands

**New subcommands**:

```bash
# One-time setup: test SSH connectivity to all remote peers
claude-mesh remote-doctor

# Manual sync: push local writes, pull remote writes
claude-mesh sync [--peer NAME]

# Watch mode: sync every N seconds (for Neuro's periodic polling)
claude-mesh sync --watch --interval 30
```

**Hook integration** (optional, off by default):
- New env var: `CLAUDE_MESH_AUTO_SYNC=1` enables post-publish sync
- `PostToolUse` hook appends to remote inbox → calls `claude-mesh sync --peer {remote}` if enabled

### 3.4 Neuro Adapter

Neuro uses the standard CLI from its Linux box:

```bash
# Neuro publishes an event
claude-mesh send --message "Task claim: backend auth refactor" --to claude-mac

# Neuro syncs to deliver the message
claude-mesh sync --peer claude-mac

# Neuro drains unread events from other peers
claude-mesh sync  # pull first
claude-mesh drain
```

**Neuro bridge integration** (optional):
- If `~/bin/neuro` already handles file sync, wrap `claude-mesh sync` inside it
- Otherwise, Neuro calls `claude-mesh sync` directly via SSH or cron job

---

## 4. Security

### 4.1 Updated Threat Model

> The trust boundary extends to: processes running under the same user on **user-owned machines connected via passwordless SSH**. We trust that Mike owns both the Mac mini and Grok Bot, and that SSH keys are properly secured. We still do NOT trust that mesh content is non-adversarial.

**New risks**:
- **SSH key compromise**: If `~/.ssh/id_rsa` is stolen, attacker could inject mesh events
  - *Mitigation*: Standard SSH key security (passphrase, key rotation, file permissions)
- **MitM on local network**: Attacker on LAN could intercept rsync traffic
  - *Mitigation*: SSH encrypts transport; additionally, local network is user-controlled
- **Remote machine compromise**: If Grok Bot is compromised, it could write malicious FTAI
  - *Mitigation*: Same as current same-machine threat model (content is untrusted)

**No new input sanitization needed**: All existing sanitizers (CAT 1-5) apply to remote-sourced events identically.

### 4.2 Setup Requirements

Mike must:
1. Generate SSH keypair on Mac (if not present): `ssh-keygen -t ed25519`
2. Copy pubkey to Grok Bot: `ssh-copy-id mike@grokbot.local`
3. Test passwordless SSH: `ssh mike@grokbot.local 'echo ok'`
4. Install `claude-mesh` on both machines (same version)
5. Configure `.claude-mesh` with `remote_peers` on both sides

**Firewall**: SSH port 22 must be open between Mac and Grok Bot (default on local network).

---

## 5. Implementation Plan

### 5.1 Files to Create

| File | Purpose |
|---|---|
| `src/claude_mesh/commands/sync.py` | Sync command implementation |
| `src/claude_mesh/commands/remote_doctor.py` | Remote peer connectivity check |
| `src/claude_mesh/remote.py` | SSH/rsync transport logic |
| `tests/unit/test_sync.py` | Unit tests for sync logic |
| `tests/integration/test_remote_peer.py` | Integration test with mock SSH |
| `docs/remote-peer-setup.md` | Setup guide for Neuro |

### 5.2 Files to Modify

| File | Change |
|---|---|
| `src/claude_mesh/config.py` | Add `remote_peers` field to `MeshConfig` |
| `src/claude_mesh/cli.py` | Register `sync` and `remote-doctor` commands |
| `src/claude_mesh/publish.py` | Optional: call sync after fanout if auto-sync enabled |
| `docs/security-posture.md` | Update threat model for cross-machine topology |
| `README.md` | Link to remote peer setup guide |

### 5.3 Test Strategy

**Unit tests**:
- Config parsing with `remote_peers`
- Rsync command construction
- Error handling (SSH unreachable, rsync failure)

**Integration tests**:
- Mock SSH/rsync with `subprocess` patches
- Verify push/pull order
- Verify read-marker stays local

**Manual E2E** (Mike's setup):
1. Configure Mac as `claude-mac` with `neuro-grokbot` as remote peer
2. Configure Grok Bot as `neuro-grokbot` with `claude-mac` as remote peer
3. Claude on Mac publishes `@file_change`
4. Run `claude-mesh sync` on Mac → inbox appears on Grok Bot
5. Neuro on Grok Bot drains → sees the file change
6. Neuro publishes `@message` reply
7. Run `claude-mesh sync` on Grok Bot → Mac receives message
8. Claude drains → sees Neuro's reply

---

## 6. Alternatives Considered

### Alt 1: Mount remote filesystem via SSHFS
- **Pro**: Transparent file access, no explicit sync
- **Con**: Introduces latency and failure modes (network blip = hung reads)
- **Verdict**: Rejected — rsync is more robust for intermittent connectivity

### Alt 2: Shared NFS/SMB mount between Mac and Grok Bot
- **Pro**: Single source of truth, no sync lag
- **Con**: Requires additional daemon setup; Mike doesn't have this infrastructure
- **Verdict**: Rejected — SSH is already present, rsync is simpler

### Alt 3: Mesh relay daemon (long-running process)
- **Pro**: Real-time sync, no manual polling
- **Con**: Adds complexity, daemon management, and out-of-scope for v1
- **Verdict**: Deferred to v2 — Neuro's periodic polling is acceptable for initial deployment

---

## 7. Success Criteria

- [ ] `claude-mesh remote-doctor` validates SSH connectivity to all remote peers
- [ ] `claude-mesh sync` pushes and pulls inbox files correctly
- [ ] Neuro can publish an event on Grok Bot and Claude sees it on Mac after sync
- [ ] Claude can publish an event on Mac and Neuro sees it on Grok Bot after sync
- [ ] Unit tests pass for config parsing and rsync command construction
- [ ] Integration tests pass with mocked SSH
- [ ] `docs/remote-peer-setup.md` documents complete Neuro setup (SSH keys, config, sync)
- [ ] Security posture updated with cross-machine trust model
- [ ] CI green on both Mac and Linux runners

---

## 8. Open Questions

1. **Sync frequency**: How often should Neuro poll? Default to 30s? User-configurable?
2. **Conflict resolution**: If Mac and Grok Bot both append to the same inbox simultaneously, rsync will pick last-write-wins. Acceptable?
3. **Supervisor integration**: Should the adversarial supervisor support remote workers? (Out of scope for v1, revisit if Mike requests it)

---

## 9. References

- SPEC-001: Claude Mesh v1 (same-machine model)
- SPEC-002: N-way Mesh (generalizes beyond pairs)
- `rsync` man page: https://linux.die.net/man/1/rsync
- SSH key setup: https://www.ssh.com/academy/ssh/keygen

---

**END OF SPEC-003.**
