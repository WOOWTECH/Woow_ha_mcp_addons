// Test-only: let the fixed n8n child reach its test's owned ephemeral loopback
// backend. Never copied into an image; production strict SSRF is tested separately.
'use strict';
const path = require('path');
const pkg = path.resolve(__dirname, '../apps/n8n/node_modules/n8n-mcp/dist');
const {N8nApiClient} = require(path.join(pkg, 'services/n8n-api-client.js'));
const {SSRFProtection} = require(path.join(pkg, 'utils/ssrf-protection.js'));
N8nApiClient.prototype.getPinnedAgents = async function () {
  const expected = new URL(process.env.N8N_API_URL);
  const requested = new URL(this.baseUrl);
  if (expected.hostname !== '127.0.0.1' || expected.protocol !== 'http:' ||
      !expected.port || Number(expected.port) < 1024 || expected.href !== requested.href)
    throw Error('owned test backend required');
  return SSRFProtection.createPinnedAgents([{address: '127.0.0.1', family: 4}]);
};
