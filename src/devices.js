'use strict';
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');

// Descobre placas de captura ligadas ao Pi para o assistente de configuração.

function run(cmd, args, timeout = 5000) {
  return new Promise((resolve) => {
    execFile(cmd, args, { timeout, encoding: 'utf8' }, (err, stdout, stderr) => resolve({ ok: !err, out: stdout || '', err: stderr || '' }));
  });
}

function read(file) {
  try {
    return fs.readFileSync(file, 'utf8').trim();
  } catch (e) {
    return '';
  }
}

// Dispositivos internos do Pi (codec, ISP, câmera CSI) não são placas de captura.
const INTERNAL = /^(bcm2835|rpivid|rpi-hevc|pispbe|rp1-cfe|unicam|hantro|cedrus)/i;

// Interpreta a saída de `v4l2-ctl --list-formats-ext`.
function parseFormats(text) {
  const formats = [];
  let cur = null;
  let size = null;
  for (const line of text.split('\n')) {
    let m = line.match(/\[\d+\]:\s+'(\w+)'\s+\((.+?)\)/);
    if (m) {
      cur = { fourcc: m[1], description: m[2], sizes: [] };
      formats.push(cur);
      continue;
    }
    m = line.match(/Size:\s+Discrete\s+(\d+)x(\d+)/);
    if (m && cur) {
      size = { width: Number(m[1]), height: Number(m[2]), fps: [] };
      cur.sizes.push(size);
      continue;
    }
    m = line.match(/Interval:.*\(([\d.]+)\s*fps\)/);
    if (m && size) {
      const f = Math.round(Number(m[1]) * 100) / 100;
      if (!size.fps.includes(f)) size.fps.push(f);
    }
  }
  for (const f of formats) {
    f.sizes.sort((a, b) => b.width * b.height - a.width * a.height);
    for (const s of f.sizes) s.fps.sort((a, b) => b - a);
  }
  return formats;
}

// Nome do formato no ffmpeg (-input_format) a partir do FourCC do V4L2.
function ffmpegFormat(fourcc) {
  return { MJPG: 'mjpeg', YUYV: 'yuyv422', NV12: 'nv12', YU12: 'yuv420p', H264: 'h264', UYVY: 'uyvy422', RGB3: 'rgb24' }[fourcc] || null;
}

async function videoDevices() {
  const base = '/sys/class/video4linux';
  let names = [];
  try {
    names = fs.readdirSync(base).filter((n) => /^video\d+$/.test(n));
  } catch (e) {
    return [];
  }
  names.sort((a, b) => Number(a.slice(5)) - Number(b.slice(5)));
  const out = [];
  for (const n of names) {
    const dev = `/dev/${n}`;
    const name = read(path.join(base, n, 'name')) || n;
    if (INTERNAL.test(name)) continue;
    const info = await run('v4l2-ctl', ['-d', dev, '--info']);
    if (info.ok) {
      // Só nós de captura (placas UVC criam também um nó de metadados).
      const caps = (info.out.split('Device Caps')[1] || info.out).toLowerCase();
      if (!caps.includes('video capture') || caps.includes('memory-to-memory')) continue;
    }
    const fmt = info.ok ? await run('v4l2-ctl', ['-d', dev, '--list-formats-ext']) : { ok: false, out: '' };
    const formats = parseFormats(fmt.out)
      .map((f) => ({ ...f, ffmpeg: ffmpegFormat(f.fourcc) }))
      .filter((f) => f.ffmpeg && f.sizes.length);
    if (info.ok && !formats.length) continue;
    const bus = (info.out.match(/Bus info\s*:\s*(.+)/) || [])[1] || '';
    out.push({ path: dev, name, bus: bus.trim(), formats, toolMissing: !info.ok });
  }
  return out;
}

function audioDevices() {
  const text = read('/proc/asound/cards');
  const out = [];
  const re = /^\s*(\d+)\s+\[(\S+)\s*\]:\s+(.+?)\s+-\s+(.+)$/gm;
  let m;
  while ((m = re.exec(text))) {
    const [, num, id, driver, longName] = m;
    let captures = false;
    try {
      captures = fs.readdirSync(`/proc/asound/card${num}`).some((f) => /^pcm\d+c$/.test(f));
    } catch (e) {}
    if (!captures) continue;
    out.push({ card: Number(num), id, name: longName.trim(), driver: driver.trim(), alsa: `hw:CARD=${id},DEV=0` });
  }
  return out;
}

async function detect() {
  const [video, audio] = await Promise.all([videoDevices(), audioDevices()]);
  const tools = { v4l2ctl: (await run('v4l2-ctl', ['--version'])).ok, ffmpeg: (await run('ffmpeg', ['-hide_banner', '-version'])).ok };
  return { video, audio, tools };
}

module.exports = { detect, parseFormats, run };
