#!/usr/bin/env python3
"""
Generate Weekly Status Summary
-------------------------------
Queries the active JIRA sprint and generates a styled HTML leadership
status report with executive summary, issue register, burn bars,
risk register, and priority actions.

Optionally reads pre-saved Slack channel messages and Google Drive standup
notes to populate a "Team Communications Highlights" section.

Workflow for Slack/Drive integration:
  1. Before running, have Claude read Slack channel C06PHK1DPH7 and save to
     data/slack_notes_YYYY-MM-DD.txt (Claude MCP → file).
  2. Optionally have Claude read Google Drive standup notes folder and save to
     data/standup_notes_YYYY-MM-DD.txt (when Drive network is available).
  3. Pass the saved files to this script via --slack-notes and --drive-notes.

Usage:
    python3 8_weekly_status_report.py \
        --project IGSIFP \
        --board 18086 \
        --email "$JIRA_EMAIL" \
        --token "$JIRA_API_TOKEN" \
        --summary data/executive_summary.txt \
        --slack-notes data/slack_notes_2026-08-13.txt \
        --output reports/IGSIFP_LeadershipStatusReport_2026-08-13.html
"""

import argparse
import json
import os
import subprocess
from collections import defaultdict
from datetime import date, datetime

base_url_DEFAULT = os.environ.get('base_url', 'https://salesforce.atlassian.net')
DRIVE_FOLDER_DEFAULT  = os.environ.get('DRIVE_FOLDER', '')

STATUS_BADGE = {
    'Closed':                  ('badge-green',  'Closed'),
    'In Progress':             ('badge-blue',   'In Progress'),
    'Blocked':                 ('badge-red',    'Blocked'),
    'Open':                    ('badge-grey',   'Open'),
    'Ready for Implementation':('badge-purple', 'Ready'),
    'In Review':               ('badge-blue',   'In Review'),
    'QA In Progress':          ('badge-amber',  'QA In Progress'),
}

RISK_BADGE = {
    'Blocked':    ('badge-red',    'HIGH'),
    'past_due':   ('badge-red',    'HIGH'),
    'on_track':   ('badge-green',  'ON TRACK'),
}

ACCOMPLISHMENT_KEYWORDS = [
    'completed', 'closed', 'delivered', 'shipped', 'done', 'finished',
    'sprint closed', 'sprint complete', 'all stories', 'story points delivered',
    'successfully', 'wrapped up', 'ready for implementation',
]

RISK_KEYWORDS = [
    'risk', 'blocked', 'blocker', 'concern', 'tbd', 'assumption',
    'pending', 'need to confirm', 'before we', 'not complete', 'not ready',
    'waiting', 'need due date', 'need story point', 'need to assign',
    'incomplete', 'unclear', 'unresolved', 'still open',
]

ISSUE_KEYWORDS = [
    'issue', 'problem', 'error', "can't", 'unable', 'missing',
    'broken', 'failed', 'failure', 'outage', 'incident', 'escalation',
    'access', 'permission', 'not working', 'need to re-request',
]


def api(creds, method, url, payload=None):
    args = ['curl', '-s', '-u', creds, '-X', method,
            '-H', 'Content-Type: application/json',
            '-H', 'Accept: application/json']
    if payload:
        args += ['-d', json.dumps(payload)]
    args.append(url)
    r = subprocess.run(args, capture_output=True, text=True)
    return json.loads(r.stdout) if r.stdout.strip() else {}


def business_days_between(start, end):
    count = 0
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            count += 1
        cur = date.fromordinal(cur.toordinal() + 1)
    return count


def fmt_date(iso):
    if not iso:
        return '—'
    try:
        return datetime.strptime(iso[:10], '%Y-%m-%d').strftime('%b %d')
    except ValueError:
        return iso[:10]


def status_badge(status):
    cls, label = STATUS_BADGE.get(status, ('badge-grey', status))
    return f'<span class="badge {cls}">{label}</span>'


def risk_badge(key):
    cls, label = RISK_BADGE.get(key, ('badge-grey', key))
    return f'<span class="badge {cls}">{label}</span>'


def bar(label, pct, color, detail, detail_color=None):
    dc = f'color:{detail_color};font-weight:700' if detail_color else ''
    filled = min(int(pct), 100)
    text = f'{filled}%' if filled >= 15 else ''
    return f'''
      <div class="burn-bar-row">
        <div class="burn-label">{label}</div>
        <div class="burn-bar-bg">
          <div class="burn-bar-fill" style="width:{filled}%;background:{color};">{text}</div>
        </div>
        <div class="burn-detail" style="{dc}">{detail}</div>
      </div>'''


def read_executive_summary(path):
    if not path:
        return '<p style="font-size:14px;line-height:1.9;color:#1a1a2e;">[Executive summary not provided. Pass --summary to include one.]</p>'
    try:
        with open(path, encoding='utf-8') as f:
            raw = f.read()
        paragraphs = [p.strip() for p in raw.split('\n\n') if p.strip()]
        html = ''
        for i, p in enumerate(paragraphs):
            mb = 'margin-bottom:14px;' if i < len(paragraphs) - 1 else ''
            html += f'<p style="font-size:14px;line-height:1.9;color:#1a1a2e;{mb}">{p}</p>\n    '
        return html
    except FileNotFoundError:
        return f'<p style="font-size:14px;color:#c0392b;">[Summary file not found: {path}]</p>'


def read_notes_file(path):
    """Read a timestamped messages file. Returns list of (date_str, author, text) tuples."""
    if not path:
        return []
    try:
        with open(path, encoding='utf-8') as f:
            lines = [l.rstrip() for l in f if l.strip()]
        messages = []
        for line in lines:
            # Format: [YYYY-MM-DD] Author: message text
            if line.startswith('[') and ']' in line:
                bracket_end = line.index(']')
                date_str = line[1:bracket_end]
                rest = line[bracket_end + 2:]  # skip '] '
                if ':' in rest:
                    colon = rest.index(':')
                    author = rest[:colon].strip()
                    text = rest[colon + 1:].strip()
                    messages.append((date_str, author, text))
            elif line:
                messages.append(('', '', line))
        return messages
    except FileNotFoundError:
        print(f'  WARN: Notes file not found: {path}')
        return []


def categorize_messages(messages):
    """Classify messages into accomplishments, risks, and issues by keyword matching."""
    accomplishments = []
    risks = []
    issues = []

    for date_str, author, text in messages:
        lower = text.lower()
        is_accomplishment = any(kw in lower for kw in ACCOMPLISHMENT_KEYWORDS)
        is_risk = any(kw in lower for kw in RISK_KEYWORDS)
        is_issue = any(kw in lower for kw in ISSUE_KEYWORDS)

        entry = (date_str, author, text)
        if is_accomplishment and not is_risk and not is_issue:
            accomplishments.append(entry)
        elif is_risk:
            risks.append(entry)
        elif is_issue:
            issues.append(entry)

    return accomplishments, risks, issues


def build_highlights_html(slack_messages, drive_messages, drive_folder):
    """Build HTML for the Team Communications Highlights section."""
    all_messages = slack_messages + drive_messages
    if not all_messages:
        return ''

    accomplishments, risks, issues = categorize_messages(all_messages)

    sources = []
    if slack_messages:
        sources.append('Slack channel')
    if drive_messages:
        sources.append('Daily standup notes')

    # Google Drive placeholder block (shown when Drive folder is configured but notes unavailable)
    drive_note = ''
    if drive_folder and not drive_messages:
        drive_note = f'''
    <div class="note-box" style="margin-top:14px;margin-bottom:0;">
      <strong>Google Drive Standup Notes</strong>
      Drive folder <code>{drive_folder}</code> configured but not yet read for this report.
      When network is available, have Claude read the folder and save to <code>data/standup_notes_YYYY-MM-DD.txt</code>,
      then rerun with <code>--drive-notes data/standup_notes_YYYY-MM-DD.txt</code>.
    </div>'''

    def fmt_item(date_str, author, text):
        prefix = f'<span style="font-size:11px;color:#888;">{date_str} · {author}:</span> ' if (date_str or author) else ''
        return f'<li>{prefix}{text}</li>\n          '

    accom_html = ''
    if accomplishments:
        items = ''.join(fmt_item(*m) for m in accomplishments[:8])
        accom_html = f'''
    <div style="margin-bottom:16px;">
      <div style="font-size:12px;font-weight:700;color:#1e8449;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.4px;">Key Accomplishments</div>
      <ul class="bullet">{items}</ul>
    </div>'''

    risks_html = ''
    if risks:
        items = ''.join(fmt_item(*m) for m in risks[:8])
        risks_html = f'''
    <div style="margin-bottom:16px;">
      <div style="font-size:12px;font-weight:700;color:#c0392b;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.4px;">Risks &amp; Concerns</div>
      <ul class="bullet">{items}</ul>
    </div>'''

    issues_html = ''
    if issues:
        items = ''.join(fmt_item(*m) for m in issues[:6])
        issues_html = f'''
    <div style="margin-bottom:16px;">
      <div style="font-size:12px;font-weight:700;color:#d35400;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.4px;">Issues &amp; Action Items</div>
      <ul class="bullet">{items}</ul>
    </div>'''

    if not accom_html and not risks_html and not issues_html:
        summary_html = '<p style="font-size:12px;color:#888;">No flagged items identified in team communications this week.</p>'
    else:
        summary_html = accom_html + risks_html + issues_html

    source_label = ' + '.join(sources)
    return f'''
  <div class="section-block">
    <div class="section-title">Team Communications Highlights — {source_label}</div>
    <p style="font-size:12px;color:#555;margin-bottom:14px;">Auto-extracted from {len(all_messages)} messages. Items are keyword-matched; review for accuracy before sharing.</p>
    {summary_html}{drive_note}
  </div>'''


def generate_html(sprint, issues, exec_summary, today, highlights_html='', project='', project_name=''):
    # ── Sprint metadata ────────────────────────────────────────────────────────
    sprint_name  = sprint.get('name', 'Unknown Sprint')
    start_str    = sprint.get('startDate', '')[:10]
    end_str      = sprint.get('endDate',   '')[:10]
    start_dt     = date.fromisoformat(start_str) if start_str else today
    end_dt       = date.fromisoformat(end_str)   if end_str   else today

    total_days   = max(business_days_between(start_dt, end_dt), 1)
    elapsed_days = min(business_days_between(start_dt, today), total_days)
    elapsed_pct  = round(elapsed_days / total_days * 100)

    # ── Story metrics ──────────────────────────────────────────────────────────
    total       = len(issues)
    closed      = [i for i in issues if i['fields']['status']['name'] == 'Closed']
    blocked     = [i for i in issues if i['fields']['status']['name'] == 'Blocked']
    open_issues = [i for i in issues if i['fields']['status']['name'] not in ('Closed',)]
    closed_pct  = round(len(closed) / total * 100) if total else 0
    at_risk     = elapsed_pct - closed_pct > 15

    start_fmt = fmt_date(start_str)
    end_fmt   = fmt_date(end_str)
    today_str = today.strftime('%B %d, %Y')

    # ── Assignee workload ──────────────────────────────────────────────────────
    workload = defaultdict(int)
    for i in open_issues:
        a = i['fields'].get('assignee')
        name = a['displayName'] if a else 'Unassigned'
        workload[name] += 1
    max_load = max(workload.values(), default=1)

    # ── Past-due open stories ──────────────────────────────────────────────────
    past_due = []
    for i in open_issues:
        dd = (i['fields'].get('duedate') or '')[:10]
        if dd and date.fromisoformat(dd) < today:
            past_due.append(i)

    # ── Row style helper ──────────────────────────────────────────────────────
    def row_class(issue):
        s = issue['fields']['status']['name']
        dd = (issue['fields'].get('duedate') or '')[:10]
        if s == 'Blocked':
            return ' class="blocked-row"'
        if s == 'Closed':
            return ' style="background:#f0faf4;"'
        if dd and date.fromisoformat(dd) < today:
            return ' class="late-row"'
        return ''

    # ── CSS ───────────────────────────────────────────────────────────────────
    css = '''
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f0f2f5; color: #1a1a2e; font-size: 14px; }
  .header { background: linear-gradient(135deg, #0d1b2a 0%, #1b263b 60%, #415a77 100%); color: #fff; padding: 32px 40px 28px; }
  .header h1 { font-size: 22px; font-weight: 700; letter-spacing: 0.3px; }
  .header .meta { margin-top: 8px; font-size: 12px; color: #a8c0d6; display: flex; gap: 32px; flex-wrap: wrap; }
  .critical-banner { background: #c0392b; color: #fff; padding: 14px 40px; font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 12px; }
  .content { padding: 28px 40px; max-width: 1280px; margin: 0 auto; }
  .section-title { font-size: 15px; font-weight: 700; color: #0d1b2a; margin-bottom: 14px; padding-bottom: 6px; border-bottom: 2px solid #415a77; text-transform: uppercase; letter-spacing: 0.5px; }
  .card-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 28px; }
  .card { background: #fff; border-radius: 8px; padding: 18px 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); border-left: 4px solid #ccc; }
  .card.red    { border-left-color: #c0392b; }
  .card.orange { border-left-color: #e67e22; }
  .card.amber  { border-left-color: #f39c12; }
  .card.green  { border-left-color: #27ae60; }
  .card .label { font-size: 11px; color: #666; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
  .card .value { font-size: 26px; font-weight: 800; color: #0d1b2a; }
  .card .sub   { font-size: 11px; color: #888; margin-top: 4px; }
  .section-block { background: #fff; border-radius: 8px; padding: 22px 24px; margin-bottom: 24px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { background: #1b263b; color: #fff; padding: 10px 12px; text-align: left; font-weight: 600; font-size: 12px; letter-spacing: 0.3px; }
  td { padding: 9px 12px; border-bottom: 1px solid #eef0f3; vertical-align: top; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #f8fafc; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.3px; }
  .badge-red    { background: #fce8e6; color: #c0392b; }
  .badge-orange { background: #fef3e2; color: #d35400; }
  .badge-amber  { background: #fefae0; color: #b7770d; }
  .badge-green  { background: #e8f8f0; color: #1e8449; }
  .badge-blue   { background: #e8f0fe; color: #1a5276; }
  .badge-grey   { background: #f0f0f0; color: #555; }
  .badge-purple { background: #f3e8ff; color: #6b21a8; }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px; }
  .burn-bar-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
  .burn-label   { width: 160px; font-size: 12px; font-weight: 600; flex-shrink: 0; }
  .burn-bar-bg  { flex: 1; background: #eef0f3; border-radius: 4px; height: 22px; overflow: hidden; }
  .burn-bar-fill { height: 22px; border-radius: 4px; display: flex; align-items: center; padding-left: 10px; font-size: 11px; font-weight: 700; color: #fff; white-space: nowrap; }
  .burn-detail  { width: 100px; font-size: 12px; color: #555; text-align: right; flex-shrink: 0; }
  .note-box { background: #fef9e7; border-left: 4px solid #f39c12; padding: 12px 16px; border-radius: 0 6px 6px 0; font-size: 12px; margin-top: 14px; line-height: 1.6; }
  .note-box strong { display: block; margin-bottom: 4px; color: #b7770d; }
  .footer { background: #1b263b; color: #7f9ab5; font-size: 11px; padding: 16px 40px; margin-top: 8px; display: flex; justify-content: space-between; }
  .late-row td { background: #fff8f8; }
  .blocked-row td { background: #fff8f0; }
  ul.bullet { margin: 8px 0 0 16px; }
  ul.bullet li { font-size: 12px; color: #444; line-height: 1.7; }
  @media (max-width: 900px) { .card-grid { grid-template-columns: repeat(2,1fr); } .two-col { grid-template-columns: 1fr; } }
'''

    # ── Issue register rows ───────────────────────────────────────────────────
    def issue_row(i):
        f       = i['fields']
        key     = i['key']
        summary = f.get('summary', '')
        status  = f['status']['name']
        a       = f.get('assignee')
        assignee= a['displayName'] if a else '—'
        dd      = fmt_date(f.get('duedate', ''))
        risk_key= 'Blocked' if status == 'Blocked' else ('past_due' if i in past_due else 'on_track')
        rc      = row_class(i)
        return f'''        <tr{rc}>
          <td><strong>{key}</strong></td>
          <td>{summary}</td>
          <td>{assignee}</td>
          <td>{dd}</td>
          <td>{status_badge(status)}</td>
          <td>{risk_badge(risk_key)}</td>
        </tr>'''

    issue_rows = '\n'.join(issue_row(i) for i in issues)

    # ── Burn bars ─────────────────────────────────────────────────────────────
    burn_color   = '#e67e22' if at_risk else '#27ae60'
    burn_bars    = bar('Time Elapsed',    elapsed_pct, '#415a77', f'Day {elapsed_days} of {total_days}')
    burn_bars   += bar('Stories Closed',  closed_pct,  burn_color, f'{len(closed)} of {total}',
                       '#e67e22' if at_risk else '#27ae60')
    expected_pct = elapsed_pct
    burn_bars   += bar('Expected at Pace', expected_pct, '#27ae60', f'~{round(expected_pct/100*total)} of {total}',
                       '#27ae60')
    if blocked:
        block_pct = round(len(blocked) / total * 100)
        burn_bars += bar('Blocked', block_pct, '#c0392b', f'{len(blocked)} of {total}', '#c0392b')

    # ── Workload bars ─────────────────────────────────────────────────────────
    workload_bars = ''
    for name, count in sorted(workload.items(), key=lambda x: -x[1]):
        pct   = round(count / max_load * 100)
        color = '#c0392b' if count >= 4 else '#415a77' if count >= 2 else '#27ae60'
        workload_bars += bar(name[:22], pct, color, f'{count} open')

    # ── Accomplishments list ──────────────────────────────────────────────────
    accom_items = ''
    for i in sorted(closed, key=lambda x: x['key']):
        f = i['fields']
        a = f.get('assignee')
        assignee = a['displayName'] if a else '—'
        accom_items += f'<li><strong>{i["key"]}</strong> — {f.get("summary","")} <em style="color:#888;font-size:11px;">({assignee})</em></li>\n          '

    # ── Risk rows ─────────────────────────────────────────────────────────────
    risk_rows = ''
    rn = 1
    for i in blocked:
        f       = i['fields']
        a       = f.get('assignee')
        owner   = a['displayName'] if a else '—'
        risk_rows += f'''        <tr>
          <td style="font-weight:700">{rn}</td>
          <td><span class="badge badge-red">HIGH</span></td>
          <td><strong>{i["key"]} — {f.get("summary","")}</strong><br>
              <span style="font-size:11px;color:#555;">Status: Blocked. Review blocker details in JIRA and confirm resolution timeline.</span></td>
          <td>{i["key"]}</td>
          <td>{owner}</td>
          <td style="font-size:12px">Confirm blocker owner and resolution date. If unresolved by sprint end, move to next sprint and communicate to stakeholders.</td>
        </tr>'''
        rn += 1
    for i in past_due:
        if i in blocked:
            continue
        f       = i['fields']
        a       = f.get('assignee')
        owner   = a['displayName'] if a else '—'
        dd      = fmt_date(f.get('duedate', ''))
        risk_rows += f'''        <tr>
          <td style="font-weight:700">{rn}</td>
          <td><span class="badge badge-amber">MEDIUM</span></td>
          <td><strong>{i["key"]} — {f.get("summary","")}</strong><br>
              <span style="font-size:11px;color:#555;">Due date {dd} has passed and story is not yet Closed.</span></td>
          <td>{i["key"]}</td>
          <td>{owner}</td>
          <td style="font-size:12px">Review status with assignee. Confirm expected close date or move to next sprint.</td>
        </tr>'''
        rn += 1
    if not risk_rows:
        risk_rows = '<tr><td colspan="6" style="color:#888;text-align:center;padding:16px;">No active risks identified.</td></tr>'

    # ── Critical banner ───────────────────────────────────────────────────────
    banner = ''
    if at_risk:
        gap = elapsed_pct - closed_pct
        banner = f'''<div class="critical-banner">
  <span style="font-size:18px;">⚠️</span>
  SPRINT AT RISK: Day {elapsed_days} of {total_days} ({elapsed_pct}% elapsed) — only {closed_pct}% of stories closed ({len(closed)} of {total}). Velocity is {gap} points behind expected pace.
</div>'''

    # ── HTML assembly ─────────────────────────────────────────────────────────
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{project} {sprint_name} — Leadership Status Report</title>
<style>{css}</style>
</head>
<body>

<div class="header">
  <h1>{project} — {sprint_name} Leadership Status Report</h1>
  <div class="meta">
    <span>📋 Project: {project_name if project_name else project}</span>
    <span>📅 Report Date: {today_str}</span>
    <span>🗓 Sprint: {sprint_name} &nbsp;|&nbsp; {start_fmt} – {end_fmt}</span>
  </div>
</div>

{banner}

<div class="content">
  <div class="card-grid" style="margin-top:4px;">
    <div class="card {'red' if at_risk else 'green'}">
      <div class="label">Sprint Progress</div>
      <div class="value">{closed_pct}%</div>
      <div class="sub">{len(closed)} closed of {total} · Day {elapsed_days} of {total_days} ({elapsed_pct}% elapsed)</div>
    </div>
    <div class="card {'red' if blocked else 'green'}">
      <div class="label">Blocked Stories</div>
      <div class="value">{len(blocked)}</div>
      <div class="sub">{'· '.join(i["key"] for i in blocked) if blocked else 'No blocked stories'}</div>
    </div>
    <div class="card {'orange' if len(open_issues)-len(blocked) > 3 else 'amber'}">
      <div class="label">Open / In Progress</div>
      <div class="value">{len(open_issues)}</div>
      <div class="sub">{len(open_issues) - len(blocked)} active · {len(blocked)} blocked</div>
    </div>
    <div class="card green">
      <div class="label">Closed This Sprint</div>
      <div class="value">{len(closed)}</div>
      <div class="sub">of {total} committed stories</div>
    </div>
  </div>

  <div class="section-block">
    <div class="section-title">Executive Summary</div>
    {exec_summary}
  </div>

  <div class="section-block">
    <div class="section-title">Accomplishments — Closed Stories</div>
    <ul class="bullet">
      {accom_items if accom_items else '<li style="color:#888;">No stories closed yet this sprint.</li>'}
    </ul>
  </div>

{highlights_html}

  <div class="section-block">
    <div class="section-title">Sprint Issue Register</div>
    <table>
      <thead>
        <tr>
          <th style="width:100px">Key</th>
          <th>Summary</th>
          <th style="width:150px">Assignee</th>
          <th style="width:80px">Due Date</th>
          <th style="width:130px">Status</th>
          <th style="width:100px">Risk</th>
        </tr>
      </thead>
      <tbody>
{issue_rows}
      </tbody>
    </table>
  </div>

  <div class="two-col">
    <div class="section-block" style="margin-bottom:0">
      <div class="section-title">Sprint Burn — Day {elapsed_days} of {total_days}</div>
      <p style="font-size:12px;color:#555;margin-bottom:16px;">Sprint: {start_fmt} – {end_fmt} · {total_days} business days total.</p>
      {burn_bars}
    </div>
    <div class="section-block" style="margin-bottom:0">
      <div class="section-title">Team Workload — Open Stories by Assignee</div>
      <p style="font-size:12px;color:#555;margin-bottom:16px;">Open = not yet Closed.</p>
      {workload_bars if workload_bars else '<p style="font-size:12px;color:#888;">All stories closed.</p>'}
    </div>
  </div>

  <div class="section-block">
    <div class="section-title">Risk Register</div>
    <table>
      <thead>
        <tr>
          <th style="width:40px">#</th>
          <th style="width:100px">Severity</th>
          <th>Risk</th>
          <th style="width:120px">Affected</th>
          <th style="width:140px">Owner</th>
          <th>Mitigation</th>
        </tr>
      </thead>
      <tbody>
{risk_rows}
      </tbody>
    </table>
  </div>

</div>

<div class="footer">
  <span>{project} Leadership Status Report · Generated {today_str} · Source: Jira Board</span>
  <span>{sprint_name} · {start_fmt} – {end_fmt}</span>
</div>

</body>
</html>'''
    return html


def main():
    parser = argparse.ArgumentParser(description='Generate weekly leadership status report.')
    parser.add_argument('--project',      required=True,  help='JIRA project key (e.g. IGSIFP)')
    parser.add_argument('--project-name', default=None,   help='Full project name for report header (default: project key)')
    parser.add_argument('--board',        required=True,  help='JIRA board ID')
    parser.add_argument('--email',        required=True,  help='JIRA email address')
    parser.add_argument('--token',        required=True,  help='JIRA API token')
    parser.add_argument('--base-url',     default=base_url_DEFAULT, help='JIRA base URL (default: $base_url)')
    parser.add_argument('--summary',      default=None,   help='Path to plain-text executive summary file')
    parser.add_argument('--slack-notes',  default=None,
                        help='Path to pre-saved Slack messages file (e.g. data/slack_notes_YYYY-MM-DD.txt)')
    parser.add_argument('--drive-notes',  default=None,
                        help='Path to pre-saved Google Drive standup notes file (e.g. data/standup_notes_YYYY-MM-DD.txt)')
    parser.add_argument('--drive-folder', default=DRIVE_FOLDER_DEFAULT,
                        help='Google Drive folder ID for standup notes (default: $DRIVE_FOLDER)')
    parser.add_argument('--output',       default=None,   help='Output HTML path (default: reports/{PROJECT}_LeadershipStatusReport_YYYY-MM-DD.html)')
    parser.add_argument('--today',        default=None,   help='Override today\'s date (YYYY-MM-DD)')
    args = parser.parse_args()

    today = date.fromisoformat(args.today) if args.today else date.today()
    creds = f'{args.email}:{args.token}'
    base_url = args.base_url

    output = args.output or f'reports/{args.project}_LeadershipStatusReport_{today}.html'

    # Fetch active sprint
    print('Fetching active sprint...')
    sprint_resp = api(creds, 'GET',
        f'{base_url}/rest/agile/1.0/board/{args.board}/sprint?state=active')
    sprints = sprint_resp.get('values', [])
    if not sprints:
        print('ERROR: No active sprint found on board', args.board)
        return
    sprint = sprints[0]
    print(f'  Active sprint: {sprint["name"]}')

    # Fetch all issues in the sprint
    print('Fetching sprint issues...')
    issues = []
    start_at = 0
    while True:
        resp = api(creds, 'GET',
            f'{base_url}/rest/agile/1.0/sprint/{sprint["id"]}/issue'
            f'?startAt={start_at}&maxResults=100'
            f'&fields=summary,status,duedate,assignee,customfield_10014,priority,labels,issuetype')
        batch = resp.get('issues', [])
        if not batch:
            break
        issues.extend(batch)
        start_at += len(batch)
        if start_at >= resp.get('total', 0):
            break
    print(f'  Issues found: {len(issues)}')
    issues = [i for i in issues if i['fields']['issuetype']['name'] in ('Story', 'Bug')]
    print(f'  Stories + Bugs: {len(issues)} (Tasks and Sub-tasks excluded)')

    # Read Slack and Drive notes files
    slack_messages = []
    drive_messages = []

    if args.slack_notes:
        print(f'Reading Slack notes: {args.slack_notes}')
        slack_messages = read_notes_file(args.slack_notes)
        print(f'  {len(slack_messages)} Slack messages loaded')
    else:
        # Auto-detect: look for data/slack_notes_YYYY-MM-DD.txt matching today
        auto_slack = f'data/slack_notes_{today}.txt'
        if os.path.exists(auto_slack):
            print(f'Auto-detected Slack notes: {auto_slack}')
            slack_messages = read_notes_file(auto_slack)
            print(f'  {len(slack_messages)} Slack messages loaded')

    if args.drive_notes:
        print(f'Reading Drive standup notes: {args.drive_notes}')
        drive_messages = read_notes_file(args.drive_notes)
        print(f'  {len(drive_messages)} standup notes loaded')
    else:
        # Auto-detect: look for data/standup_notes_YYYY-MM-DD.txt matching today
        auto_drive = f'data/standup_notes_{today}.txt'
        if os.path.exists(auto_drive):
            print(f'Auto-detected Drive notes: {auto_drive}')
            drive_messages = read_notes_file(auto_drive)
            print(f'  {len(drive_messages)} standup notes loaded')
        elif args.drive_folder:
            print(f'  Drive folder configured ({args.drive_folder}) but no notes file found.')
            print(f'  To include Drive data: have Claude read the folder and save to data/standup_notes_{today}.txt')

    highlights_html = build_highlights_html(slack_messages, drive_messages, args.drive_folder)

    exec_summary = read_executive_summary(args.summary)
    html = generate_html(sprint, issues, exec_summary, today, highlights_html,
                         project=args.project, project_name=args.project_name or '')

    with open(output, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'\nReport saved to: {output}')


if __name__ == '__main__':
    main()
