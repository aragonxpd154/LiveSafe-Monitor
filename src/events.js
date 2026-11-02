'use strict';
const fs = require('fs');
const path = require('path');
const EventEmitter = require('events');
const { logger } = require('./log');

const log = logger('eventos');

// Histórico de ocorrências: anel em memória + arquivo JSONL pequeno com
// rotação (arquivo -> arquivo.1). Só grava quando algo acontece, então o
// desgaste do cartão SD é desprezível.
class EventStore extends EventEmitter {
  constructor(cfg) {
    super();
    this.max = Math.max(50, cfg.memory || 500);
    this.file = cfg.file || null;
    this.maxBytes = cfg.maxBytes || 1024 * 1024;
    this.items = [];
    this.seq = 0;
    if (this.file) {
      try {
        fs.mkdirSync(path.dirname(this.file), { recursive: true });
        this.loadTail();
      } catch (e) {
        log.warn(`não foi possível usar ${this.file}: ${e.message}. Histórico só em memória.`);
        this.file = null;
      }
    }
  }

  loadTail() {
    for (const f of [this.file + '.1', this.file]) {
      if (!fs.existsSync(f)) continue;
      const lines = fs.readFileSync(f, 'utf8').split('\n');
      for (const l of lines) {
        if (!l) continue;
        try {
          this.items.push(JSON.parse(l));
        } catch (e) {}
      }
    }
    if (this.items.length > this.max) this.items = this.items.slice(-this.max);
    this.seq = this.items.reduce((m, e) => Math.max(m, e.id || 0), 0);
  }

  add(ev) {
    const item = { id: ++this.seq, ts: new Date().toISOString(), ...ev };
    this.items.push(item);
    if (this.items.length > this.max) this.items.shift();
    this.emit('event', item);
    if (this.file) this.persist(item);
    return item;
  }

  persist(item) {
    try {
      let size = 0;
      try {
        size = fs.statSync(this.file).size;
      } catch (e) {}
      if (size > this.maxBytes) fs.renameSync(this.file, this.file + '.1');
      fs.appendFileSync(this.file, JSON.stringify(item) + '\n');
    } catch (e) {
      log.warn('falha ao gravar histórico: ' + e.message);
    }
  }

  recent(limit = 100) {
    return this.items.slice(-limit).reverse();
  }
}

module.exports = { EventStore };
