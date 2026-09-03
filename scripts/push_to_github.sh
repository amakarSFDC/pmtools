#!/bin/bash
# Stage, secret-scan, commit, and push local changes to GitHub (origin).
#
# Usage:
#   scripts/push_to_github.sh -m "commit message"
#   scripts/push_to_github.sh -m "commit message" --force   # skip the secret scan
#
# One-time setup (interactive — run yourself, not from an automated context):
#   gh auth login --hostname github.com --git-protocol https --web
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

FORCE=0
MESSAGE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--message) MESSAGE="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$MESSAGE" ]]; then
  echo "Usage: $0 -m \"commit message\" [--force]" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "Not logged in to GitHub. Run this once, interactively:" >&2
  echo "  gh auth login --hostname github.com --git-protocol https --web" >&2
  exit 1
fi

if [[ -z "$(git status --porcelain)" ]]; then
  echo "Nothing to commit — working tree clean."
  exit 0
fi

echo "Changes to be pushed:"
git status -s
echo

git add -A

if [[ "$FORCE" -eq 0 ]]; then
  echo "Scanning staged changes for likely secrets..."
  PATTERN='ATATT[0-9A-Za-z_=-]{20,}|gh[oprsu]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|sk-ant-[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----'
  HITS="$(git diff --cached | grep -EnI "$PATTERN" || true)"
  if [[ -n "$HITS" ]]; then
    echo "Possible secret detected in staged changes — aborting commit:" >&2
    echo "$HITS" >&2
    echo >&2
    echo "Review the file(s) above. If this is a false positive, rerun with --force." >&2
    git reset >/dev/null
    exit 1
  fi
fi

git commit -m "$MESSAGE"

BRANCH="$(git branch --show-current)"
git push origin "$BRANCH"

echo
echo "Pushed to origin/$BRANCH."
