# JIRA PM Scripts

Nine Python scripts for syncing a GUS/Jira export file (`import.xls`) with a JIRA project.
No third-party libraries required — only Python 3 standard library + `curl`.

## Setup

### Credentials

All scripts require your JIRA credentials passed as arguments or set as environment variables:

| Variable | Argument | Description |
|---|---|---|
| `JIRA_EMAIL` | `--email` | Your Atlassian account email |
| `JIRA_API_TOKEN` | `--token` | Your API token — generate at https://id.atlassian.net/manage-api-tokens |
| `JIRA_BASE_URL` | `--base-url` | Your Atlassian domain (e.g. `https://yourcompany.atlassian.net`) |
| `JIRA_DEFAULT_ASSIGNEE` | `--default-assignee` | JIRA account ID to use when assignee lookup fails (Script 3 only) |
| `SLACK_CHANNEL` | `--slack-channel` | Slack channel ID for posting results (Scripts 8, 9) |
| `DRIVE_FOLDER` | `--drive-folder` | Google Drive folder ID for standup notes (Script 8 only) |

Copy the template and fill in your values:

```bash
cp config/credentials.env config/credentials.env.local
# Edit config/credentials.env.local with your credentials
source config/credentials.env.local
python3 scripts/1_create_sprints.py --email "$JIRA_EMAIL" --token "$JIRA_API_TOKEN" ...
```

`config/credentials.env.local` is git-ignored and will never be committed. `config/credentials.env` is the template — only placeholder values should be committed there.

**Finding your JIRA account ID** (needed for `JIRA_DEFAULT_ASSIGNEE`):
```bash
curl -u your_email:your_token \
  "https://yourcompany.atlassian.net/rest/api/3/user/search?query=firstname.lastname" \
  | python3 -c "import sys,json; [print(u['accountId'], u['displayName']) for u in json.load(sys.stdin)]"
```

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
| `--base-url` | No | `$JIRA_BASE_URL` | JIRA base URL |
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
| `--base-url` | No | `$JIRA_BASE_URL` | JIRA base URL |
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
| `--base-url` | No | `$JIRA_BASE_URL` | JIRA base URL |
| `--default-assignee` | No | `$JIRA_DEFAULT_ASSIGNEE` | JIRA account ID fallback when assignee lookup fails |
| `--status` | No | `User Story Complete` | Only create stories matching this import status; pass `--status ""` to create stories of any status |
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

**Active sprint behaviour:** If the target sprint is currently active in JIRA, the story is created in the backlog instead and tagged with the label `New_Scope_to_Active_Sprint`. This prevents unplanned work from being silently added to an in-progress sprint without the team's awareness. Stories targeting future or closed sprints are assigned to the sprint as normal.

---

## Script 4 — Compare JIRA to File

Compares Work ID and status between the import file and JIRA for one or
more sprints. Reports matches, mismatches, and stories not found in the
target sprint (including those in the backlog or other sprints).
Also detects future sprint assignment changes — reported only by default,
applied when `--apply` is passed. Prints results to the terminal.

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
| `--base-url` | No | `$JIRA_BASE_URL` | JIRA base URL |
| `--sprints` | Yes | — | One or more sprint names from the import file (with date suffix, space-separated) |
| `--apply` | No | off | Apply sprint assignment changes to JIRA (default: report only) |

Note: `--sprints` accepts multiple values. Sprint names must match exactly as they appear in the import file, **including the date suffix** (e.g. `"2026.07c-Comp Systems 7/29 - 8/11"`, not `"2026.07c-Comp Systems"`). The date suffix is stripped internally for matching against JIRA sprint names.

When a Work ID is not found in the queried sprint(s), the script searches the full project — including the backlog and all other sprints — before declaring it `MISSING`. Stories found outside the target sprint are reported as `IN JIRA (sprint name)` or `IN JIRA ((backlog))` so you can decide whether to move them rather than create duplicates.

The future sprint analysis section identifies stories in JIRA that no longer appear in the import file (removed from scope) and stories whose sprint assignments differ between JIRA and the import. Sprint changes are reported as `PENDING` by default — pass `--apply` to write them to JIRA.

---

## Script 5 — Identify Source File Updates

Compares JIRA status, due date, assignee, story points, and sprint against the import file
and flags anything needing source system attention. Outputs a highlighted `.xls` report
with flagged cells in yellow and an Actions Required column.

Sprint defaults to the **active sprint** when `--sprint` is omitted.

```bash
# Active sprint (default):
python3 scripts/5_identify_source_file_updates.py \
  --file data/import.xls \
  --project IGSIFP \
  --board 18086 \
  --email "$JIRA_EMAIL" \
  --token "$JIRA_API_TOKEN"

# Specific sprint:
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
| `--base-url` | No | `$JIRA_BASE_URL` | JIRA base URL |
| `--sprint` | No | active sprint | Sprint base name (without date suffix, e.g. `2026.07c-Comp Systems`) |
| `--output` | No | `reports/source_update_report.xls` | Path for the output report |
| `--today` | No | system date | Override today's date (YYYY-MM-DD) |

Seven checks are performed:

| Check | Condition | Flag | Highlighted Column | Action Required |
|---|---|---|---|---|
| Due Date | JIRA Due Date is later than import Dev Deadline (skipped if JIRA status is Closed) | DUE DATE | Import Dev Deadline + JIRA Due Date (yellow) | Update due date in source system |
| Status (closed) | JIRA is Closed and import shows Development | STATUS | Import Status (yellow) | UPDATE SOURCE SYSTEM |
| Status (USC) | Import shows User Story Complete but JIRA has progressed beyond Open or Ready for Implementation | STATUS | Import Status (yellow) | JIRA status is "X" — update import status to reflect current work state |
| Removed from Scope | Story exists in JIRA sprint but has no matching Work ID in the import file (non-Closed only) | REMOVED FROM SCOPE | JIRA Status + Import Status (orange) | Confirm if removed from scope |
| Sprint Mismatch | Story is in the JIRA sprint but import assigns it to a different sprint (non-Closed only) | SPRINT MISMATCH | Import Sprint (orange) | Import assigns to "sprint" — team may be working ahead of schedule |
| Assignee Mismatch | JIRA assignee differs from import Assigned To after normalization (non-Closed only) | ASSIGNEE MISMATCH | Import Assignee (yellow) | JIRA assignee "X" differs from import "Y" |
| Story Points Mismatch | JIRA story points differ from import Story Points - Dev (when both are set) | STORY POINTS MISMATCH | Import Story Points + JIRA Story Points (yellow) | JIRA story points (X) differ from import (Y) |

**Note:** `User Story Complete` means the story has been written and handed to the dev team — it is not an implementation-complete status. If JIRA has progressed beyond Open or Ready for Implementation, the source system should be updated to reflect the current work state.

**Assignee comparison logic:** Both sides normalized to `firstname.lastname` before comparison (e.g. `Leo Kennedy` → `leo.kennedy`). Only genuine mismatches flagged.

Report columns: Work ID, JIRA Key, Summary, JIRA Status, Import Status, Import Dev Deadline, JIRA Due Date, Import Sprint, Import Assignee, JIRA Assignee, Import Story Points, JIRA Story Points, Flag Type, Action Required.

If a story triggers more than one check, all applicable flags and actions appear in their respective columns.

The script header in `scripts/5_identify_source_file_updates.py` also lists the seven checks for quick reference.

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
| `--base-url` | No | `$JIRA_BASE_URL` | JIRA base URL |
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
| `--base-url` | No | `$JIRA_BASE_URL` | JIRA base URL |
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
and past-due stories), a list of accomplishments, and optionally a "Team
Communications Highlights" section populated from Slack messages and/or Google
Drive standup notes.

**Workflow for Slack/Drive integration:**

1. Have Claude read Slack channel C06PHK1DPH7 and save messages to `data/slack_notes_YYYY-MM-DD.txt`
2. (Optional) Have Claude read Google Drive standup notes folder `10zqzHGYSjehzJAgUUPX0VOF2cykB10jC` and save to `data/standup_notes_YYYY-MM-DD.txt`
3. Pass the saved files to the script via `--slack-notes` and/or `--drive-notes`

The script also **auto-detects** notes files named `data/slack_notes_YYYY-MM-DD.txt` and `data/standup_notes_YYYY-MM-DD.txt` matching today's date, so the flags can be omitted when files are in place.

```bash
# Step 1: Write your executive summary (one paragraph per blank line):
cat > data/executive_summary.txt << 'EOF'
The GIC workstream is executing Sprint 2026.07c (7/29–8/11) with three business days remaining...

The team adopted two new delivery practices this sprint...
EOF

# Step 2: Generate the report (with optional Slack notes):
python3 scripts/8_weekly_status_report.py \
  --project IGSIFP \
  --board 18086 \
  --email "$JIRA_EMAIL" \
  --token "$JIRA_API_TOKEN" \
  --summary data/executive_summary.txt \
  --slack-notes data/slack_notes_2026-08-13.txt \
  --output reports/IGSIFP_LeadershipStatusReport_2026-08-13.html
```

| Argument | Required | Default | Description |
|---|---|---|---|
| `--project` | Yes | — | JIRA project key |
| `--project-name` | No | project key | Full project name for report header (e.g. `"Internal GIC Spiff Implementation FY27"`) |
| `--board` | Yes | — | JIRA board ID |
| `--email` | Yes | — | Atlassian email |
| `--token` | Yes | — | Atlassian API token |
| `--base-url` | No | `$JIRA_BASE_URL` | JIRA base URL |
| `--summary` | No | — | Path to plain-text executive summary file |
| `--slack-notes` | No | auto-detect `data/slack_notes_YYYY-MM-DD.txt` | Path to pre-saved Slack messages file |
| `--drive-notes` | No | auto-detect `data/standup_notes_YYYY-MM-DD.txt` | Path to pre-saved Google Drive standup notes file |
| `--drive-folder` | No | `$DRIVE_FOLDER` | Google Drive folder ID (shown in placeholder when Drive unavailable) |
| `--output` | No | `reports/{PROJECT}_LeadershipStatusReport_YYYY-MM-DD.html` | Output HTML path |
| `--today` | No | system date | Override today's date (YYYY-MM-DD) |
| `--week-start` | No | Monday of current week | Override the reporting week start date (YYYY-MM-DD); messages outside `[week-start, today]` are excluded |

**Executive summary file format:** Plain text, paragraphs separated by blank lines. Each paragraph becomes its own `<p>` block in the report.

**Notes file format:** One message per line in the format `[YYYY-MM-DD] Author: message text`. Claude saves Slack and Drive content in this format automatically.

**Highlights extraction:** Messages are filtered to the current reporting week (Monday through today) before keyword matching — messages from prior weeks are excluded even if they appear in the notes file. The three groups — Key Accomplishments, Risks & Concerns, and Issues & Action Items — are derived by keyword matching within that window. The section header shows the exact date range covered (e.g. `Aug 17 – Aug 21`). The section includes a disclaimer to review for accuracy before sharing. When a Drive folder is configured but no notes file is present, a placeholder note is shown with instructions to add Drive data for future runs. Use `--week-start` to override the week start date if the default Monday calculation is not the desired window.

**Risk assessment model:** The report uses an *effective progress* metric to determine sprint health, not just raw closed count:

- **Closed** stories count as full credit (1.0).
- **Near-done** stories (`Ready for Test`, `Ready for Demo`, `In Test`) count as half-credit (0.5) — they are late in the workflow and expected to close quickly per the Definition of Done.
- **In Progress with a future due date** counts as quarter-credit (0.25) — active work that is not yet overdue.
- **Blocked / On Hold** stories are flagged HIGH risk and shown in the risk register.
- The sprint is flagged `AT RISK` (red critical banner) only when effective progress lags time elapsed by more than 15 percentage points.

| Status | Credit | Risk badge | Row highlight |
|---|---|---|---|
| `Closed` | 1.0 | — | Green background |
| `Ready for Test` / `Ready for Demo` / `In Test` | 0.5 | NEAR DONE (green) | Normal |
| `In Progress` with future due date | 0.25 | IN PROGRESS (blue) | Normal |
| `In Progress` past due / `Open` / `Ready for Implementation` | 0 | ON TRACK (grey) | Normal or red if past-due |
| `Blocked` / `On Hold` | 0 | HIGH (red) | Orange background |
| Past-due open (any non-closed, non-blocked) | 0 | HIGH (red) | Red background |

**Editable executive summary:** The Executive Summary section in the generated HTML is `contenteditable` — click to edit directly in the browser. A toolbar provides:
- **💾 Save to File** — downloads the edited text as a `.txt` file (preserving paragraph breaks), ready to use as `--summary` on the next run
- **📋 Copy Text** — copies plain text to the clipboard for pasting into email or Slack
- **↩ Reset** — reverts to the original generated text (with confirmation prompt)
- An **Unsaved changes** indicator appears in orange as soon as you begin typing

Report sections generated:

| Section | Source |
|---|---|
| Header + sprint metadata | Active sprint from JIRA Agile API |
| Critical banner | Auto — shown if effective progress lags elapsed% by >15 points |
| Summary cards (4) | Sprint Progress (effective %), Blocked/On Hold count, Near Done count, Closed count |
| Executive Summary | `--summary` file (PM-authored); editable in browser with Save/Copy/Reset toolbar |
| Accomplishments | All Closed stories in the sprint |
| Team Communications Highlights | Keyword-extracted from Slack + Drive notes (when provided) |
| Issue Register | All sprint stories with status badges, risk badges, and row highlights |
| Sprint Burn bars | Time elapsed · Stories Closed · Near Done · In Progress · Effective Progress · Expected at Pace · Blocked/On Hold |
| Team Workload bars | Open story count per assignee |
| Risk Register | Auto-populated from Blocked/On Hold stories and past-due open stories |
| Footer | Sprint name and report date |

Note: Only User Stories and Bugs are analyzed; Tasks and Sub-tasks are excluded.

---

## Script 9 — Definition of Ready Check

Checks all User Stories in the upcoming (next future) sprint against the Definition of Ready.
Tasks and other non-Story issue types are automatically skipped. Reports total story points
for the sprint and optionally posts results to Slack.

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
| `--base-url` | No | `$JIRA_BASE_URL` | JIRA base URL |
| `--sprint` | No | next future sprint | Sprint name override (without date suffix) |
| `--slack-channel` | No | `$SLACK_CHANNEL` env var | Slack channel ID to post results; falls back to env var if not passed |

**Definition of Ready criteria (all 5 must pass):**

| Check | Column | Field | Pass Condition |
|---|---|---|---|
| Title | Title | `summary` | Non-empty |
| Description | Desc | `description` | Contains non-empty text (ADF traversal) |
| Acceptance Criteria | AC | `customfield_10033` | Contains non-empty text (ADF traversal) |
| Story Points | Pts | `customfield_10047` | Numeric value > 0 |
| Ready for Implementation | RFI | `status.name` | Must equal `Ready for Implementation` |

Note: Blocker/dependency check is not automatable via the JIRA API and must be reviewed manually.

**Output format:** Terminal table with Y/N per check column and READY/NOT READY status. Summary line includes total story points across all User Stories in the sprint. Stories that fail are listed with their missing fields at the end of the report.

**Slack channel:** Set `$SLACK_CHANNEL` in `config/credentials.env.local` or pass `--slack-channel`. The script prints the configured channel at the end of each run. Post results using the Slack MCP tool.
