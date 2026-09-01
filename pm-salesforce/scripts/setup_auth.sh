#!/bin/bash
# One-time interactive login. Opens a browser for SSO/credentials, then
# stores the resulting auth under the alias in ~/.sfdx/ — nothing is
# written to this project.
#
# Usage:
#   source config/salesforce.env.local
#   bash scripts/setup_auth.sh
set -euo pipefail

: "${SF_ALIAS:?SF_ALIAS not set — did you 'source config/salesforce.env.local'?}"
: "${SF_INSTANCE_URL:?SF_INSTANCE_URL not set — did you 'source config/salesforce.env.local'?}"

echo "Opening browser to log in to ${SF_INSTANCE_URL} as alias '${SF_ALIAS}'..."
sf org login web --instance-url "$SF_INSTANCE_URL" --alias "$SF_ALIAS"

echo
echo "Connection check:"
sf org display --target-org "$SF_ALIAS"
