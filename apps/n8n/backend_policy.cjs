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
const { AsyncLocalStorage } = require("node:async_hooks");
const runtime = path.join(__dirname, "node_modules/n8n-mcp/dist");
const apiPath = path.join(runtime, "services/n8n-api-client.js");
// This deliberately fails closed on package drift until the adapter is re-audited.
if (crypto.createHash("sha256").update(fs.readFileSync(apiPath)).digest("hex") !==
    "e64be8d3def0623b6710c6e98f7a08ed14a49a1764a5f789def58ea1e900947c") {
    throw new Error("backend adapter requires source review");
}
// The error types/formatter and actual handler are part of this boundary too.
for (const [relative, digest] of [
    ["utils/n8n-errors.js", "efd5783846cf1eb61dbf9387de260e5a1d336ec609bc4c4d5601c369b5d2f20a"],
    ["mcp/handlers-n8n-manager.js", "0d99e10ec1eb9a6e4d78726636aa79f52eb4f3862be506785b794f1aeb9608cc"],
    ["mcp/server.js", "a4dfc41f48282423a610ee9ac45c0374357b7409cdaa4858e11ba58a32b2128c"],
    ["mcp/handlers-official-tools.js", "e85937c58d5a8426d54b1b69598adc83a14648402fc58a8714ef5db8132977cd"],
    ["mcp/official-mcp-access.js", "113d3556e4b93a870b36986a0fce8de45391ce64d7ab4c9f50fd6715eee3c733"],
    ["utils/npm-version-checker.js", "35eb4789eef7766e4516f78caf125542778cf7de33e1fff4bc670c1f1029057a"],
]) {
    if (crypto.createHash("sha256").update(fs.readFileSync(path.join(runtime, relative))).digest("hex") !== digest) {
        throw new Error("public API error boundary requires source review");
    }
}
const { N8nApiClient } = require(apiPath);
const { SSRFProtection } = require(path.join(runtime, "utils/ssrf-protection.js"));
const { N8nApiError } = require(path.join(runtime, "utils/n8n-errors.js"));

function classifyApiError(error) {
    // Only the pinned mapper's typed status/code is authority, never backend
    // message/details (including publish-specific codes inferred from its body).
    let code = "BACKEND_UNAVAILABLE";
    let status;
    if (error instanceof N8nApiError) {
        const codes = new Map([[400, "VALIDATION_ERROR"], [401, "AUTHENTICATION_ERROR"],
            [403, "FORBIDDEN"], [404, "NOT_FOUND"], [429, "RATE_LIMIT_ERROR"]]);
        if (codes.has(error.statusCode)) {
            status = error.statusCode;
            code = codes.get(status);
        } else if (Number.isInteger(error.statusCode) && error.statusCode >= 500 && error.statusCode <= 599) {
            status = error.statusCode;
            code = "SERVER_ERROR";
        } else if (error.code === "NO_RESPONSE") {
            code = "NO_RESPONSE";
        }
    }
    return {status, code};
}
function publicCreateError(error) {
    const {status, code} = classifyApiError(error);
    return new N8nApiError("Workflow creation failed; backend outcome may be unknown.", status, code);
}

// Creation returns metadata only. Rejections must be narrowed BEFORE the real
// handler formats them. Keep upstream cleaner/retry semantics; never fake success
// or claim rollback after a POST, even when its response cannot be accepted.
const createWorkflow = N8nApiClient.prototype.createWorkflow;
N8nApiClient.prototype.createWorkflow = async function (...args) {
    let value;
    try {
        value = await createWorkflow.apply(this, args);
    } catch (error) {
        throw publicCreateError(error);
    }
    if (!value || typeof value.id !== "string" || !/^[A-Za-z0-9_-]{1,128}$/.test(value.id) ||
        typeof value.name !== "string" || value.name.length > 256 ||
        value.active !== false || !Array.isArray(value.nodes) || value.nodes.length > 20) {
        throw new N8nApiError("Backend workflow metadata invalid; creation may have committed.",
            undefined, "BACKEND_INVALID_RESPONSE");
    }
    return {id: value.id, name: value.name, active: false, nodes: value.nodes.map(() => ({}))};
};

// Public formatting is deliberately separate from handleN8nApiError and the
// client's raw-error settings fallback/retry logic. The genuine handlers copy
// details and sometimes catch ordinary exceptions themselves, so merely replacing
// their error text is insufficient. Retain only this per-call typed classification
// at the final boundary; never inspect a returned error/message/details/stack.
const publicMessages = new Map([
    ["VALIDATION_ERROR", "The n8n backend rejected the request."],
    ["AUTHENTICATION_ERROR", "Authentication with the n8n backend failed."],
    ["FORBIDDEN", "The n8n backend denied access to this operation."],
    ["NOT_FOUND", "The requested n8n resource or API route was not found."],
    ["RATE_LIMIT_ERROR", "The n8n backend rate limit was reached. Try again later."],
    ["SERVER_ERROR", "The n8n backend reported a server error."],
    ["NO_RESPONSE", "No response was received from the n8n backend."],
    ["BACKEND_INVALID_RESPONSE", "The n8n backend returned an invalid response."],
    ["BACKEND_UNAVAILABLE", "The n8n operation could not be completed."],
]);
function publicFailure(error, write) {
    const code = error instanceof N8nApiError && error.code === "BACKEND_INVALID_RESPONSE"
        ? "BACKEND_INVALID_RESPONSE" : classifyApiError(error).code;
    return {success: false, code, error: publicMessages.get(code) +
        (write ? " Write outcome may be unknown; verify before retrying." : "")};
}
// Concurrent requests must not share classification, and the context contains
// only a fixed public result, never a raw error. No new client/retry/write occurs.
const publicErrors = new AsyncLocalStorage();
const errors = require(path.join(runtime, "utils/n8n-errors.js"));
errors.getUserFriendlyErrorMessage = function (error) {
    const boundary = publicErrors.getStore();
    const failure = publicFailure(error, boundary?.write === true);
    if (boundary) boundary.failure = failure;
    return failure.error;
};
const handlers = require(path.join(runtime, "mcp/handlers-n8n-manager.js"));
// Audited server.js dispatch: minimal only, and list/create/rename folder actions.
// Other handlers remain withheld by the existing parent policy (65 tools total).
for (const [name, write] of [
    ["handleListWorkflows", false], ["handleGetWorkflowMinimal", false],
    ["handleDeleteWorkflow", true], ["handleListFolders", false],
    ["handleCreateFolder", true], ["handleRenameFolder", true],
    ["handleCreateWorkflow", true],
]) {
    const handler = handlers[name];
    handlers[name] = function (...args) {
        return publicErrors.run({write}, async () => {
            try {
                const result = await handler.apply(this, args);
                // Business data on success is not diagnostic text or a DLP target.
                if (result?.success === true) return result;
                return publicErrors.getStore().failure || publicFailure(undefined, write);
            } catch (error) {
                // Unexpected ordinary rejections also fail closed, never success.
                return publicFailure(error, write);
            }
        });
    };
}

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

require('./metadata_reads.cjs')({runtime, N8nApiClient, publicErrors, publicFailure});
