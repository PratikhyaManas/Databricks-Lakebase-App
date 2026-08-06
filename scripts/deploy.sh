#!/usr/bin/env bash
# Validate then deploy the bundle to a target (default: prod).
#
# Usage:
#   ./scripts/deploy.sh [target]
#
# Requires: Databricks CLI v1.0.0+, and either:
#   - a configured profile (databricks auth login), or
#   - DATABRICKS_HOST / DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET env vars
set -euo pipefail

TARGET="${1:-prod}"

echo "==> Validating bundle for target: ${TARGET}"
databricks bundle validate -t "${TARGET}"

echo "==> Deploying bundle for target: ${TARGET}"
databricks bundle deploy -t "${TARGET}"

echo "==> Done. If this is the first deploy and it did not fully complete,"
echo "    re-run this script (some Lakebase resources take a moment to settle)."
