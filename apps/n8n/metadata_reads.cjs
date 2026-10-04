"use strict";
// Narrow adaptations around genuine pinned handlers/client methods, not new RPCs.
// Installed by backend_policy only after all dependency source guards pass.
module.exports = function install({runtime, N8nApiClient, publicErrors, publicFailure}) {
    const path = require('node:path');
    const {N8nApiError} = require(path.join(runtime, 'utils/n8n-errors.js'));
    const handlers = require(path.join(runtime, 'mcp/handlers-n8n-manager.js'));
    const official = require(path.join(runtime, 'mcp/handlers-official-tools.js'));
    const axios = require('axios');
    const segment = /^[A-Za-z0-9_-]{1,128}$/;
    const cursor = /^[A-Za-z0-9_+=-]{1,512}$/;
    const timestamp = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/;
    const invalid = () => { throw new N8nApiError('Invalid metadata response.', undefined, 'BACKEND_INVALID_RESPONSE'); };
    const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
    // Match Pydantic/JSON Schema character bounds, not UTF-16 code units.
    // Stop at max + 1 without allocating an array or normalizing the text.
    function exceedsCodePoints(value, max) {
        let count = 0;
        for (const point of value) {
            if (++count > max) return true;
        }
        return false;
    }
    function text(value, max, pattern) {
        if (typeof value !== 'string' || exceedsCodePoints(value, max) || (pattern && !pattern.test(value)) ||
            /[\x00-\x1f\x7f]/.test(value) ||
            [process.env.N8N_API_KEY, process.env.N8N_API_URL].some(secret => secret && value.includes(secret))) invalid();
        return value;
    }
    function id(value) { return text(value, 128, segment); }
    function inputText(value, max, pattern) {
        if (typeof value !== 'string' || exceedsCodePoints(value, max) || (pattern && !pattern.test(value))) invalid();
    }
    function dateFields(value, result) {
        for (const key of ['createdAt', 'updatedAt', 'startedAt', 'stoppedAt', 'waitTill']) {
            if (value[key] !== undefined) result[key] = value[key] === null ? null : text(value[key], 32, timestamp);
        }
        return result;
    }
    function page(value, limit, project) {
        if (!object(value) || !Array.isArray(value.data) || value.data.length > limit) invalid();
        const result = {data: value.data.map(project)};
        if (value.nextCursor !== undefined && value.nextCursor !== null && value.nextCursor !== '') {
            result.nextCursor = text(value.nextCursor, 512, cursor);
        }
        return result;
    }
    function folder(value) {
        if (!object(value)) invalid();
        const result = {id: id(value.id), name: text(value.name, 256)};
        if (value.parentFolderId !== undefined) result.parentFolderId = value.parentFolderId === null ? null : id(value.parentFolderId);
        return dateFields(value, result);
    }
    function execution(value) {
        if (!object(value) || !['new','running','success','error','canceled','crashed','waiting','unknown'].includes(value.status)) invalid();
        return dateFields(value, {id: id(value.id), workflowId: id(value.workflowId), status: value.status});
    }
    function argsFor(kind, value) {
        if (!object(value)) invalid();
        const allowed = {
            catalog: ['kind','query','limit'], executions: ['action','limit','includeData','cursor','workflowId','projectId','status'],
            health: ['mode'], folder: ['action','projectId','folderId','name'],
        }[kind];
        if (Object.keys(value).some(key => !allowed.includes(key))) invalid();
        const args = {...value};
        if (kind === 'catalog') {
            if (args.kind !== 'tags') invalid();
            if (args.query !== undefined) inputText(args.query,256);
            args.limit ??= 20;
            if (value.limit === null || !Number.isInteger(args.limit) || args.limit < 1 || args.limit > 250) invalid();
        } else if (kind === 'executions') {
            if (args.action !== 'list') invalid();
            args.limit ??= 20;
            if (value.limit === null || !Number.isInteger(args.limit) || args.limit < 1 || args.limit > 100) invalid();
            if (args.includeData !== undefined && args.includeData !== false) invalid();
            args.includeData = false;
            if (args.cursor !== undefined) inputText(args.cursor,512,cursor);
            for (const key of ['workflowId','projectId']) if (args[key] !== undefined) inputText(args[key],128,segment);
            if (args.projectId === 'personal' || (args.status !== undefined && !['success','error','waiting'].includes(args.status))) invalid();
        } else if (kind === 'folder') {
            if (args.action !== 'get' || args.projectId === 'personal' || (args.name !== undefined && args.name !== null)) invalid();
            inputText(args.projectId,128,segment); inputText(args.folderId,128,segment);
        } else if (args.mode !== undefined && args.mode !== 'status') invalid();
        return args;
    }
    // New paths only: one attempt, five-second socket/total deadline, 64 KiB
    // decompressed HTTP body. Reuse the client's original auth/pinning/no-redirect
    // interceptors. Never change the shared client's defaults or old retry paths.
    function boundedClient(client, allowed) {
        const facade = Object.create(client);
        facade.client = {
            defaults: client.client.defaults,
            get: async (url, options = {}) => {
                if (!allowed.includes(url)) invalid();
                const response = await client.client.get(url, {...options, timeout:5000,
                    signal:AbortSignal.timeout(5000), maxContentLength:65536, maxBodyLength:0,
                    maxRedirects:0, __retryCount:client.maxRetries});
                if (url === '/workflows' && (!object(response.data) || !Array.isArray(response.data.data) || response.data.data.length > 1)) invalid();
                return response;
            },
        };
        // Health's version discovery is auxiliary (normally /settings). No need
        // to query it to establish availability; leave old clients untouched.
        facade.getVersion = async () => null;
        return facade;
    }
    for (const [method, kind] of [['listTags','catalog'], ['listExecutions','executions'], ['getFolder','folder'], ['healthCheck','health']]) {
        const original = N8nApiClient.prototype[method];
        N8nApiClient.prototype[method] = async function (...args) {
            const boundary = publicErrors.getStore();
            if (boundary?.metadata !== kind) return original.apply(this,args);
            try {
                const routes = kind === 'catalog' ? ['/tags'] : kind === 'executions' ? ['/executions'] :
                    kind === 'folder' ? [`/projects/${id(args[0])}/folders/${id(args[1])}`] : ['/workflows'];
                if (kind === 'health') boundary.healthUrl = this.client.defaults.baseURL.replace(/\/api\/v\d+\/?$/, '') + '/healthz';
                let result = await original.apply(boundedClient(this,routes),args);
                if (kind === 'catalog') {
                    result = page(result,250, item => {
                        if (!object(item)) invalid();
                        return {id:id(item.id),name:text(item.name,256)};
                    });
                    boundary.hasMore = !!result.nextCursor;
                } else if (kind === 'executions') result = page(result,boundary.limit,execution);
                else if (kind === 'folder') result = folder(result);
                else if (result?.status !== 'ok') invalid();
                return result;
            } catch (error) {
                boundary.failure = publicFailure(error,false);
                // Catalog formats err.message directly; ordinary failures must
                // never reach that formatter with backend content attached.
                throw new N8nApiError(boundary.failure.error,
                    error instanceof N8nApiError ? error.statusCode : undefined, boundary.failure.code);
            }
        };
    }
    // Upstream healthCheck uses global axios.get for /healthz, not its instance.
    // Scope this extra route to the exact derived configured backend URL before
    // any transport/DNS. Agents still enforce original origin and pinning.
    const get = axios.get;
    axios.get = function (url, options) {
        const boundary = publicErrors.getStore();
        if (boundary?.metadata !== 'health') return get.call(this,url,options);
        if (url !== boundary.healthUrl) invalid();
        return get.call(this,url,{...options, timeout:5000, signal:AbortSignal.timeout(5000),
            maxContentLength:65536, maxBodyLength:0, maxRedirects:0});
    };
    // These are explicitly unavailable auxiliary checks, NOT a fake health
    // result. They cannot invoke fetch, DNS or official MCP construction.
    for (const [file, name, unavailable] of [
        ['utils/npm-version-checker.js','checkNpmVersion',{currentVersion:'unavailable',latestVersion:null,isOutdated:false,error:'Auxiliary check disabled'}],
        ['mcp/official-mcp-access.js','buildOfficialMcpHealth',{configured:false}],
    ]) {
        const module = require(path.join(runtime,file));
        const original = module[name];
        module[name] = function (...args) {
            return publicErrors.getStore()?.metadata === 'health' ? Promise.resolve({...unavailable}) : original.apply(this,args);
        };
    }
    for (const [module, name, kind] of [
        [official,'handleListCatalog','catalog'],[handlers,'handleListExecutions','executions'],
        [handlers,'handleGetFolder','folder'],[handlers,'handleHealthCheck','health'],
    ]) {
        const original = module[name];
        module[name] = function (...input) {
            return publicErrors.run({write:false,metadata:kind},async () => {
                const boundary = publicErrors.getStore();
                try {
                    if (kind !== 'health') {
                        input[0] = argsFor(kind,input[0]);
                        boundary.limit = input[0].limit;
                    }
                    const result = await original.apply(this,input);
                    if (result?.success !== true) return boundary.failure || publicFailure(undefined,false);
                    if (kind === 'health') {
                        if (result.data?.status !== 'ok') invalid();
                        return {success:true,data:{status:'ok',scope:'service-availability',authentication:'not-verified'}};
                    }
                    if (kind === 'catalog') return {...result,data:{...result.data,scanLimit:250,hasMore:boundary.hasMore,scope:'first-page'}};
                    if (kind === 'executions') {
                        const {_note, ...data} = result.data;
                        return {success:true,data};
                    }
                    return result;
                } catch (error) { return boundary.failure || publicFailure(error,false); }
            });
        };
    }
    // Defense in depth at private native dispatcher: invalid actions must not
    // reach upstream execution-get fallback, diagnostics, or project discovery.
    const {N8NDocumentationMCPServer} = require(path.join(runtime,'mcp/server.js'));
    const execute = N8NDocumentationMCPServer.prototype.executeTool;
    N8NDocumentationMCPServer.prototype.executeTool = function (name,args) {
        const kind = {'n8n_list_catalog':'catalog','n8n_executions':'executions','n8n_health_check':'health'}[name] ||
            (name === 'n8n_manage_folders' && args?.action === 'get' ? 'folder' : null);
        if (kind) {
            try { args = argsFor(kind,args); }
            catch (error) { return Promise.resolve(publicFailure(error,false)); }
        }
        return execute.call(this,name,args);
    };
};
