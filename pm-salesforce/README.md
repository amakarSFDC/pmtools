# pm-salesforce

Reusable scripts for connecting to a Salesforce org (`hui`) to read reports, run SOQL
queries, and create/update records — mirrors the `pm-jira` project's structure and
dry-run-by-default safety pattern.

Auth is delegated entirely to the [Salesforce CLI](https://developer.salesforce.com/tools/salesforcecli)
(`sf`), which owns OAuth and stores tokens under `~/.sfdx/` keyed by an alias. This project
holds **no secrets** — only the alias, instance URL, and API version.

## Setup

1. Confirm the `sf` CLI is installed: `sf --version`
2. Copy the config template (already done if `config/salesforce.env.local` exists) and adjust
   if your org's My Domain URL differs:
   ```bash
   cp config/salesforce.env config/salesforce.env.local
   ```
3. Source the config and log in (opens a browser for SSO/credentials):
   ```bash
   source config/salesforce.env.local
   bash scripts/setup_auth.sh
   ```
4. Confirm the connection any time with:
   ```bash
   sf org display --target-org hui
   ```

You only need to repeat step 3 when the stored auth expires or you switch orgs.

## Scripts

### `scripts/1_run_report.py` — fetch a report

Calls the Analytics Reports REST API (`/services/data/{version}/analytics/reports/{id}`) via
`sf api request rest`, then flattens the `factMap` / `reportMetadata.detailColumns` /
`reportExtendedMetadata` structure into one row per detail record.

| Flag | Default | Description |
|---|---|---|
| `--report-id` | `00OUc00000BBDmnMAH` | Salesforce report ID |
| `--alias` | `$SF_ALIAS` or `hui` | org alias |
| `--api-version` | `$SF_REPORT_API_VERSION` or `v64.0` | API version |
| `--format` | `human` | `human`, `csv`, or `json` |
| `--output` | `reports/{report-id}.csv` (csv only) | write to this path instead of stdout |

```bash
python3 scripts/1_run_report.py
python3 scripts/1_run_report.py --format csv --output reports/pipeline.csv
```

### `scripts/2_query.py` — run SOQL

Wraps `sf data query`. Accepts a query inline or from a file.

| Flag | Description |
|---|---|
| `--soql` | SOQL string |
| `--file` | path to a `.soql` file (alternative to `--soql`) |
| `--alias` | org alias |
| `--format` | `human`, `csv`, or `json` |
| `--output` | write to this path instead of stdout |
| `--use-tooling-api` | query Tooling API objects (ApexClass, etc.) |

```bash
python3 scripts/2_query.py --soql "SELECT Id, Name FROM Account LIMIT 5"
```

### `scripts/3_create_record.py` and `scripts/4_update_record.py` — write records

Both wrap `sf data create record` / `sf data update record` and default to **dry-run**: they
print the exact `sf` command they would run and make no change. Pass `--apply` to execute.

```bash
# Dry run — prints the command only
python3 scripts/3_create_record.py --sobject Account --values "Name=ClaudeTest"

# Actually create the record
python3 scripts/3_create_record.py --sobject Account --values "Name=ClaudeTest" --apply

# Update by ID
python3 scripts/4_update_record.py --sobject Account --record-id 001XXXXXXXXXXXXXXX --values "Industry=Tech" --apply

# Update by WHERE clause
python3 scripts/4_update_record.py --sobject Account --where "Name='ClaudeTest'" --values "Industry=Tech" --apply
```

### `scripts/5_compare_jira_to_csv.py` — compare a report export to JIRA

Compares Work ID and status between a CSV produced by `1_run_report.py` (e.g.
`reports/PS_Scope_Extract_YYYY-MM-DD.csv`) and JIRA, across the whole project. Mirrors
`pm-jira`'s `scripts/4_compare_jira_to_file.py --all` mode — same literal status comparison,
no GUS↔JIRA status translation.

| Flag | Required | Description |
|---|---|---|
| `--file` | Yes | Path to CSV produced by `1_run_report.py` |
| `--project` | Yes | JIRA project key (e.g. `IGSIFP`) |
| `--board` | Yes | JIRA board ID (used to resolve sprint names for display) |
| `--email` | No | JIRA email (default: `$JIRA_EMAIL`) |
| `--token` | No | JIRA API token (default: `$JIRA_API_TOKEN`) |
| `--base-url` | No | JIRA base URL (default: `$JIRA_BASE_URL`) |

```bash
source /path/to/pm-jira/config/credentials.env.local
python3 scripts/5_compare_jira_to_csv.py \
  --file reports/PS_Scope_Extract_2026-08-28.csv \
  --project IGSIFP --board 18086 \
  --email "$JIRA_EMAIL" --token "$JIRA_API_TOKEN"
```

Output columns: Work ID, Subject, CSV Status, JIRA Key, JIRA Status, JIRA Sprint, Match.
`Match` is one of `YES`, `NO` (status differs — literal string comparison, so GUS/JIRA
vocabulary differences like `User Story Complete` vs `Open` always show as `NO`), `MISSING`
(Work ID not found in JIRA), or `NOT IN CSV` (JIRA ticket not present in the report export).

## Project layout

```
config/
  salesforce.env        # tracked template — no secrets
  salesforce.env.local  # your local copy, git-ignored
scripts/
  sf_helpers.py          # shared sf-CLI-as-subprocess helper
  setup_auth.sh          # one-time interactive login
  1_run_report.py
  2_query.py
  3_create_record.py
  4_update_record.py
  5_compare_jira_to_csv.py
data/      # git-ignored — query/report output you keep around
reports/   # git-ignored — generated report exports
```

## Troubleshooting

- **"Not connected to Salesforce org"** — run `bash scripts/setup_auth.sh` again; the stored
  auth may have expired.
- **404 on the report or API call** — the org's max supported API version may be lower than
  `v64.0`; check with `sf org display --target-org hui --json | jq .result.apiVersion` and
  update `SF_REPORT_API_VERSION` in `config/salesforce.env.local`.
- **Wrong org / instance URL** — if `hui`'s login host isn't the standard
  `https://hui.my.salesforce.com`, update `SF_INSTANCE_URL` in `config/salesforce.env.local`
  and re-run `setup_auth.sh`.
