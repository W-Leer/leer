# AGENTS.md

## Purpose
Guide AI coding agents (Cursor, etc.) when working on Leer.

---

## Core Rules

1. Always read:
   - docs/00-product/vision.md
   - docs/01-architecture/overview.md
   before implementing anything.

2. Do not invent architecture.
   Follow defined concepts:
   - Run
   - Step
   - Event
   - Artifact

3. Before writing major code:
   - check if a spec exists
   - if not, create one in /docs/03-specs

4. Keep implementation simple:
   - minimal dependencies
   - local-first
   - no unnecessary abstractions

5. All logic must support future:
   - replay
   - diffing
   - execution control

6. When changing structure:
   - update docs
   - create ADR in docs/02-decisions

---

## Coding Style

- Prefer clarity over cleverness
- Use typed Python
- Avoid magic behavior
- Keep functions small

---

## Testing

- Add tests for stateful logic
- Ensure replay consistency when possible

---

## Goal

Build a system that:
- developers understand instantly
- scales into execution platform later