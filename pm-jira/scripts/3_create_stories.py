#!/usr/bin/env python3
"""
Create Stories from Data File
--------------------------------
Compares Work IDs in an import file vs JIRA story summaries and creates
missing stories matching specified filters (status, sprint).

Usage:
    python3 3_create_stories.py --file import.xls --project IGSIFP --board 18086 \
        --status "User Story Complete" --future-only

Requirements:
    - import file must be HTML-formatted .xls with standard columns
    - Assignees are looked up by name; unknown assignees fall back to default
"""

import argparse
import os
import re
import json
import subprocess
from datetime import datetime
from html.parser import HTMLParser

# ── Config ──────────────────────────────────────────────────────────────────
base_url_DEFAULT     = os.environ.get('JIRA_BASE_URL', 'https://salesforce.atlassian.net')
DEFAULT_ASSIGNEE_FALLBACK = os.environ.get('JIRA_DEFAULT_ASSIGNEE', '')
FIELD_ACCEPTANCE          = 'customfield_10033'
FIELD_STORY_POINTS        = 'customfield_10047'
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


def make_doc(text):
    return {"type": "doc", "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


def strip_date(s):
    return re.sub(r'\s+\d+/\d+\s*-\s*\d+/\d+$', '', s).strip()


def parse_due_date(val):
    if not val:
        return None
    for fmt in ('%m/%d/%Y', '%m/%d/%y'):
        try:
            return datetime.strptime(val, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return None


def get_sprint_start_date(raw_name):
    year_m = re.match(r'(\d{4})\.', raw_name)
    base_year = int(year_m.group(1)) if year_m else datetime.today().year
    m = re.search(r'(\d+)/(\d+)\s*-\s*\d+/\d+$', raw_name)
    if not m:
        return None
    return datetime(base_year, int(m.group(1)), int(m.group(2)))


def norm_username(display_name):
    """Normalize 'First Last' → 'first.last' to match JIRA username format."""
    return display_name.strip().lower().replace(' ', '.')


def lookup_user(creds, display_name, base_url=None):
    if base_url is None:
        base_url = base_url_DEFAULT
    # Search by full display name first
    query = display_name.replace(' ', '%20')
    data = api(creds, 'GET', f'{base_url}/rest/api/3/user/search?query={query}')
    if isinstance(data, list):
        norm = norm_username(display_name)
        # Prefer exact display name match, then normalized username match
        for u in data:
            if u.get('displayName', '').lower() == display_name.lower():
                return u['accountId']
        for u in data:
            if norm_username(u.get('displayName', '')) == norm or \
               u.get('name', '').lower() == norm or \
               u.get('emailAddress', '').lower().split('@')[0] == norm:
                return u['accountId']
        if data:
            return data[0]['accountId']
    # Fallback: search by normalized username
    norm = norm_username(display_name)
    data2 = api(creds, 'GET', f'{base_url}/rest/api/3/user/search?query={norm}')
    if isinstance(data2, list) and data2:
        return data2[0]['accountId']
    return None


def main():
    parser = argparse.ArgumentParser(description='Create missing JIRA stories from import file.')
    parser.add_argument('--file',              default='data/import.xls',  help='Path to import .xls file')
    parser.add_argument('--project',           required=True,               help='JIRA project key (e.g. IGSIFP)')
    parser.add_argument('--board',             required=True,               help='JIRA board ID')
    parser.add_argument('--email',             required=True,               help='JIRA email address')
    parser.add_argument('--token',             required=True,               help='JIRA API token')
    parser.add_argument('--base-url',          default=base_url_DEFAULT, help='JIRA base URL (default: $JIRA_BASE_URL)')
    parser.add_argument('--default-assignee',  default=DEFAULT_ASSIGNEE_FALLBACK, help='JIRA account ID to assign when lookup fails (default: $JIRA_DEFAULT_ASSIGNEE)')
    parser.add_argument('--status',            default='User Story Complete', help='Filter: only create stories with this import status')
    parser.add_argument('--future-only',       action='store_true',         help='Only create stories in future-dated sprints')
    parser.add_argument('--today',             default=datetime.today().strftime('%Y-%m-%d'), help='Override today date (YYYY-MM-DD)')
    args = parser.parse_args()

    creds = f'{args.email}:{args.token}'
    base_url = args.base_url
    DEFAULT_ASSIGNEE = args.default_assignee
    today = datetime.strptime(args.today, '%Y-%m-%d')

    # Parse import file
    with open(args.file, 'r', encoding='iso-8859-1') as f:
        content = f.read()
    p = TableParser()
    p.feed(content)
    idx = {col: p.headers.index(col) for col in p.headers}

    def g(row, col):
        i = idx.get(col, -1)
        return row[i].strip() if i >= 0 and i < len(row) else ''

    # Fetch existing JIRA issues (work IDs from first 8 chars of summary) — paginated
    jira_work_ids = set()
    next_token = None
    while True:
        payload = {'jql': f'project={args.project} ORDER BY rank', 'maxResults': 100, 'fields': ['summary']}
        if next_token:
            payload['nextPageToken'] = next_token
        resp = api(creds, 'POST', f'{base_url}/rest/api/3/search/jql', payload)
        batch = resp.get('issues', [])
        if not batch:
            break
        jira_work_ids.update(i['fields']['summary'][:8] for i in batch)
        next_token = resp.get('nextPageToken')
        if not next_token:
            break

    # Fetch all sprints for board
    sprint_data = api(creds, 'GET',
        f'{base_url}/rest/agile/1.0/board/{args.board}/sprint?maxResults=200')
    sprint_map    = {s['name']: s['id']    for s in sprint_data.get('values', [])}
    active_sprint_ids = {s['id'] for s in sprint_data.get('values', []) if s.get('state') == 'active'}

    # Cache assignee lookups
    assignee_cache = {}

    created, failed, skipped = [], [], []

    for row in p.rows:
        wid        = g(row, 'Work: Work ID')
        imp_status = g(row, 'Status')
        sprint_raw = g(row, 'Sprint Name')
        sprint     = strip_date(sprint_raw)

        if not wid:
            continue
        if args.status and imp_status != args.status:
            continue
        if args.future_only:
            start = get_sprint_start_date(sprint_raw)
            if not start or start <= today:
                skipped.append(wid)
                continue
        if wid in jira_work_ids:
            skipped.append(wid)
            continue

        sprint_id = sprint_map.get(sprint)
        if not sprint_id:
            print(f'  SKIP {wid} — sprint not found in JIRA: {sprint}')
            skipped.append(wid)
            continue

        # Resolve assignee
        assignee_name = g(row, 'Assigned To')
        if assignee_name not in assignee_cache:
            account_id = lookup_user(creds, assignee_name, base_url)
            # Verify the resolved account can actually be assigned; fall back if not
            if account_id and account_id != DEFAULT_ASSIGNEE:
                test = api(creds, 'GET',
                    f'{base_url}/rest/api/3/user/assignable/search'
                    f'?project={args.project}&accountId={account_id}')
                if not (isinstance(test, list) and test):
                    account_id = None
            assignee_cache[assignee_name] = account_id or DEFAULT_ASSIGNEE or None
            if not account_id:
                default_label = f'$JIRA_DEFAULT_ASSIGNEE ({DEFAULT_ASSIGNEE})' if DEFAULT_ASSIGNEE else 'none (story will be unassigned)'
                print(f'  WARN  Assignee "{assignee_name}" not found or not assignable, defaulting to {default_label}')
        assignee_id = assignee_cache[assignee_name]

        summary       = g(row, 'Subject')
        biz_desc      = g(row, 'Business Description')
        ac            = g(row, 'Product Acceptance Criteria')
        product_owner = g(row, 'Product Owner')
        due_raw       = g(row, 'Dev Deadline')
        sp_raw        = g(row, 'Story Points - Dev')

        description = biz_desc
        if product_owner:
            description += f'\n\nProduct Owner: {product_owner}'

        due_date = parse_due_date(due_raw)
        try:
            story_points = float(sp_raw) if sp_raw else None
        except ValueError:
            story_points = None

        fields = {
            'project':   {'key': args.project},
            'issuetype': {'name': 'Story'},
            'summary':   summary,
            'description': make_doc(description),
        }
        if assignee_id:
            fields['assignee'] = {'accountId': assignee_id}
        if ac:            fields[FIELD_ACCEPTANCE]   = make_doc(ac)
        if due_date:      fields['duedate']           = due_date
        if story_points:  fields[FIELD_STORY_POINTS]  = story_points

        # If the target sprint is active, send to backlog with label instead
        active_scope = sprint_id in active_sprint_ids
        if active_scope:
            fields['labels'] = ['New_Scope_to_Active_Sprint']

        create_resp = api(creds, 'POST', f'{base_url}/rest/api/3/issue', {'fields': fields})

        if 'key' not in create_resp:
            print(f'  FAILED  {wid}: {create_resp.get("errors", create_resp.get("errorMessages", create_resp))}')
            failed.append(wid)
            continue

        issue_key = create_resp['key']

        if active_scope:
            print(f'  CREATED {issue_key} | {wid} | BACKLOG (active sprint — labeled "New Scope to Active Sprint")')
        else:
            # Move to sprint
            sprint_resp = api(creds, 'POST',
                f'{base_url}/rest/agile/1.0/sprint/{sprint_id}/issue',
                {'issues': [issue_key]})
            if sprint_resp:
                print(f'  WARN  Sprint move {issue_key}: {sprint_resp}')
            print(f'  CREATED {issue_key} | {wid} | {sprint}')

        created.append(issue_key)

    print()
    print(f'Created: {len(created)}  |  Failed: {len(failed)}  |  Skipped: {len(skipped)}')


if __name__ == '__main__':
    main()
