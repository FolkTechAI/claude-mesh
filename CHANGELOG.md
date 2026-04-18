# Changelog

All notable changes to this project will be documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.2] — 2026-04-18

### Fixed
- **Bug: init accepted group names the runtime would later reject.** `claude-mesh init --group spike` used to write a config that the PostToolUse hook silently rejected with `"cannot infer peer from group name"`. `init` now validates that the group name contains one of the peer names and always writes an explicit `mesh_peers` list so resolution is unambiguous.
- **Bug: peer names containing hyphens silently disabled mesh writes.** `notify_change` used `cfg.mesh_group.split("-")` and required exactly 2 parts, which broke for any peer like `mesh-test` or project named `my-project`. Resolution now uses the explicit `mesh_peers` list when present, falling back to prefix/suffix match on the group name. Both routes handle multi-token peer names.

### Added
- `mesh_peers: [a, b]` — optional explicit peer list in `.claude-mesh`. Authoritative for peer inference; group name becomes a human-readable label.
- `claude-mesh init --other PEER` — explicit flag for the second peer in the pair.
- Regression tests for both bugs.

### Changed
- README install instructions now use the working `/plugin marketplace add` + `/plugin install` flow.
- README quickstart shows the two-peer init pattern and documents the `mesh_peers` field.

## [0.1.1] — 2026-04-17

- Initial public release of the plugin.
