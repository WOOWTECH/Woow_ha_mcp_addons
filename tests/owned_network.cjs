'use strict';
// Test preload only. Reject before the original net operation (including fetch).
const net = require('node:net');
function check(args) {
  if (Array.isArray(args[0])) args = args[0];
  const first = args[0];
  const port = first && typeof first === 'object' ? first.port : first;
  if (String(port) === '3000') throw Error('test network operation on production port forbidden');
}
function guard(original) {
  return function (...args) { check(args); return original.apply(this, args); };
}
net.Socket.prototype.connect = guard(net.Socket.prototype.connect);
net.Server.prototype.listen = guard(net.Server.prototype.listen);
module.exports = { check, guard };
