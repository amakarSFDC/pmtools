#!/usr/bin/env python3
"""
ICYMI Slack Digest
-------------------
Reads the last N days (default 7) of messages from a fixed list of Slack
channels and writes a single Markdown digest, grouped by channel in
chronological order. Top-level channel messages only — thread replies are
not fetched.

Uses the `claude` CLI's own Slack MCP connection to read channels — no Slack
bot app, token, or admin rights required. It shells out to `claude -p` once
per channel, asking it to resolve the channel name and return the message
history as JSON.

Usage:
    python3 scripts/1_slack_digest.py
    python3 scripts/1_slack_digest.py --days 7 --output data/icymi_2026-09-04.md
    python3 scripts/1_slack_digest.py --channels csg-proservices-all all-salesforce

Requirements:
    - `claude` CLI installed and on $PATH, logged in, with the Slack MCP
      plugin connected (`claude mcp list` should show plugin:slack:slack as
      Connected). No SLACK_BOT_TOKEN or Slack admin rights needed.
"""

import argparse
import json
import os
import re
import subprocess
import time
from datetime import datetime, timedelta

CLAUDE_BIN = os.environ.get('CLAUDE_BIN', 'claude')

ALLOWED_TOOLS = ','.join([
    'mcp__plugin_slack_slack__slack_search_channels',
    'mcp__plugin_slack_slack__slack_read_channel',
    'mcp__plugin_slack_slack__slack_read_user_profile',
    'mcp__plugin_slack_slack__slack_search_users',
])

DEFAULT_CHANNELS = [
    'csg-proservices-amers-tmtcbs-ou',
    'fy27-cbs-delivery-acct-mgmt-team-proserv',
    'all-salesforce',
    'broadcast-the-daily',
    'csg-proservices-all',
    'csg-proservices-go-lives',
    'csg-proservices-amers-recognition',
    'csg-service-alerts',
]

PROMPT_TEMPLATE = '''You have access to Slack MCP tools. Task:
1) Use slack_search_channels to resolve the channel named "{name}" to its channel ID (search both public_channel and private_channel types).
2) If no matching channel is found, respond with exactly {{"found": false}}.
3) If found, use slack_read_channel to fetch top-level messages (not thread replies) in that channel between unix timestamps {oldest_ts} and {latest_ts}, paginating with cursor if needed. Skip system/subtype messages (channel joins/leaves/renames/topic changes).
4) For each message, resolve the author's display name (via user profile if only a user ID is given) and replace newlines in the text with spaces.
Respond with ONLY a single JSON object, no markdown code fences, no commentary before or after, in exactly this shape:
{{"found": true, "channel_id": "...", "messages": [{{"ts": "...", "author": "...", "text": "..."}}]}}
Sort messages chronologically ascending by ts.'''


def fetch_channel(name, oldest_ts, latest_ts, timeout_sec):
    """Shell out to `claude -p` to resolve + read one channel. Returns a dict
    like {'found': bool, 'channel_id': str, 'messages': [...]}."""
    prompt = PROMPT_TEMPLATE.format(name=name, oldest_ts=int(oldest_ts), latest_ts=int(latest_ts))
    try:
        r = subprocess.run(
            [CLAUDE_BIN, '-p', prompt, '--allowedTools', ALLOWED_TOOLS, '--output-format', 'text'],
            capture_output=True, text=True, timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        print(f'  WARN: claude -p timed out reading #{name}')
        return {'found': False}

    raw = r.stdout.strip()
    # Defensive: strip ```json ... ``` fences if the model added them anyway.
    raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip())
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f'  WARN: could not parse claude output for #{name}: {raw[:200]!r}')
        return {'found': False}


def fmt_ts(ts):
    return datetime.fromtimestamp(float(ts)).strftime('%Y-%m-%d %H:%M')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--channels', nargs='+', default=DEFAULT_CHANNELS,
                         help='Channel names (with or without leading #) to read; default is the fixed ICYMI list')
    parser.add_argument('--days', type=int, default=7, help='Number of days back to fetch (default: 7)')
    parser.add_argument('--output', default=None, help='Output Markdown path (default: data/icymi_digest_YYYY-MM-DD.md)')
    parser.add_argument('--today', default=None, help='Override today\'s date (YYYY-MM-DD), for the lookback window and output filename')
    parser.add_argument('--timeout', type=int, default=300, help='Per-channel timeout in seconds for the claude CLI call (default: 300)')
    args = parser.parse_args()

    today = datetime.strptime(args.today, '%Y-%m-%d') if args.today else datetime.today()
    oldest = today - timedelta(days=args.days)
    oldest_ts = time.mktime(oldest.timetuple())
    latest_ts = time.mktime(today.timetuple())

    output = args.output or f'data/icymi_digest_{today.strftime("%Y-%m-%d")}.md'
    os.makedirs(os.path.dirname(output) or '.', exist_ok=True)

    requested = [c.lstrip('#').strip() for c in args.channels]

    sections = []
    missing = []

    for name in requested:
        print(f'Reading #{name}...')
        result = fetch_channel(name, oldest_ts, latest_ts, args.timeout)

        if not result.get('found'):
            print(f'  WARN: channel "#{name}" not found or not readable')
            missing.append(name)
            continue

        messages = result.get('messages', [])
        messages.sort(key=lambda m: float(m.get('ts', 0)))
        print(f'  {len(messages)} message(s) in the last {args.days} day(s)')

        lines = [f'## #{name}', '']
        if not messages:
            lines.append('_No messages this week._')
        else:
            for m in messages:
                text = (m.get('text') or '').replace('\n', ' ').strip()
                lines.append(f'- **{fmt_ts(m["ts"])}** — *{m.get("author", "Unknown")}*: {text}')
        sections.append('\n'.join(lines))

    header = [
        f'# ICYMI Slack Digest',
        f'',
        f'Window: {oldest.strftime("%Y-%m-%d")} – {today.strftime("%Y-%m-%d")} ({args.days} days) · Generated {today.strftime("%Y-%m-%d %H:%M")}',
        f'',
    ]
    if missing:
        header.append(f'**Not fetched (not found or unreadable):** {", ".join("#" + m for m in missing)}')
        header.append('')

    with open(output, 'w', encoding='utf-8') as f:
        f.write('\n'.join(header) + '\n\n' + '\n\n'.join(sections) + '\n')

    print(f'\nDigest saved to: {output}')
    if missing:
        print(f'  {len(missing)} channel(s) skipped — see warnings above.')


if __name__ == '__main__':
    main()
