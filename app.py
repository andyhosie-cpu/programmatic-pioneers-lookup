"""FastAPI app for the Programmatic Pioneers attendee lookup.

Single entrypoint so Vercel's Python runtime can find one `app`. Exposes:
  GET  /                serves public/index.html
  GET  /api/lookup      attendee lookup with merged target context
  POST /api/query       free-form chat about attendees, powered by Claude
plus the static assets under /public/* (rewrites are handled in vercel.json).
"""
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from anthropic import Anthropic

HERE = Path(__file__).resolve().parent
DATA_PATH = HERE / 'data' / 'attendees.json'
INDEX_HTML = HERE / 'public' / 'index.html'
MODEL = 'claude-sonnet-4-6'

app = FastAPI(title='Programmatic Pioneers Lookup')


def load_data():
    with open(DATA_PATH) as f:
        return json.load(f)


def build_target_indexes(data):
    trade = {t['name'].lower(): t for t in data['trade_body_targets']}
    agency = {a['name'].lower(): a for a in data['agency_targets']}
    bc = {c['name'].lower(): c for c in data['better_collective']['in_room_contacts']}
    return trade, agency, bc


def enrich(attendee, trade, agency, bc):
    out = dict(attendee)
    key = attendee['name'].lower()
    if key in trade:
        out['trade_body'] = trade[key]
    if key in agency:
        out['agency_target'] = agency[key]
    if key in bc:
        out['better_collective_contact'] = bc[key]
    return out


def fuzzy_search(attendees, query, limit=10):
    q = query.strip().lower()
    if not q:
        return []
    matches = [a for a in attendees if q in a['name'].lower() or q in a['company'].lower()]
    def rank(a):
        name = a['name'].lower()
        company = a['company'].lower()
        if name.startswith(q):
            return 0
        if q in name:
            return 1
        if company.startswith(q):
            return 2
        return 3
    matches.sort(key=rank)
    return matches[:limit]


@app.get('/')
def index():
    return FileResponse(INDEX_HTML)


@app.get('/api/lookup')
def lookup(
    name: str | None = None,
    id: int | None = None,
    company: str | None = None,
    tier: str | None = None,
    priority: str | None = None,
):
    data = load_data()
    trade, agency, bc = build_target_indexes(data)

    def enriched(a):
        return enrich(a, trade, agency, bc)

    if id is not None:
        match = next((a for a in data['attendees'] if a['id'] == id), None)
        if not match:
            return JSONResponse({'error': 'Not found'}, status_code=404)
        return {'result': enriched(match)}

    if tier:
        tier_up = tier.strip().upper()
        results = [a for a in data['agency_targets'] if a['tier'].upper() == tier_up]
        return {'tier': tier_up, 'count': len(results), 'results': results}

    if priority:
        needle = priority.strip().lower()
        results = [t for t in data['trade_body_targets'] if needle in t['priority'].lower()]
        return {'priority': priority.upper(), 'count': len(results), 'results': results}

    if company:
        needle = company.strip().lower()
        results = [enriched(a) for a in data['attendees'] if needle in a['company'].lower()]
        return {'company': company, 'count': len(results), 'results': results}

    if name:
        matches = fuzzy_search(data['attendees'], name)
        results = [enriched(a) for a in matches]
        return {'query': name, 'count': len(results), 'results': results}

    # No params: prioritised summary
    tier1 = [a for a in data['agency_targets'] if a['tier'] == 'TIER 1']
    highest_priority = [t for t in data['trade_body_targets'] if 'HIGHEST' in t['priority'].upper()]
    return {
        'metadata': data['metadata'],
        'trade_body_targets': data['trade_body_targets'],
        'agency_tier_1': tier1,
        'better_collective_in_room': data['better_collective']['in_room_contacts'],
        'highest_priority_trade_body': highest_priority,
    }


def build_chat_context(data):
    meta = data['metadata']
    lines = [
        f"CONFERENCE: {meta['conference']} - {meta['date']} - {meta['location']}",
        f"Organiser: {meta['organiser']}. Host: {meta['host']}.",
        f"Captured by: {meta['captured_by']}.",
        f"Total attendees: {meta['total_attendees']}.",
        '',
        '=== TRADE BODY TARGETS ===',
    ]
    for t in data['trade_body_targets']:
        lines.append(f"- {t['name']} | {t['title']} | {t['org']} ({t['org_meaning']}) | {t['priority']} | {t['open_angle']}")
    lines.append('')

    lines.append('=== AGENCY TARGETS (flagged tiers + verticals) ===')
    for a in data['agency_targets']:
        if a['tier'] in ('TIER 1', 'TIER 2', 'INDIE LEAD', 'VERTICAL'):
            lines.append(f"- {a['name']} | {a['title']} | {a['agency']} ({a['holdco']}) | {a['tier']} | {a['lens']}")
    lines.append('')

    lines.append('=== BETTER COLLECTIVE BRIEF ===')
    bc = data['better_collective']
    lines.append('Company:')
    for k, v in bc['company'].items():
        lines.append(f"  {k}: {v}")
    lines.append('House of Brands:')
    for b in bc['house_of_brands']:
        lines.append(f"  {b['brand']}: {b['description']}")
    lines.append('FanReach:')
    for k, v in bc['fanreach'].items():
        lines.append(f"  {k}: {v}")
    lines.append('In-room contacts:')
    for c in bc['in_room_contacts']:
        lines.append(f"  {c['name']} | {c['title']} | {c['lens']} | {c['notes']}")
    lines.append('Why a CapClear account:')
    for w in bc['why_capclear_account']:
        lines.append(f"  {w['reason']}: {w['detail']}")
    lines.append('Action board:')
    for a in bc['action_board']:
        lines.append(f"  {a['when']}: {a['action']}")
    lines.append(f"Open angle: {bc['open_angle']}")
    lines.append('')

    lines.append('=== ALL ATTENDEES (id | name | title | company | notes) ===')
    for a in data['attendees']:
        notes = f" | {a['notes']}" if a['notes'] else ''
        lines.append(f"{a['id']} | {a['name']} | {a['title']} | {a['company']}{notes}")

    return '\n'.join(lines)


SYSTEM_PROMPT = """You are Andy Hosie's research assistant for the Programmatic Pioneers Summit (London, 2 June 2026). Andy is Head of Strategy at Northell and is using this app to navigate a 451-person attendee list, with annotated target lists for trade body decision-makers, agency holdco contacts, and the Better Collective account brief.

Northell's relevant products:
- CapClear: AI ad creative clearance (used by Clearcast, gambling-vertical fit)
- MM Verify: AI advertising verification
- The pitch with Better Collective is FanReach-first, CapClear-second.

Rules:
- Be terse and practical, written for Andy mid-conference.
- Pull from the context provided. If something is not in the context, say so.
- When listing people, give name, title, company, and the lens/priority/tier label if one exists in the brief.
- Group by holdco or tier when listing many people.
- Use clean markdown - tables for multi-row lists, short bullets for ranked suggestions.
- Never invent profile URLs, priorities, or tiers that are not in the context.
- Do not use em dashes. Use a hyphen with spaces, a comma, or a colon."""


@app.post('/api/query')
async def query(request: Request):
    body = await request.json()
    question = body.get('question', '')
    history = body.get('history', [])

    if not question:
        return JSONResponse({'error': 'No question provided'}, status_code=400)

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return JSONResponse({'error': 'API key not configured'}, status_code=500)

    try:
        data = load_data()
        client = Anthropic(api_key=api_key)
        ctx = build_chat_context(data)

        messages = []
        for h in history[-6:]:
            messages.append({'role': h['role'], 'content': h['content']})
        messages.append({
            'role': 'user',
            'content': f'CONFERENCE CONTEXT:\n{ctx}\n\nQUESTION: {question}',
        })

        message = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        return {'answer': message.content[0].text}
    except Exception as e:
        return JSONResponse({'error': f'API error: {str(e)}'}, status_code=500)
