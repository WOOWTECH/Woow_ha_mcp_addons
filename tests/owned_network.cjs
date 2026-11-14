'use strict';
// Test preload only. Reject before the original net operation (including fetch).
// HM-01: the default profile's child port 3000 and the extra profiles' 18000-18099 (multi-profile plan).
const net = require('node:net');
function forbidden(port) {
  // Node's own port reading (validatePort): a number, or a non-blank string read with unary +, so ' 18000',
  // '0x4650' and '18000.0' all name port 18000. A Unix socket path or a handle has no port.
  if (typeof port !== 'number' && typeof port !== 'string') return false;
  if (typeof port === 'string' && port.trim() === '') return false;
  const value = +port;
  return value === 3000 || (Number.isInteger(value) && value >= 18000 && value <= 18099);
}
function check(args) {
  if (Array.isArray(args[0])) args = args[0];
  const first = args[0];
  const port = first && typeof first === 'object' ? first.port : first;
  if (forbidden(port)) throw Error('test network operation on production port forbidden');
}
function guard(original) {
  return function (...args) { check(args); return original.apply(this, args); };
}
net.Socket.prototype.connect = guard(net.Socket.prototype.connect);
net.Server.prototype.listen = guard(net.Server.prototype.listen);
module.exports = { check, forbidden, guard };
