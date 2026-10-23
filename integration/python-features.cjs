'use strict';

// Adaptador de transporte para Express. Las tres funcionalidades viven en Python.
const http = require('node:http');
const https = require('node:https');
const { rateLimit } = require('express-rate-limit');

module.exports = function mountPythonFeatures(app, options = {}) {
  const origin = new URL(options.origin || process.env.PERFUME_SERVICE_URL || 'http://127.0.0.1:8000');
  if (!['http:', 'https:'].includes(origin.protocol) || origin.username || origin.password) {
    throw new Error('PERFUME_SERVICE_URL debe ser una URL HTTP(S) sin credenciales.');
  }
  const mount = '/asesor';
  const allowed = new Map([
    ['/', ['GET', 'HEAD']], ['/static/app.js', ['GET', 'HEAD']], ['/static/style.css', ['GET', 'HEAD']],
    ['/api/health', ['GET']], ['/api/options', ['GET']],
    ['/api/recommendations', ['POST']], ['/api/compare', ['POST']], ['/api/chat', ['POST']],
  ]);
  app.get(mount, (req, res, next) => req.path.endsWith('/') ? next() : res.redirect(308, mount + '/'));
  app.use(mount, rateLimit({ windowMs: 60_000, limit: 120, standardHeaders: true, legacyHeaders: false }));
  app.use(mount, (req, res) => {
    const pathname = req.path;
    if (!allowed.get(pathname)?.includes(req.method)) return res.sendStatus(404);
    const target = new URL(pathname, origin);
    // Puede montarse antes o después de express.json(); nunca reenvía cookies/claves.
    const payload = req.body === undefined ? null : Buffer.from(JSON.stringify(req.body));
    const headers = { accept: req.headers.accept || '*/*' };
    if (req.headers['content-type']) headers['content-type'] = req.headers['content-type'];
    if (payload) headers['content-length'] = payload.length;
    const transport = target.protocol === 'https:' ? https : http;
    const upstream = transport.request(target, { method: req.method, headers }, response => {
      res.status(response.statusCode);
      for (const name of ['content-type', 'cache-control', 'content-security-policy', 'x-content-type-options', 'referrer-policy']) {
        if (response.headers[name]) res.setHeader(name, response.headers[name]);
      }
      response.on('error', () => res.destroy());
      response.pipe(res);
    });
    upstream.setTimeout(15000, () => upstream.destroy(new Error('Python timeout')));
    upstream.on('error', () => {
      if (!res.headersSent) res.status(502).json({ detail: 'El asesor no está disponible. Inicia el servicio de Python.' });
      else res.destroy();
    });
    req.on('aborted', () => upstream.destroy());
    if (payload) upstream.end(payload);
    else req.pipe(upstream);
  });
};
