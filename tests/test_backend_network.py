"""Installed Node API client plus loopback fake backend, never production n8n."""
import asyncio
import json
from pathlib import Path

import pytest

from mcp_admin_core.config import Store
from n8n_adapter import child_spec


async def node(store, code):
    spec = child_spec(store.load(), store.directory)
    process = await asyncio.create_subprocess_exec(*spec.argv[:-1], "-e", code,
        cwd=store.directory, env=spec.env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await asyncio.wait_for(process.communicate(), 8)
    assert process.returncode == 0, "Node network policy harness failed (output suppressed)"
    return json.loads(out.decode().splitlines()[-1])


ROOT = Path(__file__).resolve().parents[1] / "apps/n8n/node_modules/n8n-mcp"
IMPORT = f"const {{N8nApiClient}} = require({str(ROOT / 'dist/services/n8n-api-client.js')!r});\n"
CLIENT = "new N8nApiClient({baseUrl: process.env.N8N_API_URL, apiKey: 'DUMMY', maxRetries: 0, timeout: 1000})"


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / "state")
    yield value
    value.close()


@pytest.mark.parametrize("hostname", ["127.0.0.1", "backend.test"])
async def test_installed_client_private_backend_pins_dns_and_denies_redirect(store, hostname):
    calls = []
    handlers = set()
    async def backend(reader, writer):
        handlers.add(asyncio.current_task())
        try:
            request = await reader.readuntil(b"\r\n\r\n")
            calls.append(request)
            if len(calls) == 1:
                body = b'{"data":[],"nextCursor":null}'
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
            else:
                writer.write(b"HTTP/1.1 302 Found\r\nLocation: http://169.254.169.254/latest/meta-data\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            handlers.discard(asyncio.current_task())
    server = await asyncio.start_server(backend, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    store.update(backend_url=f"http://{hostname}:{port}/n8n", backend_key="DUMMY")
    # The resolver would return metadata on a second lookup for the SAME request.
    # An agent doing another DNS lookup during connect would never reach the fake.
    code = IMPORT + '''
const dns = require('node:dns');
let lookups = 0;
if (new URL(process.env.N8N_API_URL).hostname === 'backend.test') {
    dns.promises.lookup = async () => {
        lookups++;
        return [{address: lookups === 1 ? '127.0.0.1' : '169.254.169.254', family: 4}];
    };
    dns.lookup = () => { throw Error('unpinned connection lookup'); };
}
''' + f"const client = {CLIENT};" + '''
(async () => {
    let ok = false, redirectDenied = false, reboundDenied = false;
    try { ok = (await client.listWorkflows({limit: 1})).data.length === 0; } catch {}
    if (lookups) {
        try { await client.listWorkflows({limit: 1}); } catch { reboundDenied = true; }
    } else {
        try { await client.listWorkflows({limit: 1}); } catch { redirectDenied = true; }
    }
    console.log(JSON.stringify({ok, redirectDenied, reboundDenied}));
})();
'''
    try:
        result = await node(store, code)
        assert result["ok"] is True
        if hostname == "backend.test":
            assert result["reboundDenied"] is True and len(calls) == 1
        else:
            assert result["redirectDenied"] is True and len(calls) == 2
        assert all(b"GET /n8n/api/v1/workflows?limit=1 " in call for call in calls)
    finally:
        server.close()
        await server.wait_closed()
        if handlers:
            await asyncio.gather(*handlers)


@pytest.mark.parametrize("address,allowed", [
    ("192.168.1.50", True), ("10.1.2.3", True), ("172.30.32.1", True),
    ("[fd12:3456::1]", True), ("[::1]", True), ("8.8.8.8", True),
    ("169.254.169.254", False), ("169.254.170.2", False), ("100.100.100.200", False),
    ("192.0.0.192", False), ("0.0.0.0", False), ("224.0.0.1", False),
    ("[fd00:ec2::254]", False), ("[::ffff:169.254.169.254]", False),
    ("[64:ff9b::a9fe:a9fe]", False), ("[2002:a9fe:a9fe::1]", False),
    ("[fe80::1]", False), ("[::]", False), ("168.63.129.16", False),
    ("[64:ff9b:1::a9fe:a9fe]", False), ("[2001::a9fe:a9fe]", False),
])
async def test_destination_policy_validation_only_no_connect(store, address, allowed):
    store.update(backend_url=f"http://{address}:5678", backend_key="DUMMY")
    result = await node(store, IMPORT + f"const client = {CLIENT};" + '''
(async () => {
    let allowed = false;
    try { await client.getPinnedAgents(); allowed = true; } catch {}
    console.log(JSON.stringify({allowed}));
})();
''')
    assert result["allowed"] is allowed


@pytest.mark.parametrize("mixed", [False, True])
async def test_backend_origin_and_all_dns_answers_restricted(store, mixed):
    store.update(backend_url="http://backend.test:5678/n8n", backend_key="DUMMY")
    answers = [{"address": "127.0.0.1", "family": 4}]
    if mixed:
        answers.append({"address": "169.254.169.254", "family": 4})
    result = await node(store, IMPORT + "const answers = " + json.dumps(answers) + ''';
const dns = require('node:dns');
dns.promises.lookup = async () => answers;
(async () => {
    const urls = [process.env.N8N_API_URL, 'http://127.0.0.1:9999', 'http://backend.test:5678/other', 'https://backend.test:5678/n8n'];
    const allowed = [];
    for (const baseUrl of urls) {
        try { await new N8nApiClient({baseUrl, apiKey: 'DUMMY'}).getPinnedAgents(); allowed.push(true); }
        catch { allowed.push(false); }
    }
    console.log(JSON.stringify({allowed}));
})();
''')
    assert result["allowed"] == [not mixed, False, False, False]


async def test_webhook_ssrf_stays_strict_and_socket_origin_guard(store):
    store.update(backend_url="http://127.0.0.1:5678", backend_key="DUMMY")
    result = await node(store, IMPORT + f"const client = {CLIENT};" + f'''
const {{SSRFProtection}} = require({str(ROOT / 'dist/utils/ssrf-protection.js')!r});
(async () => {{
    const validation = await SSRFProtection.validateWebhookUrl('http://192.168.1.50:5678');
    const agents = await client.getPinnedAgents();
    let denied = 0;
    for (const options of [{{host: '127.0.0.2', port: 5678}}, {{host: '127.0.0.1', port: 5679}},
                            {{host: '127.0.0.1', port: 5678, protocol: 'https:'}}]) {{
        try {{ agents.httpAgent.createConnection(options); }}
        catch (error) {{ if (error.message === 'configured backend network policy denied') denied++; }}
    }}
    console.log(JSON.stringify({{strict: !validation.valid, denied}}));
}})();
''')
    assert result == {"strict": True, "denied": 3}
