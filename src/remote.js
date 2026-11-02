'use strict';
const http = require('http');
const https = require('https');
const EventEmitter = require('events');
const { Hysteresis } = require('./detectors');
const { logger } = require('./log');

// Códigos de trap do servidor central (alarme N, normalizado N + 10).
const COMM_CODE = 6;

// Um Pi remoto (abrigo) visto pelo servidor central.
// - Mantém UMA conexão HTTP (SSE) com o Pi para receber estado e ocorrências.
// - Se ficar sem dados por offlineSeconds, alarma "sem comunicação".
// - Repassa imagens e o stream HLS com cache em memória: N pessoas assistindo
//   o mesmo abrigo geram UM único download no enlace até o Pi.
class Site extends EventEmitter {
  constructor(cfg, opts) {
    super();
    this.cfg = cfg;
    this.log = logger('site:' + cfg.id);
    this.cache = opts.cache;
    this.stateIntervalMs = opts.stateIntervalMs || 500;
    this.offlineMs = opts.offlineSeconds * 1000;
    const u = new URL(cfg.url);
    this.mod = u.protocol === 'https:' ? https : http;
    this.agent = new this.mod.Agent({ keepAlive: true, maxSockets: 8, keepAliveMsecs: 10000 });
    this.headers = cfg.auth ? { Authorization: 'Basic ' + Buffer.from(`${cfg.auth.user}:${cfg.auth.password}`).toString('base64') } : {};

    this.remote = null; // último estado recebido do Pi
    this.offset = 0; // relógio central − relógio do Pi
    this.connected = false;
    this.lastDataAt = 0;
    this.lastError = '';
    this.req = null;
    this.backoff = 1000;
    this.timer = null;
    this.lastSeenId = null;
    this.comm = new Hysteresis(this.offlineMs, 2000);
    this.commSince = 0;
    this.startedAt = Date.now();
    this.stopped = false;
  }

  start() {
    this.connect();
  }

  connect() {
    if (this.stopped) return;
    clearTimeout(this.timer);
    let buf = '';
    const req = this.mod.get(
      `${this.cfg.url}/api/stream?interval=${this.stateIntervalMs}`,
      { agent: false, headers: { ...this.headers, Accept: 'text/event-stream' }, timeout: 15000 },
      (res) => {
        if (res.statusCode !== 200) {
          this.fail(`HTTP ${res.statusCode}${res.statusCode === 401 ? ' — confira user/password do site' : ''}`);
          res.resume();
          return;
        }
        res.setEncoding('utf8');
        this.connected = true;
        this.backoff = 1000;
        this.log.info(`conectado a ${this.cfg.url}`);
        res.on('data', (chunk) => {
          this.lastDataAt = Date.now();
          buf += chunk;
          let i;
          while ((i = buf.indexOf('\n\n')) >= 0) {
            const block = buf.slice(0, i);
            buf = buf.slice(i + 2);
            this.onBlock(block);
          }
          if (buf.length > 2 * 1024 * 1024) buf = '';
        });
        res.on('end', () => this.fail('conexão encerrada pelo Pi'));
        res.on('error', (e) => this.fail(e.message === 'aborted' ? 'conexão interrompida' : e.message));
      }
    );
    req.on('timeout', () => req.destroy(new Error('tempo esgotado')));
    req.on('error', (e) => this.fail(e.code === 'ECONNREFUSED' ? 'conexão recusada (LiveSafe parado?)' : e.code === 'EHOSTUNREACH' ? 'Pi inalcançável na rede' : e.message));
    this.req = req;
  }

  fail(msg) {
    if (this.req) {
      this.req.removeAllListeners('error');
      this.req.on('error', () => {});
      this.req.destroy();
      this.req = null;
    }
    if (this.connected) this.log.warn(`desconectado: ${msg}`);
    this.connected = false;
    this.lastError = msg;
    if (this.stopped) return;
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.connect(), this.backoff);
    this.backoff = Math.min(this.backoff * 2, 15000);
  }

  onBlock(block) {
    let event = 'message';
    let data = '';
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) data += line.slice(5).trim();
    }
    if (!data) return;
    let obj;
    try {
      obj = JSON.parse(data);
    } catch (e) {
      return;
    }
    if (event === 'state') this.onState(obj);
    else if (event === 'event') this.onRemoteEvent(obj);
  }

  onState(s) {
    this.offset = Date.now() - s.now;
    this.remote = s;
    if (Array.isArray(s.events)) {
      // Reconexão: traz o que aconteceu no Pi enquanto o enlace estava fora.
      const maxId = s.events.reduce((m, e) => Math.max(m, e.id || 0), 0);
      if (this.lastSeenId !== null) {
        s.events
          .filter((e) => e.id > this.lastSeenId)
          .sort((a, b) => a.id - b.id)
          .forEach((e) => this.forward(e));
      }
      this.lastSeenId = Math.max(this.lastSeenId || 0, maxId);
    }
  }

  onRemoteEvent(e) {
    if (this.lastSeenId !== null && e.id <= this.lastSeenId) return;
    this.lastSeenId = e.id;
    this.forward(e);
  }

  forward(e) {
    this.emit('remote-event', { ...e, remoteId: e.id, site: this.cfg.id, siteName: this.cfg.name });
  }

  online(now = Date.now()) {
    return this.connected && now - this.lastDataAt < this.offlineMs;
  }

  tick(now = Date.now()) {
    // Conexão "viva" mas sem dados (ex.: enlace travado): derruba e reconecta.
    if (this.connected && now - this.lastDataAt > this.offlineMs) this.fail(`sem dados há ${Math.round(this.offlineMs / 1000)} s`);
    const down = !this.online(now) && now - this.startedAt > 3000;
    const change = this.comm.update(down, now);
    if (change) {
      const active = change === 'raise';
      this.commSince = active ? now : 0;
      this.emit('alarm', {
        site: this.cfg.id,
        siteName: this.cfg.name,
        channelIndex: 0,
        channelName: this.cfg.name,
        type: 'comm',
        active,
        code: active ? COMM_CODE : COMM_CODE + 10,
        message: active ? 'Sem comunicação com o Pi' : 'Comunicação restabelecida',
        detail: active ? this.lastError : undefined,
      });
    }
  }

  // Grupo para a GUI: canais do Pi com horários convertidos para o relógio central.
  group(now = Date.now()) {
    const r = this.remote;
    let channels = [];
    if (r) {
      const local = (r.groups || []).find((g) => g.key === 'local');
      channels = (local ? local.channels : r.channels || []).map((ch) => {
        const alarms = {};
        for (const [k, a] of Object.entries(ch.alarms)) alarms[k] = { ...a, since: a.since ? a.since + this.offset : null };
        return { ...ch, alarms };
      });
    }
    const online = this.online(now);
    return {
      key: this.cfg.id,
      name: this.cfg.name,
      remoteName: r ? r.siteName : null,
      base: `sites/${encodeURIComponent(this.cfg.id)}/`,
      kind: 'remote',
      url: this.cfg.url,
      online,
      comm: { state: this.comm.active ? 'alarm' : online ? 'ok' : 'pending', since: this.commSince || null },
      lastError: online ? '' : this.lastError,
      version: r ? r.version : null,
      system: r ? r.system : null,
      snmp: r ? r.snmp : null,
      channels,
    };
  }

  // ---------- proxy ----------
  request(method, path, body) {
    return new Promise((resolve) => {
      const req = this.mod.request(
        `${this.cfg.url}${path}`,
        { method, agent: this.agent, headers: { ...this.headers, ...(body ? { 'Content-Type': 'application/json' } : {}) }, timeout: 8000 },
        (res) => {
          const parts = [];
          let size = 0;
          res.on('data', (d) => {
            size += d.length;
            if (size <= 16 * 1024 * 1024) parts.push(d);
          });
          res.on('end', () => resolve({ status: res.statusCode, type: res.headers['content-type'] || 'application/octet-stream', body: Buffer.concat(parts) }));
          res.on('error', (e) => resolve({ status: 502, type: 'application/json', body: Buffer.from(JSON.stringify({ error: e.message })) }));
        }
      );
      req.on('timeout', () => req.destroy(new Error('tempo esgotado')));
      req.on('error', (e) => resolve({ status: 502, type: 'application/json', body: Buffer.from(JSON.stringify({ error: `Pi ${this.cfg.name} não respondeu: ${e.message}` })) }));
      req.end(body);
    });
  }

  // GET com cache: segmentos .ts ficam 60 s, playlist e imagem por meio segundo.
  get(path) {
    const ttl = /\.ts$/.test(path) ? 60000 : /\.m3u8$/.test(path) ? 400 : 500;
    return this.cache.fetch(`${this.cfg.id}:${path}`, ttl, () => this.request('GET', path));
  }

  stop() {
    this.stopped = true;
    clearTimeout(this.timer);
    if (this.req) this.req.destroy();
    this.agent.destroy();
  }
}

// Cache LRU limitado por tamanho, com coalescência: pedidos simultâneos da
// mesma URL esperam um único download.
class ProxyCache {
  constructor(maxBytes) {
    this.max = maxBytes;
    this.size = 0;
    this.map = new Map();
    this.inflight = new Map();
    this.hits = 0;
    this.misses = 0;
  }

  fetch(key, ttl, loader) {
    const now = Date.now();
    const hit = this.map.get(key);
    if (hit && hit.exp > now) {
      this.map.delete(key);
      this.map.set(key, hit);
      this.hits++;
      return Promise.resolve(hit.res);
    }
    if (this.inflight.has(key)) return this.inflight.get(key);
    this.misses++;
    const p = loader().then((res) => {
      this.inflight.delete(key);
      if (res.status === 200) this.put(key, res, now + ttl);
      else if (res.status === 404) this.put(key, res, now + Math.min(ttl, 1000));
      return res;
    });
    this.inflight.set(key, p);
    return p;
  }

  put(key, res, exp) {
    const old = this.map.get(key);
    if (old) {
      this.size -= old.res.body.length;
      this.map.delete(key);
    }
    if (res.body.length > this.max / 4) return;
    this.map.set(key, { res, exp });
    this.size += res.body.length;
    for (const [k, v] of this.map) {
      if (this.size <= this.max) break;
      this.map.delete(k);
      this.size -= v.res.body.length;
    }
  }

  stats() {
    return { entries: this.map.size, bytes: this.size, hits: this.hits, misses: this.misses };
  }
}

module.exports = { Site, ProxyCache, COMM_CODE };
