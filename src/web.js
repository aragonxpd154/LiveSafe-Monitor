'use strict';
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { logger } = require('./log');

const log = logger('http');
const PUBLIC = path.join(__dirname, '..', 'public');
const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.svg': 'image/svg+xml' };
const MAX_SSE = 32;
const MAX_MJPEG_PER_CH = 8;

function loadStatic() {
  const files = {};
  const add = (route, file, type) => {
    const body = fs.readFileSync(file);
    files[route] = { body, type, etag: '"' + crypto.createHash('sha1').update(body).digest('hex').slice(0, 16) + '"' };
  };
  for (const f of fs.readdirSync(PUBLIC)) {
    const ext = path.extname(f);
    if (TYPES[ext]) add('/' + f, path.join(PUBLIC, f), TYPES[ext]);
  }
  files['/'] = files['/index.html'];
  // Player HLS servido localmente: o painel funciona sem internet.
  try {
    add('/vendor/hls.js', require.resolve('hls.js/dist/hls.light.min.js'), TYPES['.js']);
  } catch (e) {
    log.warn('hls.js não instalado (rode npm install); o player ao vivo só funcionará no Safari');
  }
  return files;
}

// Servidor HTTP com o módulo nativo do Node (sem Express): menos memória,
// menos dependências e nada para atualizar.
function createServer(app, cfg) {
  const files = loadStatic();
  const auth = cfg.auth && cfg.auth.user ? 'Basic ' + Buffer.from(`${cfg.auth.user}:${cfg.auth.password || ''}`).toString('base64') : null;
  const sse = new Map(); // res -> { interval, last }
  const mjpeg = new Map();

  function json(res, code, obj) {
    res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify(obj));
  }

  function authorized(req) {
    if (!auth) return true;
    const a = Buffer.from(req.headers.authorization || '');
    const b = Buffer.from(auth);
    return a.length === b.length && crypto.timingSafeEqual(a, b);
  }

  function hlsHeaders(name, len) {
    const isList = name.endsWith('.m3u8');
    return {
      'Content-Type': isList ? 'application/vnd.apple.mpegurl' : 'video/mp2t',
      'Content-Length': len,
      'Cache-Control': isList ? 'no-cache' : 'public, max-age=60, immutable',
      'Access-Control-Allow-Origin': '*',
    };
  }

  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, 'http://x');
    const p = url.pathname;

    if (p === '/healthz') {
      const h = app.health();
      return json(res, h.ok ? 200 : 503, h);
    }
    if (!authorized(req)) {
      res.writeHead(401, { 'WWW-Authenticate': 'Basic realm="LiveSafe", charset="UTF-8"' });
      return res.end('Autenticação necessária');
    }

    if (req.method === 'GET' && files[p]) {
      const f = files[p];
      if (req.headers['if-none-match'] === f.etag) {
        res.writeHead(304);
        return res.end();
      }
      res.writeHead(200, { 'Content-Type': f.type, ETag: f.etag, 'Cache-Control': 'no-cache' });
      return res.end(f.body);
    }

    if (req.method === 'GET' && p === '/api/state') return json(res, 200, app.state(true));
    if (req.method === 'GET' && p === '/api/events') {
      const limit = Math.min(500, Math.max(1, Number(url.searchParams.get('limit')) || 100));
      return json(res, 200, app.events.recent(limit));
    }

    if (req.method === 'GET' && p === '/api/stream') {
      if (sse.size >= MAX_SSE) return json(res, 503, { error: 'Muitos painéis abertos' });
      const interval = Math.min(5000, Math.max(250, Number(url.searchParams.get('interval')) || 250));
      res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store', Connection: 'keep-alive', 'X-Accel-Buffering': 'no' });
      res.socket.setNoDelay(true);
      res.write('retry: 3000\n\n');
      res.write(`event: state\ndata: ${JSON.stringify(app.state(true))}\n\n`);
      sse.set(res, { interval, last: Date.now() });
      req.on('close', () => sse.delete(res));
      return;
    }

    if (req.method === 'POST' && p === '/api/test-trap') return json(res, 200, await app.testTrap());

    // Stream ao vivo (HLS) gerado neste Pi.
    let m = p.match(/^\/hls\/([A-Za-z0-9_-]+)\/([A-Za-z0-9_.]+)$/);
    if (m && req.method === 'GET') {
      const ch = app.channel(m[1]);
      const file = ch && ch.hlsFile(m[2]);
      if (!file) return json(res, 404, { error: 'Stream não encontrado' });
      return fs.readFile(file, (err, body) => {
        if (err) return json(res, 404, { error: 'Stream ainda não disponível' });
        res.writeHead(200, hlsHeaders(m[2], body.length));
        res.end(body);
      });
    }

    // Servidor central: repassa pedidos para o Pi do abrigo (com cache).
    m = p.match(/^\/sites\/([A-Za-z0-9_-]+)(\/.*)$/);
    if (m) {
      const site = app.site(m[1]);
      if (!site) return json(res, 404, { error: 'Site não encontrado' });
      const sub = m[2];
      const getOk = /^\/hls\/[A-Za-z0-9_-]+\/(index\.m3u8|seg_\d{1,20}\.ts)$/.test(sub) || /^\/api\/channels\/[A-Za-z0-9_-]+\/(snapshot\.jpg|diagnostics)$/.test(sub);
      const postOk = /^\/api\/channels\/[A-Za-z0-9_-]+\/restart$/.test(sub) || sub === '/api/test-trap';
      let r;
      if (req.method === 'GET' && getOk) r = await site.get(sub);
      else if (req.method === 'POST' && postOk) r = await site.request('POST', sub, '');
      else return json(res, 404, { error: 'Não encontrado' });
      const headers = { 'Content-Type': r.type, 'Content-Length': r.body.length, 'Cache-Control': 'no-store' };
      if (/\.ts$/.test(sub) && r.status === 200) headers['Cache-Control'] = 'public, max-age=60, immutable';
      res.writeHead(r.status, headers);
      return res.end(r.body);
    }

    m = p.match(/^\/api\/channels\/([A-Za-z0-9_-]+)\/(snapshot\.jpg|live\.mjpg|restart|diagnostics)$/);
    if (m) {
      const ch = app.channel(m[1]);
      if (!ch) return json(res, 404, { error: 'Canal não encontrado' });
      const what = m[2];
      if (what === 'snapshot.jpg' && req.method === 'GET') {
        if (!ch.jpeg) return json(res, 404, { error: 'Ainda sem imagem' });
        res.writeHead(200, { 'Content-Type': 'image/jpeg', 'Content-Length': ch.jpeg.length, 'Cache-Control': 'no-store' });
        return res.end(ch.jpeg);
      }
      if (what === 'live.mjpg' && req.method === 'GET') return serveMjpeg(ch, req, res);
      if (what === 'restart' && req.method === 'POST') {
        ch.restart();
        app.events.add({ channel: ch.cfg.id, channelName: ch.cfg.name, type: 'restart', active: false, message: 'Captura reiniciada pelo painel' });
        return json(res, 200, { ok: true });
      }
      if (what === 'diagnostics' && req.method === 'GET') return json(res, 200, ch.diagnostics());
    }

    json(res, 404, { error: 'Não encontrado' });
  });

  // MJPEG contínuo — útil para abrir no VLC ou num multiviewer externo.
  function serveMjpeg(ch, req, res) {
    let set = mjpeg.get(ch.cfg.id);
    if (!set) mjpeg.set(ch.cfg.id, (set = new Set()));
    if (set.size >= MAX_MJPEG_PER_CH) return json(res, 503, { error: 'Muitos clientes neste canal' });
    res.writeHead(200, { 'Content-Type': 'multipart/x-mixed-replace; boundary=livesafe', 'Cache-Control': 'no-store', Connection: 'close' });
    const send = (jpg) => {
      if (res.writableLength > 1024 * 1024) return;
      res.write(`--livesafe\r\nContent-Type: image/jpeg\r\nContent-Length: ${jpg.length}\r\n\r\n`);
      res.write(jpg);
      res.write('\r\n');
    };
    if (ch.jpeg) send(ch.jpeg);
    ch.on('jpeg', send);
    set.add(res);
    req.on('close', () => {
      ch.off('jpeg', send);
      set.delete(res);
    });
  }

  function write(res, msg) {
    if (res.writableLength > 256 * 1024) {
      res.destroy();
      sse.delete(res);
      return;
    }
    res.write(msg);
  }

  // Eventos vão para todos na hora; o estado respeita o intervalo de cada cliente
  // (o servidor central pede 500 ms para economizar o enlace).
  function broadcast(event, data) {
    if (sse.size === 0) return;
    const msg = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
    for (const res of sse.keys()) write(res, msg);
  }

  function pushState(build) {
    if (sse.size === 0) return;
    const now = Date.now();
    let msg = null;
    for (const [res, c] of sse) {
      if (now - c.last < c.interval - 20) continue;
      c.last = now;
      msg = msg || `event: state\ndata: ${JSON.stringify(build())}\n\n`;
      write(res, msg);
    }
  }

  const ka = setInterval(() => {
    for (const res of sse.keys()) res.write(': ka\n\n');
  }, 15000);
  ka.unref();

  server.on('clientError', (err, socket) => socket.destroy());
  server.keepAliveTimeout = 5000;
  server.headersTimeout = 10000;

  return {
    server,
    broadcast,
    pushState,
    clients: () => sse.size,
    listen: () =>
      new Promise((resolve, reject) => {
        server.once('error', reject);
        server.listen(cfg.port, cfg.host, () => {
          log.info(`painel em http://${cfg.host === '0.0.0.0' ? '<ip-desta-máquina>' : cfg.host}:${cfg.port}`);
          resolve();
        });
      }),
    close: () => {
      for (const res of sse.keys()) res.destroy();
      for (const set of mjpeg.values()) for (const res of set) res.destroy();
      return new Promise((r) => server.close(() => r()));
    },
  };
}

module.exports = { createServer };
