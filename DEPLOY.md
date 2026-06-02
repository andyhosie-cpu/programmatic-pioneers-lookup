# Programmatic Pioneers Lookup - Deployment Guide

## What This Is
A web app for Andy to navigate the Programmatic Pioneers Summit (London, 2 June 2026) attendee list, with merged target context for trade body decision-makers, agency holdco contacts, and the Better Collective account brief. Includes a search/filter view, per-attendee Met + Follow-up notes (localStorage-only), and an AI chat powered by Claude.

## Files
```
attendees-app/
  app.py                - FastAPI app (single Vercel entrypoint). Routes: GET /, GET /api/lookup, POST /api/query
  data/attendees.json   - Pre-parsed data from attendees.xlsx
  static/index.html     - Frontend. Named static/ rather than public/ so Vercel bundles it with the function
  build_data.py         - One-shot xlsx-to-json converter (run before deploying)
  vercel.json           - Vercel config (no special rewrites needed - FastAPI handles routing)
  requirements.txt      - Python dependencies (fastapi, anthropic)
```

## Architecture notes
- Vercel's Python runtime no longer supports multiple `/api/*.py` files as separate serverless functions, so the app is structured as a single FastAPI app at root.
- A directory named `public/` is auto-stripped from the Python function bundle (Vercel treats it as separate static assets); the directory here is named `static/` to keep the HTML bundled.
- Both `static/index.html` and `data/attendees.json` are read once at module load to avoid per-request disk I/O.

## Build the data first
The xlsx is not parsed at request time. Re-run the converter before deploying or whenever the source spreadsheet changes:
```bash
cd "Conferences/2026-06-02/attendees-app"
python3 build_data.py
```
By default the script reads from `~/Desktop/Brain/! Northell/CRM/attendees-programmatic-pioneers-2026-06-02.xlsx`. Override with `ATTENDEES_XLSX=/path/to/file.xlsx python3 build_data.py`.

## Deploy to Vercel

### 1. First-time setup
Already done. Repo is at https://github.com/andyhosie-cpu/programmatic-pioneers-lookup. Vercel project is `attendees-app` under the `andys-projects-21766ec0` team. SSO Deployment Protection is disabled so the URL is publicly reachable.

### 2. Local iteration (no upload, no wait)
For everything except final production verification, use `vercel dev`:
```bash
cd "Conferences/2026-06-02/attendees-app"
vercel dev
```
Runs the full app on `http://localhost:3000` with hot reload. Edits to `app.py`, `static/index.html`, or `data/attendees.json` show up instantly without uploading.

### 3. Redeploy after changes (auto via git push)
This Vercel project is linked to the GitHub repo, so a normal push triggers a production deploy:
```bash
git add . && git commit -m "..." && git push
```
No need to run `vercel deploy` separately. Watch the deploy at https://vercel.com/andys-projects-21766ec0/attendees-app.

If you need to deploy without committing (uncommitted local changes), use:
```bash
vercel deploy --prod --yes
```

### 4. Set or rotate the Anthropic API key
```bash
vercel env add ANTHROPIC_API_KEY production
# paste the key when prompted
vercel deploy --prod --yes
```

### 5. Production URL
`https://attendees-app.vercel.app`

## Notes
- Attendee data is baked into `data/attendees.json` - no database
- Search, filter, and per-attendee notes work without the API key; chat requires it
- Notes live in browser localStorage only; "Export notes" button on the header dumps a markdown table you paste back into Claude to update the xlsx
- Chat model is `claude-sonnet-4-6`. Update the `MODEL` constant in `app.py` to swap it
- Rotate any API key that was shared in chat
