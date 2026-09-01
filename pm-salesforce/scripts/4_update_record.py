#!/usr/bin/env python3
"""Update a Salesforce record. Dry-run by default — pass --apply to actually write.

Usage:
    python3 scripts/4_update_record.py --sobject Account --record-id 001XXXXXXXXXXXXXXX --values "Name=Acme Corp"
        # prints the sf command it would run; makes no change

    python3 scripts/4_update_record.py --sobject Account --where "Name='ClaudeTest'" --values "Industry=Tech" --apply
        # actually updates the matching record(s)

Wraps: sf data update record --sobject {sobject} --record-id {id} --values "{values}" --target-org {alias}
   or: sf data update record --sobject {sobject} --where "{where}" --values "{values}" --target-org {alias}
"""
import argparse
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from sf_helpers import get_alias, require_org


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sobject', required=True, help='sObject API name, e.g. Account')
    parser.add_argument('--record-id', default=None, help='Record ID to update')
    parser.add_argument('--where', default=None, help='WHERE clause to select the record to update, e.g. "Name=\'Acme\'"')
    parser.add_argument('--values', required=True, help='Field values, e.g. "Industry=Tech"')
    parser.add_argument('--alias', default=None, help='sf org alias (default: $SF_ALIAS or "hui")')
    parser.add_argument('--apply', action='store_true', help='Actually update the record (default is dry-run)')
    args = parser.parse_args()

    if not args.record_id and not args.where:
        sys.exit("Provide --record-id or --where to select the record(s) to update")

    alias = get_alias(args.alias)
    cmd = ['sf', 'data', 'update', 'record', '--sobject', args.sobject]
    if args.record_id:
        cmd += ['--record-id', args.record_id]
    else:
        cmd += ['--where', args.where]
    cmd += ['--values', args.values, '--target-org', alias]

    if not args.apply:
        print("DRY RUN — no record will be updated. Command that would run:")
        print(' '.join(f'"{c}"' if ' ' in c else c for c in cmd))
        print("\nRe-run with --apply to execute.")
        return

    require_org(alias)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    print(proc.stdout)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        sys.exit(proc.returncode)


if __name__ == '__main__':
    main()
