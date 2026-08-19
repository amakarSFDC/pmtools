#!/usr/bin/env python3
"""
Create JIRA Stories by Epic Report
--------------------------------------
Queries all JIRA stories, groups them by epic, sorts alphabetically by epic
name, and writes a highlighted XLS report.

Usage:
    python3 7_stories_by_epic.py --project IGSIFP \
        --email "$JIRA_EMAIL" --token "$JIRA_API_TOKEN"

Requirements:
    - JIRA project must use Epic Link (customfield_10014)
"""

import argparse
import os
import json
import subprocess
from collections import defaultdict
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────────────────
base_url_DEFAULT = os.environ.get('JIRA_BASE_URL', 'https://salesforce.atlassian.net')
# ─────────────────────────────────────────────────────────────────────────────


def api(creds, method, url, payload=None):
    args = ['curl', '-s', '-u', creds, '-X', method,
            '-H', 'Content-Type: application/json',
            '-H', 'Accept: application/json']
    if payload:
        args += ['-d', json.dumps(payload)]
    args.append(url)
    r = subprocess.run(args, capture_output=True, text=True)
    return json.loads(r.stdout) if r.stdout.strip() else {}


def write_xls(by_epic, output_path):
    header_style = 'background-color:#4472C4;color:white;font-weight:bold'
    epic_style   = 'background-color:#D9E1F2;font-weight:bold;vnd.ms-excel.numberformat:@'
    plain_style  = 'vnd.ms-excel.numberformat:@'

    html  = '<head><META http-equiv="Content-Type" content="text/html; charset=ISO-8859-1"></head>\n'
    html += '<table border="1">\n'
    html += '<tr>\n'
    for col in ['Epic', 'JIRA Key', 'Summary', 'Status', 'Due Date']:
        html += f'  <th style="{header_style}">{col}</th>\n'
    html += '</tr>\n'

    for epic_name in sorted(by_epic.keys()):
        stories = sorted(by_epic[epic_name], key=lambda x: x['key'])
        html += f'<tr><td colspan="5" style="{epic_style}">{epic_name} ({len(stories)} stories)</td></tr>\n'
        for s in stories:
            html += '<tr>\n'
            html += f'  <td style="{plain_style}">{epic_name}</td>\n'
            html += f'  <td style="{plain_style}">{s["key"]}</td>\n'
            html += f'  <td style="{plain_style}">{s["summary"]}</td>\n'
            html += f'  <td style="{plain_style}">{s["status"]}</td>\n'
            html += f'  <td style="{plain_style}">{s["duedate"]}</td>\n'
            html += '</tr>\n'

    html += '</table>\n'

    with open(output_path, 'w', encoding='iso-8859-1') as f:
        f.write(html)
    print(f'\nReport saved to: {output_path}')


def main():
    parser = argparse.ArgumentParser(description='Generate a JIRA Stories by Epic XLS report.')
    parser.add_argument('--project',  required=True,                          help='JIRA project key (e.g. IGSIFP)')
    parser.add_argument('--email',    required=True,                          help='JIRA email address')
    parser.add_argument('--token',    required=True,                          help='JIRA API token')
    parser.add_argument('--base-url', default=base_url_DEFAULT,          help='JIRA base URL (default: $JIRA_BASE_URL)')
    parser.add_argument('--output',   default='reports/JIRA_Stories_by_Epic.xls', help='Output .xls report path')
    args = parser.parse_args()

    creds = f'{args.email}:{args.token}'
    base_url = args.base_url

    # Fetch all epics
    epic_map   = {}
    next_token = None
    while True:
        payload = {
            'jql':        f'project={args.project} AND issuetype = Epic ORDER BY summary',
            'maxResults': 100,
            'fields':     ['summary', 'status']
        }
        if next_token:
            payload['nextPageToken'] = next_token
        epic_resp = api(creds, 'POST', f'{base_url}/rest/api/3/search/jql', payload)
        batch = epic_resp.get('issues', [])
        if not batch:
            break
        epic_map.update({i['key']: i['fields']['summary'] for i in batch})
        next_token = epic_resp.get('nextPageToken')
        if not next_token:
            break
    print(f'Epics found: {len(epic_map)}')

    # Fetch all non-epic stories with pagination
    issues = []
    next_token = None
    while True:
        payload = {
            'jql':        f'project={args.project} AND issuetype != Epic ORDER BY rank',
            'maxResults': 100,
            'fields':     ['summary', 'status', 'duedate', 'customfield_10014']
        }
        if next_token:
            payload['nextPageToken'] = next_token
        resp  = api(creds, 'POST', f'{base_url}/rest/api/3/search/jql', payload)
        batch = resp.get('issues', [])
        if not batch:
            break
        issues.extend(batch)
        next_token = resp.get('nextPageToken')
        if not next_token:
            break
    print(f'Stories found: {len(issues)}')

    # Group by epic
    by_epic = defaultdict(list)
    for issue in issues:
        f         = issue['fields']
        epic_key  = f.get('customfield_10014') or '(No Epic)'
        epic_name = epic_map.get(epic_key, epic_key) if epic_key != '(No Epic)' else '(No Epic)'
        due_raw   = f.get('duedate') or ''
        due_fmt   = datetime.strptime(due_raw, '%Y-%m-%d').strftime('%m/%d/%Y') if due_raw else ''
        by_epic[epic_name].append({
            'key':     issue['key'],
            'summary': f.get('summary', ''),
            'status':  f['status']['name'],
            'duedate': due_fmt,
        })

    # Print summary
    print()
    print(f'{"Epic":<55} {"Stories"}')
    print('-' * 65)
    for epic_name in sorted(by_epic.keys()):
        print(f'{epic_name[:53]:<55} {len(by_epic[epic_name])}')

    write_xls(by_epic, args.output)
    print(f'Total: {len(issues)} stories across {len(by_epic)} epic groups')


if __name__ == '__main__':
    main()
