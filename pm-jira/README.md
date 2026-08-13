# JIRA PM Scripts

Nine Python scripts for syncing a GUS/Jira export file (`import.xls`) with a JIRA project.
No third-party libraries required — only Python 3 standard library + `curl`.

## Setup

### Credentials

All scripts require your JIRA credentials passed as arguments:
- `--email`  : your Atlassian email (e.g. `amakar@salesforce.com`)
- `--token`  : your Atlassian API token (generate at https://id.atlassian.net/manage-api-tokens)

A local credentials file is provided for convenience. Source it before running any script:

```bash
source config/credentials.env.local
python3 scripts/1_create_sprints.py --email "$JIRA_EMAIL" --token "$JIRA_API_TOKEN" ...
```

`config/credentials.env.local` is git-ignored and will never be committed. `config/credentials.env` is a safe template with placeholder values only.

### Import file

The import file must be an HTML-formatted `.xls` export (from GUS) with these columns:
`Work: Work ID`, `Subject`, `Status`, `Assigned To`, `Product Owner`,
`Dev Deadline`, `Story Points - Dev`, `Business Description`,
`Product Acceptance Criteria`, `Sprint Name`, `Scheduled Build`

Place the file in the `data/` folder and rename it to `import.xls`. All scripts default to `--file data/import.xls`.

### Output

Reports are written to the `reports/` folder by default.

---

## Script 1 — Create Sprints from Data File

Compares sprint names in the import file vs the JIRA board and creates any
missing future-dated sprints. Date suffixes (e.g. `7/29 - 8/11`) are stripped
before comparison so only the base sprint name is matched.

```bash
python3 scripts/1_create_sprints.py \
  --file data/import.xls \
  --board 18086 \
  --email "$JIRA_EMAIL" \
  --token "$JIRA_API_TOKEN"
```

| Argument | Required | Default | Description |
|---|---|---|---|
| `--file` | No | `data/import.xls` | Path to import file |
| `--board` | Yes | — | JIRA board ID |
| `--email` | Yes | — | Atlassian email |
| `--token` | Yes | — | Atlassian API token |
| `--today` | No | system date | Override today's date (YYYY-MM-DD) for future sprint filtering |

---

## Script 2 — Create Fix Versions from Data File

Compares the `Scheduled Build` column vs JIRA Fix Versions and creates any
missing future-dated ones. Skips `_NO_BUILD_REQUIRED` and `MOCK` values.

```bash
python3 scripts/2_create_fix_versions.py \
  --file data/import.xls \
  --project IGSIFP \
  --email "$JIRA_EMAIL" \
  --token "$JIRA_API_TOKEN"
```

| Argument | Required | Default | Description |
|---|---|---|---|
| `--file` | No | `data/import.xls` | Path to import file |
| `--project` | Yes | — | JIRA project key |
| `--email` | Yes | — | Atlassian email |
| `--token` | Yes | — | Atlassian API token |
| `--today` | No | system date | Override today's date (YYYY-MM-DD) for future version filtering |

---

## Script 3 — Create Stories from Data File

Creates missing JIRA stories from the import file. Filters by status and
optionally restricts to future sprints only. Sprint assignment is done in a
second API call after issue creation (JIRA limitation).

```bash
python3 scripts/3_create_stories.py \
  --file data/import.xls \
  --project IGSIFP \
  --board 18086 \
  --email "$JIRA_EMAIL" \
  --token "$JIRA_API_TOKEN" \
  --status "User Story Complete" \
  --future-only
```

| Argument | Required | Default | Description |
|---|---|---|---|
| `--file` | No | `data/import.xls` | Path to import file |
| `--project` | Yes | — | JIRA project key |
| `--board` | Yes | — | JIRA board ID |
| `--email` | Yes | — | Atlassian email |
| `--token` | Yes | — | Atlassian API token |
| `--status` | No | `User Story Complete` | Only create stories matching this import status |
| `--future-only` | No | off | Only create stories in future-dated sprints |
| `--today` | No | system date | Override today's date (YYYY-MM-DD) for future sprint filtering |

Field mapping:

| Import Column | JIRA Field | Notes |
|---|---|---|
| Subject | Summary | |
| Business Description | Description | |
| Product Owner | Description (appended) | Added as "Product Owner: name" |
| Product Acceptance Criteria | Acceptance Criteria | |
| Assigned To | Assignee | See assignee resolution logic below |
| Dev Deadline | Due Date | |
| Story Points - Dev | Story Points | |
| Sprint Name | Sprint | See active sprint behaviour below |

**Assignee resolution logic:** The `Assigned To` value from the import (e.g. `Leo Kennedy`) is resolved to a JIRA account using the following steps in order:

1. Search JIRA for the full display name (e.g. `Leo Kennedy`)
2. If no exact match, normalize the name to `firstname.lastname` format (e.g. `leo.kennedy`) and compare against each result's display name, username, and email prefix
3. If still no match, search JIRA again using the normalized username directly
4. If all lookups fail or the resolved account is not assignable to the project, fall back to the default assignee (Leo Kennedy) and log a `WARN`

This normalization ensures names like `Brandon Winter` correctly resolve to the JIRA account `brandon.winter`.

**Active sprint behaviour:** If the target sprint is currently active in JIRA, the story is created in the backlog instead and tagged with the label `New Scope to Active Sprint`. This prevents unplanned work from being silently added to an in-progress sprint without the team's awareness. Stories targeting future or closed sprints are assigned to the sprint as normal.

---

## Script 4 — Compare JIRA to File

Compares Work ID and status between the import file and JIRA for one or
more sprints. Reports matches, mismatches, and stories missing from JIRA.
Also detects sprint assignment changes for future sprints and applies them automatically.
Prints results to the terminal.

```bash
python3 scripts/4_compare_jira_to_file.py \
  --file data/import.xls \
  --project IGSIFP \
  --board 18086 \
  --email "$JIRA_EMAIL" \
  --token "$JIRA_API_TOKEN" \
  --sprints "2026.07c-Comp Systems" "2026.08a-Comp Systems"
```

| Argument | Required | Default | Description |
|---|---|---|---|
| `--file` | No | `data/import.xls` | Path to import file |
| `--project` | Yes | — | JIRA project key |
| `--board` | Yes | — | JIRA board ID |
| `--email` | Yes | — | Atlassian email |
| `--token` | Yes | — | Atlassian API token |
| `--sprints` | Yes | — | One or more sprint base names (without date suffix, space-separated) |

Note: `--sprints` accepts multiple values. Sprint names should be the base name without the date suffix (e.g. `2026.07c-Comp Systems`, not `2026.07c-Comp Systems 7/29 - 8/11`).

The future sprint analysis section also identifies stories in JIRA that no longer appear in the import file (removed from scope) and stories whose sprint assignments differ between JIRA and the import — and applies sprint changes automatically.

---

## Script 5 — Identify Source File Updates

Compares JIRA status, due date, assignee, and sprint against the import file for a sprint
and flags anything needing source system attention. Outputs a highlighted `.xls` report
with flagged cells in yellow and an Actions Required column.

```bash
python3 scripts/5_identify_source_file_updates.py \
  --file data/import.xls \
  --project IGSIFP \
  --board 18086 \
  --email "$JIRA_EMAIL" \
  --token "$JIRA_API_TOKEN" \
  --sprint "2026.07c-Comp Systems" \
  --output reports/source_update_report.xls
```

| Argument | Required | Default | Description |
|---|---|---|---|
| `--file` | No | `data/import.xls` | Path to import file |
| `--project` | Yes | — | JIRA project key |
| `--board` | Yes | — | JIRA board ID |
| `--email` | Yes | — | Atlassian email |
| `--token` | Yes | — | Atlassian API token |
| `--sprint` | Yes | — | Sprint base name (without date suffix, e.g. `2026.07c-Comp Systems`) |
| `--output` | No | `reports/source_update_report.xls` | Path for the output report |
| `--today` | No | system date | Override today's date (YYYY-MM-DD) |

Note: `--sprint` takes a single sprint name (without date suffix), unlike `--sprints` in script 4.

Six checks are performed:

| Check | Condition | Flag | Highlighted Column | Action Required |
|---|---|---|---|---|
| Due Date | JIRA Due Date is later than import Dev Deadline (skipped if JIRA status is Closed) | DUE DATE | Import Dev Deadline + JIRA Due Date (yellow) | Update due date in source system |
| Status (closed, dev) | JIRA is Closed and import shows Development or User Story Complete | STATUS | Import Status (yellow) | UPDATE SOURCE SYSTEM |
| Status (closed, other) | JIRA is Closed and import shows any other active status | STATUS | Import Status (yellow) | REVIEW STATUS IN SOURCE SYSTEM |
| Status (review) | Import shows User Story Complete but JIRA is not Open or Ready for Implementation | STATUS | Import Status (yellow) | REVIEW STATUS IN SOURCE SYSTEM |
| Sprint Mismatch | Story is in the JIRA sprint but import assigns it to a different sprint (non-Closed only) | SPRINT MISMATCH | Import Sprint (orange) | Import assigns to "sprint" — team may be working ahead of schedule |
| Assignee Mismatch | JIRA assignee differs from import Assigned To after normalization (non-Closed only) | ASSIGNEE MISMATCH | Import Assignee (yellow) | JIRA assignee "X" differs from import "Y" |

**Assignee comparison logic:** Both the JIRA assignee and the import `Assigned To` value are normalized before comparison — converted to lowercase with spaces replaced by dots (e.g. `Leo Kennedy` → `leo.kennedy`). This prevents false positives where the same person is stored differently across the two systems. Only genuine mismatches (different people) are flagged.

Report columns: Work ID, JIRA Key, Summary, JIRA Status, Import Status, Import Dev Deadline, JIRA Due Date, Import Sprint, Import Assignee, JIRA Assignee, Flag Type, Action Required.

If a story triggers more than one check, all applicable flags and actions appear in their respective columns.

---

## Script 6 — Update Stories with Version

Finds all JIRA stories missing a fix version, compares their `Work: Work ID`
to the import file's `Scheduled Build` column, and assigns the matching fix
version in JIRA. Skips stories where Scheduled Build contains
`_NO_BUILD_REQUIRED` or `MOCK`.

```bash
python3 scripts/6_update_stories_with_version.py \
  --file data/import.xls \
  --project IGSIFP \
  --email "$JIRA_EMAIL" \
  --token "$JIRA_API_TOKEN"
```

Add `--dry-run` to report what would be updated without making any changes.

| Argument | Required | Default | Description |
|---|---|---|---|
| `--file` | No | `data/import.xls` | Path to import file |
| `--project` | Yes | — | JIRA project key |
| `--email` | Yes | — | Atlassian email |
| `--token` | Yes | — | Atlassian API token |
| `--dry-run` | No | off | Report only — do not update JIRA |

The script categorises every story missing a fix version into one of three groups:

| Category | Condition | Action |
|---|---|---|
| Has scheduled build | Scheduled Build exists and is not `_NO_BUILD_REQUIRED`/`MOCK` | Fix version assigned in JIRA |
| No build required | Scheduled Build contains `_NO_BUILD_REQUIRED` or `MOCK` | Skipped |
| Not in import | Work ID not found in import file | Reported only, no update |

---

## Script 7 — Create JIRA Stories by Epic Report

Queries all JIRA stories, groups them by epic, and writes a highlighted XLS
report sorted alphabetically by epic name. Stories with no epic assigned appear
under a `(No Epic)` group.

```bash
python3 scripts/7_stories_by_epic.py \
  --project IGSIFP \
  --email "$JIRA_EMAIL" \
  --token "$JIRA_API_TOKEN"
```

| Argument | Required | Default | Description |
|---|---|---|---|
| `--project` | Yes | — | JIRA project key |
| `--email` | Yes | — | Atlassian email |
| `--token` | Yes | — | Atlassian API token |
| `--output` | No | `reports/JIRA_Stories_by_Epic.xls` | Output report path |

Report format:

| Column | Description |
|---|---|
| Epic | Epic name the story belongs to |
| JIRA Key | JIRA issue key |
| Summary | Full issue summary |
| Status | Current JIRA status |
| Due Date | Due date formatted mm/dd/yyyy |

Each epic group has a blue-tinted header row showing the epic name and story count. The column header row is blue.

---

## Script 8 — Generate Weekly Status Summary

Queries the active JIRA sprint and generates a styled HTML leadership status
report. Includes an executive summary (from a plain-text input file), issue
register, burn bars, workload bars, risk register (auto-populated from blocked
and past-due stories), and a list of accomplishments.

```bash
# Step 1: Write your executive summary (one paragraph per blank line):
cat > data/executive_summary.txt << 'EOF'
The GIC workstream is executing Sprint 2026.07c (7/29–8/11) with three business days remaining...

The team adopted two new delivery practices this sprint...

Two items are actively being managed as user story risks...
EOF

# Step 2: Generate the report:
python3 scripts/8_weekly_status_report.py \
  --project IGSIFP \
  --board 18086 \
  --email "$JIRA_EMAIL" \
  --token "$JIRA_API_TOKEN" \
  --summary data/executive_summary.txt \
  --output reports/IGSIFP_LeadershipStatusReport_2026-08-11.html
```

| Argument | Required | Default | Description |
|---|---|---|---|
| `--project` | Yes | — | JIRA project key |
| `--board` | Yes | — | JIRA board ID |
| `--email` | Yes | — | Atlassian email |
| `--token` | Yes | — | Atlassian API token |
| `--summary` | No | — | Path to plain-text executive summary file |
| `--output` | No | `reports/IGSIFP_LeadershipStatusReport_YYYY-MM-DD.html` | Output HTML path |
| `--today` | No | system date | Override today's date (YYYY-MM-DD) |

**Executive summary file format:** Plain text, paragraphs separated by blank lines. Each paragraph becomes its own `<p>` block in the report. Write three paragraphs: (1) sprint status, (2) delivery practices / team, (3) risks.

Report sections generated:

| Section | Source |
|---|---|
| Header + sprint metadata | Active sprint from JIRA Agile API |
| Critical banner | Auto — shown if closed% lags elapsed% by >15 points |
| Summary cards | Story counts from sprint issues |
| Executive Summary | `--summary` file (PM-authored) |
| Accomplishments | All Closed stories in the sprint |
| Issue Register | All sprint stories with status badges and row highlights |
| Sprint Burn bars | Time elapsed vs. stories closed vs. expected pace |
| Team Workload bars | Open story count per assignee |
| Risk Register | Auto-populated from Blocked stories and past-due open stories |
| Footer | Sprint name and report date |

---

## Script 9 — Definition of Ready Check

Checks all User Stories in the upcoming (next future) sprint against the Definition of Ready.
Tasks and other non-Story issue types are automatically skipped.

```bash
python3 scripts/9_definition_of_ready.py \
  --project IGSIFP \
  --board 18086 \
  --email "$JIRA_EMAIL" \
  --token "$JIRA_API_TOKEN"
```

| Argument | Required | Default | Description |
|---|---|---|---|
| `--project` | Yes | — | JIRA project key |
| `--board` | Yes | — | JIRA board ID |
| `--email` | Yes | — | Atlassian email |
| `--token` | Yes | — | Atlassian API token |
| `--sprint` | No | next future sprint | Sprint name override (without date suffix) |
| `--slack-channel` | No | `$SLACK_CHANNEL` env var | Slack channel ID to post results; falls back to env var if not passed |

**Definition of Ready criteria:**

| Check | Field | Pass Condition |
|---|---|---|
| Title | `summary` | Non-empty |
| Description | `description` | Contains non-empty text (ADF traversal) |
| Acceptance Criteria | `customfield_10033` | Contains non-empty text (ADF traversal) |
| Story Points | `customfield_10047` | Numeric value > 0 |

Note: Blocker/dependency check is not automatable via the JIRA API and must be reviewed manually.

**Output format:** Terminal table with Y/N per check and READY/NOT READY status. Stories that fail are listed with their missing fields at the end of the report.

**Slack posting:** Results can be posted to Slack channel `C06PHK1DPH7` using the Slack MCP tool.
