#!/usr/bin/env python3
"""Run a SOQL (or Tooling API) query against Salesforce.

Usage:
    python3 scripts/2_query.py --soql "SELECT Id, Name FROM Account LIMIT 5"
    python3 scripts/2_query.py --file queries/my_query.soql --format csv --output data/accounts.csv
    python3 scripts/2_query.py --soql "SELECT Id FROM ApexClass" --use-tooling-api

Wraps: sf data query --query "..." --target-org {alias} --result-format {format}
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from sf_helpers import get_alias, require_org


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--soql', default=None, help='SOQL query string')
    parser.add_argument('--file', default=None, help='Path to a file containing the SOQL query')
    parser.add_argument('--alias', default=None, help='sf org alias (default: $SF_ALIAS or "hui")')
    parser.add_argument('--format', choices=['human', 'csv', 'json'], default='human',
                         help='Result format passed to `sf data query --result-format`')
    parser.add_argument('--output', default=None, help='Write output to this path instead of stdout')
    parser.add_argument('--use-tooling-api', action='store_true', help='Query Tooling API objects instead of standard/custom objects')
    args = parser.parse_args()

    if not args.soql and not args.file:
        sys.exit("Provide --soql \"SELECT ...\" or --file path/to/query.soql")

    query = args.soql
    if args.file:
        with open(args.file) as f:
            query = f.read().strip()

    alias = get_alias(args.alias)
    require_org(alias)

    result_format = 'human' if args.format == 'human' else args.format
    cmd = ['sf', 'data', 'query', '--query', query, '--target-org', alias, '--result-format', result_format]
    if args.use_tooling_api:
        cmd.append('--use-tooling-api')

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or proc.stdout)
        sys.exit(proc.returncode)

    if args.output:
        os.makedirs(os.path.dirname(args.output), exist_ok=True) if os.path.dirname(args.output) else None
        with open(args.output, 'w') as f:
            f.write(proc.stdout)
        print(f"Wrote query output to {args.output}")
    else:
        print(proc.stdout)


if __name__ == '__main__':
    main()
