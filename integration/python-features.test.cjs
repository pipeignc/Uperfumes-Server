'use strict';

const { before, after, test } = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const express = require('express');
const { JSDOM, VirtualConsole } = require('jsdom');
const mount = require('./python-features.cjs');

let python;
let server;
let base;

async function until(check, timeout = 15000) {
  const deadline = Date.now() + timeout;
  while (!check()) {
    if (Date.now() > deadline) throw new Error('Tiempo agotado esperando la interfaz');
    await new Promise(resolve => setTimeout(resolve, 30));
  }
}

before(async () => {
  python = spawn('.venv/bin/python', ['-m', 'uvicorn', 'python_service.app:app', '--host', '127.0.0.1', '--port', '0'], {
    cwd: require('node:path').resolve(__dirname, '..'), stdio: ['ignore', 'pipe', 'pipe'],
  });
  let logs = '';
  let failed = false;
  python.on('error', error => { logs += error.message; failed = true; });
  python.on('exit', () => { failed = true; });
  python.stdout.on('data', data => { logs += data; });
  python.stderr.on('data', data => { logs += data; });
  await until(() => failed || /Uvicorn running on http:\/\/127\.0\.0\.1:\d+/.test(logs), 30000);
  if (failed) throw new Error(logs);
  const port = logs.match(/Uvicorn running on http:\/\/127\.0\.0\.1:(\d+)/)[1];
  const app = express();
  app.use(express.json({ limit: '32kb' }));
  mount(app, { origin: 'http://127.0.0.1:' + port });
  server = app.listen(0, '127.0.0.1');
  await once(server, 'listening');
  base = `http://127.0.0.1:${server.address().port}`;
});

after(async () => {
  if (server) await new Promise(resolve => server.close(resolve));
  if (python && python.exitCode === null) { python.kill(); await once(python, 'exit'); }
});

test('Express redirige a /asesor/ y limita las rutas del proxy', async () => {
  const response = await fetch(base + '/asesor', { redirect: 'manual' });
  assert.equal(response.status, 308);
  assert.equal(response.headers.get('location'), '/asesor/');
  assert.equal((await fetch(base + '/asesor/docs')).status, 404);
  const health = await (await fetch(base + '/asesor/api/health')).json();
  assert.equal(health.model_status, 'ready');
  assert.equal(health.perfume_count, 236);
});

test('La pantalla ejecuta las tres funcionalidades usando Python real', async () => {
  const errors = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on('jsdomError', error => errors.push(error.message));
  const dom = await JSDOM.fromURL(base + '/asesor/', {
    resources: 'usable', runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole,
    beforeParse(window) { window.fetch = (url, options) => fetch(String(url), options); },
  });
  try {
    const document = dom.window.document;
    const $ = id => document.getElementById(id);
    const submit = id => $(id).dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true }));
    await until(() => $('service-status').textContent.includes('236 perfumes'));
    $('recommend-form').elements.age.value = '19';
    $('climate').value = 'Frío';
    $('occasion').value = 'Oficina/Trabajo';
    $('gender').value = 'Masculino';
    $('recommend-form').elements.budget_clp.value = '142500';
    submit('recommend-form');
    await until(() => document.querySelectorAll('.perfume-card').length === 3);
    assert.match($('recommend-results').textContent, /Sauvage EDP/);
    assert.match($('recommend-results').textContent, /99\.750 CLP/);

    document.querySelector('[data-panel="compare"]').click();
    assert.equal($('compare').hidden, false);
    $('compare-form').elements.query.value = 'sauvage';
    submit('compare-form');
    await until(() => $('compare-results').children.length > 0);
    assert.match($('compare-results').textContent, /Sauvage EDP/);

    document.querySelector('[data-panel="chat"]').click();
    $('chat-message').value = '¿Cuánto cuesta Sauvage EDP?';
    submit('chat-form');
    await until(() => document.querySelectorAll('.bubble.assistant').length === 2);
    assert.match($('chat-log').textContent, /99\.750 CLP/);
    assert.match($('chat-log').textContent, /Precio_Real_USD/);
    assert.deepEqual(errors, []);
  } finally { dom.window.close(); }
});

test('No interpreta texto del usuario como HTML', async () => {
  const response = await fetch(base + '/asesor/api/chat', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: '<script>alert(1)</script>', rate: '950' }),
  });
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.matched, false);
  assert.doesNotMatch(body.answer, /<script>/);
});
