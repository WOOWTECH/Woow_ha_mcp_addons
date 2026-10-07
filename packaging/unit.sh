#!/bin/sh
# Disposable CI only: all downloads pinned by existing locks, no backend credentials.
set -eu
unset SUPERVISOR_TOKEN
uv sync --frozen --python python3.13
for app in odoo odoo-manage hermes opendesign emqx litellm nextcloud; do
  uv sync --project "apps/$app" --frozen --no-dev --python python3.13
done
npm ci --prefix apps/n8n --ignore-scripts --no-audit --no-fund
node --check apps/n8n/backend_policy.cjs
npm ci --prefix packages/mcp-admin-ui --ignore-scripts --no-audit --no-fund
npm test --prefix packages/mcp-admin-ui
npm run build --prefix packages/mcp-admin-ui
node packages/mcp-admin-ui/tests/build-closure.mjs
npm run browser:install --prefix packages/mcp-admin-ui
UI_EVIDENCE_DIR=/tmp/woow-ui-evidence npm run test:browser --prefix packages/mcp-admin-ui -- --output=/tmp/woow-ui-results
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/tool_inventory.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests --junitxml=/tmp/woow-unit-results.xml
python3 packaging/check_results.py /tmp/woow-unit-results.xml
