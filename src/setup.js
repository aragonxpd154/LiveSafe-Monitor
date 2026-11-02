'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const http = require('http');
const https = require('https');
const { spawn } = require('child_process');
const config = require('./config');
const devices = require('./devices');
const { hashPassword } = require('./auth');
const { logger } = require('./log');

const log = logger('setup');

function ips() {
  const out = [];
  for (const [name, list] of Object.entries(os.networkInterfaces())) {
    for (const a of list || []) if (a.family === 'IPv4' && !a.internal) out.push({ iface: name, address: a.address });
  }
  return out;
}

function model() {
  try {
    return fs.readFileSync('/proc/device-tree/model', 'utf8').replace(/\0/g, '').trim();
  } catch (e) {
    return `${os.type()} ${os.arch()}`;
  }
}

// Cópia da configuração sem senhas, para mandar ao navegador.
function sanitize(raw) {
  const c = JSON.parse(JSON.stringify(raw || {}));
  if (c.http && c.http.auth) {
    c.http.auth = { user: c.http.auth.user || '', hasPassword: !!(c.http.auth.passwordHash || c.http.auth.password) };
  }
  for (const s of c.sites || []) {
    s.hasPassword = !!s.password;
    delete s.password;
  }
  return c;
}

function request(url, { user, password, timeout = 6000 } = {}) {
  return new Promise((resolve) => {
    let u;
    try {
      u = new URL(url);
    } catch (e) {
      return resolve({ ok: false, error: 'Endereço inválido' });
    }
    const mod = u.protocol === 'https:' ? https : http;
    const headers = user ? { Authorization: 'Basic ' + Buffer.from(`${user}:${password || ''}`).toString('base64') } : {};
    const req = mod.get(u, { headers, timeout }, (res) => {
      const parts = [];
      res.on('data', (d) => parts.push(d));
      res.on('end', () => {
        const text = Buffer.concat(parts).toString('utf8');
        let body = null;
        try {
          body = JSON.parse(text);
        } catch (e) {}
        resolve({ ok: res.statusCode === 200, status: res.statusCode, body });
      });
    });
    req.on('timeout', () => req.destroy(new Error('sem resposta em 6 s')));
    req.on('error', (e) =>
      resolve({
        ok: false,
        error: e.code === 'ECONNREFUSED' ? 'conexão recusada: o LiveSafe não está rodando nesse endereço' : e.code === 'EHOSTUNREACH' || e.code === 'ENETUNREACH' ? 'endereço inalcançável na rede' : e.message,
      })
    );
  });
}

function createSetup(ctx) {
  async function info() {
    const cfg = ctx.cfg;
    const port = cfg.http.port;
    const addr = ips();
    const res = {
      role: cfg.role,
      setupPending: cfg.setupPending,
      version: ctx.version,
      host: { hostname: os.hostname(), model: model(), ips: addr },
      config: sanitize(cfg.raw),
      defaults: config.DEFAULTS.defaults,
    };
    if (cfg.role === 'edge') res.devices = await devices.detect();
    if (cfg.role === 'central') {
      const ip = addr[0] ? addr[0].address : '<ip-do-central>';
      res.installCommand = `curl -fsSL http://${ip}:${port}/instalar.sh | sudo bash`;
    }
    return res;
  }

  // Captura um quadro e mede o áudio por 3 s para o operador conferir a entrada.
  async function testInput(body) {
    const ch = config.normalizeChannel(body && body.channel, 0, ctx.cfg.defaults);
    const devs = ch.inputArgs.filter((a) => /^\/dev\/video\d+$/.test(a) || /^hw:/.test(a));
    const owner = ctx.channels.find((c) => c.proc && c.cfg.inputArgs.some((a) => devs.includes(a)));
    if (owner) {
      const st = owner.status();
      const levels = st.metrics.levels;
      return {
        ok: true,
        busy: true,
        owner: owner.cfg.name,
        image: owner.jpeg ? owner.jpeg.toString('base64') : null,
        audioDb: levels ? Math.max(...levels.map((l) => l.rms)) : null,
        source: st.source,
      };
    }
    const args = ['-hide_banner', '-nostdin', ...ch.decoderArgs, ...ch.inputArgs];
    if (ch.video) {
      args.push('-map', ch.videoStream, '-vf', "select='gte(n\\,15)',scale=480:-2", '-frames:v', '1', '-f', 'image2pipe', '-c:v', 'mjpeg', '-q:v', '5', 'pipe:1');
    }
    if (ch.audio) args.push('-map', ch.audioStream, '-t', '3', '-af', 'volumedetect', '-f', 'null', '-');
    return new Promise((resolve) => {
      const p = spawn(ctx.ffmpegPath, args, { stdio: ['ignore', 'pipe', 'pipe'] });
      const img = [];
      let err = '';
      p.stdout.on('data', (d) => img.push(d));
      p.stderr.on('data', (d) => {
        err += d.toString('utf8');
        if (err.length > 200000) err = err.slice(-100000);
      });
      const t = setTimeout(() => p.kill('SIGKILL'), 15000);
      p.on('error', (e) => {
        clearTimeout(t);
        resolve({ ok: false, error: e.code === 'ENOENT' ? 'ffmpeg não encontrado' : e.message });
      });
      p.on('close', (code) => {
        clearTimeout(t);
        const source = {};
        for (const m of err.matchAll(/Stream #\d+:\d+.*?: (Video|Audio): (.*)/g)) {
          const k = m[1] === 'Video' ? 'video' : 'audio';
          if (!source[k]) source[k] = m[2].slice(0, 160);
        }
        const mean = err.match(/mean_volume:\s*(-?[\d.]+|-inf) dB/);
        const image = img.length ? Buffer.concat(img) : null;
        const ok = (!ch.video || (image && image.length > 100)) && (code === 0 || (image && image.length > 100));
        const lines = err
          .split('\n')
          .map((l) => l.trim())
          .filter((l) => /error|failed|invalid|no such|not found|busy|denied|cannot|unable|matches no streams|timed out|refused/i.test(l));
        resolve({
          ok: !!ok,
          image: image ? image.toString('base64') : null,
          audioDb: mean ? (mean[1] === '-inf' ? -96 : Number(mean[1])) : null,
          source,
          error: ok ? null : lines.slice(-3).join(' | ') || `ffmpeg terminou com código ${code}`,
        });
      });
    });
  }

  async function testSite(body) {
    let { url, user, password, id } = body || {};
    if (!url && body && body.host) url = `http://${body.host}:${body.port || 8080}`;
    url = String(url || '').replace(/\/+$/, '');
    if (!/^https?:\/\//.test(url)) return { ok: false, error: 'Use o formato http://IP:porta (ex.: http://10.10.8.21:8080)' };
    if (!password && id) {
      const old = (ctx.cfg.raw.sites || []).find((s) => s.id === id);
      if (old) password = old.password;
    }
    const h = await request(`${url}/healthz`);
    if (!h.ok && !h.status) return { ok: false, error: h.error };
    const st = await request(`${url}/api/state`, { user, password });
    if (st.status === 401) return { ok: false, error: 'O Pi respondeu, mas recusou o usuário ou a senha' };
    if (!st.ok || !st.body) return { ok: false, error: st.error || `O Pi respondeu com HTTP ${st.status}` };
    const local = (st.body.groups || []).find((g) => g.key === 'local');
    return {
      ok: true,
      siteName: st.body.siteName,
      version: st.body.version,
      role: st.body.mode,
      channels: (local ? local.channels : []).map((c) => c.name),
      temp: st.body.system ? st.body.system.tempC : null,
    };
  }

  async function save(body) {
    if (!body || typeof body.config !== 'object') throw new Error('Envie { config }');
    const old = ctx.cfg.raw || {};
    const next = JSON.parse(JSON.stringify(body.config));
    next.http = next.http || {};
    // Senha do painel: troca só quando uma nova é informada.
    const a = next.http.auth || {};
    const oldAuth = (old.http && old.http.auth) || null;
    if (a.newPassword) {
      if (String(a.newPassword).length < 6) throw new Error('A senha do painel precisa ter pelo menos 6 caracteres');
      next.http.auth = { user: String(a.user || 'admin'), passwordHash: hashPassword(a.newPassword) };
    } else if (oldAuth && (oldAuth.passwordHash || oldAuth.password)) {
      next.http.auth = { ...oldAuth, user: String(a.user || oldAuth.user || 'admin') };
    } else {
      throw new Error('Defina uma senha para o painel: ele permite mudar a configuração e reiniciar a captura');
    }
    // Caminhos do sistema não mudam pelo navegador.
    for (const k of ['ffmpeg', 'streamDir']) {
      if (old[k] === undefined) delete next[k];
      else next[k] = old[k];
    }
    // Senhas dos Pis: em branco = manter a que já estava gravada.
    for (const s of next.sites || []) {
      delete s.hasPassword;
      if (!s.password) {
        const prev = (old.sites || []).find((o) => o.id === s.id);
        if (prev && prev.password) s.password = prev.password;
        else delete s.password;
      }
    }
    config.fromObject(next, path.dirname(ctx.cfg.file)); // valida; lança erro legível
    const tmp = `${ctx.cfg.file}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(next, null, 2) + '\n', { mode: 0o640 });
    fs.renameSync(tmp, ctx.cfg.file);
    log.info('configuração salva pelo assistente; reiniciando para aplicar');
    setTimeout(() => ctx.restart('configuração alterada pelo painel'), 600);
    return { ok: true, restartInMs: 600 };
  }

  return {
    async handle(method, p, body) {
      if (method === 'GET' && p === '/api/setup') return { body: await info() };
      if (method === 'POST' && p === '/api/setup/test-input') return { body: await testInput(body) };
      if (method === 'POST' && p === '/api/setup/test-site') return { body: await testSite(body) };
      if (method === 'POST' && p === '/api/setup/save') return { body: await save(body) };
      return null;
    },
  };
}

module.exports = { createSetup, sanitize };
