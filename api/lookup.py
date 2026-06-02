"""GET /api/lookup - search and filter attendees with merged target context.

Query params (mutually exclusive priority order):
- id=<n>           one attendee by id (row number)
- tier=<TIER 1>    all agency targets at that tier
- priority=<text>  trade-body targets whose priority contains the substring (case-insensitive)
- company=<name>   everyone whose company contains the substring
- name=<query>     fuzzy substring match across name AND company, up to 10 records
- (no params)      metadata + prioritised target lists summary

Records returned are enriched: an attendee who also appears as a trade-body /
agency / Better Collective contact gets the matching target detail merged in.
"""
import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'attendees.json')


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
    matches = []
    for a in attendees:
        if q in a['name'].lower() or q in a['company'].lower():
            matches.append(a)
    # Prefer name matches that start with the query, then name contains, then company.
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


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        data = load_data()
        trade, agency, bc = build_target_indexes(data)

        def enriched(a):
            return enrich(a, trade, agency, bc)

        if 'id' in query:
            try:
                target_id = int(query['id'][0])
            except ValueError:
                self._respond(400, {'error': 'id must be an integer'})
                return
            match = next((a for a in data['attendees'] if a['id'] == target_id), None)
            self._respond(200, {'result': enriched(match)} if match else {'error': 'Not found'})
            return

        if 'tier' in query:
            tier = query['tier'][0].strip().upper()
            results = [a for a in data['agency_targets'] if a['tier'].upper() == tier]
            self._respond(200, {'tier': tier, 'count': len(results), 'results': results})
            return

        if 'priority' in query:
            needle = query['priority'][0].strip().lower()
            results = [t for t in data['trade_body_targets'] if needle in t['priority'].lower()]
            self._respond(200, {'priority': needle.upper(), 'count': len(results), 'results': results})
            return

        if 'company' in query:
            needle = query['company'][0].strip().lower()
            results = [enriched(a) for a in data['attendees'] if needle in a['company'].lower()]
            self._respond(200, {'company': query['company'][0], 'count': len(results), 'results': results})
            return

        if 'name' in query:
            matches = fuzzy_search(data['attendees'], query['name'][0])
            results = [enriched(a) for a in matches]
            self._respond(200, {'query': query['name'][0], 'count': len(results), 'results': results})
            return

        # No params - prioritised summary
        tier1 = [a for a in data['agency_targets'] if a['tier'] == 'TIER 1']
        highest_priority = [t for t in data['trade_body_targets'] if 'HIGHEST' in t['priority'].upper()]
        summary = {
            'metadata': data['metadata'],
            'trade_body_targets': data['trade_body_targets'],
            'agency_tier_1': tier1,
            'better_collective_in_room': data['better_collective']['in_room_contacts'],
            'highest_priority_trade_body': highest_priority,
        }
        self._respond(200, summary)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def _respond(self, status, payload):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())
