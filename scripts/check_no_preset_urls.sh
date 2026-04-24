#!/usr/bin/env bash
# Pre-commit hook: block Preset infrastructure URLs from being committed.
# GitHub repo URLs (preset-io/testmcpy) and NOTICE copyright are allowed.
# docs/presentation.html and docs/talking_points.md are exempt (internal presentation materials).
set -euo pipefail

EXEMPT_FILES="NOTICE|docs/presentation\.html|docs/talking_points\.md|README\.md|scripts/check_no_preset_urls\.sh"

# Patterns that should NOT appear in committed code
# (Preset infrastructure domains, not GitHub repo URLs)
PATTERN='(\.preset\.io|\.preset\.zone|preset-mcp-client|PRESET_WORKSPACE|PRESET_DOMAIN|PRESET_ENVIRONMENT|PRESET_API_TOKEN|PRESET_API_SECRET|PRESET_API_URL|testmcpy\.sandbox)'

status=0
for file in "$@"; do
    # Skip exempt files
    if echo "$file" | grep -qE "$EXEMPT_FILES"; then
        continue
    fi
    # Skip binary files
    if file "$file" | grep -q "binary"; then
        continue
    fi
    if grep -nEi "$PATTERN" "$file" 2>/dev/null; then
        echo "ERROR: $file contains Preset infrastructure references."
        echo "       Use generic placeholders (example.com) instead."
        status=1
    fi
done

if [ "$status" -ne 0 ]; then
    echo ""
    echo "Blocked by no-preset-infra-urls hook."
    echo "See CLAUDE.md for details on allowed vs blocked references."
fi

exit $status
