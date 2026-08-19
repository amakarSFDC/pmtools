#!/usr/bin/env python3
"""
Create Sprints from Data File
------------------------------
Compares sprint names in an import file vs a JIRA board and creates
any missing future-dated sprints.

Usage:
    python3 1_create_sprints.py --file import.xls --board 18086

Requirements:
    - import file must be HTML-formatted .xls with a 'Sprint Name' column
    - Sprint names must follow the format: 'YYYY.MMx-Team Name MM/DD - MM/DD'
"""

import argparse
import os
import re
import json
import subprocess
from datetime import datetime
from html.parser import HTMLParser

# ── Config ──────────────────────────────────────────────────────────────────
base_url_DEFAULT = os.environ.get('JIRA_BASE_URL', 'https://salesforce.atlassian.net')
# ─────────────────────────────────────────────────────────────────────────────


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_td = False
        self.current_row = []
        self.rows = []
        self.current_cell = ''
        self.headers = []
        self.header_done = False

    def handle_starttag(self, tag, attrs):
        if tag in ('td', 'th'):
            self.in_td = True
            self.current_cell = ''

    def handle_endtag(self, tag):
        if tag in ('td', 'th'):
            self.in_td = False
            self.current_row.append(self.current_cell.strip())
        elif tag == 'tr':
            if self.current_row:
                if not self.header_done:
                    self.headers = self.current_row
                    self.header_done = True
                else:
                    self.rows.append(self.current_row)
            self.current_row = []

    def handle_data(self, data):
        if self.in_td:
            self.current_cell += data


def api_get(creds, url):
    result = subprocess.run(
        ['curl', '-s', '-u', creds, '-H', 'Accept: application/json', url],
        capture_output=True, text=True
    )
    return json.loads(result.stdout) if result.stdout.strip() else {}


def api_post(creds, url, payload):
    result = subprocess.run(
        ['curl', '-s', '-u', creds, '-X', 'POST',
         '-H', 'Content-Type: application/json',
         '-H', 'Accept: application/json',
         '-d', json.dumps(payload), url],
        capture_output=True, text=True
    )
    return json.loads(result.stdout) if result.stdout.strip() else {}


def strip_date(name):
    return re.sub(r'\s+\d+/\d+\s*-\s*\d+/\d+$', '', name).strip()


def get_sprint_start_date(raw_name):
    year_m = re.match(r'(\d{4})\.', raw_name)
    base_year = int(year_m.group(1)) if year_m else datetime.today().year
    m = re.search(r'(\d+)/(\d+)\s*-\s*\d+/\d+$', raw_name)
    if not m:
        return None
    return datetime(base_year, int(m.group(1)), int(m.group(2)))


def parse_sprint_dates(raw_name):
    year_m = re.match(r'(\d{4})\.', raw_name)
    base_year = int(year_m.group(1)) if year_m else datetime.today().year
    m = re.search(r'(\d+)/(\d+)\s*-\s*(\d+)/(\d+)$', raw_name)
    if not m:
        return None, None
    sm, sd, em, ed = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    end_year = base_year if em >= sm else base_year + 1
    start = f'{base_year}-{sm:02d}-{sd:02d}T00:00:00.000Z'
    end   = f'{end_year}-{em:02d}-{ed:02d}T00:00:00.000Z'
    return start, end


def main():
    parser = argparse.ArgumentParser(description='Create missing future sprints in JIRA from import file.')
    parser.add_argument('--file',     default='data/import.xls', help='Path to import .xls file')
    parser.add_argument('--board',    required=True,        help='JIRA board ID')
    parser.add_argument('--email',    required=True,        help='JIRA email address')
    parser.add_argument('--token',    required=True,        help='JIRA API token')
    parser.add_argument('--base-url', default=base_url_DEFAULT, help='JIRA base URL (default: $JIRA_BASE_URL)')
    parser.add_argument('--today',    default=datetime.today().strftime('%Y-%m-%d'), help='Override today date (YYYY-MM-DD)')
    args = parser.parse_args()

    creds = f'{args.email}:{args.token}'
    base_url = args.base_url
    today = datetime.strptime(args.today, '%Y-%m-%d')

    # Parse import file
    with open(args.file, 'r', encoding='iso-8859-1') as f:
        content = f.read()
    p = TableParser()
    p.feed(content)
    idx = {col: p.headers.index(col) for col in p.headers}

    import_sprints = {}
    for row in p.rows:
        raw = row[idx['Sprint Name']].strip() if 'Sprint Name' in idx and idx['Sprint Name'] < len(row) else ''
        if not raw:
            continue
        clean = strip_date(raw)
        if clean not in import_sprints:
            import_sprints[clean] = raw

    # Fetch existing JIRA sprints
    data = api_get(creds, f'{base_url}/rest/agile/1.0/board/{args.board}/sprint?maxResults=200')
    jira_sprints = {s['name'] for s in data.get('values', [])}

    # Find missing future sprints
    missing = []
    for clean, raw in import_sprints.items():
        start_date = get_sprint_start_date(raw)
        if start_date and start_date > today and clean not in jira_sprints:
            missing.append((clean, raw, start_date))
    missing.sort(key=lambda x: x[2])

    print(f'Import sprints:        {len(import_sprints)}')
    print(f'Existing JIRA sprints: {len(jira_sprints)}')
    print(f'Missing future sprints:{len(missing)}')
    print()

    for clean, raw, start_date in missing:
        start, end = parse_sprint_dates(raw)
        resp = api_post(creds, f'{base_url}/rest/agile/1.0/sprint', {
            'name': clean,
            'startDate': start,
            'endDate': end,
            'originBoardId': int(args.board)
        })
        if 'id' in resp:
            print(f'  CREATED [{resp["id"]}] {resp["name"]}  {start[:10]} -> {end[:10]}')
        else:
            print(f'  FAILED  {clean}: {resp}')


if __name__ == '__main__':
    main()
