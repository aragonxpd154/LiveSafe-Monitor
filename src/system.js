'use strict';
const fs = require('fs');
const os = require('os');

// Saúde do host (pensado para o Raspberry Pi, mas funciona em qualquer Linux).
let lastCpu = cpuTimes();

function cpuTimes() {
  let idle = 0;
  let total = 0;
  for (const c of os.cpus()) {
    for (const k of Object.keys(c.times)) total += c.times[k];
    idle += c.times.idle;
  }
  return { idle, total };
}

function readNum(file) {
  try {
    return Number(fs.readFileSync(file, 'utf8').trim());
  } catch (e) {
    return null;
  }
}

function cpuTemp() {
  const v = readNum('/sys/class/thermal/thermal_zone0/temp');
  return v === null || Number.isNaN(v) ? null : Math.round(v / 100) / 10;
}

function memAvailable() {
  // MemAvailable é o número que importa no Linux (free conta cache como usado).
  try {
    const m = fs.readFileSync('/proc/meminfo', 'utf8').match(/MemAvailable:\s+(\d+)/);
    if (m) return Number(m[1]) * 1024;
  } catch (e) {}
  return os.freemem();
}

function model() {
  try {
    return fs.readFileSync('/proc/device-tree/model', 'utf8').replace(/\0/g, '').trim();
  } catch (e) {
    return `${os.type()} ${os.arch()}`;
  }
}

const MODEL = model();

function snapshot() {
  const now = cpuTimes();
  const dTotal = now.total - lastCpu.total;
  const dIdle = now.idle - lastCpu.idle;
  lastCpu = now;
  const total = os.totalmem();
  const avail = memAvailable();
  return {
    host: os.hostname(),
    model: MODEL,
    cpuPct: dTotal > 0 ? Math.round((1 - dIdle / dTotal) * 1000) / 10 : 0,
    load: os.loadavg().map((l) => Math.round(l * 100) / 100),
    cores: os.cpus().length,
    tempC: cpuTemp(),
    memTotal: total,
    memUsed: total - avail,
    rss: process.memoryUsage().rss,
    uptime: Math.round(os.uptime()),
    appUptime: Math.round(process.uptime()),
  };
}

module.exports = { snapshot };
