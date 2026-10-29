# leer-web

Next.js UI for browsing Leer execution records. It reads everything from
the Leer API and has no database of its own.

## Requirements

- Node.js 20.9+
- A running Leer API (see [`apps/api/README.md`](../api/README.md))

## Run

```bash
cd apps/web
npm install
npm run dev
```

Open http://localhost:3000.

The API URL comes from `NEXT_PUBLIC_API_BASE_URL`, which defaults to
`http://127.0.0.1:8000`. To point at another API, set it in `.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## Pages

| Route        | What it shows |
| ------------ | ------------- |
| `/`          | Runs list with search, status filter, and sort |
| `/runs/[id]` | Run detail: step timeline, LLM calls (including refusals), tool calls, artifacts, recorded-stream playback |
| `/compare`   | Two runs side by side, step by step |

The sidebar picks the project. It defaults to `?project=<slug>` in the URL,
then the last project picked in this browser, then the most recently active
project. See `src/components/project-provider.tsx`.

## Layout

- `src/app/`: routes
- `src/components/`: run detail, LLM step detail, artifact and media viewers
- `src/lib/api.ts`: API client
- `src/lib/types.ts`: response types, mirroring the API's read schemas
- `src/lib/*.ts`: pure helpers (formatting, latency, tool linkage,
  provider hardening)

The UI renders the canonical LLM call shape. Provider-specific fields are
only shown as supplemental detail.

## Checks

```bash
bun test        # helper tests (src/lib/*.test.ts)
npm run build   # production build + typecheck
npm run lint
```
