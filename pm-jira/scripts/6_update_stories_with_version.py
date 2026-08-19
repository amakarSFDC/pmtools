#!/usr/bin/env python3
"""
Update Stories with Version
------------------------------
Finds JIRA stories missing a fix version, compares their Scheduled Build
from the import file, and assigns the matching fix version in JIRA.

Skips stories where Scheduled Build contains _NO_BUILD_REQUIRED or MOCK.

Usage:
    python3 6_update_stories_with_version.py --project IGSIFP \
        --email "$JIRA_EMAIL" --token "$JIRA_API_TOKEN"

Requirements:
    - import file must be HTML-formatted .xls with standard columns
"""

import argparse
import os
import json
import subprocess
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


def api(creds, method, url, payload=None):
    args = ['curl', '-s', '-u', creds, '-X', method,
            '-H', 'Content-Type: application/json',
            '-H', 'Accept: application/json']
    if payload:
        args += ['-d', json.dumps(payload)]
    args.append(url)
    r = subprocess.run(args, capture_output=True, text=True)
    return json.loads(r.stdout) if r.stdout.strip() else {}


def main():
    parser = argparse.ArgumentParser(description='Assign fix versions to JIRA stories missing them.')
    parser.add_argument('--file',     default='data/import.xls', help='Path to import .xls file')
    parser.add_argument('--project',  required=True,             help='JIRA project key (e.g. IGSIFP)')
    parser.add_argument('--email',    required=True,             help='JIRA email address')
    parser.add_argument('--token',    required=True,             help='JIRA API token')
    parser.add_argument('--base-url', default=base_url_DEFAULT, help='JIRA base URL (default: $JIRA_BASE_URL)')
    parser.add_argument('--dry-run',  action='store_true',       help='Report only — do not update JIRA')
    args = parser.parse_args()

    creds = f'{args.email}:{args.token}'
    base_url = args.base_url

    # Parse import file
    with open(args.file, 'r', encoding='iso-8859-1') as f:
        content = f.read()
    p = TableParser()
    p.feed(content)
    idx = {col: p.headers.index(col) for col in p.headers}

    def g(row, col):
        i = idx.get(col, -1)
        return row[i].strip() if i >= 0 and i < len(row) else ''

    import_data = {}
    for row in p.rows:
        wid = g(row, 'Work: Work ID')
        if wid:
            import_data[wid] = g(row, 'Scheduled Build')

    # Fetch project fix versions (name → id map)
    versions = api(creds, 'GET', f'{base_url}/rest/api/3/project/{args.project}/versions')
    version_map = {v['name']: v['id'] for v in versions}

    # Fetch all JIRA stories missing a fix version
    no_fix = {}
    next_token = None
    while True:
        payload = {
            'jql':        f'project={args.project} AND issuetype != Epic AND fixVersion is EMPTY ORDER BY rank',
            'maxResults': 100,
            'fields':     ['summary', 'status', 'fixVersions']
        }
        if next_token:
            payload['nextPageToken'] = next_token
        resp   = api(creds, 'POST', f'{base_url}/rest/api/3/search/jql', payload)
        issues = resp.get('issues', [])
        if not issues:
            break
        for issue in issues:
            f       = issue['fields']
            summary = f.get('summary', '')
            wid     = summary[:8]
            no_fix[wid] = {'key': issue['key'], 'status': f['status']['name'], 'summary': summary}
        next_token = resp.get('nextPageToken')
        if not next_token:
            break

    print(f'JIRA stories missing fix version: {len(no_fix)}')
    print()

    has_build   = []
    no_build    = []
    not_import  = []

    for wid, jira in sorted(no_fix.items()):
        sb = import_data.get(wid)
        if sb is None:
            not_import.append((wid, jira))
        elif '_NO_BUILD_REQUIRED' in sb or 'MOCK' in sb:
            no_build.append((wid, jira, sb))
        else:
            has_build.append((wid, jira, sb))

    # Report and assign
    print(f'=== HAS SCHEDULED BUILD — fix version will be assigned ({len(has_build)}) ===')
    updated, failed, skipped_ver = [], [], []
    for wid, jira, sb in has_build:
        vid = version_map.get(sb)
        if not sb:
            print(f'  SKIP  {jira["key"]} | {wid} — no scheduled build in import')
            skipped_ver.append(wid)
            continue
        if not vid:
            print(f'  SKIP  {jira["key"]} | {wid} — fix version "{sb}" not found in JIRA')
            skipped_ver.append(wid)
            continue
        if args.dry_run:
            print(f'  DRY   {jira["key"]} | {wid} -> {sb}')
            updated.append(wid)
        else:
            r = api(creds, 'PUT', f'{base_url}/rest/api/3/issue/{jira["key"]}',
                    {'fields': {'fixVersions': [{'id': vid}]}})
            if r:
                print(f'  FAIL  {jira["key"]} | {wid}: {r}')
                failed.append(wid)
            else:
                print(f'  OK    {jira["key"]} | {wid} -> {sb}')
                updated.append(wid)

    print()
    print(f'=== NO BUILD REQUIRED — skipped ({len(no_build)}) ===')
    for wid, jira, sb in no_build:
        print(f'  SKIP  {jira["key"]} | {wid} | {sb}')

    print()
    print(f'=== NOT IN IMPORT FILE ({len(not_import)}) ===')
    for wid, jira in not_import:
        print(f'  INFO  {jira["key"]} | {wid} | {jira["status"]}')

    print()
    print(f'Summary:')
    print(f'  Total missing fix version:  {len(no_fix)}')
    print(f'  Updated{"(dry run)" if args.dry_run else "":>10}:  {len(updated)}')
    print(f'  Failed:                     {len(failed)}')
    print(f'  Skipped (version not found):{len(skipped_ver)}')
    print(f'  No build required:          {len(no_build)}')
    print(f'  Not in import:              {len(not_import)}')


if __name__ == '__main__':
    main()
