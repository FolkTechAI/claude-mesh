"""Remote-doctor command: validate SSH connectivity to remote peers."""

from __future__ import annotations

import sys
from pathlib import Path

from claude_mesh.config import ConfigError, find_config, load_config
from claude_mesh.remote import validate_ssh_connectivity


def run_remote_doctor() -> int:
    """Test SSH connectivity to all configured remote peers.

    Returns:
        Exit code (0 = all healthy, 1 = any failures)
    """
    cwd = Path.cwd()
    
    cfg_path = find_config(cwd)
    if cfg_path is None:
        print("claude-mesh remote-doctor: no .claude-mesh config found", file=sys.stderr)
        return 1

    try:
        config = load_config(cfg_path)
    except ConfigError as exc:
        print(f"claude-mesh remote-doctor: config error: {exc}", file=sys.stderr)
        return 1

    if not config.remote_peers:
        print("No remote peers configured")
        return 0

    print(f"Testing connectivity to {len(config.remote_peers)} remote peer(s)...")
    print()

    all_healthy = True
    for peer_name, remote_config in config.remote_peers.items():
        print(f"  {peer_name} ({remote_config['user']}@{remote_config['host']}):", end=" ")
        success, message = validate_ssh_connectivity(remote_config)
        
        if success:
            print("✓ OK")
        else:
            print(f"✗ FAILED")
            print(f"    {message}")
            all_healthy = False

    print()
    if all_healthy:
        print("All remote peers are reachable")
        return 0
    else:
        print("Some remote peers are unreachable (see above)", file=sys.stderr)
        print()
        print("Troubleshooting:")
        print("  1. Ensure SSH keys are set up: ssh-keygen -t ed25519")
        print("  2. Copy key to remote: ssh-copy-id user@host")
        print("  3. Test manually: ssh user@host 'echo ok'")
        return 1
