#!/usr/bin/env python3
"""
Identify Source File Updates
--------------------------------
Compares JIRA status, due date, assignee, story points, and sprint against
the import file for a sprint and flags anything requiring a source system
update. Outputs a highlighted .xls report.

Sprint defaults to the active sprint when --sprint is omitted.

Checks performed:
  1. JIRA Due Date is LATER than import Dev Deadline
  2. JIRA Status is Closed but import shows Development
  3. Import shows User Story Complete but JIRA has progressed beyond Open or Ready for Implementation
     — source system needs updating to reflect current work state
  4. Story exists in JIRA sprint but not in import file (removed from scope)
  5. Story sprint in import differs from JIRA sprint
  6. JIRA assignee differs from import Assigned To (normalized comparison)
  7. JIRA story points differ from import Story Points - Dev

Usage:
    python3 5_identify_source_file_updates.py --file import.xls --project IGSIFP \
        --board 18086 --output report.xls

    # Target a specific sprint:
    python3 5_identify_source_file_updates.py --file import.xls --project IGSIFP \
        --board 18086 --sprint "2026.07c-Comp Systems" --output report.xls

Requirements:
    - import file must be HTML-formatted .xls with standard columns
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
FIELD_STORY_POINTS = 'customfield_10047'
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


def parse_date(s, fmt):
    try:
        return datetime.strptime(s, fmt)
    except Exception:
        return None


def write_xls(rows, output_path, sprint_name):
    header_style  = 'background-color:#4472C4;color:white;font-weight:bold'
    flag_style    = 'background-color:#FFFF00;font-weight:bold;vnd.ms-excel.numberformat:@'
    removed_style = 'background-color:#F4B942;font-weight:bold;vnd.ms-excel.numberformat:@'
    plain_style   = 'vnd.ms-excel.numberformat:@'

    html = '<head><META http-equiv="Content-Type" content="text/html; charset=ISO-8859-1"></head>\n'
    html += '<table border="1">\n'
    html += '<tr>\n'
    for col in ['Work ID', 'JIRA Key', 'Summary', 'JIRA Status', 'Import Status',
                'Import Dev Deadline', 'JIRA Due Date', 'Import Sprint',
                'Import Assignee', 'JIRA Assignee', 'Import Story Points', 'JIRA Story Points',
                'Flag Type', 'Action Required']:
        html += f'  <th style="{header_style}">{col}</th>\n'
    html += '</tr>\n'

    for row in rows:
        wid, key, summary, jira_status, imp_status, imp_dl, jira_due, imp_sprint, imp_assignee, jira_assignee, imp_pts, jira_pts, assignee_flagged, pts_flagged, flag_types, actions = row
        due_flagged     = 'DUE DATE'            in flag_types
        status_flagged  = 'STATUS'              in flag_types
        removed_flagged = 'REMOVED FROM SCOPE'  in flag_types
        sprint_flagged  = 'SPRINT MISMATCH'     in flag_types

        html += '<tr>\n'
        html += f'  <td style="{plain_style}">{wid}</td>\n'
        html += f'  <td style="{plain_style}">{key}</td>\n'
        html += f'  <td style="{plain_style}">{summary}</td>\n'
        html += f'  <td style="{removed_style if removed_flagged else plain_style}">{jira_status}</td>\n'
        html += f'  <td style="{flag_style if status_flagged else (removed_style if removed_flagged else plain_style)}">{imp_status}</td>\n'
        html += f'  <td style="{flag_style if due_flagged else plain_style}">{imp_dl}</td>\n'
        html += f'  <td style="{flag_style if due_flagged else plain_style}">{jira_due}</td>\n'
        html += f'  <td style="{removed_style if sprint_flagged else plain_style}">{imp_sprint}</td>\n'
        html += f'  <td style="{flag_style if assignee_flagged else plain_style}">{imp_assignee}</td>\n'
        html += f'  <td style="{plain_style}">{jira_assignee}</td>\n'
        html += f'  <td style="{flag_style if pts_flagged else plain_style}">{imp_pts}</td>\n'
        html += f'  <td style="{flag_style if pts_flagged else plain_style}">{jira_pts}</td>\n'
        html += f'  <td style="{plain_style}">{", ".join(flag_types)}</td>\n'
        html += f'  <td style="{plain_style}">{"; ".join(actions)}</td>\n'
        html += '</tr>\n'

    html += '</table>\n'

    with open(output_path, 'w', encoding='iso-8859-1') as f:
        f.write(html)
    print(f'\nReport saved to: {output_path}')


def main():
    parser = argparse.ArgumentParser(description='Identify stories needing source system updates.')
    parser.add_argument('--file',     default='data/import.xls',      help='Path to import .xls file')
    parser.add_argument('--project',  required=True,                   help='JIRA project key (e.g. IGSIFP)')
    parser.add_argument('--board',    required=True,                   help='JIRA board ID')
    parser.add_argument('--sprint',   default=None,                    help='Sprint name (without date suffix, e.g. "2026.07c-Comp Systems"); defaults to active sprint')
    parser.add_argument('--email',    required=True,                   help='JIRA email address')
    parser.add_argument('--token',    required=True,                   help='JIRA API token')
    parser.add_argument('--base-url', default=base_url_DEFAULT,  help='JIRA base URL (default: $base_url)')
    parser.add_argument('--output',   default='reports/source_update_report.xls', help='Output .xls report filename')
    parser.add_argument('--today',    default=datetime.today().strftime('%Y-%m-%d'), help='Override today date (YYYY-MM-DD)')
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
            sp_raw = g(row, 'Story Points - Dev')
            try:
                imp_pts = float(sp_raw) if sp_raw else None
            except ValueError:
                imp_pts = None
            import_data[wid] = {
                'status':   g(row, 'Status'),
                'deadline': g(row, 'Dev Deadline'),
                'sprint':   strip_date(g(row, 'Sprint Name')),
                'assignee': g(row, 'Assigned To'),
                'points':   imp_pts,
            }

    # Find sprint ID
    sprint_data = api(creds, 'GET',
        f'{base_url}/rest/agile/1.0/board/{args.board}/sprint?maxResults=200')
    sprint_id   = None
    sprint_name = args.sprint
    for s in sprint_data.get('values', []):
        if sprint_name:
            if s['name'] == sprint_name or sprint_name in s['name']:
                sprint_id   = s['id']
                sprint_name = s['name']
                break
        else:
            if s.get('state') == 'active':
                sprint_id   = s['id']
                sprint_name = s['name']
                break
    if not sprint_id:
        msg = f'Sprint "{args.sprint}"' if args.sprint else 'active sprint'
        print(f'ERROR: No {msg} found on board {args.board}')
        return
    args.sprint = sprint_name

    # Fetch JIRA issues for sprint
    resp = api(creds, 'POST', f'{base_url}/rest/api/3/search/jql', {
        'jql': f'project={args.project} AND sprint={sprint_id} ORDER BY rank',
        'maxResults': 200,
        'fields': ['summary', 'status', 'duedate', 'assignee', FIELD_STORY_POINTS]
    })

    jira_data = {}
    for issue in resp.get('issues', []):
        f       = issue['fields']
        summary = f.get('summary', '')
        wid     = summary[:8]
        a       = f.get('assignee')
        pts     = f.get(FIELD_STORY_POINTS)
        if wid.startswith('W-'):
            jira_data[wid] = {
                'key':      issue['key'],
                'status':   f['status']['name'],
                'duedate':  f.get('duedate') or '',
                'summary':  summary,
                'assignee': a['displayName'] if a else '',
                'points':   pts,
            }

    # Run checks
    report_rows = []
    for wid, jira in sorted(jira_data.items()):
        imp             = import_data.get(wid, {})
        imp_status      = imp.get('status', '')
        imp_dl          = imp.get('deadline', '')
        imp_sprint      = imp.get('sprint', '')
        imp_assignee    = imp.get('assignee', '')
        imp_pts         = imp.get('points')
        jira_status     = jira['status']
        jira_due        = jira['duedate']
        jira_assignee   = jira['assignee']
        jira_pts        = jira['points']
        key             = jira['key']
        summary         = jira['summary']

        def fmt_pts(v):
            if v is None: return ''
            return str(int(v)) if v == int(v) else str(v)

        flag_types = []
        actions    = []

        # Check 1: JIRA due date later than import deadline (skip if story is Closed)
        if imp_dl and jira_due and jira_status != 'Closed':
            imp_date  = parse_date(imp_dl, '%m/%d/%Y')
            jira_date = parse_date(jira_due, '%Y-%m-%d')
            if imp_date and jira_date and jira_date > imp_date:
                flag_types.append('DUE DATE')
                actions.append('Update due date in source system')

        # Check 2: JIRA Closed but import shows an active development status
        if jira_status == 'Closed' and imp_status == 'Development':
            flag_types.append('STATUS')
            actions.append('UPDATE SOURCE SYSTEM')

        # Check 3: Import shows User Story Complete but JIRA has progressed beyond ready-state
        # "User Story Complete" means the story is written and ready for dev — any JIRA status
        # beyond Open or Ready for Implementation means work has started and the import needs updating.
        if imp_status == 'User Story Complete' and jira_status not in ('Open', 'Ready for Implementation'):
            if 'STATUS' not in flag_types:
                flag_types.append('STATUS')
            actions.append(f'JIRA status is "{jira_status}" - update import status to reflect current work state')

        # Check 4: Story exists in JIRA sprint but no longer in import file, and is unresolved
        if wid not in import_data and jira_status != 'Closed':
            flag_types.append('REMOVED FROM SCOPE')
            actions.append('Story not found in import file — confirm if removed from scope')

        # Check 5: Story is in the import file but assigned to a different sprint
        if imp_sprint and imp_sprint != args.sprint and jira_status != 'Closed':
            flag_types.append('SPRINT MISMATCH')
            actions.append(f'Import assigns to "{imp_sprint}" - team may be working ahead of schedule')

        # Check 6: Assignee mismatch between JIRA and import
        # Normalize both sides: lowercase and replace spaces with dots
        # e.g. "Leo Kennedy" → "leo.kennedy", "leo.kennedy" → "leo.kennedy" (already normalized)
        assignee_flagged = False
        if imp_assignee and jira_assignee:
            def norm(s): return s.strip().lower().replace(' ', '.')
            if norm(imp_assignee) != norm(jira_assignee):
                flag_types.append('ASSIGNEE MISMATCH')
                actions.append(f'JIRA assignee "{jira_assignee}" differs from import "{imp_assignee}"')
                assignee_flagged = True

        # Check 7: Story points mismatch between JIRA and import
        pts_flagged = False
        if imp_pts is not None and jira_pts is not None and imp_pts != jira_pts:
            flag_types.append('STORY POINTS MISMATCH')
            actions.append(f'JIRA story points ({fmt_pts(jira_pts)}) differ from import ({fmt_pts(imp_pts)})')
            pts_flagged = True

        if flag_types:
            imp_dl_fmt  = parse_date(imp_dl, '%m/%d/%Y')
            jira_du_fmt = parse_date(jira_due, '%Y-%m-%d')
            report_rows.append((
                wid, key, summary, jira_status, imp_status,
                imp_dl_fmt.strftime('%m/%d/%Y') if imp_dl_fmt else '',
                jira_du_fmt.strftime('%m/%d/%Y') if jira_du_fmt else '',
                imp_sprint, imp_assignee, jira_assignee,
                fmt_pts(imp_pts), fmt_pts(jira_pts),
                assignee_flagged, pts_flagged, flag_types, actions
            ))

    # Print report
    print(f'SOURCE SYSTEM UPDATE REPORT — Sprint: {args.sprint}')
    print(f'Generated: {args.today}')
    print('=' * 110)
    print()

    for wid, key, summary, jira_status, imp_status, imp_dl, jira_due, imp_sprint, imp_assignee, jira_assignee, imp_pts, jira_pts, assignee_flagged, pts_flagged, flag_types, actions in report_rows:
        print(f'Work ID:          {wid}')
        print(f'JIRA Key:         {key}')
        print(f'Summary:          {summary}')
        print(f'JIRA Status:      {jira_status}')
        print(f'Import Status:    {imp_status}')
        if imp_sprint and imp_sprint != args.sprint:
            print(f'Import Sprint:    {imp_sprint}')
        if assignee_flagged:
            print(f'JIRA Assignee:    {jira_assignee}')
            print(f'Import Assignee:  {imp_assignee}')
        if pts_flagged:
            print(f'JIRA Story Pts:   {jira_pts}')
            print(f'Import Story Pts: {imp_pts}')
        for ft, ac in zip(flag_types, actions):
            print(f'  !! [{ft}] {ac}')
        print()

    print(f'Total stories requiring source system update: {len(report_rows)}')
    print(f'  Due date issues:           {sum(1 for r in report_rows if "DUE DATE" in r[14])}')
    print(f'  Status issues:             {sum(1 for r in report_rows if "STATUS" in r[14])}')
    print(f'  Assignee mismatches:       {sum(1 for r in report_rows if "ASSIGNEE MISMATCH" in r[14])}')
    print(f'  Story points mismatches:   {sum(1 for r in report_rows if "STORY POINTS MISMATCH" in r[14])}')
    print(f'  Removed from scope:        {sum(1 for r in report_rows if "REMOVED FROM SCOPE" in r[14])}')
    print(f'  Sprint mismatches:         {sum(1 for r in report_rows if "SPRINT MISMATCH" in r[14])}')

    write_xls(report_rows, args.output, args.sprint)


if __name__ == '__main__':
    main()
