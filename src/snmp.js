'use strict';
const snmp = require('net-snmp');
const { logger } = require('./log');

const log = logger('snmp');

// Enterprise OID usado desde a v1 do LiveSafe.
const BASE = '1.3.6.1.4.1.53864';
const OID = {
  code: `${BASE}.1.1`, // Integer — mesmo OID das versões anteriores
  channelIndex: `${BASE}.1.2`,
  channelName: `${BASE}.1.3`,
  message: `${BASE}.1.4`,
  channelId: `${BASE}.1.5`,
  trap: (code) => `${BASE}.0.${code}`, // v1: enterprise BASE.0, specific = código
};
const STARTUP_CODE = 1;
const TEST_CODE = 9;

class Traps {
  constructor(cfg) {
    this.cfg = cfg;
    this.sessions = [];
    this.sent = 0;
    this.failed = 0;
    this.lastError = '';
    if (!cfg.enabled) return;
    const version = cfg.version === '2c' ? snmp.Version2c : snmp.Version1;
    for (const t of cfg.targets) {
      const s = snmp.createSession(t.host, t.community || cfg.community, { port: t.port || 162, version, trapPort: t.port || 162 });
      s.on('error', (e) => {
        this.lastError = e.message;
        log.warn(`sessão ${t.host}: ${e.message}`);
      });
      this.sessions.push({ target: `${t.host}:${t.port || 162}`, session: s });
    }
    log.info(`traps SNMPv${cfg.version} para ${this.sessions.map((s) => s.target).join(', ') || '(nenhum destino)'}`);
  }

  send(code, info = {}) {
    if (!this.cfg.enabled || this.sessions.length === 0) return Promise.resolve([]);
    const vb = [
      { oid: OID.code, type: snmp.ObjectType.Integer, value: code },
      { oid: OID.channelIndex, type: snmp.ObjectType.Integer, value: info.channelIndex || 0 },
      { oid: OID.channelName, type: snmp.ObjectType.OctetString, value: Buffer.from(String(info.channelName || 'LiveSafe'), 'utf8') },
      { oid: OID.message, type: snmp.ObjectType.OctetString, value: Buffer.from(String(info.message || ''), 'utf8') },
      { oid: OID.channelId, type: snmp.ObjectType.OctetString, value: Buffer.from(String(info.channel || ''), 'utf8') },
    ];
    return Promise.all(
      this.sessions.map(
        ({ target, session }) =>
          new Promise((resolve) => {
            try {
              session.trap(OID.trap(code), vb, (err) => {
                if (err) {
                  this.failed++;
                  this.lastError = `${target}: ${err.message}`;
                  log.warn(`falha ao enviar trap ${code} para ${target}: ${err.message}`);
                  resolve({ target, ok: false, error: err.message });
                } else {
                  this.sent++;
                  log.info(`trap ${code} enviada para ${target}${info.channelName ? ' (' + info.channelName + ')' : ''}`);
                  resolve({ target, ok: true });
                }
              });
            } catch (e) {
              this.failed++;
              this.lastError = `${target}: ${e.message}`;
              resolve({ target, ok: false, error: e.message });
            }
          })
      )
    );
  }

  status() {
    return {
      enabled: !!this.cfg.enabled,
      version: this.cfg.version,
      targets: this.sessions.map((s) => s.target),
      sent: this.sent,
      failed: this.failed,
      lastError: this.lastError,
    };
  }

  close() {
    for (const s of this.sessions) {
      try {
        s.session.close();
      } catch (e) {}
    }
  }
}

// Agente SNMP opcional (GET/WALK) — permite que o NMS consulte o estado.
// Tabela lsChannelTable em BASE.2.1.1.<coluna>.<índice do canal>.
const ALARM_NUM = { off: 0, ok: 1, pending: 2, alarm: 3 };
const OVERALL_NUM = { ok: 1, warn: 2, alarm: 3, starting: 4 };

class Agent {
  constructor(cfg, version) {
    this.cfg = cfg;
    this.agent = null;
    this.rows = new Set();
    if (!cfg.enabled) return;
    try {
      this.agent = snmp.createAgent({ port: cfg.port, address: cfg.address, transport: 'udp4' }, (err) => {
        if (err) log.warn('agente: ' + err.message);
      });
      this.agent.getAuthorizer().addCommunity(cfg.community);
      const ro = snmp.MaxAccess['read-only'];
      const I = snmp.ObjectType.Integer;
      const S = snmp.ObjectType.OctetString;
      const mib = this.agent.getMib();
      mib.registerProvider({ name: 'lsVersion', type: snmp.MibProviderType.Scalar, oid: `${BASE}.3.1`, scalarType: S, maxAccess: ro });
      mib.setScalarValue('lsVersion', String(version));
      mib.registerProvider({ name: 'lsActiveAlarms', type: snmp.MibProviderType.Scalar, oid: `${BASE}.3.2`, scalarType: I, maxAccess: ro });
      mib.setScalarValue('lsActiveAlarms', 0);
      const cols = [
        ['lsChIndex', I],
        ['lsChId', S],
        ['lsChName', S],
        ['lsChOverall', I],
        ['lsChSignal', I],
        ['lsChFreeze', I],
        ['lsChBlack', I],
        ['lsChSilence', I],
        ['lsChMotionX100', I],
        ['lsChAudioDbX10', I],
        ['lsChRestarts', I],
      ];
      mib.registerProvider({
        name: 'lsChannelTable',
        type: snmp.MibProviderType.Table,
        oid: `${BASE}.2.1.1`,
        maxAccess: snmp.MaxAccess['not-accessible'],
        tableColumns: cols.map(([name, type], i) => ({ number: i + 1, name, type, maxAccess: ro })),
        tableIndex: [{ columnName: 'lsChIndex' }],
      });
      this.mib = mib;
      log.info(`agente SNMP ouvindo em ${cfg.address}:${cfg.port} (comunidade "${cfg.community}")`);
    } catch (e) {
      log.error('não foi possível iniciar o agente SNMP: ' + e.message);
      this.agent = null;
    }
  }

  update(channels) {
    if (!this.agent) return;
    let active = 0;
    for (const ch of channels) {
      const a = ch.alarms;
      for (const k of Object.keys(a)) if (a[k].state === 'alarm') active++;
      const levels = ch.metrics.levels;
      const loud = levels ? Math.max(...levels.map((l) => l.rms)) : -96;
      const row = [
        ch.index,
        ch.id,
        Buffer.from(ch.name, 'utf8'),
        OVERALL_NUM[ch.overall] || 4,
        ALARM_NUM[a.signal.state],
        ALARM_NUM[a.freeze.state],
        ALARM_NUM[a.black.state],
        ALARM_NUM[a.silence.state],
        Math.round((ch.metrics.motionPct || 0) * 100),
        Math.round(loud * 10),
        ch.restarts,
      ];
      try {
        if (!this.rows.has(ch.index)) {
          this.mib.addTableRow('lsChannelTable', row);
          this.rows.add(ch.index);
        } else {
          for (let c = 4; c <= row.length; c++) this.mib.setTableSingleCell('lsChannelTable', c, [ch.index], row[c - 1]);
        }
      } catch (e) {
        log.debug('agente: ' + e.message);
      }
    }
    try {
      this.mib.setScalarValue('lsActiveAlarms', active);
    } catch (e) {}
  }

  close() {
    if (this.agent) {
      try {
        this.agent.close();
      } catch (e) {}
    }
  }
}

module.exports = { Traps, Agent, OID, STARTUP_CODE, TEST_CODE, BASE };
