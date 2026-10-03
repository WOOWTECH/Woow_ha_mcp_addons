"use strict";
// New local adapter code, not copied upstream. Loaded only by our fixed launcher.
// The pinned API client's base backend is trusted configuration, NOT a webhook.
// Do not change WEBHOOK_SECURITY_MODE or the global SSRFProtection validators.
const dns = require("node:dns");
const net = require("node:net");
const crypto = require("node:crypto");
const fs = require("node:fs");
const ipaddr = require("ipaddr.js");
const path = require("node:path");
const runtime = path.join(__dirname, "node_modules/n8n-mcp/dist");
const apiPath = path.join(runtime, "services/n8n-api-client.js");
// This deliberately fails closed on package drift until the adapter is re-audited.
if (crypto.createHash("sha256").update(fs.readFileSync(apiPath)).digest("hex") !==
    "e64be8d3def0623b6710c6e98f7a08ed14a49a1764a5f789def58ea1e900947c") {
    throw new Error("backend adapter requires source review");
}
const { N8nApiClient } = require(apiPath);
const { SSRFProtection } = require(path.join(runtime, "utils/ssrf-protection.js"));

function denied() { throw new Error("configured backend network policy denied"); }
function hostname(value) { return value.toLowerCase().replace(/^\[|\]$/g, ""); }
function backend(value) {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password ||
        url.search || url.hash) denied();
    return url;
}
function allowedAddress(address) {
    if (!net.isIP(address)) return false;
    const parsed = ipaddr.parse(address);
    // Permit only explicit backend unicast, RFC1918/ULA and loopback. Reject
    // link-local, unspecified, multicast, CGNAT, reserved and all IPv6 transition
    // /mapped mechanisms rather than trying to guess their eventual destination.
    const ranges = parsed.kind() === "ipv4" ? ["unicast", "private", "loopback"] :
        ["unicast", "uniqueLocal", "loopback"];
    if (!ranges.includes(parsed.range())) return false;
    // ipaddr.js 1.9.1 does not classify RFC8215 translation prefixes. Public
    // IPv6 must be global-unicast 2000::/3 (and not its classified transition
    // ranges); ULA/loopback above are the only exceptions.
    if (parsed.kind() === "ipv6" && parsed.range() === "unicast" &&
        (parsed.parts[0] & 0xe000) !== 0x2000) return false;
    return !["169.254.169.254", "169.254.170.2", "100.100.100.200", "192.0.0.192",
        "168.63.129.16", "fd00:ec2::254"].includes(parsed.toString());
}

N8nApiClient.prototype.getPinnedAgents = async function () {
    if (!process.env.N8N_API_URL) denied();
    const configured = backend(process.env.N8N_API_URL);
    const requested = backend(this.baseUrl);
    // Match full configured origin AND base path; there is no per-call override.
    if (requested.href.replace(/\/$/, "") !== configured.href.replace(/\/$/, "")) denied();
    const host = hostname(configured.hostname);
    if (["metadata", "metadata.google.internal", "instance-data"].includes(host.replace(/\.$/, ""))) denied();
    const addresses = net.isIP(host) ? [{address: host, family: net.isIP(host)}] :
        await dns.promises.lookup(host, {all: true});
    if (!addresses.length || addresses.some(a => !allowedAddress(a.address) || net.isIP(a.address) !== a.family)) denied();
    // Re-resolve on each API request; check EVERY answer, then pin precisely those
    // answers through the socket connect. No TOCTOU second lookup or DNS cache.
    const agents = SSRFProtection.createPinnedAgents(addresses);
    const port = configured.port || (configured.protocol === "https:" ? "443" : "80");
    for (const agent of [agents.httpAgent, agents.httpsAgent]) {
        const connect = agent.createConnection;
        agent.createConnection = function (options, callback) {
            // Pinned lookup alone does not constrain numeric/absolute URL callers.
            if (hostname(options.hostname || options.host || "") !== host ||
                String(options.port) !== port || (options.protocol || agent.protocol) !== configured.protocol) denied();
            return connect.call(this, options, callback);
        };
    }
    return agents;
};
