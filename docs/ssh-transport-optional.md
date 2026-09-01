# SSH Transport for LAN Mesh (Optional)

This guide explains how to use **SSH/rsync transport** for mesh coordination between two user-owned machines on the same LAN.

**This is NOT the default for Neuro.** Neuro uses file-drop transport (see `neuro-file-drop-setup.md`).

Use SSH transport when:
- You have two machines with SSH daemons running
- Both machines are on the same local network
- You want real-time sync without manual copy operations

---

## Prerequisites

- Two machines on same LAN (e.g., two Macs, Mac + Linux server)
- SSH server running on both machines
- Same user on both machines (or different users with SSH access)
- `rsync` installed (comes with macOS and most Linux distros)

---

## Setup

### Step 1: Generate SSH Keypair

On **Machine A**:

```bash
ssh-keygen -t ed25519 -C "mesh-transport"
# Press Enter to accept defaults
```

### Step 2: Copy Public Key to Machine B

From **Machine A**:

```bash
ssh-copy-id user@machine-b.local
```

Test passwordless SSH:

```bash
ssh user@machine-b.local 'echo "SSH OK"'
```

Repeat Steps 1-2 in reverse (Machine B → Machine A) for bidirectional sync.

### Step 3: Configure `.claude-mesh` with `remote_peers`

On **Machine A**:

```yaml
mesh_group: my-lan-mesh
mesh_peer: machine-a
mesh_peers:
  - machine-a
  - machine-b
remote_peers:
  machine-b:
    host: machine-b.local  # or IP: 192.168.1.100
    user: username
    inbox_path: /home/username/.claude-mesh/groups/my-lan-mesh
```

On **Machine B**:

```yaml
mesh_group: my-lan-mesh
mesh_peer: machine-b
mesh_peers:
  - machine-a
  - machine-b
remote_peers:
  machine-a:
    host: machine-a.local
    user: username
    inbox_path: /home/username/.claude-mesh/groups/my-lan-mesh
```

### Step 4: Install claude-mesh on Both Machines

⚠️ **claude-mesh is NOT on PyPI.**

**If you have an existing installation** (e.g., via Homebrew or local checkout):
```bash
which claude-mesh
claude-mesh --version
```

**If installing from source** (requires local checkout):
```bash
cd /path/to/claude-mesh
pip3 install -e .
```

### Step 5: Validate Connectivity

On **Machine A**:

```bash
claude-mesh remote-doctor
```

Expected output:

```
Testing connectivity to 1 remote peer(s)...
  machine-b (username@machine-b.local): ✓ OK
All remote peers are reachable
```

---

## Usage

### Manual Sync

After publishing an event:

```bash
claude-mesh sync --peer machine-b
```

Before draining:

```bash
claude-mesh sync
claude-mesh drain
```

### Watch Mode

For continuous sync (runs in background):

```bash
# In tmux or screen
claude-mesh sync --watch --interval 30
```

Or via systemd/launchd:

**systemd service** (Linux):

```ini
[Unit]
Description=Claude Mesh SSH Sync
After=network.target

[Service]
Type=simple
User=username
WorkingDirectory=/path/to/project
ExecStart=/usr/local/bin/claude-mesh sync --watch --interval 30
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

**launchd plist** (macOS):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.folktech.mesh-sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/claude-mesh</string>
        <string>sync</string>
        <string>--watch</string>
        <string>--interval</string>
        <string>30</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/username/project</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

---

## How It Works

### Bidirectional rsync

1. **Push**: Sync local writes to remote peer's inbox
   ```
   rsync -az ~/.claude-mesh/groups/{group}/{remote-peer}.ftai \
     user@remote:/path/.claude-mesh/groups/{group}/{remote-peer}.ftai
   ```

2. **Pull**: Fetch your inbox from remote peer
   ```
   rsync -az user@remote:/path/.claude-mesh/groups/{group}/{local-peer}.ftai \
     ~/.claude-mesh/groups/{group}/{local-peer}.ftai
   ```

3. **Read-marker**: Stays local (each peer owns its read position)

---

## Security

### Threat Model

- **Transport**: SSH encrypts all rsync traffic
- **Authentication**: SSH keys (passphrase-protected recommended)
- **Network**: Local LAN assumed trusted (no routing over public internet without VPN)
- **Content**: Still untrusted (all sanitizers apply)

### Risks

| Risk | Mitigation |
|---|---|
| SSH key compromise | Use passphrase; rotate keys periodically |
| Network eavesdropping | SSH encrypts; use on trusted LAN only |
| Remote machine compromise | Content is untrusted (same as local) |

---

## Troubleshooting

### "SSH connection timed out"

- Verify both machines are on same network
- Check SSH server is running: `sudo systemctl status sshd` (Linux) or `sudo systemsetup -getremotelogin` (macOS)
- Test manual SSH: `ssh user@machine-b.local`

### "rsync: command not found"

- Install rsync: `sudo apt install rsync` (Linux) or use Homebrew on macOS

### "Permission denied (publickey)"

- Verify SSH key is copied: `ssh-copy-id user@machine-b.local`
- Check `~/.ssh/authorized_keys` permissions: `chmod 600 ~/.ssh/authorized_keys`

---

## Example Workflow

**Scenario**: Claude on Mac A edits file, peer on Mac B sees it.

1. **Mac A** (Claude edits `src/api/auth.rs`):
   ```bash
   # PostToolUse hook auto-publishes to machine-b.ftai
   claude-mesh sync --peer machine-b
   ```

2. **Mac B** (next prompt):
   ```bash
   # Pull inbox from Mac A
   claude-mesh sync
   claude-mesh drain
   # Sees: @file_change from machine-a
   ```

---

## When NOT to Use SSH Transport

- **Neuro on Grok Bot**: Use file-drop instead (see `neuro-file-drop-setup.md`)
- **Cloud machines**: SSH over internet requires VPN; consider dedicated cloud mesh
- **Untrusted network**: SSH is encrypted but not authenticated against MitM on untrusted networks

---

## References

- [File-Drop Setup (Neuro Default)](neuro-file-drop-setup.md)
- [SPEC-003: Cross-Machine Mesh](../specs/SPEC-003-remote-peer-sync.md)
- [Security Posture](../security-posture.md)

For issues or questions, open an issue at [github.com/FolkTechAI/claude-mesh](https://github.com/FolkTechAI/claude-mesh).
