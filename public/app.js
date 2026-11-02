'use strict';
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const wall = $('#wall');
  const siteTpl = $('#site-tpl');
  const tileTpl = $('#tile-tpl');
  const eventsEl = $('#events');
  const groups = new Map(); // key -> { el, tilesEl, tiles: Map }
  const nf1 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 });
  const nf0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });
  const PRIORITY = ['signal', 'black', 'freeze', 'silence'];
  const ALARM_TYPES = ['freeze', 'black', 'silence', 'signal', 'comm'];
  const ALARM_TEXT = { signal: 'Sem sinal', black: 'Tela preta', freeze: 'Imagem congelada', silence: 'Silêncio' };
  const PENDING_TEXT = { signal: 'Sinal instável', black: 'Possível tela preta', freeze: 'Possível congelamento', silence: 'Possível silêncio' };
  let clockOffset = 0;
  let events = [];
  let lastState = null;

  // ---------- utilidades ----------
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
  };
  const dbFrac = (db) => Math.max(0, Math.min(1, (db + 60) / 60));
  const dbText = (db) => (db <= -95 ? '−∞ dBFS' : nf0.format(db).replace('-', '−') + ' dBFS');
  const enc = encodeURIComponent;
  const now = () => Date.now() + clockOffset;

  function duration(sec) {
    sec = Math.max(0, Math.round(sec));
    if (sec < 60) return `${sec} s`;
    const m = Math.floor(sec / 60);
    if (m < 60) return `${m} min ${String(sec % 60).padStart(2, '0')} s`;
    const h = Math.floor(m / 60);
    if (h < 48) return `${h} h ${String(m % 60).padStart(2, '0')} min`;
    return `${Math.floor(h / 24)} d ${h % 24} h`;
  }
  function bytes(n) {
    if (n >= 1024 ** 3) return nf1.format(n / 1024 ** 3) + ' GB';
    return nf0.format(n / 1024 ** 2) + ' MB';
  }
  function kbps(bits) {
    if (!bits) return '—';
    return bits >= 1e6 ? nf1.format(bits / 1e6) + ' Mbit/s' : nf0.format(bits / 1e3) + ' kbit/s';
  }
  // "2000k" -> "2 Mbit/s"
  function rate(str) {
    const m = String(str || '').match(/^([\d.]+)([kKmM]?)$/);
    if (!m) return str || '—';
    const bits = Number(m[1]) * (/[mM]/.test(m[2]) ? 1e6 : /[kK]/.test(m[2]) ? 1e3 : 1);
    return kbps(bits);
  }
  function timeLabel(iso) {
    const d = new Date(iso);
    const t = d.toLocaleTimeString('pt-BR', { hour12: false });
    return new Date().toDateString() === d.toDateString() ? t : d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) + ' ' + t;
  }
  function hostItems(y) {
    if (!y) return [];
    const items = [['', `<b>${esc(y.model.replace(/ Model /, ' ').replace(/ Rev [\d.]+$/, ''))}</b>`]];
    if (y.tempC !== null) items.push([y.tempC >= 80 ? 'very-hot' : y.tempC >= 70 ? 'hot' : '', `Temperatura <b>${nf1.format(y.tempC)} °C</b>`]);
    items.push([y.cpuPct >= 85 ? 'hot' : '', `CPU <b>${nf0.format(y.cpuPct)} %</b>`]);
    items.push([y.memUsed / y.memTotal > 0.9 ? 'hot' : '', `Memória <b>${bytes(y.memUsed)}</b> de ${bytes(y.memTotal)}`]);
    items.push(['', `No ar há <b>${duration(y.appUptime)}</b>`]);
    return items;
  }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  }
  function setList(el, items) {
    const html = items.map(([cls, h]) => `<li class="${cls}">${h}</li>`).join('');
    if (el.innerHTML !== html) el.innerHTML = html;
  }

  // ---------- medidores com retenção de pico ----------
  function meter(fillEls, peakEls, horizontal) {
    const peaks = fillEls.map(() => ({ db: -96, at: 0 }));
    return function update(levels) {
      const t = performance.now();
      fillEls.forEach((fill, i) => {
        const l = levels && levels[i] ? levels[i] : { rms: -96, peak: -96 };
        const f = dbFrac(l.rms);
        fill.style.clipPath = horizontal ? `inset(0 ${(1 - f) * 100}% 0 0)` : `inset(${(1 - f) * 100}% 0 0 0)`;
        const p = peaks[i];
        const held = t - p.at < 1500 ? p.db : p.db - ((t - p.at - 1500) / 1000) * 20;
        if (l.peak >= held) { p.db = l.peak; p.at = t; } else { p.db = held; p.at = t - 1500; }
        const pf = dbFrac(p.db);
        peakEls[i].style.opacity = pf > 0 ? 1 : 0;
        if (horizontal) peakEls[i].style.left = `calc(${pf * 100}% - 2px)`;
        else peakEls[i].style.bottom = `calc(${pf * 100}% - 2px)`;
      });
    };
  }

  // ---------- locais (um por Pi) ----------
  function groupFor(g) {
    let G = groups.get(g.key);
    if (G) return G;
    const el = siteTpl.content.firstElementChild.cloneNode(true);
    el.dataset.key = g.key;
    $('.site-name', el).textContent = g.name;
    wall.appendChild(el);
    G = { el, tilesEl: $('.tiles', el), tiles: new Map(), status: $('.site-status', el), host: $('.site-host', el) };
    groups.set(g.key, G);
    return G;
  }

  function updateGroup(g, t) {
    const G = groupFor(g);
    G.el.dataset.online = String(g.online);
    if (g.kind === 'local') {
      G.status.textContent = lastState && lastState.mode === 'central' ? 'Neste servidor' : 'Este Pi';
    } else if (g.online) {
      G.status.textContent = `Online${g.version ? `, LiveSafe ${g.version}` : ''}`;
    } else if (g.comm.state === 'alarm') {
      G.status.textContent = `Sem comunicação há ${duration((t - g.comm.since) / 1000)}${g.lastError ? ` (${g.lastError})` : ''}`;
    } else {
      G.status.textContent = g.lastError ? `Conectando (${g.lastError})` : 'Conectando…';
    }
    setList(G.host, g.online ? hostItems(g.system) : []);
    for (const ch of g.channels) updateTile(G, g, ch, t);
    if (!g.channels.length && !G.empty) {
      G.empty = document.createElement('p');
      G.empty.className = 'site-empty';
      G.tilesEl.appendChild(G.empty);
    }
    if (G.empty) {
      if (g.channels.length) { G.empty.remove(); G.empty = null; }
      else G.empty.textContent = g.online ? 'Este Pi não tem canais configurados.' : 'Os canais aparecem quando o Pi responder.';
    }
  }

  // ---------- tiles (um por canal) ----------
  function createTile(G, g, ch) {
    const el = tileTpl.content.firstElementChild.cloneNode(true);
    const base = `${g.base}api/channels/${enc(ch.id)}/`;
    el.dataset.id = ch.id;
    $('.name', el).textContent = ch.name;
    $('.name', el).title = ch.name;
    el.setAttribute('aria-label', `${g.name}: ${ch.name}`);
    if (!ch.video) {
      el.classList.add('audio-only');
      $('.frame', el).remove();
      $('.radio', el).hidden = false;
      for (const k of ['motion', 'luma', 'fps']) $(`[data-m="${k}"]`, el).hidden = true;
    }
    if (!ch.audio) {
      el.classList.add('no-audio');
      $('[data-m="audio"]', el).hidden = true;
    }
    $('.diag', el).href = `${base}diagnostics`;
    $('.restart', el).addEventListener('click', (e) => {
      const b = e.currentTarget;
      b.disabled = true;
      b.textContent = 'Reiniciando…';
      fetch(`${base}restart`, { method: 'POST' })
        .catch(() => {})
        .finally(() => setTimeout(() => { b.disabled = false; b.textContent = 'Reiniciar captura'; }, 3000));
    });
    const open = () => player.open(g.key, ch.id);
    $('.watch', el).addEventListener('click', open);
    $('.play-over', el).addEventListener('click', open);

    const t = {
      el,
      base,
      img: $('.frame', el),
      banner: $('.banner', el),
      stateText: $('.state-text', el),
      watch: $('.watch', el),
      playOver: $('.play-over', el),
      lamps: Object.fromEntries([...el.querySelectorAll('.lamps li')].map((li) => [li.dataset.k, li])),
      m: Object.fromEntries([...el.querySelectorAll('.metrics [data-m]')].map((d) => [d.dataset.m, $('dd', d)])),
      facts: $('.facts', el),
      factsKey: '',
      jpegAt: null,
      vu: meter([...el.querySelectorAll('.vu-fill')], [...el.querySelectorAll('.vu-peak')], false),
      hbar: meter([...el.querySelectorAll('.hbar-fill')], [...el.querySelectorAll('.hbar-peak')], true),
    };
    if (t.img) t.img.addEventListener('load', () => el.classList.add('has-pic'));
    G.tilesEl.appendChild(el);
    G.tiles.set(ch.id, t);
    return t;
  }

  function alarmBanner(ch, t) {
    const active = PRIORITY.filter((k) => ch.alarms[k].state === 'alarm');
    const pending = PRIORITY.filter((k) => ch.alarms[k].state === 'pending');
    if (active.length) {
      const since = Math.min(...active.map((k) => ch.alarms[k].since || t));
      return { text: active.map((k) => ALARM_TEXT[k]).join(' + ') + ' há ' + duration((t - since) / 1000), warn: false, count: active.length };
    }
    if (pending.length) return { text: PENDING_TEXT[pending[0]], warn: true, count: 0 };
    return null;
  }

  function paintBanner(el, b) {
    if (!b) { el.hidden = true; return; }
    el.textContent = b.text;
    el.className = el.id ? 'stage-banner banner' + (b.warn ? ' warn' : '') : 'banner' + (b.warn ? ' warn' : '');
    el.hidden = false;
  }

  function updateTile(G, g, ch, t) {
    const T = G.tiles.get(ch.id) || createTile(G, g, ch);
    const el = T.el;
    el.dataset.overall = g.online ? ch.overall : 'starting';
    el.dataset.signal = ch.alarms.signal.state;
    for (const k of PRIORITY) T.lamps[k].dataset.s = ch.alarms[k].state;
    const b = alarmBanner(ch, t);
    paintBanner(T.banner, b);

    let st;
    if (!g.online) st = 'Sem dados do Pi';
    else if (ch.overall === 'alarm') st = b && b.count > 1 ? `${b.count} alarmes` : 'Em alarme';
    else if (ch.overall === 'warn') st = 'Em observação';
    else if (ch.state === 'restarting') st = `Reconectando (${ch.restarts}ª tentativa)`;
    else if (ch.overall === 'starting') st = 'Iniciando';
    else st = `Normal há ${duration(ch.runningFor)}`;
    T.stateText.textContent = st;

    const canWatch = !!(ch.stream && ch.stream.ready && g.online);
    T.watch.hidden = !ch.stream;
    T.watch.disabled = !canWatch;
    T.watch.textContent = canWatch ? (ch.video ? 'Assistir ao vivo' : 'Ouvir ao vivo') : 'Stream indisponível';
    T.playOver.hidden = !canWatch;

    if (T.img && ch.jpegAt && ch.jpegAt !== T.jpegAt && g.online) {
      T.jpegAt = ch.jpegAt;
      T.img.src = `${T.base}snapshot.jpg?t=${ch.jpegAt}`;
    }

    const m = ch.metrics;
    if (ch.video) {
      T.m.motion.textContent = m.motionPct === null ? '—' : nf1.format(m.motionPct) + ' %';
      T.m.luma.textContent = m.luma === null ? '—' : nf0.format(m.luma);
      T.m.fps.textContent = nf1.format(m.fps) + ' q/s';
    }
    if (ch.audio) {
      const loud = m.levels ? Math.max(...m.levels.map((l) => l.rms)) : null;
      T.m.audio.textContent = loud === null ? '—' : dbText(loud);
      (ch.video ? T.vu : T.hbar)(g.online ? m.levels : null);
    }

    const th = ch.thresholds;
    const facts = [];
    if (ch.video) facts.push(['Vídeo', ch.source.video || '—']);
    if (ch.audio) facts.push(['Áudio', ch.source.audio || '—']);
    if (ch.stream) {
      const s = ch.stream;
      facts.push(['Stream ao vivo', ch.video ? `H.264 até ${s.width} px, ${s.fps} q/s, ${rate(s.bitrate)} (${s.encoder === 'h264_v4l2m2m' ? 'hardware' : 'software'})${s.audioBitrate ? ` + AAC ${rate(s.audioBitrate)}` : ''}` : `AAC ${rate(s.audioBitrate)}`]);
    }
    if (ch.video) {
      facts.push(['Congelamento', `movimento abaixo de ${nf1.format(th.freezeMotionPct)} % por ${th.freezeSeconds} s`]);
      facts.push(['Tela preta', `${nf0.format(th.blackPct)} % da tela escura por ${th.blackSeconds} s`]);
    }
    if (ch.audio) facts.push(['Silêncio', `abaixo de ${dbText(th.silenceDbfs)} por ${th.silenceSeconds} s`]);
    facts.push(['Reinícios', String(ch.restarts)]);
    if (ch.lastError) facts.push(['Último erro', ch.lastError, 'err']);
    const key = JSON.stringify(facts);
    if (key !== T.factsKey) {
      T.factsKey = key;
      T.facts.replaceChildren(
        ...facts.flatMap(([k, v, cls]) => {
          const dt = document.createElement('dt');
          dt.textContent = k;
          const dd = document.createElement('dd');
          dd.textContent = v;
          if (cls) dd.className = cls;
          return [dt, dd];
        })
      );
    }
  }

  // ---------- topo ----------
  function updateHeader(s) {
    const chs = s.groups.flatMap((g) => (g.online ? g.channels : []));
    const off = s.groups.filter((g) => g.kind === 'remote' && g.comm.state === 'alarm').length;
    const alarm = chs.filter((c) => c.overall === 'alarm').length;
    const warn = chs.filter((c) => c.overall === 'warn').length;
    const total = s.groups.reduce((n, g) => n + g.channels.length, 0);
    const sum = $('#summary');
    const plural = (n, a, b) => (n === 1 ? a : b);
    const parts = [];
    if (alarm) parts.push(`${alarm} ${plural(alarm, 'canal em alarme', 'canais em alarme')}`);
    if (off) parts.push(`${off} ${plural(off, 'Pi sem comunicação', 'Pis sem comunicação')}`);
    if (alarm || off) {
      document.body.dataset.global = 'alarm';
      sum.innerHTML = `<b>${parts.join(', ')}</b>`;
    } else if (warn) {
      document.body.dataset.global = 'warn';
      sum.innerHTML = `<b>${warn} ${plural(warn, 'canal em observação', 'canais em observação')}</b> de ${total}`;
    } else {
      document.body.dataset.global = 'ok';
      sum.innerHTML = `<b>Tudo normal</b> em ${total} ${plural(total, 'canal', 'canais')}`;
    }
    document.title = alarm + off ? `(${alarm + off}) LiveSafe` : 'LiveSafe';
    $('#site-name').textContent = s.siteName;
    // No central, o topo mostra a saúde do próprio servidor; num Pi isso já está no cabeçalho do local.
    setList($('#host'), s.mode === 'central' ? hostItems(s.system) : []);

    const sn = s.snmp;
    const line = !sn.enabled
      ? 'Traps SNMP desativadas no config.json.'
      : sn.targets.length === 0
        ? 'Nenhum destino de trap configurado.'
        : `Traps SNMPv${sn.version} para ${sn.targets.join(', ')}. ${sn.sent} ${sn.sent === 1 ? 'enviada' : 'enviadas'}${sn.failed ? `, ${sn.failed} com falha` : ''}.`;
    const sl = $('#snmp-line');
    if (!sl.dataset.hold && sl.textContent !== line) sl.textContent = line;
  }

  // ---------- ocorrências ----------
  function eventItem(ev, fresh) {
    const li = document.createElement('li');
    const kind = ALARM_TYPES.includes(ev.type) ? (ev.active ? 'on' : 'off') : '';
    li.className = kind + (fresh ? ' fresh' : '');
    const msg = document.createElement('span');
    msg.className = 'ev-msg';
    msg.textContent = ev.message;
    const time = document.createElement('time');
    time.className = 'ev-time';
    time.dateTime = ev.remoteTs || ev.ts;
    time.textContent = timeLabel(ev.remoteTs || ev.ts);
    const ch = document.createElement('span');
    ch.className = 'ev-ch';
    let where = ev.channelName || '';
    if (ev.siteName && ev.channelName && ev.channelName !== ev.siteName) where = `${ev.siteName}: ${ev.channelName}`;
    else if (ev.siteName) where = ev.siteName;
    ch.textContent = (where || (ev.detail ? '' : 'Sistema')) + (ev.detail ? (where ? ` (${ev.detail})` : ev.detail) : '');
    li.append(msg, time, ch);
    if (fresh) setTimeout(() => li.classList.remove('fresh'), 4000);
    return li;
  }

  function renderEvents() {
    if (!events.length) {
      const li = document.createElement('li');
      li.className = 'empty';
      li.textContent = 'Nenhuma ocorrência registrada. Alarmes e normalizações aparecem aqui.';
      eventsEl.replaceChildren(li);
    } else {
      eventsEl.replaceChildren(...events.map((e) => eventItem(e, false)));
    }
    $('#log-count').textContent = events.length ? `últimas ${events.length}` : '';
  }

  function addEvent(ev) {
    if (events.some((e) => e.id === ev.id)) return;
    events.unshift(ev);
    if (events.length > 200) events.pop();
    if (eventsEl.firstElementChild && eventsEl.firstElementChild.classList.contains('empty')) eventsEl.replaceChildren();
    eventsEl.prepend(eventItem(ev, true));
    while (eventsEl.children.length > 200) eventsEl.lastElementChild.remove();
    $('#log-count').textContent = `últimas ${events.length}`;
    if (ev.active && ALARM_TYPES.includes(ev.type)) beep();
  }

  // ---------- som ----------
  let soundOn = store.get('livesafe.sound') === '1';
  let actx = null;
  const soundBtn = $('#sound');
  function paintSound() {
    soundBtn.setAttribute('aria-pressed', String(soundOn));
    soundBtn.textContent = soundOn ? 'Som ligado' : 'Som desligado';
  }
  soundBtn.addEventListener('click', () => {
    soundOn = !soundOn;
    store.set('livesafe.sound', soundOn ? '1' : '0');
    paintSound();
    if (soundOn) beep();
  });
  function beep() {
    if (!soundOn) return;
    try {
      actx = actx || new (window.AudioContext || window.webkitAudioContext)();
      const t0 = actx.currentTime;
      [0, 0.25].forEach((d) => {
        const o = actx.createOscillator();
        const gn = actx.createGain();
        o.frequency.value = 880;
        gn.gain.setValueAtTime(0.0001, t0 + d);
        gn.gain.exponentialRampToValueAtTime(0.25, t0 + d + 0.02);
        gn.gain.exponentialRampToValueAtTime(0.0001, t0 + d + 0.18);
        o.connect(gn).connect(actx.destination);
        o.start(t0 + d);
        o.stop(t0 + d + 0.2);
      });
    } catch (e) {}
  }
  paintSound();

  // ---------- trap de teste ----------
  $('#test-trap').addEventListener('click', async (e) => {
    const b = e.currentTarget;
    const sl = $('#snmp-line');
    b.disabled = true;
    try {
      const r = await (await fetch('api/test-trap', { method: 'POST' })).json();
      const ok = r.results.filter((x) => x.ok).length;
      sl.textContent = r.results.length
        ? `Trap de teste enviada para ${ok} de ${r.results.length} ${r.results.length === 1 ? 'destino' : 'destinos'}. Confira no seu NMS.`
        : 'Traps desativadas: nada foi enviado.';
    } catch (err) {
      sl.textContent = 'Não foi possível falar com o servidor para enviar a trap.';
    }
    sl.dataset.hold = '1';
    setTimeout(() => { delete sl.dataset.hold; b.disabled = false; }, 5000);
  });

  // ---------- player ao vivo (HLS) ----------
  const player = (() => {
    const dlg = $('#player');
    const video = $('#video');
    const stage = $('#stage');
    const spinner = $('#spinner');
    const msg = $('#stage-msg');
    const tl = $('#timeline');
    const tlBuf = $('#tl-buffered');
    const tlPlayed = $('#tl-played');
    const knob = $('#tl-knob');
    const hoverT = $('#tl-hover');
    const btnPlay = $('#btn-play');
    const btnMute = $('#btn-mute');
    const vol = $('#volume');
    const btnLive = $('#btn-live');
    const lagEl = $('#lag');
    const btnStats = $('#btn-stats');
    const statsEl = $('#stats');
    const stageAudio = $('#stage-audio');
    const stageBanner = $('#stage-banner');
    const hmeter = meter([...stageAudio.querySelectorAll('.hbar-fill')], [...stageAudio.querySelectorAll('.hbar-peak')], true);
    let hls = null;
    let cur = null; // { group, channel }
    let raf = 0;
    let statsTimer = 0;
    let loaded = 0;
    let retryTimer = 0;

    const savedVol = Number(store.get('livesafe.volume'));
    if (savedVol >= 0 && savedVol <= 1 && store.get('livesafe.volume') !== null) vol.value = String(savedVol);
    video.volume = Number(vol.value);
    video.muted = store.get('livesafe.muted') === '1';

    function window_() {
      const s = video.seekable;
      if (s && s.length) return { start: s.start(0), end: s.end(s.length - 1) };
      const b = video.buffered;
      if (b && b.length) return { start: b.start(0), end: b.end(b.length - 1) };
      return null;
    }
    function liveEdge() {
      if (hls && typeof hls.liveSyncPosition === 'number' && hls.liveSyncPosition) return hls.liveSyncPosition;
      const w = window_();
      return w ? w.end : 0;
    }
    function bufferedEnd() {
      const b = video.buffered;
      for (let i = 0; i < b.length; i++) if (video.currentTime >= b.start(i) - 0.3 && video.currentTime <= b.end(i) + 0.3) return b.end(i);
      return video.currentTime;
    }

    function paint() {
      raf = requestAnimationFrame(paint);
      const w = window_();
      if (!w || w.end - w.start <= 0) return;
      const span = w.end - w.start;
      const pos = Math.min(Math.max(video.currentTime, w.start), w.end);
      const p = (pos - w.start) / span;
      const be = (Math.min(bufferedEnd(), w.end) - w.start) / span;
      tlPlayed.style.width = `${p * 100}%`;
      tlBuf.style.width = `${Math.max(be, p) * 100}%`;
      knob.style.left = `${p * 100}%`;
      const behind = Math.max(0, liveEdge() - video.currentTime);
      const atEdge = behind < 2.5 && !video.paused;
      btnLive.dataset.atEdge = String(atEdge);
      lagEl.textContent = atEdge ? '' : `−${duration(behind)}`;
      tl.setAttribute('aria-valuemax', String(Math.round(span)));
      tl.setAttribute('aria-valuenow', String(Math.round(pos - w.start)));
      tl.setAttribute('aria-valuetext', atEdge ? 'Ao vivo' : `${Math.round(behind)} segundos atrás do ao vivo`);
    }

    function seekFrac(f) {
      const w = window_();
      if (!w) return;
      const target = w.start + Math.max(0, Math.min(1, f)) * (w.end - w.start);
      video.currentTime = Math.min(target, liveEdge());
      if (video.paused) video.play().catch(() => {});
    }
    function fracAt(e) {
      const r = tl.querySelector('.track').getBoundingClientRect();
      return (e.clientX - r.left) / r.width;
    }
    let dragging = false;
    tl.addEventListener('pointerdown', (e) => {
      dragging = true;
      tl.setPointerCapture(e.pointerId);
      seekFrac(fracAt(e));
    });
    tl.addEventListener('pointermove', (e) => {
      const w = window_();
      const f = Math.max(0, Math.min(1, fracAt(e)));
      if (w) {
        const ago = (1 - f) * (w.end - w.start);
        hoverT.hidden = false;
        hoverT.textContent = ago < 1.5 ? 'Ao vivo' : `−${duration(ago)}`;
        hoverT.style.left = `${16 + f * (tl.clientWidth - 32)}px`;
      }
      if (dragging) seekFrac(f);
    });
    tl.addEventListener('pointerup', () => { dragging = false; });
    tl.addEventListener('pointerleave', () => { hoverT.hidden = true; });
    tl.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowLeft') { video.currentTime = Math.max((window_() || { start: 0 }).start, video.currentTime - 5); e.preventDefault(); }
      if (e.key === 'ArrowRight') { video.currentTime = Math.min(liveEdge(), video.currentTime + 5); e.preventDefault(); }
      if (e.key === 'End') { goLive(); e.preventDefault(); }
    });

    function goLive() {
      const edge = liveEdge();
      if (edge) video.currentTime = edge;
      video.play().catch(() => {});
    }
    btnLive.addEventListener('click', goLive);

    function paintPlay() {
      btnPlay.dataset.paused = String(video.paused);
      btnPlay.setAttribute('aria-label', video.paused ? 'Reproduzir' : 'Pausar');
    }
    function paintMute() {
      const m = video.muted || video.volume === 0;
      btnMute.dataset.muted = String(m);
      btnMute.setAttribute('aria-label', m ? 'Ativar som' : 'Silenciar');
    }
    btnPlay.addEventListener('click', () => (video.paused ? video.play().catch(() => {}) : video.pause()));
    stage.addEventListener('click', (e) => { if (e.target === video) btnPlay.click(); });
    btnMute.addEventListener('click', () => {
      video.muted = !video.muted;
      if (!video.muted && video.volume === 0) { video.volume = 0.5; vol.value = '0.5'; }
      store.set('livesafe.muted', video.muted ? '1' : '0');
    });
    vol.addEventListener('input', () => {
      video.volume = Number(vol.value);
      video.muted = video.volume === 0;
      store.set('livesafe.volume', vol.value);
      store.set('livesafe.muted', video.muted ? '1' : '0');
    });
    video.addEventListener('play', paintPlay);
    video.addEventListener('pause', paintPlay);
    video.addEventListener('volumechange', paintMute);
    video.addEventListener('waiting', () => { spinner.hidden = false; });
    video.addEventListener('playing', () => { spinner.hidden = true; msg.hidden = true; });
    video.addEventListener('canplay', () => { spinner.hidden = true; });

    $('#btn-full').addEventListener('click', () => {
      if (document.fullscreenElement) document.exitFullscreen();
      else if (dlg.requestFullscreen) dlg.requestFullscreen().catch(() => {});
    });
    btnStats.addEventListener('click', () => {
      const open = statsEl.hidden;
      statsEl.hidden = !open;
      btnStats.setAttribute('aria-expanded', String(open));
      store.set('livesafe.stats', open ? '1' : '0');
      renderStats();
    });
    if (store.get('livesafe.stats') === '1') { statsEl.hidden = false; btnStats.setAttribute('aria-expanded', 'true'); }

    function showMsg(text) {
      msg.textContent = text;
      msg.hidden = !text;
    }

    function find() {
      if (!cur || !lastState) return {};
      const g = lastState.groups.find((x) => x.key === cur.group);
      const ch = g && g.channels.find((c) => c.id === cur.channel);
      return { g, ch };
    }

    function renderStats() {
      if (statsEl.hidden || !cur) return;
      const { g, ch } = find();
      const rows = [];
      const lvl = hls && hls.levels && hls.levels[hls.currentLevel >= 0 ? hls.currentLevel : 0];
      const w = window_();
      const ahead = Math.max(0, bufferedEnd() - video.currentTime);
      const q = video.getVideoPlaybackQuality ? video.getVideoPlaybackQuality() : null;
      if (ch && ch.video) rows.push(['Resolução', video.videoWidth ? `${video.videoWidth}×${video.videoHeight}` : '—']);
      if (lvl && lvl.videoCodec) rows.push(['Codec de vídeo', lvl.videoCodec]);
      if (lvl && lvl.audioCodec) rows.push(['Codec de áudio', lvl.audioCodec]);
      if (ch && ch.stream) rows.push(['Taxa do stream', ch.video ? `${rate(ch.stream.bitrate)}${ch.stream.audioBitrate ? ` + ${rate(ch.stream.audioBitrate)}` : ''}` : rate(ch.stream.audioBitrate)]);
      if (hls) rows.push(['Banda medida', kbps(hls.bandwidthEstimate)]);
      rows.push(['Buffer à frente', `${nf1.format(ahead)} s`]);
      if (hls && typeof hls.latency === 'number') rows.push(['Atraso do ao vivo', `${nf1.format(hls.latency)} s`]);
      if (w) rows.push(['Janela para voltar', `${nf0.format(w.end - w.start)} s`]);
      if (ch && ch.stream) rows.push(['Segmento', `${ch.stream.segmentSeconds} s`]);
      rows.push(['Carregado', bytes(loaded)]);
      if (q) rows.push(['Quadros perdidos', `${q.droppedVideoFrames} de ${q.totalVideoFrames}`]);
      if (ch && ch.stream && ch.video) rows.push(['Codificação no Pi', ch.stream.encoder === 'h264_v4l2m2m' ? 'hardware (h264_v4l2m2m)' : 'software (libx264)']);
      if (g) rows.push(['Origem', g.kind === 'remote' ? `${g.name} via servidor central` : g.name]);
      statsEl.innerHTML = rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('');
    }

    function attach(url) {
      clearTimeout(retryTimer);
      if (window.Hls && window.Hls.isSupported()) {
        hls = new window.Hls({
          lowLatencyMode: false,
          liveSyncDurationCount: 3,
          liveMaxLatencyDurationCount: 10,
          maxLiveSyncPlaybackRate: 1.1,
          maxBufferLength: 10,
          backBufferLength: 40,
          manifestLoadingMaxRetry: 6,
          levelLoadingMaxRetry: 6,
          fragLoadingMaxRetry: 6,
        });
        hls.on(window.Hls.Events.FRAG_LOADED, (_, d) => {
          loaded += (d.frag && d.frag.stats && d.frag.stats.total) || 0;
        });
        hls.on(window.Hls.Events.ERROR, (_, d) => {
          if (!d.fatal) return;
          if (d.type === window.Hls.ErrorTypes.MEDIA_ERROR) {
            hls.recoverMediaError();
            return;
          }
          showMsg('Sem dados do stream. O Pi pode estar sem sinal ou fora da rede; tentando de novo…');
          spinner.hidden = true;
          const h = hls;
          retryTimer = setTimeout(() => {
            if (hls !== h) return;
            h.destroy();
            hls = null;
            attach(url);
          }, 3000);
        });
        hls.loadSource(url);
        hls.attachMedia(video);
      } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        video.src = url; // Safari / iOS tocam HLS nativamente
      } else {
        showMsg('Este navegador não consegue tocar o stream. Use Chrome, Edge, Firefox ou Safari atualizados.');
        return;
      }
      video.play().catch(() => {
        showMsg('Clique em reproduzir para iniciar.');
      });
    }

    function open(groupKey, chId) {
      const g = lastState.groups.find((x) => x.key === groupKey);
      const ch = g && g.channels.find((c) => c.id === chId);
      if (!ch || !ch.stream) return;
      close();
      cur = { group: groupKey, channel: chId };
      loaded = 0;
      $('#player-site').textContent = g.name;
      $('#player-title').textContent = ch.name;
      stageAudio.hidden = !!ch.video;
      video.style.visibility = ch.video ? 'visible' : 'hidden';
      spinner.hidden = false;
      showMsg('');
      if (!dlg.open) dlg.showModal();
      attach(`${g.base}hls/${enc(ch.id)}/index.m3u8`);
      paintPlay();
      paintMute();
      raf = requestAnimationFrame(paint);
      statsTimer = setInterval(renderStats, 1000);
      renderStats();
    }

    function close() {
      cancelAnimationFrame(raf);
      clearInterval(statsTimer);
      clearTimeout(retryTimer);
      if (hls) { hls.destroy(); hls = null; }
      video.pause();
      video.removeAttribute('src');
      video.load();
      cur = null;
    }

    $('#player-close').addEventListener('click', () => dlg.close());
    dlg.addEventListener('close', close);
    dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
    document.addEventListener('keydown', (e) => {
      if (!dlg.open || e.target.closest('input,button,[role=slider]')) return;
      if (e.key === ' ' || e.key === 'k') { btnPlay.click(); e.preventDefault(); }
      if (e.key === 'm') btnMute.click();
      if (e.key === 'f') $('#btn-full').click();
    });

    // O estado ao vivo também alimenta o player: alarme sobre a imagem e VU do rádio.
    function onState() {
      if (!cur) return;
      const { ch } = find();
      if (!ch) return;
      paintBanner(stageBanner, alarmBanner(ch, now()));
      if (!ch.video) hmeter(ch.metrics.levels);
    }

    return { open, onState };
  })();

  // ---------- conexão ao vivo (SSE) ----------
  function onState(s) {
    // Instalação nova, ainda sem canais nem Pis: vai direto para o assistente.
    if (s.setupPending) {
      location.replace('setup');
      return;
    }
    clockOffset = s.now - Date.now();
    lastState = s;
    const t = now();
    for (const g of s.groups) updateGroup(g, t);
    updateHeader(s);
    player.onState();
    if (s.events) {
      events = s.events.slice(0, 200);
      renderEvents();
    }
  }

  function connect() {
    const es = new EventSource('api/stream');
    es.addEventListener('state', (e) => {
      $('#offline').hidden = true;
      onState(JSON.parse(e.data));
    });
    es.addEventListener('event', (e) => addEvent(JSON.parse(e.data)));
    es.onerror = () => {
      $('#offline').hidden = false;
      document.body.dataset.global = 'alarm';
    };
  }
  connect();
})();
