"""POST /api/query - free-form chat about attendees, powered by Claude.

Mirrors api/query.py from the Lumo rota app. Builds a context block containing
the full attendees list summary, trade body targets, agency Tier 1 list, and
the Better Collective brief, then asks Claude to answer the user's question.

Reads the API key from the ANTHROPIC_API_KEY env var, model is claude-sonnet-4-6.
"""
import json
import os
from http.server import BaseHTTPRequestHandler
from anthropic import Anthropic

DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'attendees.json')
MODEL = 'claude-sonnet-4-6'


def load_data():
    with open(DATA_PATH) as f:
        return json.load(f)


def build_context(data):
    """Compact text context for Claude: attendees summary + targets + Better Collective."""
    meta = data['metadata']
    lines = []
    lines.append(f"CONFERENCE: {meta['conference']} - {meta['date']} - {meta['location']}")
    lines.append(f"Organiser: {meta['organiser']}. Host: {meta['host']}.")
    lines.append(f"Captured by: {meta['captured_by']}.")
    lines.append(f"Total attendees: {meta['total_attendees']}.")
    lines.append('')

    lines.append('=== TRADE BODY TARGETS ===')
    for t in data['trade_body_targets']:
        lines.append(f"- {t['name']} | {t['title']} | {t['org']} ({t['org_meaning']}) | {t['priority']} | {t['open_angle']}")
    lines.append('')

    lines.append('=== AGENCY TARGETS (Tier 1 + Tier 2 + flagged) ===')
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


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length))
        question = body.get('question', '')
        history = body.get('history', [])

        if not question:
            self._respond(400, {'error': 'No question provided'})
            return

        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            self._respond(500, {'error': 'API key not configured'})
            return

        try:
            data = load_data()
            client = Anthropic(api_key=api_key)
            ctx = build_context(data)

            messages = []
            for h in history[-6:]:
                messages.append({'role': h['role'], 'content': h['content']})
            messages.append({
                'role': 'user',
                'content': f'CONFERENCE CONTEXT:\n{ctx}\n\nQUESTION: {question}',
            })

            system = """You are Andy Hosie's research assistant for the Programmatic Pioneers Summit (London, 2 June 2026). Andy is Head of Strategy at Northell and is using this app to navigate a 451-person attendee list, with annotated target lists for trade body decision-makers, agency holdco contacts, and the Better Collective account brief.

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

            message = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=system,
                messages=messages,
            )
            answer = message.content[0].text
            self._respond(200, {'answer': answer})
        except Exception as e:
            self._respond(500, {'error': f'API error: {str(e)}'})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def _respond(self, status, payload):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())
