#!/usr/bin/env bash
# Validate the bundle without deploying anything.
#
# Usage:
#   ./scripts/validate.sh [target]
set -euo pipefail

TARGET="${1:-prod}"
databricks bundle validate -t "${TARGET}"
