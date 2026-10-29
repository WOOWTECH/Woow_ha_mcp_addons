"use strict";
// Execute the pinned server's entire tools/call callback with a fake handler.
// No upstream module initialization, network, database or real n8n service.
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const source = fs.readFileSync(process.argv[2], "utf8");
const input = JSON.parse(process.argv[3]);
const start = "        this.server.setRequestHandler(types_js_1.CallToolRequestSchema,";
const end = "        this.server.setRequestHandler(types_js_1.ListResourcesRequestSchema,";
assert.equal(source.split(start).length, 2);
assert.equal(source.split(end).length, 2);
const registration = source.slice(source.indexOf(start), source.indexOf(end));
let call;
let dispatches = 0;
const noop = () => {};
const context = {
    types_js_1: {CallToolRequestSchema: "tools/call"},
    logger_1: {logger: {info: noop, warn: noop, debug: noop, error: noop}},
    telemetry_1: {telemetry: {trackToolUsage: noop, trackToolSequence: noop, trackError: noop}},
    redaction_1: {summarizeToolCallArgs: () => ({})},
    ui_1: {isUIAppsEnabled: () => false},
    instance_argument_1: {withoutInstanceArgument: args => args},
    server: {setRequestHandler: (schema, handler) => {
        assert.equal(schema, "tools/call");
        call = handler;
    }},
    additionalToolsByName: new Map(),
    getDisabledTools: () => new Set(),
    getDisabledToolOperations: () => new Map(),
    coerceStringifiedJsonParams: (name, args) => args,
    sanitizeValidationResult: result => result,
    executeTool: async (name, args) => {
        assert.equal(name, input.name);
        assert.equal(JSON.stringify(args), "{}");
        dispatches += 1;
        return input.result;
    },
};
vm.runInNewContext(registration, context, {timeout: 1000});
call({params: {name: input.name, arguments: {}}}).then(reply => {
    assert.equal(dispatches, 1);
    process.stdout.write(JSON.stringify(reply));
}).catch(error => { console.error(error); process.exitCode = 1; });
