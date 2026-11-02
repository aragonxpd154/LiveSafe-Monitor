'use strict';
const crypto = require('crypto');

// Senhas guardadas como hash scrypt — o config.json nunca tem a senha em texto.
// Formato: scrypt$N$r$p$<sal base64>$<hash base64>
const PARAMS = { N: 16384, r: 8, p: 1 };

function hashPassword(password) {
  const salt = crypto.randomBytes(16);
  const hash = crypto.scryptSync(String(password), salt, 32, PARAMS);
  return `scrypt$${PARAMS.N}$${PARAMS.r}$${PARAMS.p}$${salt.toString('base64')}$${hash.toString('base64')}`;
}

function verifyPassword(password, stored) {
  const parts = String(stored || '').split('$');
  if (parts.length !== 6 || parts[0] !== 'scrypt') return false;
  const [, N, r, p, saltB64, hashB64] = parts;
  const expected = Buffer.from(hashB64, 'base64');
  let got;
  try {
    got = crypto.scryptSync(String(password), Buffer.from(saltB64, 'base64'), expected.length, { N: Number(N), r: Number(r), p: Number(p) });
  } catch (e) {
    return false;
  }
  return got.length === expected.length && crypto.timingSafeEqual(got, expected);
}

// Verificador de Basic Auth com cache: o scrypt é caro de propósito, então
// um cabeçalho já validado não é recalculado a cada requisição da GUI.
function createChecker(authCfg) {
  const cache = new Map();
  const fails = new Map(); // ip -> { n, until }
  const configured = !!(authCfg && authCfg.user && (authCfg.passwordHash || authCfg.password));

  function check(req) {
    if (!configured) return { ok: true };
    const ip = req.socket.remoteAddress || '';
    const f = fails.get(ip);
    const now = Date.now();
    if (f && f.until > now) return { ok: false, locked: true };
    const header = req.headers.authorization || '';
    const hit = cache.get(header);
    if (hit && hit > now) return { ok: true };
    let ok = false;
    const m = header.match(/^Basic\s+(.+)$/i);
    if (m) {
      const decoded = Buffer.from(m[1], 'base64').toString('utf8');
      const i = decoded.indexOf(':');
      const user = decoded.slice(0, i);
      const pass = decoded.slice(i + 1);
      if (i > 0 && user === authCfg.user) {
        ok = authCfg.passwordHash ? verifyPassword(pass, authCfg.passwordHash) : safeEqual(pass, String(authCfg.password));
      }
    }
    if (ok) {
      if (cache.size > 100) cache.clear();
      cache.set(header, now + 10 * 60 * 1000);
      fails.delete(ip);
      return { ok: true };
    }
    if (header) {
      // 10 erros seguidos bloqueiam aquele IP por 1 minuto.
      const n = (f ? f.n : 0) + 1;
      fails.set(ip, { n: n >= 10 ? 0 : n, until: n >= 10 ? now + 60000 : 0 });
    }
    return { ok: false };
  }

  return { check, configured };
}

function safeEqual(a, b) {
  const x = Buffer.from(String(a));
  const y = Buffer.from(String(b));
  return x.length === y.length && crypto.timingSafeEqual(x, y);
}

module.exports = { hashPassword, verifyPassword, createChecker };
