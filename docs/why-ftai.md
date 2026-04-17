# Why FTAI Instead of JSON?

Claude Mesh uses FTAI v2.0 as its knowledge format. This document explains why.

---

## The Problem

Multiple Claude Code sessions on the same machine are blind to each other. One session edits a shared interface; the other doesn't know until the build breaks. Solving this requires a persistent, readable shared log: a file both sessions can write to and drain from on every turn.

The format question matters more than it looks. The log's job isn't storage — it's communication. It will be appended by one AI process, read by another, and reviewed by a human when something goes wrong. The format has to work for all three readers.

---

## What JSON Gives You

JSON is universal and well-tooled. For a message-passing bus it works fine. But for this specific use case, it creates friction:

```json
{
  "type": "file_change",
  "from": "vault",
  "timestamp": "2026-04-17T19:42:11Z",
  "path": "src/api/auth.rs",
  "tool": "Edit",
  "summary": "3 files changed, 47 insertions(+), 12 deletions(-)"
}
```

That's readable, but consider a file with 200 of these objects. You need a JSON parser or a lot of squinting. More importantly: JSON has no schema-level affordances for the concepts we actually care about. A `@decision` with impact metadata is just another dict. A `@note` looks identical to a `@message`. Nothing in the format signals "this is a cross-AI log" or "these events are structured by type." A consumer has to decode that intent from string values.

The escape problem bites harder when message bodies contain code or diff output:

```json
{
  "body": "Updated auth.rs. The decoder now expects `aud: [\\\"vault-api\\\"]` — check the AAD test in `tests/auth/` if it breaks."
}
```

Every backtick, quote, and backslash in a developer message becomes an escape problem. The larger the bodies, the worse it gets.

---

## What FTAI Expresses Natively

FTAI (FolkTech AI Interchange Format) v2.0 is designed for AI-to-AI communication with humans in the loop. The same event in FTAI:

```
@file_change
from: vault
timestamp: 2026-04-17T19:42:11Z
path: src/api/auth.rs
tool: Edit
summary: 3 files changed, 47 insertions(+), 12 deletions(-)
```

The tag is the type. `@file_change`, `@decision`, `@note`, `@task`, `@message` are vocabulary items in the format itself, not string values in a field. A human scanning the log spots event types at a glance. A Claude reading the file sees structured, named events that match how it already reasons about software development.

The format is line-oriented, not nested. No escape hell for developer-written bodies. A body containing quotes, backticks, and backslash sequences is just text.

FTAI also carries the schema declaration inline:

```
@schema
name: claude_mesh_v1
required_tags: ["@document", "@channel"]
optional_tags: ["@message", "@file_change", "@task", "@decision", "@note"]
@end
```

Any consumer — human or AI — knows immediately what tags are valid, what's required, and what's optional. A JSON file carries no such contract unless you separately maintain a schema document and reference it externally.

---

## Side-by-Side: A Decision Event

**JSON:**

```json
{
  "type": "decision",
  "from": "brain",
  "timestamp": "2026-04-17T19:45:00Z",
  "id": "use-ed25519",
  "title": "Use Ed25519 for session identity",
  "content": "Decided against RSA for smaller keys and faster signing. Existing RSA code needs migration.",
  "impact": "All future auth changes must use Ed25519."
}
```

**FTAI:**

```
@decision
from: brain
timestamp: 2026-04-17T19:45:00Z
id: use-ed25519
title: Use Ed25519 for session identity
content: Decided against RSA for smaller keys and faster signing. Existing RSA code needs migration.
impact: All future auth changes must use Ed25519.
@end
```

The FTAI version is the same length. It's readable without a parser. The `@decision` tag immediately signals architectural significance — not just a routine message. A team scanning the knowledge log can grep for `@decision` and pull every significant architectural choice made during the session.

---

## Honest Tradeoffs

FTAI is not a standard like JSON. The ecosystem is small. If you've never seen it, there's a 20-minute onboarding cost.

Claude Mesh vendors the FTAI Python parser (`src/claude_mesh/ftai.py`) to keep the plugin dependency-free. That means FTAI format updates don't auto-propagate — someone has to explicitly update the vendored parser. The spec is public and the parser is short; updates are straightforward.

For a general-purpose message bus, JSON is the right default. For a log of what two AI sessions decided, changed, and need each other to know — a format designed for that purpose does a better job.

---

## Positioning

Claude Mesh uses FTAI because coordination between AIs deserves a format designed for it, not a general-purpose format shoehorned in.

**Spec and parser:** https://github.com/FolkTechAI/ftai-spec
