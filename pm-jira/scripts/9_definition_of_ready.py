#!/usr/bin/env python3
"""
Definition of Ready Check
--------------------------
Checks all User Stories in the upcoming (next future) sprint against the
Definition of Ready. Tasks and other non-Story issue types are skipped.

Definition of Ready:
  - Story has a title (summary)
  - Story has a description
  - Story has acceptance criteria
  - Story has story points assigned

Usage:
    python3 9_definition_of_ready.py \
        --project IGSIFP \
        --board 18086 \
        --email "$JIRA_EMAIL" \
        --token "$JIRA_API_TOKEN"
"""

import argparse
import json
import os
import subprocess

JIRA_BASE_URL = "https://salesforce.atlassian.net"
FIELD_AC           = 'customfield_10033'
FIELD_STORY_POINTS = 'customfield_10047'


def api(creds, method, url, payload=None):
    args = ['curl', '-s', '-u', creds, '-X', method,
            '-H', 'Content-Type: application/json',
            '-H', 'Accept: application/json']
    if payload:
        args += ['-d', json.dumps(payload)]
    args.append(url)
    r = subprocess.run(args, capture_output=True, text=True)
    return json.loads(r.stdout) if r.stdout.strip() else {}


def has_text(field):
    if not field:
        return False
    if isinstance(field, str):
        return bool(field.strip())
    for block in field.get('content', []):
        for inline in block.get('content', []):
            if inline.get('text', '').strip():
                return True
    return False


def check_dor(issue):
    f          = issue['fields']
    has_title  = bool((f.get('summary') or '').strip())
    has_desc   = has_text(f.get('description'))
    has_ac     = has_text(f.get(FIELD_AC))
    pts        = f.get(FIELD_STORY_POINTS)
    has_pts    = pts is not None and pts > 0
    status     = f.get('status', {}).get('name', '')
    is_ready   = status == 'Ready for Implementation'
    missing    = []
    if not has_title:  missing.append('Title')
    if not has_desc:   missing.append('Description')
    if not has_ac:     missing.append('Acceptance Criteria')
    if not has_pts:    missing.append('Story Points')
    if not is_ready:   missing.append('Status (must be Ready for Implementation, currently "%s")' % status)
    return missing


def main():
    parser = argparse.ArgumentParser(description='Check upcoming sprint User Stories against Definition of Ready.')
    parser.add_argument('--project', required=True,  help='JIRA project key (e.g. IGSIFP)')
    parser.add_argument('--board',   required=True,  help='JIRA board ID')
    parser.add_argument('--email',   required=True,  help='JIRA email address')
    parser.add_argument('--token',   required=True,  help='JIRA API token')
    parser.add_argument('--sprint',        default=None,                        help='Sprint name override (default: next future sprint)')
    parser.add_argument('--slack-channel', default=os.environ.get('SLACK_CHANNEL'), help='Slack channel ID to post results (overrides $SLACK_CHANNEL)')
    args = parser.parse_args()

    creds = f'{args.email}:{args.token}'

    # Find target sprint
    sprint_resp = api(creds, 'GET',
        f'{JIRA_BASE_URL}/rest/agile/1.0/board/{args.board}/sprint?maxResults=50')
    sprints = sprint_resp.get('values', [])

    if args.sprint:
        sprint = next((s for s in sprints if args.sprint in s['name']), None)
    else:
        sprint = next((s for s in sprints if s.get('state') == 'future'), None)

    if not sprint:
        print('ERROR: No upcoming sprint found. Use --sprint to specify one.')
        return

    sprint_name  = sprint['name']
    start        = sprint.get('startDate', '')[:10]
    end          = sprint.get('endDate',   '')[:10]
    print(f'Definition of Ready Check — {sprint_name} ({start} to {end})\n')

    # Fetch sprint issues
    resp = api(creds, 'GET',
        f'{JIRA_BASE_URL}/rest/agile/1.0/sprint/{sprint["id"]}/issue'
        f'?maxResults=100&fields=summary,issuetype,description,{FIELD_AC},{FIELD_STORY_POINTS},status')
    issues = resp.get('issues', [])

    stories = [i for i in issues if i['fields']['issuetype']['name'] == 'Story']
    skipped = [i for i in issues if i['fields']['issuetype']['name'] != 'Story']

    if skipped:
        print(f'Skipping {len(skipped)} non-Story issues: {", ".join(i["key"] for i in skipped)}\n')

    print('%-12s %-6s %-6s %-6s %-6s %-6s  %-10s  %s' % ('Key', 'Title', 'Desc', 'AC', 'Pts', 'RFI', 'DoR', 'Summary'))
    print('-' * 118)

    ready        = []
    not_ready    = []
    total_points = 0.0

    for i in stories:
        key     = i['key']
        summary = i['fields'].get('summary', '')
        missing = check_dor(i)
        dor_met = len(missing) == 0

        f           = i['fields']
        pts         = f.get(FIELD_STORY_POINTS)
        jira_status = f.get('status', {}).get('name', '')
        mark        = lambda b: 'Y' if b else 'N'
        t  = mark(bool((f.get('summary') or '').strip()))
        d  = mark(has_text(f.get('description')))
        a  = mark(has_text(f.get(FIELD_AC)))
        p  = mark(pts is not None and pts > 0)
        rfi = mark(jira_status == 'Ready for Implementation')
        dor = 'READY' if dor_met else 'NOT READY'

        if pts:
            total_points += pts

        print('%-12s %-6s %-6s %-6s %-6s %-6s  %-10s  %s' % (key, t, d, a, p, rfi, dor, summary[:55]))

        if dor_met:
            ready.append(key)
        else:
            not_ready.append((key, summary, missing))

    total_pts_display = int(total_points) if total_points == int(total_points) else total_points
    print()
    print(f'Ready: {len(ready)}  |  Not Ready: {len(not_ready)}  |  Tasks skipped: {len(skipped)}  |  Total Story Points: {total_pts_display}')

    if not_ready:
        print()
        print('MISSING FIELDS:')
        for key, summary, missing in not_ready:
            print('  %-12s missing: %s' % (key, ', '.join(missing)))
            print('               %s' % summary[:75])
    else:
        print()
        print('All User Stories have met the Definition of Ready.')

    if args.slack_channel:
        print()
        print('Slack channel configured: %s' % args.slack_channel)
        print('(Post results to Slack using the Slack MCP tool with the output above.)')
    else:
        print()
        print('No Slack channel configured. Set $SLACK_CHANNEL or pass --slack-channel to enable posting.')


if __name__ == '__main__':
    main()
