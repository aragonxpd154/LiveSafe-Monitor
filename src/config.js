'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');

// Valores padrão. Tudo pode ser sobrescrito no config.json, e os blocos de
// detecção (freeze/black/silence/...) também podem ser sobrescritos por canal.
const DEFAULTS = {
  // Nome desta instalação (ex.: o abrigo onde o Pi está).
  siteName: os.hostname(),
  http: { host: '0.0.0.0', port: 8080, auth: null },
  // Onde o HLS é gravado. Em RAM para não desgastar o cartão SD.
  streamDir: null,
  // Servidor central: Pis remotos a agregar (cada um rodando o LiveSafe).
  sites: [],
  central: { offlineSeconds: 10, cacheMB: 64 },
  snmp: {
    traps: {
      enabled: true,
      targets: [{ host: '192.168.1.2', port: 162 }],
      community: 'public',
      version: '1', // "1" (como nas versões anteriores) ou "2c"
      sendStartup: true,
    },
    agent: { enabled: false, address: '0.0.0.0', port: 1161, community: 'public' },
  },
  events: { file: 'data/events.jsonl', maxBytes: 1024 * 1024, memory: 500 },
  defaults: {
    analysis: { fps: 5, width: 160, height: 90 },
    preview: { enabled: true, fps: 1, width: 480, quality: 8 },
    freeze: { enabled: true, seconds: 10, motionPct: 0.1, pixelDelta: 12 },
    black: { enabled: true, seconds: 5, pct: 98, pixelLuma: 32 },
    silence: { enabled: true, seconds: 10, dbfs: -60 },
    signal: { stallSeconds: 8 },
    clearSeconds: 2,
    warmupSeconds: 5,
    restart: { minSeconds: 2, maxSeconds: 30 },
    audioRate: 16000,
    threads: 2,
    stream: {
      enabled: true,
      encoder: 'auto', // auto = hardware do Pi 4 (h264_v4l2m2m) ou libx264
      width: 1280,
      softwareMaxWidth: 854, // limite quando cai para codificação por software
      fps: 25,
      bitrate: '2000k',
      audioBitrate: '96k',
      preset: 'ultrafast',
      segmentSeconds: 1,
      windowSeconds: 30, // tamanho da "barra" que dá para voltar no player
    },
  },
  channels: [],
};

const CHANNEL_KEYS = ['analysis', 'preview', 'freeze', 'black', 'silence', 'signal', 'clearSeconds', 'warmupSeconds', 'restart', 'audioRate', 'threads', 'stream'];

function isObj(v) {
  return v && typeof v === 'object' && !Array.isArray(v);
}

function merge(base, over) {
  if (!isObj(over)) return over === undefined ? clone(base) : over;
  const out = isObj(base) ? clone(base) : {};
  for (const k of Object.keys(over)) out[k] = isObj(over[k]) && isObj(out[k]) ? merge(out[k], over[k]) : over[k];
  return out;
}

function clone(v) {
  return v === undefined ? v : JSON.parse(JSON.stringify(v));
}

function num(obj, key, min, max, where) {
  const v = obj[key];
  if (typeof v !== 'number' || !Number.isFinite(v) || v < min || v > max) {
    throw new Error(`${where}.${key} deve ser um número entre ${min} e ${max} (recebido: ${JSON.stringify(v)})`);
  }
}

function normalizeChannel(raw, i, defaults) {
  const where = `channels[${i}]`;
  if (!isObj(raw)) throw new Error(`${where} deve ser um objeto`);
  const ch = {};
  for (const k of CHANNEL_KEYS) ch[k] = merge(defaults[k], raw[k]);

  ch.id = String(raw.id || `ch${i + 1}`);
  if (!/^[a-z0-9][a-z0-9_-]{0,31}$/i.test(ch.id)) throw new Error(`${where}.id inválido: use letras, números, - ou _ (até 32)`);
  ch.index = i + 1;
  ch.name = String(raw.name || ch.id).slice(0, 64);
  ch.video = raw.video !== false;
  ch.audio = raw.audio !== false;
  if (!ch.video && !ch.audio) throw new Error(`${where}: video e audio não podem ser ambos false`);
  ch.videoStream = String(raw.videoStream || '0:v:0');
  ch.audioStream = String(raw.audioStream || '0:a:0');

  if (Array.isArray(raw.inputArgs) && raw.inputArgs.length) {
    ch.inputArgs = raw.inputArgs.map(String);
    if (!ch.inputArgs.includes('-i')) throw new Error(`${where}.inputArgs precisa conter "-i"`);
  } else if (typeof raw.url === 'string' && raw.url) {
    ch.inputArgs = [...defaultInputOptions(raw.url), ...(raw.inputOptions || []).map(String), '-i', raw.url];
  } else {
    throw new Error(`${where}: informe "url" ou "inputArgs"`);
  }
  ch.decoderArgs = Array.isArray(raw.decoderArgs) ? raw.decoderArgs.map(String) : [];

  num(ch.analysis, 'fps', 1, 25, `${where}.analysis`);
  num(ch.analysis, 'width', 32, 640, `${where}.analysis`);
  num(ch.analysis, 'height', 18, 360, `${where}.analysis`);
  num(ch.preview, 'fps', 0.1, 10, `${where}.preview`);
  num(ch.preview, 'width', 96, 1280, `${where}.preview`);
  num(ch.preview, 'quality', 2, 31, `${where}.preview`);
  num(ch.freeze, 'seconds', 1, 3600, `${where}.freeze`);
  num(ch.freeze, 'motionPct', 0, 100, `${where}.freeze`);
  num(ch.freeze, 'pixelDelta', 1, 255, `${where}.freeze`);
  num(ch.black, 'seconds', 1, 3600, `${where}.black`);
  num(ch.black, 'pct', 1, 100, `${where}.black`);
  num(ch.black, 'pixelLuma', 0, 255, `${where}.black`);
  num(ch.silence, 'seconds', 1, 3600, `${where}.silence`);
  num(ch.silence, 'dbfs', -120, 0, `${where}.silence`);
  num(ch.signal, 'stallSeconds', 2, 600, `${where}.signal`);
  num(ch, 'clearSeconds', 0, 600, where);
  num(ch, 'warmupSeconds', 0, 600, where);
  num(ch.restart, 'minSeconds', 0.5, 600, `${where}.restart`);
  num(ch.restart, 'maxSeconds', 1, 3600, `${where}.restart`);
  num(ch, 'audioRate', 4000, 48000, where);
  num(ch, 'threads', 0, 8, where);
  num(ch.stream, 'width', 160, 1920, `${where}.stream`);
  num(ch.stream, 'softwareMaxWidth', 160, 1920, `${where}.stream`);
  num(ch.stream, 'fps', 5, 60, `${where}.stream`);
  num(ch.stream, 'segmentSeconds', 1, 10, `${where}.stream`);
  num(ch.stream, 'windowSeconds', 3, 600, `${where}.stream`);
  for (const k of ['bitrate', 'audioBitrate']) {
    if (!/^\d+(\.\d+)?[kKmM]?$/.test(String(ch.stream[k]))) throw new Error(`${where}.stream.${k} inválido (ex.: "2000k")`);
    ch.stream[k] = String(ch.stream[k]);
  }
  // Dimensões pares evitam erro do scaler.
  ch.analysis.width -= ch.analysis.width % 2;
  ch.analysis.height -= ch.analysis.height % 2;
  ch.preview.width -= ch.preview.width % 2;
  return ch;
}

function normalizeSite(raw, i) {
  const where = `sites[${i}]`;
  if (!isObj(raw)) throw new Error(`${where} deve ser um objeto`);
  const id = String(raw.id || `site${i + 1}`);
  if (!/^[a-z0-9][a-z0-9_-]{0,31}$/i.test(id)) throw new Error(`${where}.id inválido: use letras, números, - ou _ (até 32)`);
  let url = String(raw.url || '');
  if (!/^https?:\/\//.test(url)) {
    if (raw.host) url = `http://${raw.host}:${raw.port || 8080}`;
    else throw new Error(`${where}: informe "url" (ex.: "http://10.0.0.21:8080") ou "host"`);
  }
  return {
    id,
    index: i + 1,
    name: String(raw.name || id).slice(0, 64),
    url: url.replace(/\/+$/, ''),
    auth: raw.user ? { user: String(raw.user), password: String(raw.password || '') } : null,
  };
}

// Opções sensatas por protocolo para que a entrada não trave para sempre.
function defaultInputOptions(url) {
  if (/^rtsp:/i.test(url)) return ['-rtsp_transport', 'tcp', '-timeout', '10000000'];
  if (/^(udp|rtp|srt):/i.test(url)) return ['-fflags', '+discardcorrupt', '-analyzeduration', '2000000', '-probesize', '2000000'];
  if (/^https?:/i.test(url)) return ['-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '5', '-rw_timeout', '10000000'];
  return [];
}

function load(file) {
  const abs = path.resolve(file);
  let raw;
  try {
    raw = JSON.parse(fs.readFileSync(abs, 'utf8'));
  } catch (e) {
    throw new Error(`Não foi possível ler ${abs}: ${e.message}`);
  }
  const cfg = merge(DEFAULTS, raw);
  cfg.defaults = merge(DEFAULTS.defaults, raw.defaults || {});
  const rawCh = Array.isArray(raw.channels) ? raw.channels : [];
  const rawSites = Array.isArray(raw.sites) ? raw.sites : [];
  if (rawCh.length === 0 && rawSites.length === 0) {
    throw new Error('Configure ao menos um canal em "channels" (Pi de borda) ou um Pi em "sites" (servidor central)');
  }
  cfg.channels = rawCh.map((c, i) => normalizeChannel(c, i, cfg.defaults));
  cfg.sites = rawSites.map((s, i) => normalizeSite(s, i));
  const siteIds = new Set();
  for (const s of cfg.sites) {
    if (siteIds.has(s.id)) throw new Error(`id de site repetido: ${s.id}`);
    siteIds.add(s.id);
  }
  cfg.siteName = String(cfg.siteName || os.hostname()).slice(0, 64);
  cfg.streamDir = cfg.streamDir || process.env.RUNTIME_DIRECTORY || (fs.existsSync('/dev/shm') ? '/dev/shm/livesafe' : path.join(os.tmpdir(), 'livesafe-hls'));
  const ids = new Set();
  for (const c of cfg.channels) {
    if (ids.has(c.id)) throw new Error(`id de canal repetido: ${c.id}`);
    ids.add(c.id);
  }
  num(cfg.http, 'port', 1, 65535, 'http');
  if (!Array.isArray(cfg.snmp.traps.targets)) cfg.snmp.traps.targets = [];
  cfg.snmp.traps.version = String(cfg.snmp.traps.version) === '2c' ? '2c' : '1';
  // Caminhos relativos ficam relativos ao config.json.
  const base = path.dirname(abs);
  if (cfg.events.file) cfg.events.file = path.resolve(base, cfg.events.file);
  cfg.file = abs;
  return cfg;
}

module.exports = { load, DEFAULTS, normalizeChannel, normalizeSite };
