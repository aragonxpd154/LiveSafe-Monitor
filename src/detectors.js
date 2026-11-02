'use strict';
// Funções puras de análise — sem I/O, fáceis de testar.

// Histerese temporal: a condição precisa ficar verdadeira por `raiseMs` para
// disparar e falsa por `clearMs` para normalizar. Evita alarmes "piscando".
class Hysteresis {
  constructor(raiseMs, clearMs) {
    this.raiseMs = raiseMs;
    this.clearMs = clearMs;
    this.active = false;
    this.trueSince = null;
    this.falseSince = null;
  }

  // Retorna 'raise', 'clear' ou null.
  update(condition, now) {
    if (condition) {
      this.falseSince = null;
      if (this.trueSince === null) this.trueSince = now;
      if (!this.active && now - this.trueSince >= this.raiseMs) {
        this.active = true;
        return 'raise';
      }
    } else {
      this.trueSince = null;
      if (this.falseSince === null) this.falseSince = now;
      if (this.active && now - this.falseSince >= this.clearMs) {
        this.active = false;
        return 'clear';
      }
    }
    return null;
  }

  // Condição presente mas ainda dentro do tempo de tolerância.
  pending() {
    return !this.active && this.trueSince !== null;
  }

  // Esquece a contagem em andamento (mantém o estado ativo/inativo).
  hold() {
    this.trueSince = null;
    this.falseSince = null;
  }
}

// Métricas de um quadro em escala de cinza (1 byte por pixel).
//  motionPct: % de pixels que mudaram mais que pixelDelta desde o quadro anterior
//  blackPct:  % de pixels mais escuros que pixelLuma
//  luma:      luminância média 0–255
function analyzeFrame(cur, prev, pixelDelta, pixelLuma) {
  const n = cur.length;
  let changed = 0;
  let dark = 0;
  let sum = 0;
  if (prev && prev.length === n) {
    for (let i = 0; i < n; i++) {
      const v = cur[i];
      sum += v;
      if (v <= pixelLuma) dark++;
      const d = v - prev[i];
      if (d > pixelDelta || d < -pixelDelta) changed++;
    }
  } else {
    for (let i = 0; i < n; i++) {
      const v = cur[i];
      sum += v;
      if (v <= pixelLuma) dark++;
    }
    changed = n; // sem quadro anterior: não afirmar congelamento
  }
  return {
    motionPct: (changed * 100) / n,
    blackPct: (dark * 100) / n,
    luma: sum / n,
  };
}

const FLOOR_DB = -96;

function toDb(x) {
  return x > 0 ? Math.max(FLOOR_DB, 20 * Math.log10(x)) : FLOOR_DB;
}

// Níveis de um bloco PCM s16le intercalado com `channels` canais.
// Retorna [{ rms, peak }] em dBFS por canal.
function audioLevels(buf, channels) {
  const frames = Math.floor(buf.length / (2 * channels));
  const sq = new Float64Array(channels);
  const pk = new Float64Array(channels);
  let off = 0;
  for (let f = 0; f < frames; f++) {
    for (let c = 0; c < channels; c++) {
      const s = buf.readInt16LE(off) / 32768;
      off += 2;
      sq[c] += s * s;
      const a = s < 0 ? -s : s;
      if (a > pk[c]) pk[c] = a;
    }
  }
  const out = [];
  for (let c = 0; c < channels; c++) {
    out.push({ rms: toDb(frames ? Math.sqrt(sq[c] / frames) : 0), peak: toDb(pk[c]) });
  }
  return out;
}

module.exports = { Hysteresis, analyzeFrame, audioLevels, FLOOR_DB };
