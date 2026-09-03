#!/usr/bin/env python3
"""
Compare JIRA to Salesforce Report CSV
--------------------------------------
Compares Work ID and status between a CSV exported by 1_run_report.py
(e.g. reports/PS_Scope_Extract_YYYY-MM-DD.csv) and JIRA, across the whole
project. Mirrors pm-jira's scripts/4_compare_jira_to_file.py --all mode,
adapted for a plain CSV (no Sprint Name column) instead of the HTML .xls
GUS export.

Usage:
    python3 scripts/5_compare_jira_to_csv.py \
        --file reports/PS_Scope_Extract_2026-08-28.csv \
        --project IGSIFP --board 18086 \
        --email "$JIRA_EMAIL" --token "$JIRA_API_TOKEN"

Requirements:
    - CSV must have a "Work: Work ID" column and a "Status" column
      (as produced by 1_run_report.py)

Work IDs with a CSV status of "Go-Live" or "Spillover" are excluded entirely (already
deployed/terminal — not worth reconciling against JIRA).
"""

import argparse
import csv
import json
import os
import subprocess

base_url_DEFAULT = os.environ.get('JIRA_BASE_URL', 'https://salesforce.atlassian.net')


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
    import re
    return re.sub(r'\s+\d+/\d+\s*-\s*\d+/\d+$', '', s).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', required=True, help='Path to CSV produced by 1_run_report.py')
    parser.add_argument('--project', required=True, help='JIRA project key (e.g. IGSIFP)')
    parser.add_argument('--board', required=True, help='JIRA board ID (used to resolve sprint names for display)')
    parser.add_argument('--email', default=os.environ.get('JIRA_EMAIL'), help='JIRA email address')
    parser.add_argument('--token', default=os.environ.get('JIRA_API_TOKEN'), help='JIRA API token')
    parser.add_argument('--base-url', default=base_url_DEFAULT, help='JIRA base URL (default: $JIRA_BASE_URL)')
    args = parser.parse_args()

    if not args.email or not args.token:
        parser.error('--email/--token required (or set $JIRA_EMAIL / $JIRA_API_TOKEN)')

    creds = f'{args.email}:{args.token}'
    base_url = args.base_url

    # Statuses that mean the work is already deployed/terminal — excluded from
    # comparison entirely (not worth reconciling against JIRA).
    SKIP_STATUSES = {'Go-Live', 'Spillover'}

    # Parse CSV
    with open(args.file, newline='', encoding='utf-8') as f:
        reader = list(csv.DictReader(f))

    csv_data = {}
    skipped_wids = set()
    for row in reader:
        wid = (row.get('Work: Work ID') or '').strip()
        if not wid:
            continue
        status = (row.get('Status') or '').strip()
        if status in SKIP_STATUSES:
            skipped_wids.add(wid)
            continue
        csv_data[wid] = {
            'status': status,
            'subject': (row.get('Subject') or '').strip(),
        }

    # Resolve sprint id -> name for display (informational only, CSV has no sprint field)
    sprint_data = api(creds, 'GET',
        f'{base_url}/rest/agile/1.0/board/{args.board}/sprint?maxResults=200')
    sprint_name_map = {s['id']: s['name'] for s in sprint_data.get('values', [])}

    # Fetch all JIRA issues for the project
    jira_all = {}
    next_token = None
    while True:
        payload = {
            'jql': f'project={args.project} AND issuetype != Epic ORDER BY rank',
            'maxResults': 100,
            'fields': ['summary', 'status', 'customfield_10020'],
        }
        if next_token:
            payload['nextPageToken'] = next_token
        resp = api(creds, 'POST', f'{base_url}/rest/api/3/search/jql', payload)
        issues = resp.get('issues', [])
        if not issues:
            break
        for issue in issues:
            f = issue['fields']
            summary = f.get('summary', '')
            wid = summary[:8]
            sprint_field = f.get('customfield_10020') or []
            if isinstance(sprint_field, dict):
                sprint_field = [sprint_field]
            jira_sprint = strip_date(sprint_field[-1].get('name', '')) if sprint_field else '(backlog)'
            jira_all[wid] = (issue['key'], f['status']['name'], jira_sprint)
        next_token = resp.get('nextPageToken')
        if not next_token:
            break

    all_wids = sorted((set(csv_data.keys()) | set(jira_all.keys())) - skipped_wids)

    print(f'{"Work ID":<12} {"Subject":<50} {"CSV Status":<25} {"JIRA Key":<12} {"JIRA Status":<20} {"JIRA Sprint":<30} {"Match?"}')
    print('-' * 175)

    counts = {'match': 0, 'mismatch': 0, 'missing': 0, 'not_in_csv': 0}

    for wid in all_wids:
        csv_row = csv_data.get(wid, {})
        csv_status = csv_row.get('status', '')
        subject = csv_row.get('subject', '')[:48]

        if wid not in jira_all:
            jira_key, jira_status, jira_sprint = 'NOT IN JIRA', 'NOT IN JIRA', ''
        else:
            jira_key, jira_status, jira_sprint = jira_all[wid]
            subject = subject or ''

        if jira_status == 'NOT IN JIRA':
            match = 'MISSING'
            counts['missing'] += 1
        elif not csv_status:
            match = 'NOT IN CSV'
            counts['not_in_csv'] += 1
        elif csv_status == jira_status:
            match = 'YES'
            counts['match'] += 1
        else:
            match = 'NO'
            counts['mismatch'] += 1

        print(f'{wid:<12} {subject:<50} {csv_status:<25} {jira_key:<12} {jira_status:<20} {jira_sprint:<30} {match}')

    print()
    print(f'Total: {len(all_wids)}  |  Match: {counts["match"]}  |  Mismatch: {counts["mismatch"]}  '
          f'|  Missing from JIRA: {counts["missing"]}  |  Not in CSV: {counts["not_in_csv"]}  '
          f'|  Skipped (Go-Live/Spillover): {len(skipped_wids)}')


if __name__ == '__main__':
    main()
