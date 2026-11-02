'use strict';
const { spawn } = require('child_process');
const EventEmitter = require('events');
const fs = require('fs');
const path = require('path');
const encoder = require('./encoder');
const { Hysteresis, analyzeFrame, audioLevels, FLOOR_DB } = require('./detectors');
const { logger } = require('./log');

// Códigos enviados na trap (compatíveis com a v2: alarme = N, normalizado = N + 10).
const CODES = { freeze: 2, silence: 3, black: 4, signal: 5 };
const MESSAGES = {
  freeze: ['Imagem congelada', 'Imagem voltou a se mover'],
  black: ['Tela preta', 'Imagem restabelecida'],
  silence: ['Áudio em silêncio', 'Áudio restabelecido'],
  signal: ['Sem sinal na entrada', 'Sinal restabelecido'],
};
const AUDIO_CH = 2;
const EOI = Buffer.from([0xff, 0xd9]);
const MAX_JPEG = 4 * 1024 * 1024;

// Um canal = uma entrada monitorada = um processo ffmpeg.
// O ffmpeg decodifica uma única vez e entrega três saídas leves:
//   fd 3: quadros em cinza, pequenos (ex.: 160x90 a 5 q/s) para análise
//   fd 4: áudio PCM s16le estéreo em taxa baixa, para medidores e silêncio
//   fd 5: JPEG pequeno (ex.: 1 q/s) para o preview na GUI
// e, se habilitado, o stream ao vivo em HLS (H.264 + AAC, segmentos de 1 s)
// gravado em RAM (/dev/shm), servido por HTTP — nada de UDP saindo do Pi.
class Channel extends EventEmitter {
  constructor(cfg, opts = {}) {
    super();
    this.cfg = cfg;
    this.ffmpegPath = opts.ffmpegPath || 'ffmpeg';
    this.legacyVsync = !!opts.legacyVsync;
    this.log = logger(cfg.id);
    this.encoder = cfg.stream.enabled && (cfg.video || cfg.audio) ? opts.encoder || null : null;
    this.streamDir = opts.streamDir ? path.join(opts.streamDir, cfg.id) : null;
    this.streamOn = !!(cfg.stream.enabled && this.streamDir && (this.encoder || !cfg.video));
    if (this.streamOn && cfg.video && this.encoder === 'libx264' && cfg.stream.width > cfg.stream.softwareMaxWidth) {
      // Codificação por software no Pi: reduz a resolução para não saturar a CPU.
      this.streamWidth = cfg.stream.softwareMaxWidth;
    } else {
      this.streamWidth = cfg.stream.width;
    }
    this.streamWidth -= this.streamWidth % 2;
    this.streamReady = false;

    this.proc = null;
    this.state = 'stopped';
    this.stopping = false;
    this.restarts = 0;
    this.backoff = cfg.restart.minSeconds * 1000;
    this.restartTimer = null;
    this.startedAt = 0;
    this.firstDataAt = 0;
    this.lastVideoAt = 0;
    this.lastAudioAt = 0;
    this.lastGoodAt = 0;
    this.stderrTail = [];
    this.lastError = '';
    this.source = { video: '', audio: '' };

    const clearMs = cfg.clearSeconds * 1000;
    this.det = {
      signal: new Hysteresis(0, clearMs),
      freeze: new Hysteresis(cfg.freeze.seconds * 1000, clearMs),
      black: new Hysteresis(cfg.black.seconds * 1000, clearMs),
      silence: new Hysteresis(cfg.silence.seconds * 1000, clearMs),
    };
    this.alarmSince = { signal: 0, freeze: 0, black: 0, silence: 0 };

    const { width, height } = cfg.analysis;
    this.frameSize = width * height;
    this.frameA = Buffer.alloc(this.frameSize);
    this.frameB = Buffer.alloc(this.frameSize);
    this.cur = this.frameA;
    this.prev = null;
    this.frameFill = 0;
    this.blockSize = Math.round(cfg.audioRate / 10) * AUDIO_CH * 2; // blocos de 100 ms
    this.block = Buffer.alloc(this.blockSize);
    this.blockFill = 0;
    this.jpegBuf = null;
    this.jpeg = null;
    this.jpegAt = 0;

    this.metrics = { motionPct: null, luma: null, blackPct: null, levels: null, fps: 0 };
    this.frameCount = 0;
    this.fpsWindowStart = Date.now();
  }

  buildArgs() {
    const c = this.cfg;
    const a = ['-hide_banner', '-nostdin', '-nostats', '-loglevel', 'info'];
    if (c.threads > 0) a.push('-threads', String(c.threads));
    a.push(...c.decoderArgs, ...c.inputArgs);
    a.push('-filter_threads', '1');

    // select (em vez de fps) só descarta quadros, nunca duplica: entrada parada
    // vira "sem sinal" e não um falso congelamento.
    const pick = (sec) => `select='isnan(prev_selected_t)+gte(abs(t-prev_selected_t)\\,${sec.toFixed(3)})'`;
    const vfr = this.legacyVsync ? ['-vsync', '0'] : ['-fps_mode', 'passthrough'];
    const st = c.stream;
    const streamVideo = this.streamOn && c.video;
    if (c.video) {
      const { fps, width, height } = c.analysis;
      const branches = ['ana'];
      if (c.preview.enabled) branches.push('pv');
      if (streamVideo) branches.push('st');
      const n = branches.length;
      let g = `[${c.videoStream}]`;
      g += n > 1 ? `split=${n}${branches.map((b) => `[${b}0]`).join('')};` : 'null[ana0];';
      g += `[ana0]${pick((1 / fps) * 0.95)},scale=${width}:${height}:flags=area,format=gray[ana]`;
      if (c.preview.enabled) {
        const p = c.preview;
        g += `;[pv0]${pick((1 / p.fps) * 0.95)},scale=${p.width}:-2:flags=bilinear,format=yuvj420p[pv]`;
      }
      if (streamVideo) {
        g += `;[st0]fps=${st.fps},scale='min(iw,${this.streamWidth})':-2:flags=bilinear,format=yuv420p[st]`;
      }
      a.push('-filter_complex', g);
      a.push('-map', '[ana]', ...vfr, '-f', 'rawvideo', '-pix_fmt', 'gray', 'pipe:3');
      if (c.preview.enabled) a.push('-map', '[pv]', ...vfr, '-c:v', 'mjpeg', '-q:v', String(c.preview.quality), '-f', 'image2pipe', 'pipe:5');
    }
    if (c.audio) {
      a.push('-map', c.audioStream, '-vn', '-sn', '-ac', String(AUDIO_CH), '-ar', String(c.audioRate), '-c:a', 'pcm_s16le', '-f', 's16le', 'pipe:4');
    }
    if (this.streamOn) {
      if (streamVideo) {
        a.push('-map', '[st]', ...encoder.videoArgs(this.encoder, st), '-bsf:v', 'dump_extra=freq=keyframe');
      }
      if (c.audio) a.push('-map', c.audioStream, '-c:a', 'aac', '-b:a', st.audioBitrate, '-ac', '2', '-ar', '48000');
      const list = Math.max(3, Math.round(st.windowSeconds / st.segmentSeconds));
      a.push(
        '-f', 'hls',
        '-hls_time', String(st.segmentSeconds),
        '-hls_list_size', String(list),
        '-hls_delete_threshold', '3',
        '-hls_flags', 'delete_segments+independent_segments+omit_endlist+temp_file',
        '-hls_start_number_source', 'epoch',
        '-hls_segment_type', 'mpegts',
        '-hls_segment_filename', path.join(this.streamDir, 'seg_%d.ts'),
        path.join(this.streamDir, 'index.m3u8')
      );
    }
    return a;
  }

  prepareStreamDir() {
    if (!this.streamOn) return;
    try {
      // Recria a pasta do zero: remove qualquer resto (inclusive lixo inesperado).
      fs.rmSync(this.streamDir, { recursive: true, force: true });
      fs.mkdirSync(this.streamDir, { recursive: true });
    } catch (e) {
      this.log.warn(`não foi possível preparar ${this.streamDir}: ${e.message}`);
    }
    this.streamReady = false;
  }

  start() {
    if (this.proc) return;
    this.stopping = false;
    clearTimeout(this.restartTimer);
    this.restartTimer = null;
    this.prepareStreamDir();
    this.streamKill = false;
    const args = this.buildArgs();
    this.log.debug('ffmpeg ' + args.join(' '));
    const now = Date.now();
    this.startedAt = now;
    if (!this.lastGoodAt) this.lastGoodAt = now;
    this.firstDataAt = 0;
    this.prev = null;
    this.frameFill = 0;
    this.blockFill = 0;
    this.jpegBuf = null;
    this.state = 'starting';
    const seen = { video: false, audio: false };
    let inOutput = false;

    let proc;
    try {
      proc = spawn(this.ffmpegPath, args, { stdio: ['ignore', 'ignore', 'pipe', 'pipe', 'pipe', 'pipe'] });
    } catch (e) {
      this.onExit(null, e.message);
      return;
    }
    this.proc = proc;

    proc.on('error', (e) => {
      this.lastError = e.code === 'ENOENT' ? `ffmpeg não encontrado (${this.ffmpegPath}). Instale com: sudo apt install ffmpeg` : e.message;
    });
    proc.on('close', (code, signal) => this.onExit(code, signal));

    let tail = '';
    proc.stdio[2].on('data', (d) => {
      tail += d.toString('utf8');
      let i;
      while ((i = tail.search(/[\r\n]/)) >= 0) {
        const line = tail.slice(0, i).trim();
        tail = tail.slice(i + 1);
        if (!line) continue;
        if (/^Output #/.test(line)) inOutput = true;
        if (!inOutput) {
          const m = line.match(/Stream #\d+:\d+.*?: (Video|Audio): (.*)$/);
          if (m) {
            const k = m[1] === 'Video' ? 'video' : 'audio';
            if (!seen[k]) {
              seen[k] = true; // mantém a última descrição conhecida entre reconexões
              this.source[k] = m[2].replace(/\s*\(default\)\s*$/, '').slice(0, 160);
            }
          }
        }
        this.stderrTail.push(line.slice(0, 300));
        if (this.stderrTail.length > 40) this.stderrTail.shift();
        if (/error|failed|invalid|no such|not found|refused|timed out|cannot|unable|denied|busy|matches no streams/i.test(line)) {
          this.lastError = line.slice(0, 300);
          this.log.debug(line);
        }
      }
      if (tail.length > 4096) tail = tail.slice(-1024);
    });

    for (const fd of [3, 4, 5]) proc.stdio[fd].on('error', () => {});
    if (this.cfg.video) {
      proc.stdio[3].on('data', (d) => this.onVideo(d));
      proc.stdio[5].on('data', (d) => this.onJpeg(d));
    }
    if (this.cfg.audio) proc.stdio[4].on('data', (d) => this.onAudio(d));
    this.log.info(`ffmpeg iniciado (pid ${proc.pid})`);
  }

  onExit(code, signal) {
    const wasRunning = this.state === 'running';
    this.proc = null;
    if (this.stopping) {
      this.state = 'stopped';
      return;
    }
    const ranMs = Date.now() - this.startedAt;
    // Se rodou estável por 60 s, o próximo erro volta a tentar rápido.
    if (wasRunning && ranMs > 60000) this.backoff = this.cfg.restart.minSeconds * 1000;
    const wait = this.backoff;
    this.backoff = Math.min(this.backoff * 2, this.cfg.restart.maxSeconds * 1000);
    this.restarts++;
    this.state = 'restarting';
    this.log.warn(`ffmpeg terminou (${signal || 'código ' + code})${this.lastError ? ': ' + this.lastError : ''}. Nova tentativa em ${(wait / 1000).toFixed(0)} s`);
    this.restartTimer = setTimeout(() => this.start(), wait);
  }

  markData(now) {
    if (!this.firstDataAt) {
      this.firstDataAt = now;
      this.state = 'running';
      this.lastError = '';
    }
  }

  warm(now) {
    return this.firstDataAt && now - this.firstDataAt >= this.cfg.warmupSeconds * 1000;
  }

  onVideo(chunk) {
    let off = 0;
    while (off < chunk.length) {
      const n = Math.min(this.frameSize - this.frameFill, chunk.length - off);
      chunk.copy(this.cur, this.frameFill, off, off + n);
      this.frameFill += n;
      off += n;
      if (this.frameFill === this.frameSize) {
        this.frameFill = 0;
        this.onFrame(this.cur);
        this.prev = this.cur;
        this.cur = this.cur === this.frameA ? this.frameB : this.frameA;
      }
    }
  }

  onFrame(frame) {
    const now = Date.now();
    this.lastVideoAt = now;
    this.markData(now);
    this.frameCount++;
    const c = this.cfg;
    const m = analyzeFrame(frame, this.prev, c.freeze.pixelDelta, c.black.pixelLuma);
    this.metrics.motionPct = m.motionPct;
    this.metrics.luma = m.luma;
    this.metrics.blackPct = m.blackPct;
    if (!this.warm(now)) {
      this.det.freeze.hold();
      this.det.black.hold();
      return;
    }
    const isBlack = m.blackPct >= c.black.pct;
    if (c.black.enabled) this.apply('black', this.det.black.update(isBlack, now), now);
    // Tela preta também é "parada": quando ela está presente, não acusa congelamento.
    const frozen = m.motionPct < c.freeze.motionPct && !(c.black.enabled && isBlack);
    if (c.freeze.enabled) this.apply('freeze', this.det.freeze.update(frozen, now), now);
  }

  onAudio(chunk) {
    let off = 0;
    while (off < chunk.length) {
      const n = Math.min(this.blockSize - this.blockFill, chunk.length - off);
      chunk.copy(this.block, this.blockFill, off, off + n);
      this.blockFill += n;
      off += n;
      if (this.blockFill === this.blockSize) {
        this.blockFill = 0;
        this.onAudioBlock(this.block);
      }
    }
  }

  onAudioBlock(block) {
    const now = Date.now();
    this.lastAudioAt = now;
    this.markData(now);
    const levels = audioLevels(block, AUDIO_CH);
    this.metrics.levels = levels;
    if (!this.warm(now)) {
      this.det.silence.hold();
      return;
    }
    const loudest = Math.max(...levels.map((l) => l.rms));
    if (this.cfg.silence.enabled) this.apply('silence', this.det.silence.update(loudest < this.cfg.silence.dbfs, now), now);
  }

  onJpeg(chunk) {
    this.jpegBuf = this.jpegBuf ? Buffer.concat([this.jpegBuf, chunk]) : chunk;
    for (;;) {
      const end = this.jpegBuf.indexOf(EOI);
      if (end < 0) break;
      const img = this.jpegBuf.subarray(0, end + 2);
      this.jpegBuf = this.jpegBuf.subarray(end + 2);
      if (img[0] === 0xff && img[1] === 0xd8) {
        this.jpeg = Buffer.from(img); // cópia: solta o buffer grande
        this.jpegAt = Date.now();
        this.emit('jpeg', this.jpeg);
      }
    }
    if (this.jpegBuf.length > MAX_JPEG) this.jpegBuf = null;
    else if (this.jpegBuf.length === 0) this.jpegBuf = null;
  }

  apply(type, change, now) {
    if (!change) return;
    const active = change === 'raise';
    this.alarmSince[type] = active ? now : 0;
    const [onMsg, offMsg] = MESSAGES[type];
    const ev = {
      channel: this.cfg.id,
      channelIndex: this.cfg.index,
      channelName: this.cfg.name,
      type,
      active,
      code: active ? CODES[type] : CODES[type] + 10,
      message: active ? onMsg : offMsg,
    };
    if (active && type === 'signal' && this.lastError) ev.detail = this.lastError;
    (active ? this.log.warn : this.log.info)(ev.message);
    this.emit('alarm', ev);
  }

  // Chamado 1x por segundo: watchdog de entrada e alarme de "sem sinal".
  tick(now = Date.now()) {
    const fps = (this.frameCount * 1000) / Math.max(1, now - this.fpsWindowStart);
    this.metrics.fps = Math.round(fps * 10) / 10;
    this.frameCount = 0;
    this.fpsWindowStart = now;
    if (this.stopping) return;
    let playlistAge = Infinity;
    if (this.streamOn) {
      try {
        playlistAge = now - fs.statSync(path.join(this.streamDir, 'index.m3u8')).mtimeMs;
      } catch (e) {}
      this.streamReady = playlistAge < Math.max(6000, this.cfg.stream.segmentSeconds * 4000);
    }

    const c = this.cfg;
    const stallMs = c.signal.stallSeconds * 1000;
    // "Fluindo" = este processo entregou dados de todas as mídias habilitadas recentemente.
    const fresh = (t) => t >= this.startedAt && now - t <= stallMs;
    const flowing = !!this.proc && (!c.video || fresh(this.lastVideoAt)) && (!c.audio || fresh(this.lastAudioAt));
    if (flowing) this.lastGoodAt = now;

    // Análise recebendo dados mas o stream ao vivo parado (encoder travado, RAM
    // cheia…): reinicia a captura para o stream voltar.
    if (this.streamOn && flowing && !this.streamKill) {
      const staleMs = Math.max(10000, c.stream.segmentSeconds * 8000);
      const graceMs = Math.max(20000, staleMs * 2);
      if (now - this.startedAt > graceMs && playlistAge > staleMs) {
        const ago = Number.isFinite(playlistAge) ? `há ${Math.round(playlistAge / 1000)} s` : 'desde o início';
        this.log.warn(`stream ao vivo parado ${ago} com a entrada normal; reiniciando ffmpeg`);
        this.emit('notice', {
          channel: c.id,
          channelIndex: c.index,
          channelName: c.name,
          type: 'stream',
          active: false,
          message: 'Stream ao vivo parado; captura reiniciada',
          detail: [...this.stderrTail].reverse().find((l) => /hls @|m3u8|\.ts\b|No space/i.test(l)),
        });
        this.streamKill = true;
        this.kill();
      }
    }

    // Processo vivo mas sem entregar dados: está preso. Mata e o onExit reinicia.
    if (this.proc && !flowing && now - this.startedAt > stallMs) {
      const vStall = c.video && !fresh(this.lastVideoAt);
      this.log.warn(`sem ${vStall ? 'vídeo' : 'áudio'} há ${c.signal.stallSeconds} s; reiniciando ffmpeg`);
      this.kill();
    }

    // Dispara após stallSeconds sem fluxo; só normaliza com dados chegando de fato.
    const noSignal = this.det.signal.active ? !flowing : !flowing && now - this.lastGoodAt > stallMs;
    this.apply('signal', this.det.signal.update(noSignal, now), now);
    if (!flowing) {
      // Sem sinal: congela a avaliação dos outros detectores (sem traps espúrias).
      this.det.freeze.hold();
      this.det.black.hold();
      this.det.silence.hold();
      this.metrics.levels = null;
      this.metrics.motionPct = null;
      this.metrics.luma = null;
      this.metrics.blackPct = null;
    }
  }

  kill() {
    const p = this.proc;
    if (!p) return;
    try {
      p.kill('SIGTERM');
    } catch (e) {}
    setTimeout(() => {
      if (p.exitCode === null && p.signalCode === null) {
        try {
          p.kill('SIGKILL');
        } catch (e) {}
      }
    }, 2000).unref();
  }

  restart() {
    this.log.info('reinício manual');
    this.backoff = this.cfg.restart.minSeconds * 1000;
    if (this.proc) this.kill();
    else this.start();
  }

  stop() {
    this.stopping = true;
    clearTimeout(this.restartTimer);
    this.kill();
    return new Promise((resolve) => {
      if (!this.proc) return resolve();
      const p = this.proc;
      p.once('close', resolve);
      setTimeout(resolve, 3000).unref();
    });
  }

  alarmState(type) {
    const c = this.cfg;
    if (type === 'freeze' && (!c.video || !c.freeze.enabled)) return 'off';
    if (type === 'black' && (!c.video || !c.black.enabled)) return 'off';
    if (type === 'silence' && (!c.audio || !c.silence.enabled)) return 'off';
    const d = this.det[type];
    if (d.active) return 'alarm';
    if (d.pending()) return 'pending';
    return 'ok';
  }

  status(now = Date.now()) {
    const alarms = {};
    let overall = 'ok';
    for (const t of ['signal', 'freeze', 'black', 'silence']) {
      const s = this.alarmState(t);
      alarms[t] = { state: s, since: this.alarmSince[t] || null };
      if (s === 'alarm') overall = 'alarm';
      else if (s === 'pending' && overall === 'ok') overall = 'warn';
    }
    if (overall === 'ok' && (this.state !== 'running' || !this.warm(now))) overall = 'starting';
    const m = this.metrics;
    const r1 = (v) => (v === null || v === undefined ? null : Math.round(v * 100) / 100);
    return {
      id: this.cfg.id,
      index: this.cfg.index,
      name: this.cfg.name,
      video: this.cfg.video,
      audio: this.cfg.audio,
      preview: this.cfg.video && this.cfg.preview.enabled,
      state: this.state,
      overall,
      pid: this.proc ? this.proc.pid : null,
      runningFor: this.firstDataAt ? Math.round((now - this.firstDataAt) / 1000) : 0,
      restarts: this.restarts,
      lastError: this.lastError,
      source: this.source,
      jpegAt: this.jpegAt || null,
      metrics: {
        fps: m.fps,
        motionPct: r1(m.motionPct),
        luma: r1(m.luma),
        blackPct: r1(m.blackPct),
        levels: m.levels ? m.levels.map((l) => ({ rms: Math.round(l.rms * 10) / 10, peak: Math.round(l.peak * 10) / 10 })) : null,
      },
      alarms,
      stream: this.streamOn
        ? {
            ready: this.streamReady,
            encoder: this.cfg.video ? this.encoder : null,
            width: this.cfg.video ? this.streamWidth : null,
            fps: this.cfg.video ? this.cfg.stream.fps : null,
            bitrate: this.cfg.video ? this.cfg.stream.bitrate : null,
            audioBitrate: this.cfg.audio ? this.cfg.stream.audioBitrate : null,
            segmentSeconds: this.cfg.stream.segmentSeconds,
            windowSeconds: this.cfg.stream.windowSeconds,
          }
        : null,
      thresholds: {
        freezeMotionPct: this.cfg.freeze.motionPct,
        freezeSeconds: this.cfg.freeze.seconds,
        blackPct: this.cfg.black.pct,
        blackSeconds: this.cfg.black.seconds,
        silenceDbfs: this.cfg.silence.dbfs,
        silenceSeconds: this.cfg.silence.seconds,
      },
    };
  }

  // Caminho de um arquivo do HLS (index.m3u8 ou seg_N.ts) — ou null se inválido.
  hlsFile(name) {
    if (!this.streamOn || !/^(index\.m3u8|seg_\d{1,20}\.ts)$/.test(name)) return null;
    return path.join(this.streamDir, name);
  }

  diagnostics() {
    return { id: this.cfg.id, args: this.buildArgs(), stderr: this.stderrTail.slice() };
  }
}

module.exports = { Channel, CODES, FLOOR_DB };
