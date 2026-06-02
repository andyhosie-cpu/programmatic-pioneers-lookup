# Programmatic Pioneers Lookup - Deployment Guide

## What This Is
A web app for Andy to navigate the Programmatic Pioneers Summit (London, 2 June 2026) attendee list, with merged target context for trade body decision-makers, agency holdco contacts, and the Better Collective account brief. Includes a search/filter view and an AI chat powered by Claude.

## Files
```
attendees-app/
  api/lookup.py        - JSON API for attendee lookup, filters, target lists
  api/query.py         - Chat endpoint (Claude API)
  data/attendees.json  - Pre-parsed data from attendees.xlsx
  public/index.html    - Frontend (search + results + chat)
  build_data.py        - One-shot xlsx-to-json converter (run before deploying)
  vercel.json          - Vercel routing config
  requirements.txt     - Python dependencies
```

## Build the data first
The xlsx is not parsed at request time. Re-run the converter before deploying or whenever the source spreadsheet changes:
```bash
cd "Conferences/2026-06-02/attendees-app"
python3 build_data.py
```
By default the script reads from `~/Desktop/Brain/! Northell/CRM/attendees-programmatic-pioneers-2026-06-02.xlsx`. Override with `ATTENDEES_XLSX=/path/to/file.xlsx python3 build_data.py`.

## Deploy to Vercel

### 1. Install Vercel CLI (if you haven't)
```bash
npm i -g vercel
```

### 2. Push to GitHub
Create a new repo (e.g. `programmatic-pioneers-lookup`) and push the `attendees-app` folder contents:
```bash
cd "Conferences/2026-06-02/attendees-app"
git init
git add .
git commit -m "Initial attendees app"
gh repo create programmatic-pioneers-lookup --private --source=. --push
```

### 3. Deploy
```bash
vercel
```
Follow the prompts. It will detect the config and deploy.

### 4. Set the API key
In the Vercel dashboard (or CLI), add the environment variable:
```bash
vercel env add ANTHROPIC_API_KEY
```
Paste your Claude API key when prompted. Then redeploy:
```bash
vercel --prod
```

### 5. Open the URL
Vercel gives you a URL like `programmatic-pioneers-lookup.vercel.app`. Bookmark it on your phone for the day.

## Notes
- The attendee data is baked into `data/attendees.json` - no database needed
- Search and filter work without the API key; chat requires it
- To update the data later, re-run `build_data.py` and redeploy
- The chat model is `claude-sonnet-4-6`. Update the constant in `api/query.py` if you want to swap it
- Remember to rotate any API key that was shared in chat
