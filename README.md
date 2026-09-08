# pmtools

Personal PM/engineering automation scripts, tracked at
[github.com/amakarSFDC/pmtools](https://github.com/amakarSFDC/pmtools).

## Projects

| Folder | Purpose |
|---|---|
| [`pm-jira/`](pm-jira/README.md) | Sync a GUS/Salesforce export with a JIRA project — sprints, fix versions, stories, comparison reports, weekly leadership status report |
| [`pm-salesforce/`](pm-salesforce/README.md) | Read Salesforce (`hui`) reports/SOQL and create/update records via the `sf` CLI |
| [`icymi/`](icymi/README.md) | Weekly "In Case You Missed It" digest of a fixed list of Slack channels |
| `timeline/` | Standalone timeline/presentation generator |

Each project folder has its own `README.md`, `config/` template, and git-ignored
`config/*.env.local` for real credentials — see the per-project docs for setup.

## Pushing changes to GitHub

### One-time setup

Authenticate the GitHub CLI (interactive — run this yourself, not from an automated session):

```bash
gh auth login --hostname github.com --git-protocol https --web
```

This also configures `gh` as git's credential helper, so `git push` over HTTPS works with no
personal access token to manage. Check anytime with `gh auth status`.

### Pushing

Use `scripts/push_to_github.sh` from the repo root — it stages everything, scans the staged
diff for obvious secrets (API tokens, private keys) before committing, then commits and pushes:

```bash
scripts/push_to_github.sh -m "Describe the change"
```

If the scan flags a false positive, skip it with `--force`:

```bash
scripts/push_to_github.sh -m "Describe the change" --force
```

Or push manually:

```bash
git add -A
git status        # review what's staged
git commit -m "Describe the change"
git push origin main
```

**Never commit real credentials.** Each project's `config/*.env` is a placeholder template and
is tracked; the filled-in `config/*.env.local` copies (and `data/`, `reports/`) are git-ignored
per-project — see `pm-jira/.gitignore` and `pm-salesforce/.gitignore`. Always check `git status`
and `git diff` before pushing if you've edited a tracked config template.
