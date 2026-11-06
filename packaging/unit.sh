#!/bin/sh
# Disposable CI only: all downloads pinned by existing locks, no backend credentials.
set -eu
unset SUPERVISOR_TOKEN
uv sync --frozen --python python3.13
for app in odoo odoo-manage hermes opendesign emqx litellm nextcloud; do
  uv sync --project "apps/$app" --frozen --no-dev --python python3.13
done
# 0.2.0: the PaaS build patches the Odoo image applies (apps/odoo/Dockerfile); launch.py checks the patched digests.
apps/odoo/.venv/bin/python apps/odoo/patches/fix_cross_session_token_store.py
apps/odoo/.venv/bin/python apps/odoo/patches/fix_direct_writes.py
npm ci --prefix apps/n8n --ignore-scripts --no-audit --no-fund
# 0.2.2: the n8n-mcp build patch the n8n image applies (apps/n8n/Dockerfile); backend_policy.cjs checks the patched digest.
python3 apps/n8n/patches/fix_test_run_error_messages.py
python3 apps/n8n/patches/fix_tool_result_is_error.py
python3 apps/n8n/patches/fix_delete_workflow_description.py
python3 apps/n8n/patches/fix_workflow_output_schema.py
node --check apps/n8n/backend_policy.cjs
npm ci --prefix packages/mcp-admin-ui --ignore-scripts --no-audit --no-fund
npm test --prefix packages/mcp-admin-ui
npm run build --prefix packages/mcp-admin-ui
node packages/mcp-admin-ui/tests/build-closure.mjs
npm run browser:install --prefix packages/mcp-admin-ui
UI_EVIDENCE_DIR=/tmp/woow-ui-evidence npm run test:browser --prefix packages/mcp-admin-ui -- --output=/tmp/woow-ui-results
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/tool_inventory.py
# The unchanged UID10001 nondumpable proof needs chown/setuid from UID0.
# Elevate only pytest on this disposable runner; keep installs and UI unprivileged.
# The provenance tests run Git under sudo. Confirm that this exact view has the
# pinned history; the checkout user's earlier unshallow check is insufficient.
ci_repo=$(pwd -P)
git_as_pytest_root() {
  sudo -n -- env -u GIT_DIR -u GIT_COMMON_DIR -u GIT_WORK_TREE \
    -u GIT_SHALLOW_FILE -u GIT_OBJECT_DIRECTORY -u GIT_ALTERNATE_OBJECT_DIRECTORIES \
    -u GIT_GRAFT_FILE git -c "safe.directory=$ci_repo" "$@"
}
runner_git_dir=$(git rev-parse --absolute-git-dir)
root_git_dir=$(git_as_pytest_root rev-parse --absolute-git-dir)
runner_head=$(git rev-parse HEAD)
root_head=$(git_as_pytest_root rev-parse HEAD)
printf 'runner gitdir=%s head=%s shallow=%s\n' \
  "$runner_git_dir" "$runner_head" "$(git rev-parse --is-shallow-repository)"
printf 'sudo gitdir=%s head=%s shallow=%s\n' \
  "$root_git_dir" "$root_head" "$(git_as_pytest_root rev-parse --is-shallow-repository)"
test "$runner_git_dir" = "$root_git_dir"
test "$root_git_dir" = "$ci_repo/.git"
test "$runner_head" = "$root_head"
if [ "$(git_as_pytest_root rev-parse --is-shallow-repository)" = true ]; then
  sudo -n -- env -u GIT_DIR -u GIT_COMMON_DIR -u GIT_WORK_TREE \
    -u GIT_SHALLOW_FILE -u GIT_OBJECT_DIRECTORY -u GIT_ALTERNATE_OBJECT_DIRECTORIES \
    -u GIT_GRAFT_FILE GIT_TERMINAL_PROMPT=0 \
    git -c "safe.directory=$ci_repo" -c credential.helper= \
    fetch --unshallow --no-tags origin
fi
test "$(git_as_pytest_root rev-parse --is-shallow-repository)" = false
git_as_pytest_root merge-base --is-ancestor d6403f263f5246288864c15381c2d1bddbb9179c HEAD
git_as_pytest_root merge-base --is-ancestor 607d6a5c886113be6e9bc83f1418c6a64e895974 HEAD
sudo -n -- env -u GIT_DIR -u GIT_COMMON_DIR -u GIT_WORK_TREE \
  -u GIT_SHALLOW_FILE -u GIT_OBJECT_DIRECTORY -u GIT_ALTERNATE_OBJECT_DIRECTORIES \
  -u GIT_GRAFT_FILE PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -m pytest -q -p no:cacheprovider tests \
  --junitxml=/tmp/woow-unit-results.xml
python3 packaging/check_results.py /tmp/woow-unit-results.xml
