#!/usr/bin/env python3
"""Fetch a Salesforce report by ID and flatten it into rows.

Usage:
    python3 scripts/1_run_report.py
    python3 scripts/1_run_report.py --report-id 00OUc00000BBDmnMAH --format csv
    python3 scripts/1_run_report.py --format json --output reports/my_report.json

Calls the Analytics Reports REST API via the `sf` CLI:
    sf api request rest "/services/data/{version}/analytics/reports/{id}?includeDetails=true" \
        --target-org {alias}

and flattens the resulting factMap/reportMetadata structure into one row per
detail record, using reportMetadata.detailColumns for column order/labels.
"""
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from sf_helpers import get_alias, get_api_version, require_org, sf_json

DEFAULT_REPORT_ID = '00OUc00000BBDmnMAH'


def fetch_report(alias, api_version, report_id):
    path = f"/services/data/{api_version}/analytics/reports/{report_id}?includeDetails=true"
    result = sf_json(['api', 'request', 'rest', path, '--target-org', alias])
    # `sf api request rest` wraps the HTTP response as {statusCode, headers, body}.
    return result['body']


def column_labels(report):
    """Map detail column API names -> display labels, from reportExtendedMetadata."""
    detail_columns = report['reportMetadata']['detailColumns']
    label_info = report.get('reportExtendedMetadata', {}).get('detailColumnInfo', {})
    labels = []
    for col in detail_columns:
        info = label_info.get(col, {})
        labels.append(info.get('label', col))
    return detail_columns, labels


def flatten_rows(report):
    """Flatten factMap dataRows into a list of row dicts keyed by column API name."""
    detail_columns, labels = column_labels(report)
    rows = []
    fact_map = report.get('factMap', {})
    for key, block in fact_map.items():
        for data_row in block.get('rows', []):
            cells = data_row.get('dataCells', [])
            row = {}
            for col, cell in zip(detail_columns, cells):
                row[col] = cell.get('label', cell.get('value', ''))
            if row:
                rows.append(row)
    return detail_columns, labels, rows


def print_human(detail_columns, labels, rows):
    if not rows:
        print("No detail rows returned.")
        return
    widths = [max(len(labels[i]), max((len(str(r.get(c, ''))) for r in rows), default=0))
              for i, c in enumerate(detail_columns)]
    header = '  '.join(label.ljust(widths[i]) for i, label in enumerate(labels))
    print(header)
    print('-' * len(header))
    for row in rows:
        print('  '.join(str(row.get(c, '')).ljust(widths[i]) for i, c in enumerate(detail_columns)))
    print(f"\n{len(rows)} row(s)")


def write_csv(path, detail_columns, labels, rows):
    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(labels)
        for row in rows:
            writer.writerow([row.get(c, '') for c in detail_columns])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-id', default=DEFAULT_REPORT_ID, help='Salesforce report ID (default: %(default)s)')
    parser.add_argument('--alias', default=None, help='sf org alias (default: $SF_ALIAS or "hui")')
    parser.add_argument('--api-version', default=None, help='API version (default: $SF_REPORT_API_VERSION or v64.0)')
    parser.add_argument('--format', choices=['human', 'csv', 'json'], default='human')
    parser.add_argument('--output', default=None, help='Write output to this path instead of stdout (csv/json only)')
    args = parser.parse_args()

    alias = get_alias(args.alias)
    api_version = get_api_version(args.api_version)
    require_org(alias)

    report = fetch_report(alias, api_version, args.report_id)
    detail_columns, labels, rows = flatten_rows(report)

    if args.format == 'human':
        print_human(detail_columns, labels, rows)
    elif args.format == 'csv':
        output = args.output or os.path.join('reports', f'{args.report_id}.csv')
        os.makedirs(os.path.dirname(output), exist_ok=True) if os.path.dirname(output) else None
        write_csv(output, detail_columns, labels, rows)
        print(f"Wrote {len(rows)} row(s) to {output}")
    elif args.format == 'json':
        payload = [dict(zip(labels, [row.get(c, '') for c in detail_columns])) for row in rows]
        if args.output:
            os.makedirs(os.path.dirname(args.output), exist_ok=True) if os.path.dirname(args.output) else None
            with open(args.output, 'w') as f:
                json.dump(payload, f, indent=2)
            print(f"Wrote {len(rows)} row(s) to {args.output}")
        else:
            print(json.dumps(payload, indent=2))


if __name__ == '__main__':
    main()
