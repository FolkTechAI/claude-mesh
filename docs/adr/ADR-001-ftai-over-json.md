# ADR-001: FTAI v2.0 Over JSON for the Knowledge Format

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-04-17 |
| **Author** | Mike Folk (FolkTech AI LLC) |
| **Spec** | SPEC-001 Section 4 |

---

## Context

Claude Mesh persists events — file changes, task lifecycle, decisions, peer messages — in a shared file that is appended by one Claude Code session and drained by another. The file also serves as a human-readable audit log.

Three format candidates were evaluated:

1. **JSON** — universal, well-tooled, well-understood
2. **FTAI v2.0** — FolkTech AI Interchange Format, designed for AI-to-AI communication with humans in the loop
3. **Ad-hoc markdown** — used by prior art (session-bridge and similar plugins)

Ad-hoc markdown was eliminated immediately: it has no schema, no parseable structure, and every consumer reimplements fragile parsing.

Between JSON and FTAI, the deciding factors were:

**Escape overhead.** Developer message bodies contain code snippets, diff output, file paths with quotes and backslashes. In JSON these require aggressive escaping that makes the file hard to read and error-prone to write. FTAI is line-oriented; body text is literal.

**Type visibility.** In JSON, event type is a string field value. In FTAI, `@decision`, `@file_change`, `@note` are tag names — the type is structurally visible at a glance. A human scanning 200 events in a knowledge log can grep for `@decision` and extract every architectural choice without a parser.

**Schema inline.** FTAI carries the schema declaration in the file itself. Any consumer — human or Claude — can see what tags are valid, required, and optional from the file header. JSON requires a separate schema document.

**Design intent.** FTAI is explicitly designed for AI-to-AI communication. JSON is a general-purpose data interchange format. For a log whose primary readers are Claude processes, a format that models the vocabulary of cross-AI events more precisely is a better fit.

---

## Decision

Use FTAI v2.0 as the knowledge format for all Claude Mesh events.

Vendor the Python FTAI parser (`src/claude_mesh/ftai.py`) into the plugin to maintain zero runtime dependencies.

---

## Consequences

**Positive:**
- Knowledge files are readable by humans without a parser
- Event types are structurally typed, not stringly typed
- No escape overhead for code-containing bodies
- Schema is self-describing and inline
- Contributes to FTAI ecosystem adoption

**Negative / mitigations:**
- FTAI is not a widely-known standard — onboarding cost for new contributors (~20 min)
- Vendored parser means FTAI spec updates don't auto-propagate — must be manually updated in this repo. Mitigated by: the parser is ~150 lines, straightforward to audit and update.
- Dependency on a small ecosystem — mitigated by the format being simple enough to reimplement if the upstream spec stalls

See `docs/why-ftai.md` for the full positioning rationale with side-by-side examples.
