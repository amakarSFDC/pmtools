#!/usr/bin/env python3
"""
Compare JIRA to File
-----------------------
Compares Work ID and status between an import file and JIRA for one or
more specified sprints. Also identifies future-sprint scope changes:
  - Stories in future JIRA sprints that no longer exist in the import file
  - Stories assigned to a different sprint in the import file vs JIRA
    (sprint mismatches are automatically updated in JIRA)

Usage:
    # Status comparison for specific sprints
    python3 4_compare_jira_to_file.py --file import.xls --project IGSIFP \
        --sprints "2026.07b-Comp Systems 7/15 - 7/28" "2026.07c-Comp Systems 7/29 - 8/11"

    # Future sprint analysis only (no --sprints required)
    python3 4_compare_jira_to_file.py --file import.xls --project IGSIFP --board 18086

Requirements:
    - import file must be HTML-formatted .xls with standard columns
    - Sprint names must match exactly as they appear in the import file (including date suffix)
"""

import argparse
import os
import re
import json
import subprocess
from datetime import datetime
from html.parser import HTMLParser

# ── Config ──────────────────────────────────────────────────────────────────
base_url_DEFAULT = os.environ.get('base_url', 'https://salesforce.atlassian.net')
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


def strip_date(s):
    return re.sub(r'\s+\d+/\d+\s*-\s*\d+/\d+$', '', s).strip()


def main():
    parser = argparse.ArgumentParser(description='Compare JIRA stories to import file for specified sprints.')
    parser.add_argument('--file',     default='data/import.xls', help='Path to import .xls file')
    parser.add_argument('--project',  required=True,             help='JIRA project key (e.g. IGSIFP)')
    parser.add_argument('--board',    required=True,             help='JIRA board ID')
    parser.add_argument('--sprints',  nargs='+', default=[],     help='Sprint name(s) from import file (full name with dates) for status comparison')
    parser.add_argument('--all',      action='store_true',       help='Compare entire project (all JIRA stories, not just specified sprints)')
    parser.add_argument('--email',    required=True,             help='JIRA email address')
    parser.add_argument('--token',    required=True,             help='JIRA API token')
    parser.add_argument('--base-url', default=base_url_DEFAULT, help='JIRA base URL (default: $base_url)')
    parser.add_argument('--today',    default=datetime.today().strftime('%Y-%m-%d'), help='Override today date (YYYY-MM-DD)')
    args = parser.parse_args()

    creds = f'{args.email}:{args.token}'
    base_url = args.base_url
    today = datetime.strptime(args.today, '%Y-%m-%d')
    target_sprints = set(args.sprints)

    # Parse import file
    with open(args.file, 'r', encoding='iso-8859-1') as f:
        content = f.read()
    p = TableParser()
    p.feed(content)
    idx = {col: p.headers.index(col) for col in p.headers}

    def g(row, col):
        i = idx.get(col, -1)
        return row[i].strip() if i >= 0 and i < len(row) else ''

    # Build two import maps:
    #   import_data     — filtered to target sprints, used for status comparison
    #   all_import_data — all rows, used for future sprint analysis (wid → stripped sprint name)
    import_data     = {}
    all_import_data = {}
    for row in p.rows:
        wid        = g(row, 'Work: Work ID')
        sprint_raw = g(row, 'Sprint Name')
        if not wid:
            continue
        if sprint_raw:
            all_import_data[wid] = strip_date(sprint_raw)
        if sprint_raw in target_sprints:
            import_data[wid] = {
                'status':  g(row, 'Status'),
                'subject': g(row, 'Subject'),
                'sprint':  strip_date(sprint_raw),
            }

    # Fetch all sprint data from JIRA
    sprint_data = api(creds, 'GET',
        f'{base_url}/rest/agile/1.0/board/{args.board}/sprint?maxResults=200')
    all_sprints     = sprint_data.get('values', [])
    sprint_id_map   = {s['name']: s['id'] for s in all_sprints}
    sprint_name_map = {s['id']: s['name'] for s in all_sprints}

    # ── Section 1a: Full project comparison (--all flag) ────────────────────
    if args.all:
        print('FULL PROJECT COMPARISON')
        print('=' * 175)

        jira_all   = {}
        next_token = None
        while True:
            payload = {
                'jql':        f'project={args.project} AND issuetype != Epic ORDER BY rank',
                'maxResults': 100,
                'fields':     ['summary', 'status', 'customfield_10020']
            }
            if next_token:
                payload['nextPageToken'] = next_token
            resp   = api(creds, 'POST', f'{base_url}/rest/api/3/search/jql', payload)
            issues = resp.get('issues', [])
            if not issues:
                break
            for issue in issues:
                f            = issue['fields']
                summary      = f.get('summary', '')
                wid          = summary[:8]
                sprint_field = f.get('customfield_10020') or []
                if isinstance(sprint_field, dict):
                    sprint_field = [sprint_field]
                jira_sprint  = strip_date(sprint_field[-1].get('name', '')) if sprint_field else '(backlog)'
                jira_all[wid] = (issue['key'], f['status']['name'], jira_sprint)
            next_token = resp.get('nextPageToken')
            if not next_token:
                break

        all_wids = sorted(set(list(all_import_data.keys()) + list(jira_all.keys())))

        print(f'{"Work ID":<12} {"Subject":<50} {"Import Sprint":<30} {"Import Status":<25} {"JIRA Key":<12} {"JIRA Status":<20} {"JIRA Sprint":<30} {"Match?"}')
        print('-' * 200)

        counts = {'match': 0, 'mismatch': 0, 'missing': 0, 'not_in_import': 0, 'wrong_sprint': 0}

        for wid in all_wids:
            imp_sprint  = all_import_data.get(wid, '')
            imp_row     = next((r for r in p.rows
                                if g(r, 'Work: Work ID') == wid), None)
            imp_status  = g(imp_row, 'Status')  if imp_row else ''
            subject     = g(imp_row, 'Subject')[:48] if imp_row else ''

            if wid not in jira_all:
                jira_key, jira_status, jira_sprint = 'NOT IN JIRA', 'NOT IN JIRA', ''
            else:
                jira_key, jira_status, jira_sprint = jira_all[wid]

            if jira_status == 'NOT IN JIRA':
                match = 'MISSING'
                counts['missing'] += 1
            elif not imp_status:
                match = 'NOT IN IMPORT'
                counts['not_in_import'] += 1
            elif imp_sprint != jira_sprint and jira_sprint != '(backlog)':
                match = 'WRONG SPRINT'
                counts['wrong_sprint'] += 1
            elif imp_status == jira_status:
                match = 'YES'
                counts['match'] += 1
            else:
                match = 'NO'
                counts['mismatch'] += 1

            print(f'{wid:<12} {subject:<50} {imp_sprint:<30} {imp_status:<25} {jira_key:<12} {jira_status:<20} {jira_sprint:<30} {match}')

        print()
        print(f'Total: {len(all_wids)}  |  Match: {counts["match"]}  |  Mismatch: {counts["mismatch"]}  '
              f'|  Missing from JIRA: {counts["missing"]}  |  Wrong sprint: {counts["wrong_sprint"]}  '
              f'|  Not in import: {counts["not_in_import"]}')
        print()

    # ── Section 1b: Status comparison for specified sprints ───────────────────
    if target_sprints:
        target_sprint_names = {strip_date(s) for s in target_sprints}
        sprint_ids = [str(v) for k, v in sprint_id_map.items() if k in target_sprint_names]

        if not sprint_ids:
            print('ERROR: No matching sprint IDs found in JIRA. Check sprint names.')
        else:
            resp = api(creds, 'POST', f'{base_url}/rest/api/3/search/jql', {
                'jql': f'project={args.project} AND sprint in ({",".join(sprint_ids)}) ORDER BY rank',
                'maxResults': 200,
                'fields': ['summary', 'status']
            })

            jira_data = {}
            for issue in resp.get('issues', []):
                summary = issue['fields']['summary']
                work_id = summary[:8]
                jira_data[work_id] = (issue['key'], issue['fields']['status']['name'])

            all_wids = sorted(set(list(import_data.keys()) + list(jira_data.keys())))

            print(f'{"Work ID":<12} {"Subject":<50} {"Import Sprint":<30} {"Import Status":<25} {"JIRA Key":<12} {"JIRA Status":<20} {"Match?"}')
            print('-' * 165)

            counts = {'match': 0, 'mismatch': 0, 'missing': 0, 'jira_only': 0, 'wrong_sprint': 0}

            for wid in all_wids:
                imp        = import_data.get(wid, {})
                imp_status = imp.get('status', '')
                subject    = imp.get('subject', '')[:48]
                sprint     = imp.get('sprint', '')
                jira_key, jira_status = jira_data.get(wid, ('NOT IN JIRA', 'NOT IN JIRA'))

                if jira_status == 'NOT IN JIRA':
                    match = 'MISSING'
                    counts['missing'] += 1
                elif not imp_status:
                    # Not in target sprints — check if it exists in a different sprint in the import
                    other_sprint = all_import_data.get(wid)
                    if other_sprint:
                        imp_status = 'IN IMPORT — DIFFERENT SPRINT'
                        sprint     = other_sprint
                        match      = 'WRONG SPRINT'
                        counts['wrong_sprint'] += 1
                    else:
                        imp_status = 'NOT IN IMPORT'
                        match      = 'NOT IN IMPORT'
                        counts['jira_only'] += 1
                elif imp_status == jira_status:
                    match = 'YES'
                    counts['match'] += 1
                else:
                    match = 'NO'
                    counts['mismatch'] += 1

                print(f'{wid:<12} {subject:<50} {sprint:<30} {imp_status:<25} {jira_key:<12} {jira_status:<20} {match}')

            print()
            print(f'Total: {len(all_wids)}  |  Match: {counts["match"]}  |  Mismatch: {counts["mismatch"]}  '
                  f'|  Missing from JIRA: {counts["missing"]}  |  '
                  f'Wrong sprint: {counts["wrong_sprint"]}  |  Not in import: {counts["jira_only"]}')

    # ── Section 2: Future sprint scope and sprint assignment analysis ────────
    future_sprints = []
    for s in all_sprints:
        raw_start = s.get('startDate', '')
        if raw_start:
            try:
                start = datetime.strptime(raw_start[:10], '%Y-%m-%d')
                if start > today:
                    future_sprints.append(s)
            except ValueError:
                pass

    if not future_sprints:
        print('\nNo future sprints found — skipping future sprint analysis.')
        return

    future_sprint_ids = [str(s['id']) for s in future_sprints]

    resp2 = api(creds, 'POST', f'{base_url}/rest/api/3/search/jql', {
        'jql': f'project={args.project} AND sprint in ({",".join(future_sprint_ids)}) ORDER BY rank',
        'maxResults': 500,
        'fields': ['summary', 'status', 'customfield_10020']
    })

    removed        = []
    sprint_changes = []

    for issue in resp2.get('issues', []):
        summary   = issue['fields']['summary']
        wid       = summary[:8]
        issue_key = issue['key']

        # Resolve current sprint name from sprint custom field
        sprint_field = issue['fields'].get('customfield_10020') or []
        if isinstance(sprint_field, dict):
            sprint_field = [sprint_field]
        current_sprint_name = sprint_field[-1].get('name', '') if sprint_field else ''

        import_sprint = all_import_data.get(wid)

        if import_sprint is None:
            removed.append((wid, issue_key, current_sprint_name, summary))
        elif import_sprint != current_sprint_name:
            new_sprint_id = sprint_id_map.get(import_sprint)
            sprint_changes.append((wid, issue_key, summary, current_sprint_name, import_sprint, new_sprint_id))

    # Report removed stories
    print(f'\n{"=" * 100}')
    print(f'FUTURE SPRINT ANALYSIS  (sprints starting after {today.strftime("%Y-%m-%d")})')
    print('=' * 100)

    if removed:
        print(f'\nSTORIES NO LONGER IN IMPORT FILE ({len(removed)}):')
        print(f'  {"Work ID":<12} {"JIRA Key":<12} {"Current JIRA Sprint":<35} {"Summary"}')
        print(f'  {"-" * 100}')
        for wid, key, sprint, summary in removed:
            print(f'  {wid:<12} {key:<12} {sprint:<35} {summary[:55]}')
    else:
        print('\nNo stories removed from scope.')

    # Report and apply sprint changes
    if sprint_changes:
        print(f'\nSPRINT ASSIGNMENT CHANGES ({len(sprint_changes)}):')
        print(f'  {"Work ID":<12} {"JIRA Key":<12} {"Current JIRA Sprint":<35} {"Import Sprint":<35} {"Updated?"}')
        print(f'  {"-" * 120}')
        for wid, key, summary, old_sprint, new_sprint, new_sprint_id in sprint_changes:
            if new_sprint_id:
                move_resp = api(creds, 'POST',
                    f'{base_url}/rest/agile/1.0/sprint/{new_sprint_id}/issue',
                    {'issues': [key]})
                updated = 'FAILED: ' + str(move_resp) if move_resp else 'UPDATED'
            else:
                updated = f'SKIP — "{new_sprint}" not found in JIRA'
            print(f'  {wid:<12} {key:<12} {old_sprint:<35} {new_sprint:<35} {updated}')
    else:
        print('\nNo sprint assignment changes needed.')

    print()
    print(f'Future sprints scanned: {len(future_sprints)}  |  '
          f'Removed from scope: {len(removed)}  |  '
          f'Sprint changes: {len(sprint_changes)}')


if __name__ == '__main__':
    main()
