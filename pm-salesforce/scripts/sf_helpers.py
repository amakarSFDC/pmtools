"""Shared helpers for the pm-salesforce scripts.

All scripts shell out to the `sf` CLI (which owns OAuth/token storage in
~/.sfdx/) instead of talking to Salesforce APIs directly, so this project
never needs to hold a secret.
"""
import json
import os
import subprocess
import sys


def get_alias(cli_value=None):
    return cli_value or os.environ.get('SF_ALIAS', 'hui')


def get_api_version(cli_value=None):
    # Intentionally not SF_API_VERSION — that name is reserved by the `sf` CLI
    # itself as a global version override and expects a bare number ("64.0").
    return cli_value or os.environ.get('SF_REPORT_API_VERSION', 'v64.0')


def sf_json(args):
    """Run an `sf` CLI command with --json and return the parsed `result`.

    `args` is a list of CLI arguments, e.g. ['data', 'query', '--query', '...'].
    Raises RuntimeError with the CLI's own error message on failure.
    """
    cmd = ['sf'] + args + ['--json']
    proc = subprocess.run(cmd, capture_output=True, text=True)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        sys.stderr.write(proc.stderr or proc.stdout)
        raise RuntimeError(f"sf CLI returned non-JSON output (exit {proc.returncode})")

    if payload.get('status') != 0:
        message = payload.get('message', 'unknown sf CLI error')
        raise RuntimeError(f"sf CLI error: {message}")

    return payload.get('result')


def require_org(alias):
    """Fail fast with a clear message if `alias` isn't authenticated yet."""
    try:
        sf_json(['org', 'display', '--target-org', alias])
    except RuntimeError as exc:
        sys.exit(
            f"Not connected to Salesforce org '{alias}': {exc}\n"
            f"Run: bash scripts/setup_auth.sh"
        )
