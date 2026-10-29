// This is the only product/form and policy wire-format compatibility boundary.
export const products = {
  odoo: { name: 'Odoo', fields: [['url', '後端 URL', 'url'], ['database', '資料庫', 'name'], ['username', '使用者名稱', 'name'], ['password', '密碼', 'secret']] },
  'odoo-manage': { name: 'Odoo Manage', fields: [['url', '後端 URL', 'url'], ['database', '資料庫', 'name'], ['username', '使用者名稱', 'name'], ['api_key', 'API 金鑰', 'secret'], ['mode', '存取模式', 'mode']] },
  n8n: { name: 'n8n', fields: [['url', 'n8n 伺服器 URL', 'url'], ['key', 'API 金鑰', 'secret'], ['mcp_access_token', 'MCP Access Token（選填；n8n 設定 → Instance-level MCP）', 'optional-secret']] },
  hermes: { name: 'Hermes', fields: [['gateway_url', 'Gateway URL', 'url'], ['gateway_api_key', 'Gateway API 金鑰', 'secret'], ['dashboard_url', 'Dashboard URL（選填）', 'optional-url'], ['dashboard_username', 'Dashboard 使用者（選填）', 'optional-name'], ['dashboard_password', 'Dashboard 密碼（選填）', 'optional-secret']] },
  opendesign: { name: 'OpenDesign', fields: [['url', 'OpenDesign URL', 'url']] },
  emqx: { name: 'EMQX', fields: [['url', 'Broker 基底 URL（不含 /api/v5）', 'url'], ['api_key', 'API 金鑰', 'secret'], ['api_secret', 'API Secret', 'secret']] },
  litellm: { name: 'LiteLLM', fields: [['url', 'Proxy 基底 URL', 'url'], ['master_key', 'Master Key', 'secret']] },
  nextcloud: { name: 'Nextcloud', fields: [['url', 'Nextcloud 根網址', 'url'], ['username', '使用者名稱', 'name'], ['app_password', 'App 密碼（非登入密碼）', 'secret']] },
};

export class UiError extends Error {}
const tokenMaskPattern = /^[A-Za-z0-9_-]{4}\*{20}[A-Za-z0-9_-]{4}$/;
export function maskedCurrentToken(bootstrap) {
  const value = bootstrap?.token_masked;
  if (value === undefined) return null; // Earlier HA servers did not expose a mask.
  return typeof value === 'string' && (value === '' || tokenMaskPattern.test(value)) ? value : null;
}
export function tokenHistory(bootstrap) {
  const entries = bootstrap?.token_history;
  if (entries === undefined) return []; // Earlier HA servers did not expose a history.
  if (!Array.isArray(entries) || entries.length > 5) return null;
  const keys = ['action', 'previous_token_masked', 'rotated_at'];
  if (!entries.every(item => item && typeof item === 'object' && !Array.isArray(item) &&
      Object.keys(item).sort().join() === keys.join() && ['rotate', 'revoke'].includes(item.action) &&
      typeof item.rotated_at === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$/.test(item.rotated_at) &&
      typeof item.previous_token_masked === 'string' &&
      (item.previous_token_masked === '' || tokenMaskPattern.test(item.previous_token_masked)))) return null;
  return entries;
}
export const odooSwitchKeys = ['enable_writes', 'allow_direct_writes', 'allow_unknown_methods', 'chatter_direct'];
export function odooSwitches(bootstrap) {
  if (bootstrap?.product !== 'odoo' || !['saved', 'legacy_all_on'].includes(bootstrap.odoo_write_switches_source)) return null;
  const value = bootstrap.odoo_write_switches;
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      Object.keys(value).sort().join() !== [...odooSwitchKeys].sort().join() ||
      !odooSwitchKeys.every(key => typeof value[key] === 'boolean')) return null;
  return value;
}
export function odooSwitchPayload(bootstrap, values) {
  if (!odooSwitches(bootstrap) || !values || typeof values !== 'object' ||
      Object.keys(values).sort().join() !== [...odooSwitchKeys].sort().join() ||
      !odooSwitchKeys.every(key => typeof values[key] === 'boolean')) throw new UiError('Odoo 子操作開關格式不相容；未送出變更。');
  return { odoo_write_switches: Object.fromEntries(odooSwitchKeys.map(key => [key, values[key]])) };
}
const exactOdooMethod = /^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\.[A-Za-z][A-Za-z0-9_]*$/;
function validMethods(value) {
  return Array.isArray(value) && value.length <= 128 && new Set(value).size === value.length &&
    value.every(item => typeof item === 'string' && item.length <= 256 && exactOdooMethod.test(item)) &&
    JSON.stringify(value).length <= 16384;
}
export function odooMethods(bootstrap) {
  if (bootstrap?.product !== 'odoo' || !['saved','legacy_empty'].includes(bootstrap.odoo_allowed_methods_source) ||
      !validMethods(bootstrap.odoo_allowed_methods)) return null;
  return bootstrap.odoo_allowed_methods;
}
export function odooMethodsPayload(bootstrap, text) {
  if (!odooMethods(bootstrap) || typeof text !== 'string') throw new UiError('此伺服器尚未提供精確方法允許清單。');
  const methods = text.trim() === '' ? [] : text.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  if (!validMethods(methods)) throw new UiError('請每行填寫一個不重複的 model.method；最多 128 項，不接受萬用字元或私有方法。');
  return {odoo_allowed_methods:methods};
}
export function mountPath(value) {
  if (typeof value !== 'string' || value.length > 512 || (value !== '' && !/^(\/[A-Za-z0-9_-]+)+$/.test(value))) {
    throw new UiError('管理介面掛載路徑無效。請從原服務入口重新開啟。');
  }
  return value;
}
export function explicitUrl(value, endpoint = false) {
  if (typeof value !== 'string' || value.length > 2048 || /[\s\\\x00-\x20\x7f]/.test(value)) throw new UiError('請填寫不含憑證、空白或查詢參數的 HTTP(S) URL。');
  let u;
  try { u = new URL(value); } catch { throw new UiError('請填寫完整 HTTP(S) URL。'); }
  if (!['http:', 'https:'].includes(u.protocol) || !u.hostname || u.username || u.password || u.search || u.hash || value.includes('?') || value.includes('#')) throw new UiError('URL 不可包含憑證、查詢參數或片段。');
  const clean = value.replace(/\/+$/, '');
  if (endpoint && !clean.endsWith('/mcp')) throw new UiError('MCP 端點必須以 /mcp 結尾。');
  return clean;
}
export function backendPayload(product, action, values) {
  if (action === 'preserve') return null; // No API request: old API cannot preserve individual secrets.
  if (action === 'clear') return product === 'n8n' ? { url: null, key: null } : { connection: null };
  if (action !== 'replace' || !Object.hasOwn(products, product)) throw new UiError('不支援的連線設定。');
  const connection = {};
  for (const [key, label, type] of products[product].fields) {
    const value = values[key] ?? '';
    if (type === 'mode') {
      if (!['read', 'module'].includes(value)) throw new UiError('存取模式需為 read 或 module。');
      connection[key] = value; continue;
    }
    if (type.startsWith('optional') && value === '') { connection[key] = null; continue; }
    if (!value) throw new UiError(`請填寫${label}。`);
    if (type.includes('url')) connection[key] = explicitUrl(value);
    else if (type.includes('secret')) {
      if (!/^[\x20-\x7e]{1,8192}$/.test(value)) throw new UiError(`${label}需為 1–8192 個可列印 ASCII 字元。`);
      connection[key] = value; // Never trim credential bytes.
    } else {
      if (!/^[A-Za-z0-9_@. -]{1,256}$/.test(value)) throw new UiError(`${label}格式不符（限英數及 _ @ . 空白 -）。`);
      connection[key] = value;
    }
  }
  if (product === 'hermes') {
    const dashboard = ['dashboard_url', 'dashboard_username', 'dashboard_password'].map(k => connection[k]);
    if (dashboard.some(v => v !== null) && dashboard.some(v => v === null)) throw new UiError('Dashboard URL、使用者與密碼需整組提供，或全部留空。');
  }
  if (product === 'emqx' && connection.url.endsWith('/api/v5')) throw new UiError('請使用 Broker 基底 URL，不含 /api/v5。');
  // The Nextcloud child strips both and refuses an empty result: never save blank or padded values.
  if (product === 'nextcloud') {
    // An internationalized host is sent by the browser/httpx as xn--; the backend policy compares hosts exactly, so
    // only the ASCII form can work: show it instead of a generic refusal from the server.
    const authority = connection.url.split('://')[1].split('/')[0];
    const parsed = new URL(connection.url);
    // Compare the host as typed with the browser's (xn--) hostname; only a non-ASCII host differs this way.
    if (/[^\x00-\x7f]/.test(authority) && parsed.hostname !== authority.replace(/:\d+$/, '').toLowerCase()) {
      throw new UiError(`主機名稱含非 ASCII 字元，請改填 xn-- 形式：${connection.url.replace(authority, parsed.host)}`);
    }
  }
  if (product === 'nextcloud' && ['username', 'app_password'].some(k => connection[k].trim() === '' || connection[k] !== connection[k].trim())) throw new UiError('使用者名稱與 App 密碼不可空白，前後也不可有空白。');
  return product === 'n8n' ? connection : { connection };
}

export function backendEdit(bootstrap) {
  const value = bootstrap?.backend_edit;
  if (!Object.hasOwn(products, bootstrap?.product ?? '') || value?.contract !== 'woow-connection-patch-v1' ||
      !value.values || !value.secret_set || typeof value.values !== 'object' || typeof value.secret_set !== 'object' ||
      Array.isArray(value.values) || Array.isArray(value.secret_set)) return null;
  const fields = products[bootstrap.product].fields;
  const publicNames = fields.filter(([, , type]) => !type.includes('secret')).map(([name]) => name).sort();
  const secretNames = fields.filter(([, , type]) => type.includes('secret')).map(([name]) => name).sort();
  if (Object.keys(value.values).sort().join() !== publicNames.join() || Object.keys(value.secret_set).sort().join() !== secretNames.join() ||
      !Object.values(value.values).every(v => v === null || typeof v === 'string') ||
      !Object.values(value.secret_set).every(v => typeof v === 'boolean')) return null;
  if (value.withheld_fields !== undefined && (!Array.isArray(value.withheld_fields) ||
      new Set(value.withheld_fields).size !== value.withheld_fields.length ||
      !value.withheld_fields.every(name => publicNames.includes(name) && value.values[name] === null))) return null;
  return value;
}

export function backendPatchPayload(bootstrap, selections, values) {
  if (!bootstrap.connection_configured || !backendEdit(bootstrap)) throw new UiError('此伺服器尚未提供個別欄位修改。');
  const changes = {};
  for (const [key, label, type] of products[bootstrap.product].fields) {
    const action = selections[key];
    if (action === 'keep') continue;
    if (action === 'clear' && type.startsWith('optional')) { changes[key] = null; continue; }
    if (action !== 'set' || typeof values[key] !== 'string' || values[key] === '') throw new UiError(`請提供${label}的新值。`);
    const value = values[key];
    if (type.includes('url')) changes[key] = explicitUrl(value);
    else if (type.includes('secret')) {
      if (!/^[\x20-\x7e]{1,8192}$/.test(value)) throw new UiError(`${label}格式不符。`);
      changes[key] = value;
    } else if (type === 'mode') {
      if (!['read', 'module'].includes(value)) throw new UiError('存取模式格式不符。');
      changes[key] = value;
    } else {
      if (!/^[A-Za-z0-9_@. -]{1,256}$/.test(value)) throw new UiError(`${label}格式不符。`);
      changes[key] = value;
    }
  }
  return Object.keys(changes).length ? {changes} : null;
}

export function n8nSession(bootstrap) {
  const value = bootstrap?.n8n_session;
  if (bootstrap?.product !== 'n8n' || !['legacy_default', 'saved'].includes(bootstrap.n8n_session_source) ||
      !value || Object.keys(value).sort().join() !== 'max_sessions,timeout_seconds' ||
      !Number.isInteger(value.timeout_seconds) || value.timeout_seconds < 60 || value.timeout_seconds > 86400 ||
      !Number.isInteger(value.max_sessions) || value.max_sessions < 1 || value.max_sessions > 100) return null;
  return value;
}

export function n8nSessionPayload(bootstrap, values) {
  if (!n8nSession(bootstrap)) throw new UiError('此伺服器尚未提供 n8n 連線設定。');
  const parsed = {};
  for (const key of ['timeout_seconds', 'max_sessions']) {
    if (typeof values[key] !== 'string' || !/^[0-9]+$/.test(values[key])) throw new UiError('請填寫有效的整數設定。');
    parsed[key] = Number(values[key]);
  }
  if (!n8nSession({...bootstrap, n8n_session: parsed})) throw new UiError('逾時需為 60–86400 秒，連線上限需為 1–100。');
  return {n8n_session: parsed};
}

// Exact production v3 contract. Unknown/legacy contracts cannot save policy:
// global false alone would leave hidden exact grants active on a v3 server.
export function granularPolicy(b) {
  if (b.policy_contract !== 'woow-v3-exact-grants' || !Array.isArray(b.enabled_write_tools) || !Array.isArray(b.disabled) || typeof b.writes_enabled !== 'boolean' || !b.tools || typeof b.tools !== 'object') return false;
  const available = [];
  for (const [name, t] of Object.entries(b.tools)) {
    if (!t || typeof t.write !== 'boolean' || typeof t.legacy_write !== 'boolean' || !Array.isArray(t.write_grants) || !t.inputSchema || typeof t.inputSchema !== 'object' || !(t.operation_parameter === null || typeof t.operation_parameter === 'string')) return false;
    if (t.write_grants.some(g => typeof g !== 'string' || !(t.write && g === name || t.operation_parameter && g.startsWith(`${name}:`) && g.length > name.length + 1))) return false;
    if (new Set(t.write_grants).size !== t.write_grants.length || (t.write && !t.write_grants.includes(name))) return false;
    available.push(...t.write_grants);
  }
  return b.enabled_write_tools.every(g => typeof g === 'string' && available.includes(g)) && new Set(b.enabled_write_tools).size === b.enabled_write_tools.length;
}
export function toolRows(bootstrap) {
  return Object.entries(bootstrap.tools ?? {}).map(([name, tool]) => ({
    name, write: tool.write === true, legacy: tool.legacy_write === true, classified: typeof tool.write === 'boolean',
    operations: Array.isArray(tool.write_grants) ? tool.write_grants.filter(g => typeof g === 'string' && g.startsWith(`${name}:`)).map(g => g.slice(name.length + 1)) : [],
    auditedOperations: Array.isArray(tool.operations) ? tool.operations : [],
  }));
}
export function operationPolicy(b) {
  if (!granularPolicy(b) || !b.denied_operations || typeof b.denied_operations !== 'object' || Array.isArray(b.denied_operations)) return false;
  if (!Object.entries(b.denied_operations).every(([name, ops]) => /^[A-Za-z0-9_]{1,128}$/.test(name) && Array.isArray(ops) && ops.length > 0 &&
    ops.every(op => typeof op === 'string' && /^[A-Za-z0-9_.-]{1,128}$/.test(op)) && new Set(ops).size === ops.length)) return false;
  return Object.values(b.tools).every(t => Array.isArray(t.operations) &&
    t.operations.every(op => op && typeof op.name === 'string' && typeof op.write === 'boolean') &&
    new Set(t.operations.map(op => op.name)).size === t.operations.length &&
    (!t.operations.length || typeof t.operation_parameter === 'string') &&
    (t.default_operation === null || t.operations.some(op => op.name === t.default_operation)));
}
export function staleOperationDenies(b) {
  return Object.entries(b.denied_operations ?? {}).flatMap(([tool, operations]) =>
    operations.filter(op => !(Object.hasOwn(b.tools, tool) && b.tools[tool].operations?.some(item => item.name === op)))
      .map(operation => ({ tool, operation })));
}
export function policyFingerprint(b) {
  return JSON.stringify([b.product, b.policy_contract, b.tools, b.disabled, b.writes_enabled, b.enabled_write_tools, b.denied_operations]);
}
export function savedGrant(b, row, operation) {
  return b.enabled_write_tools.includes(operation === null ? row.name : `${row.name}:${operation}`) || operation === null && row.legacy && b.writes_enabled;
}
export function effectiveGrant(b, row, operation) {
  return !b.disabled.includes(row.name) && !b.denied_operations?.[row.name]?.includes(operation) && savedGrant(b, row, operation);
}
export function policySummary(b) {
  const rows = toolRows(b);
  const grants = rows.flatMap(row => (row.write ? [null] : []).concat(row.operations)
    .map(operation => effectiveGrant(b, row, operation)));
  const denies = Object.values(b.denied_operations ?? {}).reduce((sum, ops) => sum + ops.length, 0);
  return `目前已儲存政策：停用 ${b.disabled?.length ?? 0} 個工具，允許 ${grants.filter(Boolean).length} / ${grants.length} 項寫入授權。${Object.hasOwn(b, 'denied_operations') ? `已禁止 ${denies} 項操作。` : ''}`;
}
export function catalogSummary(catalog) {
  if (!catalog) return '尚未取得工具能力快照。';
  const tools = `目錄 ${catalog.catalog_count} · 政策允許 ${catalog.policy_enabled_count} · 子行程有效 ${catalog.effective_count ?? '未知'}`;
  if (!Object.hasOwn(catalog, 'operation_count')) return tools;
  return `${tools}；操作目錄 ${catalog.operation_count ?? '未知'} · 已儲存政策允許 ${catalog.policy_enabled_operation_count ?? '未知'} · 子行程有效 ${catalog.effective_operation_count ?? '未知'}`;
}
export function operationSummary(operation) {
  const policy = operation.policy_enabled === true ? '已儲存政策允許' : operation.policy_enabled === false ? '已儲存政策禁止' : '已儲存政策未知';
  const effective = operation.effective === true ? '子行程有效' : operation.effective === false ? '子行程未生效' : '子行程有效狀態未知';
  return `${operation.name} · ${operation.write ? '寫入' : '讀取'} · ${policy} · ${effective}`;
}
export function conditionalWriteSummary(rule) {
  const policy = rule.policy_enabled === true ? '允許' : rule.policy_enabled === false ? '禁止' : '未知';
  return `${rule.parameter} 正規化後為 true 時，表示要將工作流程開放給 MCP 存取；需要 ${rule.requires_tool}；相依權限：已儲存政策${policy}。`;
}
export function environmentLabels(snapshot) {
  return {
    deployment: ({ 'ha-addon': 'HA 管理介面', builtin: '內建 MCP 管理', paas: 'PaaS 管理介面' })[snapshot?.deployment?.kind] ?? 'MCP 管理介面',
    authority: ({ 'ha-admin': 'HA 管理員授權', 'ha-ingress': 'Ingress 存取授權', 'paas-password': 'PaaS 管理授權' })[snapshot?.admin?.authority] ?? '伺服器端管理授權',
  };
}
export function policyPayload(bootstrap, disabled, grants, denies) {
  if (!granularPolicy(bootstrap)) throw new UiError('工具授權版本不相容。請重新整理，未送出變更。');
  const rows = toolRows(bootstrap);
  if (disabled.some(name => !rows.some(row => row.name === name))) throw new UiError('工具清單已變更，請重新整理。');
  const enabled = new Set();
  for (const { tool, operation } of grants) {
    const row = rows.find(r => r.name === tool);
    const grant = operation === null ? tool : `${tool}:${operation}`;
    if (!row?.classified || disabled.includes(tool) || !bootstrap.tools[tool].write_grants.includes(grant)) throw new UiError('寫入授權與工具定義不符。');
    enabled.add(grant);
  }
  const result = { writes_enabled: false, disabled, enabled_write_tools: [...enabled] };
  if (Object.hasOwn(bootstrap, 'denied_operations')) {
    if (!operationPolicy(bootstrap)) throw new UiError('操作限制版本不相容。請重新整理，未送出變更。');
    // No new controls supplied: preserve all saved restrictions. An explicit
    // selection replaces only audited entries; stale entries survive UI edits.
    if (denies === undefined) result.denied_operations = structuredClone(bootstrap.denied_operations);
    else {
      const entries = new Map();
      for (const {tool, operation} of denies) {
        if (!Object.hasOwn(bootstrap.tools, tool) || !bootstrap.tools[tool].operations.some(op => op.name === operation)) throw new UiError('操作限制與工具定義不符。');
      }
      for (const {tool, operation} of [...staleOperationDenies(bootstrap), ...denies]) {
        if (!entries.has(tool)) entries.set(tool, new Set());
        entries.get(tool).add(operation);
      }
      result.denied_operations = Object.fromEntries([...entries].map(([tool, ops]) => [tool, [...ops]]));
    }
  } else if (denies?.length) throw new UiError('伺服器不支援操作限制。');
  return result;
}
export function clientExample(endpoint, token = null) {
  return JSON.stringify({ mcpServers: { woow: { type: 'http', url: endpoint ? explicitUrl(endpoint, true) : 'https://YOUR-MCP-HOST:PORT/mcp', headers: { Authorization: `Bearer ${token ?? '<YOUR_ADDON_TOKEN>'}` } } } }, null, 2);
}
// 0.1.12: Claude.ai custom connectors cannot send an Authorization header. The gateway also accepts the add-on token
// as a path segment: <the saved /mcp endpoint without its final /mcp>/private_<token>/mcp. Built only from the
// explicitly saved endpoint (never this page's origin) and only from a freshly revealed token.
export function claudeConnectorUrl(endpoint, token) {
  if (typeof token !== 'string' || !/^[A-Za-z0-9_-]{43}$/.test(token)) throw new UiError('權杖格式不符，未產生連線網址。');
  if (!endpoint) throw new UiError('尚未設定 MCP 用戶端端點，無法產生 Claude.ai 連線網址。');
  const clean = explicitUrl(endpoint, true);
  return `${clean.slice(0, -'/mcp'.length)}/private_${token}/mcp`;
}

// Owner decision 2026-10-27: the one-time all-on migration of a legacy installation reports itself here
// (bootstrap.owner_defaults). Names and times only; a malformed notice is refused rather than half shown.
const NOTICE_TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$/;
const noticeNames = value => Array.isArray(value) && value.length <= 512
  && value.every(item => typeof item === 'string' && item.length > 0 && item.length <= 300);
const noticeSwitch = value => Array.isArray(value) && value.length === 2 && value.every(item => typeof item === 'boolean');
export function ownerDefaultsView(value) {
  if (value === undefined || value === null) return null;
  const invalid = () => { throw new UiError('升級通知格式不相容。請重新整理；未送出任何變更。'); };
  const time = (item, required = false) => (item === null && !required) || (typeof item === 'string' && NOTICE_TIME.test(item));
  if (typeof value !== 'object' || Array.isArray(value) || value.applied !== 'migrated' || !time(value.at, true)
      || ![1, 2, 3].includes(value.from_schema) || !time(value.restored_at) || !time(value.acknowledged_at)
      || typeof value.notice !== 'boolean' || !['available', 'missing', 'invalid'].includes(value.recovery)) invalid();
  if (value.upgrade !== null && (typeof value.upgrade !== 'object' || typeof value.upgrade.changed !== 'boolean'
      || !noticeSwitch(value.upgrade.writes_enabled)
      || ['enabled_tools', 'granted_writes', 'cleared_operation_denies', 'new_tools', 'new_write_operations']
        .some(key => !noticeNames(value.upgrade[key])))) invalid();
  if (value.restore !== null && (typeof value.restore !== 'object' || typeof value.restore.available !== 'boolean'
      || typeof value.restore.policy_changed !== 'boolean' || !noticeSwitch(value.restore.writes_enabled)
      || ['disabled_added', 'write_grants_removed', 'operation_denies_added', 'kept_new_tools']
        .some(key => !noticeNames(value.restore[key])))) invalid();
  if (value.recovery === 'available' && (value.upgrade === null || value.restore === null)) invalid();
  return value;
}
// The server's UTC timestamp as written, without depending on the browser's time zone.
export function noticeTime(value) {
  return typeof value === 'string' && NOTICE_TIME.test(value) ? `${value.slice(0, 10)} ${value.slice(11, 16)}（UTC）` : '時間不明';
}
