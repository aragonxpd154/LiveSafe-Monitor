#!/usr/bin/env node
'use strict';
const { execFileSync, spawn } = require('child_process');
const path = require('path');
const config = require('./config');
const { Channel } = require('./channel');
const { Site, ProxyCache } = require('./remote');
const { Traps, Agent, STARTUP_CODE, TEST_CODE } = require('./snmp');
const { EventStore } = require('./events');
const { createServer } = require('./web');
const { createSetup } = require('./setup');
const { createInstaller } = require('./installer');
const encoder = require('./encoder');
const system = require('./system');
const { logger, setLevel } = require('./log');

const VERSION = require('../package.json').version;
const log = logger('livesafe');

function ffmpegMajor(bin) {
  try {
    const out = execFileSync(bin, ['-hide_banner', '-version'], { encoding: 'utf8', timeout: 5000 });
    const m = out.match(/ffmpeg version n?(\d+)\./);
    return m ? Number(m[1]) : 99; // builds "git-..." são recentes
  } catch (e) {
    return null;
  }
}

async function main() {
  const file = process.argv[2] || process.env.LIVESAFE_CONFIG || path.join(__dirname, '..', 'config.json');
  let cfg;
  try {
    cfg = config.load(file);
  } catch (e) {
    log.error(e.message);
    process.exit(2);
  }
  if (cfg.logLevel) setLevel(cfg.logLevel);
  const roles =
    [cfg.channels.length && `${cfg.channels.length} canal(is) local(is)`, cfg.sites.length && `${cfg.sites.length} Pi(s) remoto(s)`].filter(Boolean).join(' + ') ||
    `aguardando configuração (${cfg.role === 'central' ? 'servidor central' : 'Pi de borda'}) — abra o painel em /setup`;
  log.info(`LiveSafe Monitor ${VERSION} — "${cfg.siteName}": ${roles}. Config ${cfg.file}`);

  // ---------- canais locais (Pi de borda) ----------
  const ffmpegPath = cfg.ffmpeg || 'ffmpeg';
  let channels = [];
  if (cfg.channels.length) {
    const major = ffmpegMajor(ffmpegPath);
    if (major === null) log.error(`ffmpeg não encontrado em "${ffmpegPath}". Instale com: sudo apt install ffmpeg`);
    else log.info(`ffmpeg ${major}.x`);
    const wantsStream = cfg.channels.some((c) => c.stream.enabled && c.video);
    const enc = wantsStream && major !== null ? encoder.resolve(ffmpegPath, cfg.defaults.stream.encoder) : null;
    channels = cfg.channels.map((c) => new Channel(c, { ffmpegPath, legacyVsync: major !== null && major < 5, encoder: enc, streamDir: cfg.streamDir }));
  }

  // ---------- Pis remotos (servidor central) ----------
  const cache = new ProxyCache(cfg.central.cacheMB * 1024 * 1024);
  const sites = cfg.sites.map((s) => new Site(s, { cache, offlineSeconds: cfg.central.offlineSeconds, stateIntervalMs: cfg.central.stateIntervalMs || 500 }));

  const events = new EventStore(cfg.events);
  const traps = new Traps(cfg.snmp.traps);
  const agent = new Agent(cfg.snmp.agent, VERSION);
  let sys = system.snapshot();
  let lastTickAt = Date.now();

  const app = {
    events,
    channel: (id) => channels.find((c) => c.cfg.id === id),
    site: (id) => sites.find((s) => s.cfg.id === id),
    state(full) {
      const now = Date.now();
      const groups = [];
      if (channels.length) {
        groups.push({ key: 'local', name: cfg.siteName, base: '', kind: 'local', online: true, system: sys, channels: channels.map((c) => c.status(now)) });
      }
      for (const s of sites) groups.push(s.group(now));
      const st = { version: VERSION, now, siteName: cfg.siteName, mode: cfg.role, setupPending: cfg.setupPending, system: sys, snmp: traps.status(), groups };
      if (sites.length) st.cache = cache.stats();
      if (full) st.events = events.recent(100);
      return st;
    },
    // Usado pelo vigia externo (livesafe-watchdog.timer): se o laço interno de
    // 1 s parou, responde ok=false e o serviço é reiniciado.
    health() {
      const st = channels.map((c) => c.status());
      const loopAgeMs = Date.now() - lastTickAt;
      return {
        ok: loopAgeMs < 10000,
        loopAgeMs,
        version: VERSION,
        uptime: Math.round(process.uptime()),
        channels: st.length,
        alarms: st.reduce((n, c) => n + Object.values(c.alarms).filter((a) => a.state === 'alarm').length, 0),
        sites: sites.length,
        sitesOnline: sites.filter((s) => s.online()).length,
      };
    },
    async testTrap() {
      const res = await traps.send(TEST_CODE, { message: 'Trap de teste enviada pelo painel' });
      events.add({ type: 'test', active: false, code: TEST_CODE, message: 'Trap de teste enviada', detail: res.map((r) => `${r.target} ${r.ok ? 'ok' : 'erro: ' + r.error}`).join(', ') || 'traps desativadas' });
      return { results: res, snmp: traps.status() };
    },
  };

  app.setup = createSetup({ cfg, channels, version: VERSION, ffmpegPath, restart: (why) => shutdown(why, true) });
  app.installer = createInstaller(VERSION);
  const web = createServer(app, cfg.http);
  events.on('event', (ev) => web.broadcast('event', ev));

  for (const ch of channels) {
    ch.on('alarm', (ev) => {
      events.add(ev);
      traps.send(ev.code, ev);
    });
    // Ações automáticas de recuperação: só histórico, sem trap.
    ch.on('notice', (ev) => events.add(ev));
  }
  for (const s of sites) {
    // "Sem comunicação" é alarme do central (o Pi não consegue avisar que caiu).
    s.on('alarm', (ev) => {
      events.add(ev);
      traps.send(ev.code, { ...ev, channel: ev.site });
    });
    // Alarmes dos canais remotos entram no histórico central; as traps deles
    // já saem do próprio Pi, então aqui não repetimos.
    s.on('remote-event', (ev) => {
      if (['startup', 'test'].includes(ev.type)) return;
      const { id, ts, ...rest } = ev;
      events.add({ ...rest, remoteTs: ts });
    });
  }

  try {
    await web.listen();
  } catch (e) {
    log.error(`não foi possível abrir a porta ${cfg.http.port}: ${e.message}`);
    process.exit(1);
  }

  for (const ch of channels) ch.start();
  for (const s of sites) s.start();
  if (cfg.snmp.traps.sendStartup) traps.send(STARTUP_CODE, { message: `LiveSafe ${VERSION} iniciado em ${cfg.siteName}` });
  events.add({ type: 'startup', active: false, code: STARTUP_CODE, message: `LiveSafe ${VERSION} iniciado` });

  // Laço único de 1 s: watchdog dos canais e Pis, saúde do host e agente SNMP.
  const tick = setInterval(() => {
    const now = Date.now();
    lastTickAt = now;
    for (const ch of channels) ch.tick(now);
    for (const s of sites) s.tick(now);
    sys = system.snapshot();
    if (channels.length) agent.update(channels.map((c) => c.status(now)));
  }, 1000);

  // Estado ao vivo para a GUI e para o central — só quando há alguém ouvindo.
  const live = setInterval(() => web.pushState(() => app.state(false)), 250);

  let closing = false;
  // relaunch: sob o systemd basta sair (Restart=always sobe de novo com a
  // configuração nova); fora dele, o processo se reinicia sozinho.
  async function shutdown(sig, relaunch = false) {
    if (closing) return;
    closing = true;
    log.info(relaunch ? `${sig}: reiniciando…` : `${sig} recebido, encerrando…`);
    clearInterval(tick);
    clearInterval(live);
    for (const s of sites) s.stop();
    await Promise.all(channels.map((c) => c.stop()));
    await web.close();
    traps.close();
    agent.close();
    if (relaunch && !process.env.INVOCATION_ID) {
      spawn(process.execPath, [...process.execArgv, ...process.argv.slice(1)], { stdio: "inherit", detached: true }).unref();
    }
    process.exit(0);
  }
  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('uncaughtException', (e) => {
    // Melhor reiniciar limpo (o systemd sobe de novo) do que seguir em estado incerto.
    log.error('erro inesperado: ' + (e.stack || e.message));
    for (const c of channels) c.kill();
    process.exit(1);
  });
}

main();
