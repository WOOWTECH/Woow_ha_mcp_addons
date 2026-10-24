"""0.2.1 (owner decision 2026-10-15): the n8n child runs with WEBHOOK_SECURITY_MODE=permissive, the pinned n8n-mcp
2.92.1's widest webhook/URL mode (dist/utils/ssrf-protection.js, byte-identical to 2.91.0's), so n8n_test_workflow and
the official-MCP calls reach an n8n on the HA network (0.2.0: "SSRF protection: IPv6 private address not allowed" for
fd0c:ac1e:2100::11). Only the cloud metadata host names stay blocked upstream. The other products' backend policies are
unchanged.
"""
import json
from pathlib import Path
import subprocess

import pytest

from mcp_admin_core.products import ProductState
from n8n_adapter import child_spec

ROOT = Path(__file__).resolve().parents[1]


def test_child_runs_in_permissive_webhook_mode(tmp_path):
    state = ProductState(product='n8n', token='a' * 43, child_token='b' * 43)
    assert child_spec(state, tmp_path).env['WEBHOOK_SECURITY_MODE'] == 'permissive'
    configured = state.model_copy(update={'backend_url': 'http://172.30.33.10:5678', 'backend_key': 'api-key-0815'})
    assert child_spec(configured, tmp_path).env['WEBHOOK_SECURITY_MODE'] == 'permissive'


@pytest.mark.parametrize('url,permissive', [
    ('http://172.30.33.10:5678/webhook/test', True), ('http://[fd0c:ac1e:2100::11]:5678/webhook/test', True),
    ('http://127.0.0.1:5678/webhook/test', True), ('http://169.254.169.254/latest', False)])
def test_pinned_n8n_mcp_permissive_mode_reaches_private_addresses_only_metadata_stays_blocked(url, permissive):
    code = ("const {SSRFProtection} = require(process.argv[1]);"
            "(async () => { const out = {};"
            " for (const mode of ['strict', 'permissive']) { process.env.WEBHOOK_SECURITY_MODE = mode;"
            "  out[mode] = [await SSRFProtection.validateWebhookUrl(process.argv[2]), SSRFProtection.validateUrlSync(process.argv[2])]; }"
            " console.log(JSON.stringify(out)); })();")
    module = ROOT / 'apps/n8n/node_modules/n8n-mcp/dist/utils/ssrf-protection.js'
    result = subprocess.run(['node', '-e', code, str(module), url], capture_output=True, text=True, timeout=20,
                            env={'PATH': '/usr/local/bin:/usr/bin:/bin'}, cwd=ROOT)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout.strip().splitlines()[-1])
    assert out['strict'][0]['valid'] is False  # what 0.2.0 answered ("IPv6 private address not allowed" ...)
    assert out['permissive'][0]['valid'] is permissive and out['permissive'][1]['valid'] is permissive, out
