'use strict';
const test = require('node:test');
const assert = require('node:assert');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { Hysteresis, analyzeFrame, audioLevels } = require('../src/detectors');
const config = require('../src/config');
const { Channel } = require('../src/channel');

test('histerese só dispara depois do tempo e só normaliza depois do tempo de limpeza', () => {
  const h = new Hysteresis(1000, 500);
  assert.equal(h.update(true, 0), null);
  assert.ok(h.pending());
  assert.equal(h.update(true, 999), null);
  assert.equal(h.update(true, 1000), 'raise');
  assert.equal(h.update(true, 1500), null);
  assert.equal(h.update(false, 1600), null);
  assert.equal(h.update(true, 1700), null); // voltou antes de normalizar
  assert.equal(h.update(false, 1800), null);
  assert.equal(h.update(false, 2300), 'clear');
  assert.equal(h.active, false);
});

test('hold zera a contagem sem mudar o estado', () => {
  const h = new Hysteresis(1000, 0);
  h.update(true, 0);
  h.hold();
  assert.equal(h.update(true, 900), null);
  assert.equal(h.update(true, 1899), null);
  assert.equal(h.update(true, 1900), 'raise');
});

test('quadro idêntico tem movimento zero; quadro preto é detectado', () => {
  const a = Buffer.alloc(100, 120);
  const b = Buffer.from(a);
  assert.equal(analyzeFrame(b, a, 12, 32).motionPct, 0);
  b[0] = 200;
  assert.equal(analyzeFrame(b, a, 12, 32).motionPct, 1);
  const black = Buffer.alloc(100, 16);
  const m = analyzeFrame(black, null, 12, 32);
  assert.equal(m.blackPct, 100);
  assert.equal(m.motionPct, 100); // sem quadro anterior não acusa congelamento
});

test('níveis de áudio em dBFS', () => {
  const frames = 1600;
  const buf = Buffer.alloc(frames * 4);
  for (let i = 0; i < frames; i++) {
    buf.writeInt16LE(i % 2 ? 16384 : -16384, i * 4); // L: onda quadrada a -6 dBFS
    buf.writeInt16LE(0, i * 4 + 2); // R: silêncio
  }
  const [l, r] = audioLevels(buf, 2);
  assert.ok(Math.abs(l.rms - -6.02) < 0.1, `L rms ${l.rms}`);
  assert.ok(r.rms <= -96);
});

test('config: valida, aplica padrões e sobrescreve por canal', () => {
  const tmp = path.join(os.tmpdir(), `livesafe-${process.pid}.json`);
  fs.writeFileSync(
    tmp,
    JSON.stringify({
      defaults: { freeze: { seconds: 7 } },
      channels: [
        { id: 'a', url: 'udp://@239.1.1.1:1234' },
        { id: 'b', video: false, url: 'http://x/radio', silence: { dbfs: -50 } },
      ],
    })
  );
  const c = config.load(tmp);
  fs.unlinkSync(tmp);
  assert.equal(c.channels[0].freeze.seconds, 7);
  assert.equal(c.channels[0].black.seconds, 5);
  assert.equal(c.channels[1].silence.dbfs, -50);
  assert.equal(c.channels[1].silence.seconds, 10);
  assert.ok(c.channels[0].inputArgs.includes('+discardcorrupt'));
  const args = new Channel(c.channels[1]).buildArgs();
  assert.ok(!args.includes('-filter_complex'), 'canal só de áudio não decodifica vídeo');
});

test('config: rejeita canal sem entrada e ids repetidos', () => {
  assert.throws(() => config.normalizeChannel({ id: 'x' }, 0, config.DEFAULTS.defaults), /url/);
  const tmp = path.join(os.tmpdir(), `livesafe-dup-${process.pid}.json`);
  fs.writeFileSync(tmp, JSON.stringify({ channels: [{ id: 'a', url: 'x' }, { id: 'a', url: 'y' }] }));
  assert.throws(() => config.load(tmp), /repetido/);
  fs.unlinkSync(tmp);
});

test('cache do central: pedidos simultâneos geram um único download', async () => {
  const { ProxyCache } = require('../src/remote');
  const cache = new ProxyCache(1024 * 1024);
  let calls = 0;
  const loader = () => new Promise((r) => setTimeout(() => { calls++; r({ status: 200, type: 'video/mp2t', body: Buffer.alloc(1000) }); }, 20));
  const res = await Promise.all(Array.from({ length: 10 }, () => cache.fetch('a', 60000, loader)));
  assert.equal(calls, 1);
  assert.equal(res.length, 10);
  await cache.fetch('a', 60000, loader);
  assert.equal(calls, 1, 'segundo pedido sai do cache');
});

test('config: servidor central só com sites', () => {
  const s = config.normalizeSite({ id: 'serra', name: 'Serra', host: '10.0.0.5' }, 0);
  assert.equal(s.url, 'http://10.0.0.5:8080');
  assert.throws(() => config.normalizeSite({ id: 'x' }, 0), /url/);
});

test('placa HDMI-USB (MS2109): lê formatos, resoluções e quadros por segundo do v4l2-ctl', () => {
  const { parseFormats } = require('../src/devices');
  const out = `ioctl: VIDIOC_ENUM_FMT
\tType: Video Capture

\t[0]: 'MJPG' (Motion-JPEG, compressed)
\t\tSize: Discrete 1920x1080
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t\tSize: Discrete 1280x720
\t\t\tInterval: Discrete 0.017s (60.000 fps)
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t[1]: 'YUYV' (YUYV 4:2:2)
\t\tSize: Discrete 1920x1080
\t\t\tInterval: Discrete 0.200s (5.000 fps)
\t\tSize: Discrete 640x480
\t\t\tInterval: Discrete 0.033s (30.000 fps)
`;
  const f = parseFormats(out);
  assert.equal(f.length, 2);
  assert.equal(f[0].fourcc, 'MJPG');
  assert.deepEqual(f[0].sizes.map((s) => `${s.width}x${s.height}`), ['1920x1080', '1280x720']);
  assert.deepEqual(f[0].sizes[1].fps, [60, 30]);
  assert.equal(f[1].sizes[0].fps[0], 5);
});
