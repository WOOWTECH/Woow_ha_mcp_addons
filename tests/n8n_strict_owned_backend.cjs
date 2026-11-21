'use strict';
// Test-only transport redirect, after the real strict policy validates the public
// literal and the pinned agent checks its origin. Never contact the public IP.
const net = require('node:net');
const connect = net.Socket.prototype.connect;
const port = Number(process.env.OWNED_N8N_BACKEND_PORT);
if (!Number.isInteger(port) || port < 1 || port > 65535) throw Error('invalid owned backend port');
net.Socket.prototype.connect = function (...args) {
  const options = Array.isArray(args[0]) ? args[0][0] : args[0];
  if (options && typeof options === 'object' && options.host === '8.8.8.8' && Number(options.port) === port) {
    options.host = '127.0.0.1';
    if (options.hostname === '8.8.8.8') options.hostname = '127.0.0.1';
  }
  return connect.apply(this, args);
};
