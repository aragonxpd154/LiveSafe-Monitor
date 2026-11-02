'use strict';
// Log mínimo para stdout/stderr. No Pi, o systemd/journald guarda e rotaciona
// (nada de arquivo de log crescendo no cartão SD).

const LEVELS = { debug: 10, info: 20, warn: 30, error: 40 };
let current = LEVELS[(process.env.LOG_LEVEL || 'info').toLowerCase()] || LEVELS.info;
// Sob o systemd o journald já carimba a hora; fora dele, incluímos.
const withTime = !process.env.INVOCATION_ID;

function setLevel(name) {
  if (LEVELS[name]) current = LEVELS[name];
}

function write(level, scope, msg) {
  if (LEVELS[level] < current) return;
  const prefix = (withTime ? new Date().toISOString() + ' ' : '') + level.toUpperCase().padEnd(5) + ' [' + scope + '] ';
  (level === 'error' || level === 'warn' ? process.stderr : process.stdout).write(prefix + msg + '\n');
}

function logger(scope) {
  return {
    debug: (m) => write('debug', scope, m),
    info: (m) => write('info', scope, m),
    warn: (m) => write('warn', scope, m),
    error: (m) => write('error', scope, m),
  };
}

module.exports = { logger, setLevel };
