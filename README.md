# Claude Mesh

> ⚠️ **Pre-release — under active development.** The full README is the final deliverable of the implementation plan. Until then, see `docs/specs/SPEC-001-claude-mesh-v1.md` for what this is and `docs/plans/2026-04-17-claude-mesh-v1.md` for how we're building it.

**What it is** (short version): A Claude Code plugin that persists structured, human-readable, FTAI-native shared knowledge between multiple Claude Code sessions. Works as a layer on top of Anthropic's Agent Teams feature, and as a standalone pair-wise coordination tool when Agent Teams isn't in use.

**Why** [FTAI v2.0](https://github.com/FolkTechAI/ftai-spec) instead of JSON? See `docs/why-ftai.md` (written in Phase 7).

**Status:** Design + spec complete. Implementation underway. See `HANDOFF.md` for current state.

**License:** Apache 2.0.
