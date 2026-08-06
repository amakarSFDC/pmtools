#!/usr/bin/env python3
"""
Create Fix Versions from Data File
-------------------------------------
Compares the Scheduled Build column in an import file vs JIRA Fix Versions
and creates any missing future-dated ones.

Usage:
    python3 2_create_fix_versions.py --file import.xls --project IGSIFP

Requirements:
    - import file must be HTML-formatted .xls with a 'Scheduled Build' column
    - Build names must follow the format: 'YYYY.MM.DD_BuildType'
"""

import argparse
import re
import json
import subprocess
from datetime import datetime
from html.parser import HTMLParser

# ── Config ──────────────────────────────────────────────────────────────────
JIRA_BASE_URL = "https://salesforce.atlassian.net"
SKIP_PATTERNS = ['_NO_BUILD_REQUIRED', 'MOCK']
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


def get_build_date(name):
    m = re.match(r'(\d{4})\.(\d{2})\.(\d{2})_', name)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def main():
    parser = argparse.ArgumentParser(description='Create missing future Fix Versions in JIRA from import file.')
    parser.add_argument('--file',    default='data/import.xls', help='Path to import .xls file')
    parser.add_argument('--project', required=True,        help='JIRA project key (e.g. IGSIFP)')
    parser.add_argument('--email',   required=True,        help='JIRA email address')
    parser.add_argument('--token',   required=True,        help='JIRA API token')
    parser.add_argument('--today',   default=datetime.today().strftime('%Y-%m-%d'), help='Override today date (YYYY-MM-DD)')
    args = parser.parse_args()

    creds = f'{args.email}:{args.token}'
    today = datetime.strptime(args.today, '%Y-%m-%d')

    # Parse import file
    with open(args.file, 'r', encoding='iso-8859-1') as f:
        content = f.read()
    p = TableParser()
    p.feed(content)
    idx = {col: p.headers.index(col) for col in p.headers}

    import_builds = set()
    for row in p.rows:
        val = row[idx['Scheduled Build']].strip() if 'Scheduled Build' in idx and idx['Scheduled Build'] < len(row) else ''
        if not val:
            continue
        if any(skip in val for skip in SKIP_PATTERNS):
            continue
        import_builds.add(val)

    # Fetch existing JIRA Fix Versions
    data = api_get(creds, f'{JIRA_BASE_URL}/rest/api/3/project/{args.project}/versions')
    jira_versions = {v['name'] for v in (data if isinstance(data, list) else [])}

    # Find missing future versions
    missing = sorted(
        [(b, get_build_date(b)) for b in import_builds
         if b not in jira_versions and get_build_date(b) and get_build_date(b) >= today],
        key=lambda x: x[1]
    )

    print(f'Import builds:              {len(import_builds)}')
    print(f'Existing JIRA Fix Versions: {len(jira_versions)}')
    print(f'Missing future versions:    {len(missing)}')
    print()

    for name, date in missing:
        resp = api_post(creds, f'{JIRA_BASE_URL}/rest/api/3/version', {
            'name':        name,
            'releaseDate': date.strftime('%Y-%m-%d'),
            'released':    False,
            'project':     args.project
        })
        if 'id' in resp:
            print(f'  CREATED [{resp["id"]}] {resp["name"]}  (release: {resp.get("releaseDate","N/A")})')
        else:
            print(f'  FAILED  {name}: {resp}')


if __name__ == '__main__':
    main()
