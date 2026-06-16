# nb web frontend

React + Vite single-page app for the `nb web` viewer.

## Why the build output is committed

The built assets are emitted to **`../dist`** (`nb/web/dist`) and **committed to git**.
This project is Python-primary — most contributors install with `uv` and never run Node.
Committing `dist/` means `uv sync` / `pip install`, the test suite, and the built wheel all
work with **zero Node toolchain**. The trade-off is that you must rebuild before committing
frontend changes, and CI verifies `dist/` is not stale.

## Develop

```bash
cd nb/web/frontend
npm install            # once
npm run dev            # Vite dev server on :5173 (proxies /api and /ws to uvicorn)
```

Run the backend separately with `nb web --dev` (launches uvicorn and opens the Vite URL).
`VITE_API_TARGET` overrides the proxy target (defaults to `http://127.0.0.1:3000`).

## Build (required before committing FE changes)

```bash
cd nb/web/frontend
npm run build          # type-checks, then Vite build → ../dist
git add ../dist        # commit the rebuilt assets alongside your source changes
```

To verify `dist/` is in sync with source (the check CI runs):

```bash
npm run build && git diff --exit-code ../dist
```

A non-empty diff means `dist/` is stale — rebuild and commit it.
