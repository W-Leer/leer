# Contributing to Leer

Thanks for your interest. Issues and pull requests are welcome. Every pull
request is reviewed by a maintainer before it is merged.

## Before you start

- For anything larger than a small fix, **open an issue first** so we can
  agree on the approach before you write code.
- Read [`AGENTS.md`](AGENTS.md). It is written for AI coding agents, but it
  is also the clearest summary of the project's rules for humans.
- Specs live in [`docs/03-specs/`](docs/03-specs/), and architecture docs
  in [`docs/01-architecture/`](docs/01-architecture/).

## Project rules

These keep execution records stable and comparable over time:

- **Use the canonical model.** Everything is a Run, Step, Event, or
  Artifact. Provider responses normalize into one shape
  (`NormalizedLLMCall`). Don't add parallel concepts.
- **Make changes additive.** Don't make breaking schema changes, and don't
  change step types or the meaning of historical records, except to fix a
  bug.
- **Keep streaming parity.** A streamed and a non-streamed call must
  produce the same canonical output, unless the provider exposes different
  information.
- **Support OpenAI and Anthropic only, for now.** Please don't add new
  providers yet.
- **Document first.** Structural changes need a spec in `docs/03-specs/`
  and, where relevant, an ADR in `docs/02-decisions/`.

## Development setup

Follow the [quick start](README.md#quick-start) to run Postgres, the API,
and the UI locally.

## Tests

Please run the suites your change touches:

```bash
cd apps/sdk-python && uv run pytest -q   # SDK (no database needed)
cd apps/api && uv run pytest -q          # API (needs a migrated Postgres, see apps/api/README.md)
cd apps/web && bun test                  # web helpers
cd apps/web && npm run build             # web build + typecheck
```

Add tests for any stateful logic you change. Provider-facing changes must
keep the golden drift suites green (`apps/sdk-python/tests/test_provider_drift*.py`).

## Pull requests

- Keep PRs small and focused on one change.
- Describe what changed and why, and link the issue.
- CI must pass.

## Reporting security issues

Please don't open public issues for vulnerabilities. See
[`SECURITY.md`](SECURITY.md).

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
