'use strict';
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s === undefined || s === null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const nf = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 });

  const STEP_NAMES = {
    local: 'Identificação',
    entrada: 'Entrada de sinal',
    pis: 'Pis dos abrigos',
    alarmes: 'Alarmes e SNMP',
    stream: 'Vídeo ao vivo',
    revisar: 'Revisar e aplicar',
  };
  const PRESETS = [
    { id: 'eco', name: 'Econômico', width: 854, bitrate: '800k', fps: 25, note: '480p, cerca de 0,9 Mbit/s por canal. Para enlaces estreitos.' },
    { id: 'std', name: 'Padrão', width: 1280, bitrate: '2000k', fps: 25, note: '720p, cerca de 2,1 Mbit/s por canal. Bom equilíbrio.' },
    { id: 'high', name: 'Alta', width: 1920, bitrate: '4000k', fps: 25, note: '1080p, cerca de 4,1 Mbit/s por canal. Precisa do encoder por hardware do Pi 4.' },
  ];

  let info = null;
  let draft = null;
  let steps = [];
  let step = 0;
  let visited = 0;
  let editing = 0; // canal em edição
  let jsonEdited = null;
  const piStatus = new Map(); // endereço -> { cls, text } do último teste

  // ---------- utilidades ----------
  function slug(s, used) {
    let base = String(s || 'canal')
      .normalize('NFD')
      .replace(/[̀-ͯ]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 28) || 'item';
    let id = base;
    let n = 2;
    while (used.has(id)) id = `${base}-${n++}`;
    used.add(id);
    return id;
  }
  function api(path, body) {
    return fetch(path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(async (r) => {
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
      return j;
    });
  }
  function showError(msg) {
    const el = $('#form-error');
    el.textContent = msg || '';
    el.hidden = !msg;
    if (msg) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
  function normalizeUrl(addr) {
    addr = String(addr || '').trim();
    if (!addr) return '';
    if (!/^https?:\/\//i.test(addr)) addr = 'http://' + addr;
    try {
      const u = new URL(addr);
      if (!u.port && u.protocol === 'http:') u.port = '8080';
      return u.origin;
    } catch (e) {
      return addr;
    }
  }

  // ---------- modelo de canal (o que o formulário edita) ----------
  function toModel(ch) {
    if (ch.ui) return { ...ch.ui, id: ch.id, name: ch.name };
    if (ch.url) return { kind: 'url', id: ch.id, name: ch.name, url: ch.url, video: ch.video !== false, audio: ch.audio !== false };
    return { kind: 'manual', id: ch.id, name: ch.name, raw: ch };
  }
  function fromModel(m, prev) {
    if (m.kind === 'manual') return { ...m.raw, name: m.name };
    const keep = {};
    const skip = ['id', 'name', 'url', 'inputArgs', 'inputOptions', 'video', 'audio', 'videoStream', 'audioStream', 'ui'];
    for (const [k, v] of Object.entries(prev || {})) if (!skip.includes(k)) keep[k] = v;
    if (m.kind === 'url') {
      return { ...keep, id: m.id, name: m.name, url: m.url, video: !!m.video, audio: !!m.audio, ui: { kind: 'url', url: m.url, video: !!m.video, audio: !!m.audio } };
    }
    const args = ['-thread_queue_size', '1024', '-f', 'v4l2', '-input_format', m.format, '-video_size', `${m.width}x${m.height}`, '-framerate', String(m.fps), '-i', m.device];
    const out = { ...keep, id: m.id, name: m.name, video: true, videoStream: '0:v:0' };
    if (m.alsa) {
      args.push('-thread_queue_size', '1024', '-f', 'alsa', '-i', m.alsa.replace(/^hw:/, 'plughw:'));
      out.audio = true;
      out.audioStream = '1:a:0';
    } else {
      out.audio = false;
    }
    out.inputArgs = args;
    out.ui = { kind: 'device', device: m.device, format: m.format, width: m.width, height: m.height, fps: m.fps, alsa: m.alsa || '' };
    return out;
  }
  function devFormats(path) {
    const d = (info.devices && info.devices.video || []).find((v) => v.path === path);
    return d ? d.formats : [];
  }
  // Escolhas sensatas: MJPEG, 1280x720 (ou o maior até 1080p), 30 q/s.
  function bestFor(path, fmt) {
    const formats = devFormats(path);
    const f = formats.find((x) => x.ffmpeg === fmt) || formats.find((x) => x.ffmpeg === 'mjpeg') || formats[0];
    if (!f) return { format: 'mjpeg', width: 1280, height: 720, fps: 30 };
    const size = f.sizes.find((s) => s.width === 1280 && s.height === 720) || f.sizes.find((s) => s.width <= 1920 && s.height <= 1080) || f.sizes[0];
    const fps = size.fps.find((x) => x <= 30) || size.fps[0] || 30;
    return { format: f.ffmpeg, width: size.width, height: size.height, fps };
  }
  function newChannelModel() {
    const vids = (info.devices && info.devices.video) || [];
    const auds = (info.devices && info.devices.audio) || [];
    const used = new Set(draft.channels.map((c) => c.id));
    const taken = new Set(draft.channels.map((c) => c.ui && c.ui.device).filter(Boolean));
    const dev = vids.find((v) => !taken.has(v.path)) || vids[0];
    if (!dev) return { kind: 'url', id: slug('canal', used), name: 'Canal ' + (draft.channels.length + 1), url: '', video: true, audio: true };
    // Placa HDMI-USB costuma ter o áudio com o mesmo nome do vídeo (ex.: MS2109).
    const word = dev.name.split(/[\s:]+/)[0].toLowerCase();
    const aud = auds.find((a) => a.name.toLowerCase().includes(word) || a.id.toLowerCase().includes(word)) || auds.find((a) => /usb/i.test(a.driver + a.name)) || null;
    return { kind: 'device', id: slug('hdmi', used), name: 'Receptor ' + (draft.channels.length + 1), device: dev.path, ...bestFor(dev.path), alsa: aud ? aud.alsa : '' };
  }

  // ---------- etapas ----------
  function renderSteps() {
    $('#steps').innerHTML = steps
      .map((s, i) => `<li class="${i === step ? 'current' : ''} ${i < step ? 'done' : ''}"><button type="button" data-i="${i}" ${i > visited ? 'disabled' : ''} ${i === step ? 'aria-current="step"' : ''}><span class="num">${i + 1}</span>${STEP_NAMES[s]}</button></li>`)
      .join('');
    $$('#steps button').forEach((b) =>
      b.addEventListener('click', () => {
        if (!collect()) return;
        go(Number(b.dataset.i));
      })
    );
    $('#prev').hidden = step === 0;
    $('#next').textContent = steps[step] === 'revisar' ? 'Salvar e aplicar' : 'Continuar';
  }

  function go(i) {
    step = Math.max(0, Math.min(steps.length - 1, i));
    visited = Math.max(visited, step);
    showError('');
    render();
    window.scrollTo({ top: 0 });
  }

  function render() {
    renderSteps();
    const body = $('#step-body');
    const s = steps[step];
    body.innerHTML = RENDER[s]();
    BIND[s] && BIND[s](body);
    const first = body.querySelector('input:not([type=hidden]):not([disabled]), select');
    if (first && s !== 'revisar') first.focus({ preventScroll: true });
  }

  // Lê o formulário da etapa atual para o draft. Retorna false se algo está inválido.
  function collect() {
    const s = steps[step];
    showError('');
    try {
      if (COLLECT[s]) COLLECT[s]($('#step-body'));
      return true;
    } catch (e) {
      showError(e.message);
      return false;
    }
  }

  const RENDER = {};
  const BIND = {};
  const COLLECT = {};

  // ----- 1. Identificação -----
  RENDER.local = () => {
    const a = (info.config.http && info.config.http.auth) || {};
    const needPass = !a.hasPassword;
    const isEdge = info.role === 'edge';
    return `
      <h1>${isEdge ? 'Este Pi' : 'Este servidor central'}</h1>
      <p class="lead">${isEdge ? 'Dê um nome para o local onde este Pi está. É o nome que aparece no servidor central, nas ocorrências e nas traps.' : 'Dê um nome para esta central. Ele aparece no topo do painel e nas traps.'}</p>
      <label class="field"><span>Nome do local</span>
        <input name="siteName" required maxlength="64" value="${esc(draft.siteName || '')}" placeholder="${isEdge ? 'ex.: Pedra Azul' : 'ex.: Central Fonte Grande'}"></label>
      <fieldset class="group">
        <legend>Acesso ao painel</legend>
        <p class="hint">${needPass ? 'Crie a senha do painel. Ela protege a configuração e o botão de reiniciar a captura.' : 'Deixe a senha em branco para manter a atual.'}</p>
        <div class="grid-2">
          <label class="field"><span>Usuário</span><input name="user" value="${esc(a.user || 'admin')}" autocomplete="username" required></label>
          <span></span>
          <label class="field"><span>${needPass ? 'Senha' : 'Nova senha'}</span><input name="pass" type="password" autocomplete="new-password" ${needPass ? 'required' : ''} minlength="6"></label>
          <label class="field"><span>Repita a senha</span><input name="pass2" type="password" autocomplete="new-password" ${needPass ? 'required' : ''}></label>
        </div>
      </fieldset>`;
  };
  COLLECT.local = (b) => {
    const name = $('[name=siteName]', b).value.trim();
    if (!name) throw new Error('Informe o nome do local.');
    const user = $('[name=user]', b).value.trim() || 'admin';
    const p1 = $('[name=pass]', b).value;
    const p2 = $('[name=pass2]', b).value;
    const has = info.config.http && info.config.http.auth && info.config.http.auth.hasPassword;
    if (!has && !p1) throw new Error('Crie uma senha para o painel.');
    if (p1 && p1.length < 6) throw new Error('A senha precisa ter pelo menos 6 caracteres.');
    if (p1 !== p2) throw new Error('As duas senhas não conferem.');
    draft.siteName = name;
    draft.http = draft.http || {};
    draft.http.auth = { user, ...(p1 ? { newPassword: p1 } : {}) };
  };

  // ----- 2a. Entrada de sinal (Pi de borda) -----
  RENDER.entrada = () => {
    const vids = (info.devices && info.devices.video) || [];
    const auds = (info.devices && info.devices.audio) || [];
    if (!draft.channels.length) draft.channels.push(fromModel(newChannelModel()));
    editing = Math.min(editing, draft.channels.length - 1);
    const m = toModel(draft.channels[editing]);
    const tabs = draft.channels
      .map((c, i) => `<button type="button" class="tab ${i === editing ? 'on' : ''}" data-tab="${i}">${esc(c.name || 'Canal ' + (i + 1))}</button>`)
      .join('');
    let warn = '';
    if (info.devices && !info.devices.tools.ffmpeg) warn += '<p class="note warn">O ffmpeg não foi encontrado neste Pi. Rode o instalador de novo.</p>';
    if (!vids.length) warn += '<p class="note warn">Nenhuma placa de captura de vídeo foi encontrada. Confira o cabo USB da placa HDMI-USB e clique em "Procurar placas de novo", ou use um endereço de rede.</p>';
    const vidOpts = vids.map((v) => `<option value="${esc(v.path)}" ${m.device === v.path ? 'selected' : ''}>${esc(v.name)} (${esc(v.path)})</option>`).join('');
    const formats = m.kind === 'device' ? devFormats(m.device) : [];
    const fmt = formats.find((f) => f.ffmpeg === m.format) || formats[0];
    const fmtOpts = formats.map((f) => `<option value="${f.ffmpeg}" ${f === fmt ? 'selected' : ''}>${f.fourcc === 'MJPG' ? 'MJPEG (recomendado)' : esc(f.fourcc + ' — ' + f.description)}</option>`).join('');
    const sizes = fmt ? fmt.sizes : [];
    const size = sizes.find((x) => x.width === m.width && x.height === m.height) || sizes[0];
    const sizeOpts = sizes.map((x) => `<option value="${x.width}x${x.height}" ${x === size ? 'selected' : ''}>${x.width} × ${x.height}</option>`).join('');
    const fpsOpts = (size ? size.fps : [30]).map((f) => `<option value="${f}" ${Number(m.fps) === f ? 'selected' : ''}>${nf.format(f)} q/s</option>`).join('');
    const audOpts =
      `<option value="">Sem áudio</option>` + auds.map((a) => `<option value="${esc(a.alsa)}" ${m.alsa === a.alsa ? 'selected' : ''}>${esc(a.name)} (${esc(a.id)})</option>`).join('');
    const kind = m.kind;
    return `
      <h1>Entrada de sinal</h1>
      <p class="lead">Escolha de onde vem o sinal que este Pi vai monitorar. Normalmente é a placa HDMI-USB ligada na saída do receptor.</p>
      ${warn}
      <div class="tabs" role="tablist">${tabs}<button type="button" class="tab add" id="add-ch">Adicionar canal</button></div>
      <div class="channel-editor">
        <label class="field"><span>Nome do canal</span><input name="name" value="${esc(m.name)}" maxlength="64" required placeholder="ex.: Receptor TV Gazeta"></label>
        <fieldset class="group">
          <legend>Origem</legend>
          <div class="seg">
            <label><input type="radio" name="kind" value="device" ${kind === 'device' ? 'checked' : ''} ${vids.length ? '' : 'disabled'}> Placa de captura USB</label>
            <label><input type="radio" name="kind" value="url" ${kind === 'url' ? 'checked' : ''}> Endereço de rede</label>
            ${kind === 'manual' ? '<label><input type="radio" name="kind" value="manual" checked> Manual (JSON)</label>' : ''}
            ${kind !== 'manual' ? '<button type="button" class="btn ghost small" id="rescan">Procurar placas de novo</button>' : ''}
          </div>
          ${
            kind === 'device'
              ? `<div class="grid-2">
              <label class="field"><span>Placa de vídeo</span><select name="device">${vidOpts}</select></label>
              <label class="field"><span>Áudio</span><select name="alsa">${audOpts}</select></label>
              <label class="field"><span>Formato</span><select name="format">${fmtOpts}</select></label>
              <label class="field"><span>Resolução de captura</span><select name="size">${sizeOpts}</select></label>
              <label class="field"><span>Quadros por segundo</span><select name="fps">${fpsOpts}</select></label>
            </div>`
              : kind === 'url'
                ? `<label class="field"><span>Endereço</span><input name="url" value="${esc(m.url || '')}" placeholder="udp://@239.10.10.1:1234, rtsp://… ou http://…"></label>
            <div class="seg"><label><input type="checkbox" name="hasVideo" ${m.video ? 'checked' : ''}> Tem vídeo</label><label><input type="checkbox" name="hasAudio" ${m.audio ? 'checked' : ''}> Tem áudio</label></div>
            <p class="hint">Para um canal só de rádio, desmarque "Tem vídeo".</p>`
                : `<p class="hint">Este canal foi configurado à mão no arquivo. Ajuste-o na etapa "Revisar e aplicar", em "Editar a configuração completa".</p>`
          }
        </fieldset>
        <div class="test">
          <button type="button" class="btn" id="test-input" ${kind === 'manual' ? 'disabled' : ''}>Testar entrada</button>
          ${draft.channels.length > 1 ? '<button type="button" class="btn ghost danger" id="del-ch">Remover este canal</button>' : ''}
          <div class="test-result" id="test-result" aria-live="polite"></div>
        </div>
      </div>`;
  };
  BIND.entrada = (b) => {
    const saveModel = () => {
      try {
        COLLECT.entrada(b, true);
      } catch (e) {}
    };
    $$('[data-tab]', b).forEach((t) =>
      t.addEventListener('click', () => {
        saveModel();
        editing = Number(t.dataset.tab);
        render();
      })
    );
    $('#add-ch', b).addEventListener('click', () => {
      saveModel();
      draft.channels.push(fromModel(newChannelModel()));
      editing = draft.channels.length - 1;
      render();
    });
    const del = $('#del-ch', b);
    if (del)
      del.addEventListener('click', () => {
        draft.channels.splice(editing, 1);
        editing = 0;
        render();
      });
    $$('[name=kind]', b).forEach((r) =>
      r.addEventListener('change', () => {
        const cur = toModel(draft.channels[editing]);
        const name = $('[name=name]', b).value;
        let m;
        if (r.value === 'device') m = { ...newChannelModel(), id: cur.id, name };
        else m = { kind: 'url', id: cur.id, name, url: '', video: true, audio: true };
        draft.channels[editing] = fromModel(m, draft.channels[editing]);
        render();
      })
    );
    // Trocar placa ou formato muda as opções seguintes: redesenha.
    for (const n of ['device', 'format', 'size']) {
      const el = $(`[name=${n}]`, b);
      if (!el) continue;
      el.addEventListener('change', () => {
        const m = toModel(draft.channels[editing]);
        if (n === 'device') Object.assign(m, { device: el.value }, bestFor(el.value));
        if (n === 'format') Object.assign(m, bestFor(m.device, el.value));
        if (n === 'size') {
          const [w, h] = el.value.split('x').map(Number);
          const f = devFormats(m.device).find((x) => x.ffmpeg === m.format);
          const s = f && f.sizes.find((x) => x.width === w && x.height === h);
          Object.assign(m, { width: w, height: h, fps: s ? s.fps.find((x) => x <= 30) || s.fps[0] : m.fps });
        }
        m.name = $('[name=name]', b).value;
        const alsa = $('[name=alsa]', b);
        if (alsa) m.alsa = alsa.value;
        draft.channels[editing] = fromModel(m, draft.channels[editing]);
        render();
      });
    }
    const rescan = $('#rescan', b);
    if (rescan)
      rescan.addEventListener('click', async () => {
        rescan.disabled = true;
        rescan.textContent = 'Procurando…';
        saveModel();
        try {
          const fresh = await api('api/setup');
          info.devices = fresh.devices;
        } catch (e) {}
        render();
      });
    $('#test-input', b).addEventListener('click', async (e) => {
      const btn = e.currentTarget;
      const out = $('#test-result', b);
      try {
        COLLECT.entrada(b, true);
      } catch (err) {
        out.innerHTML = `<p class="note warn">${esc(err.message)}</p>`;
        return;
      }
      btn.disabled = true;
      btn.textContent = 'Testando…';
      out.innerHTML = '<p class="hint">Abrindo a entrada e capturando um quadro e 3 s de áudio…</p>';
      try {
        const r = await api('api/setup/test-input', { channel: draft.channels[editing] });
        const ch = draft.channels[editing];
        const parts = [];
        if (r.image) parts.push(`<img class="test-img" alt="Quadro capturado da entrada" src="data:image/jpeg;base64,${r.image}">`);
        const lines = [];
        if (r.busy) lines.push(`Esta placa já está em uso pelo canal "${esc(r.owner)}" em funcionamento; esta é a imagem atual dele.`);
        if (r.ok && !r.busy) lines.push('A entrada abriu e entregou sinal.');
        if (!r.ok) lines.push(`Não foi possível abrir a entrada: ${esc(r.error || 'erro desconhecido')}`);
        if (r.source && r.source.video) lines.push(`Vídeo: ${esc(r.source.video)}`);
        if (r.source && r.source.audio) lines.push(`Áudio: ${esc(r.source.audio)}`);
        if (ch.audio !== false && r.audioDb !== null && r.audioDb !== undefined) {
          const db = r.audioDb;
          lines.push(db <= -60 ? `Nível de áudio: ${nf.format(db)} dBFS. Está em silêncio; confira se o receptor está mandando áudio pelo HDMI.` : `Nível de áudio: ${nf.format(db)} dBFS.`);
        }
        out.innerHTML = `<div class="test-box ${r.ok ? 'ok' : 'bad'}">${parts.join('')}<div>${lines.map((l) => `<p>${l}</p>`).join('')}</div></div>`;
      } catch (err) {
        out.innerHTML = `<p class="note warn">${esc(err.message)}</p>`;
      }
      btn.disabled = false;
      btn.textContent = 'Testar entrada';
    });
  };
  COLLECT.entrada = (b, partial) => {
    const cur = draft.channels[editing];
    if (!cur) return;
    const m = toModel(cur);
    m.name = $('[name=name]', b).value.trim();
    if (m.kind === 'device') {
      m.device = $('[name=device]', b).value;
      m.alsa = $('[name=alsa]', b).value;
      m.format = $('[name=format]', b).value;
      const [w, h] = $('[name=size]', b).value.split('x').map(Number);
      m.width = w;
      m.height = h;
      m.fps = Number($('[name=fps]', b).value);
    } else if (m.kind === 'url') {
      m.url = $('[name=url]', b).value.trim();
      m.video = $('[name=hasVideo]', b).checked;
      m.audio = $('[name=hasAudio]', b).checked;
    }
    draft.channels[editing] = fromModel(m, cur);
    if (partial) {
      if (!m.name) throw new Error('Dê um nome ao canal.');
      if (m.kind === 'url' && !m.url) throw new Error('Informe o endereço da fonte.');
      return;
    }
    for (const [i, c] of draft.channels.entries()) {
      const cm = toModel(c);
      if (!cm.name) throw new Error(`Dê um nome ao canal ${i + 1}.`);
      if (cm.kind === 'url' && !cm.url) throw new Error(`Informe o endereço do canal "${cm.name}".`);
      if (cm.kind === 'url' && !cm.video && !cm.audio) throw new Error(`O canal "${cm.name}" precisa ter vídeo, áudio ou os dois.`);
    }
    const devs = draft.channels.map((c) => c.ui && c.ui.device).filter(Boolean);
    if (new Set(devs).size !== devs.length) throw new Error('Dois canais estão usando a mesma placa de vídeo.');
  };

  // ----- 2b. Pis dos abrigos (central) -----
  RENDER.pis = () => {
    const rows = draft.sites
      .map(
        (s, i) => `
      <div class="pi-row" data-i="${i}">
        <label class="field"><span>Nome do abrigo</span><input name="name" value="${esc(s.name || '')}" placeholder="ex.: Pedra Azul" required></label>
        <label class="field"><span>Endereço do Pi</span><input name="url" value="${esc(s.url || '')}" placeholder="10.10.8.21 ou http://10.10.8.21:8080" required></label>
        <label class="field"><span>Usuário</span><input name="user" value="${esc(s.user || 'admin')}"></label>
        <label class="field"><span>Senha</span><input name="password" type="password" autocomplete="off" placeholder="${s.hasPassword ? 'mantida' : 'senha do Pi'}"></label>
        <div class="pi-actions">
          <button type="button" class="btn small" data-test="${i}">Testar conexão</button>
          <button type="button" class="btn ghost small danger" data-del="${i}" aria-label="Remover ${esc(s.name || 'este Pi')}">Remover</button>
        </div>
        <p class="pi-status ${esc((piStatus.get(s.url) || {}).cls || '')}" id="pi-status-${i}" aria-live="polite">${esc((piStatus.get(s.url) || {}).text || '')}</p>
      </div>`
      )
      .join('');
    return `
      <h1>Pis dos abrigos</h1>
      <p class="lead">Cadastre cada Raspberry Pi que esta central vai acompanhar. Use o IP do Pi e a senha que foi criada na instalação dele.</p>
      ${
        info.installCommand
          ? `<div class="install-box"><p>Para preparar um Pi novo, rode isto nele (ele baixa o LiveSafe desta central):</p>
        <div class="cmd"><code id="install-cmd">${esc(info.installCommand)}</code><button type="button" class="btn small" id="copy-cmd">Copiar</button></div></div>`
          : ''
      }
      <div class="pi-list">${rows || '<p class="hint">Nenhum Pi cadastrado ainda.</p>'}</div>
      <button type="button" class="btn" id="add-pi">Adicionar Pi</button>`;
  };
  BIND.pis = (b) => {
    const copy = $('#copy-cmd', b);
    if (copy)
      copy.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText($('#install-cmd').textContent);
          copy.textContent = 'Copiado';
        } catch (e) {
          const r = document.createRange();
          r.selectNodeContents($('#install-cmd'));
          getSelection().removeAllRanges();
          getSelection().addRange(r);
          copy.textContent = 'Selecionado';
        }
        setTimeout(() => (copy.textContent = 'Copiar'), 2000);
      });
    $('#add-pi', b).addEventListener('click', () => {
      COLLECT.pis(b, true);
      draft.sites.push({ name: '', url: '', user: 'admin' });
      render();
      const rows = $$('.pi-row', $('#step-body'));
      rows[rows.length - 1].querySelector('input').focus();
    });
    $$('[data-del]', b).forEach((x) =>
      x.addEventListener('click', () => {
        COLLECT.pis(b, true);
        draft.sites.splice(Number(x.dataset.del), 1);
        render();
      })
    );
    $$('[data-test]', b).forEach((x) =>
      x.addEventListener('click', async () => {
        COLLECT.pis(b, true);
        const i = Number(x.dataset.test);
        const s = draft.sites[i];
        const st = $(`#pi-status-${i}`, b);
        if (!s.url) {
          st.className = 'pi-status bad';
          st.textContent = 'Informe o endereço do Pi.';
          return;
        }
        x.disabled = true;
        st.className = 'pi-status';
        st.textContent = `Testando ${s.url}…`;
        try {
          const r = await api('api/setup/test-site', { url: s.url, user: s.user, password: s.password, id: s.id });
          const remember = () => piStatus.set(s.url, { cls: st.classList.contains('ok') ? 'ok' : 'bad', text: st.textContent });
          setTimeout(remember, 0);
          if (r.ok) {
            st.className = 'pi-status ok';
            const ch = r.channels.length ? `${r.channels.length} ${r.channels.length === 1 ? 'canal' : 'canais'} (${r.channels.join(', ')})` : 'nenhum canal configurado ainda';
            st.textContent = `Conectado: "${r.siteName}", LiveSafe ${r.version}, ${ch}${r.temp !== null && r.temp !== undefined ? `, ${nf.format(r.temp)} °C` : ''}.`;
            const name = $(`.pi-row[data-i="${i}"] [name=name]`, b);
            if (!name.value.trim() && r.siteName) {
              name.value = r.siteName;
              s.name = r.siteName;
            }
          } else {
            st.className = 'pi-status bad';
            st.textContent = r.error;
          }
        } catch (e) {
          st.className = 'pi-status bad';
          st.textContent = e.message;
          piStatus.set(s.url, { cls: 'bad', text: e.message });
        }
        x.disabled = false;
      })
    );
  };
  COLLECT.pis = (b, partial) => {
    $$('.pi-row', b).forEach((row) => {
      const i = Number(row.dataset.i);
      const s = draft.sites[i];
      s.name = $('[name=name]', row).value.trim();
      s.url = normalizeUrl($('[name=url]', row).value);
      s.user = $('[name=user]', row).value.trim();
      const pw = $('[name=password]', row).value;
      if (pw) s.password = pw;
    });
    if (partial) return;
    draft.sites = draft.sites.filter((s) => s.name || s.url);
    for (const s of draft.sites) {
      if (!s.name) throw new Error(`Dê um nome ao Pi de ${s.url}.`);
      if (!s.url) throw new Error(`Informe o endereço do Pi "${s.name}".`);
    }
    const urls = draft.sites.map((s) => s.url);
    if (new Set(urls).size !== urls.length) throw new Error('Há dois Pis com o mesmo endereço.');
  };

  // ----- 3. Alarmes e SNMP -----
  RENDER.alarmes = () => {
    const t = draft.snmp.traps;
    const d = draft.defaults;
    const rows = t.targets
      .map(
        (x, i) => `<div class="trap-row" data-i="${i}">
        <label class="field"><span>IP do receptor de traps (NMS)</span><input name="host" value="${esc(x.host || '')}" placeholder="ex.: 192.168.1.2"></label>
        <label class="field narrow"><span>Porta</span><input name="port" type="number" min="1" max="65535" value="${esc(x.port || 162)}"></label>
        <button type="button" class="btn ghost small danger" data-del="${i}">Remover</button></div>`
      )
      .join('');
    const isEdge = info.role === 'edge';
    return `
      <h1>Alarmes e SNMP</h1>
      <p class="lead">${isEdge ? 'Para onde este Pi manda as traps, e quanto tempo cada falha precisa durar para virar alarme.' : 'Para onde a central manda as traps de "sem comunicação com o Pi". Os alarmes de imagem e áudio saem dos próprios Pis.'}</p>
      <fieldset class="group">
        <legend>Destinos das traps</legend>
        <div class="trap-list">${rows || '<p class="hint">Sem destinos: nenhuma trap será enviada.</p>'}</div>
        <button type="button" class="btn small" id="add-trap">Adicionar destino</button>
        <div class="grid-2">
          <label class="field"><span>Versão</span><select name="version"><option value="1" ${t.version !== '2c' ? 'selected' : ''}>SNMPv1 (igual às versões anteriores)</option><option value="2c" ${t.version === '2c' ? 'selected' : ''}>SNMPv2c</option></select></label>
          <label class="field"><span>Comunidade</span><input name="community" value="${esc(t.community || 'public')}"></label>
        </div>
      </fieldset>
      ${
        isEdge
          ? `<fieldset class="group">
        <legend>Quando alarmar</legend>
        <div class="grid-2">
          <label class="field"><span>Imagem congelada por</span><span class="unit"><input name="freeze" type="number" min="1" max="3600" value="${d.freeze.seconds}"> s</span></label>
          <label class="field"><span>Tela preta por</span><span class="unit"><input name="black" type="number" min="1" max="3600" value="${d.black.seconds}"> s</span></label>
          <label class="field"><span>Silêncio por</span><span class="unit"><input name="silence" type="number" min="1" max="3600" value="${d.silence.seconds}"> s</span></label>
          <label class="field"><span>Considerar silêncio abaixo de</span><span class="unit"><input name="dbfs" type="number" min="-120" max="0" value="${d.silence.dbfs}"> dBFS</span></label>
        </div>
        <p class="hint">Cartelas e vinhetas paradas podem disparar congelamento; se acontecer, aumente o tempo.</p>
      </fieldset>
      <fieldset class="group">
        <legend>Consulta pelo NMS (agente SNMP)</legend>
        <label class="check"><input type="checkbox" name="agent" ${draft.snmp.agent && draft.snmp.agent.enabled ? 'checked' : ''}> Responder a GET/WALK na porta <input name="agentPort" type="number" class="inline" min="1" max="65535" value="${esc((draft.snmp.agent && draft.snmp.agent.port) || 1161)}"></label>
      </fieldset>`
          : `<fieldset class="group"><legend>Quando alarmar</legend>
        <label class="field"><span>Sem comunicação com um Pi por</span><span class="unit"><input name="offline" type="number" min="3" max="600" value="${(draft.central && draft.central.offlineSeconds) || 10}"> s</span></label></fieldset>`
      }`;
  };
  BIND.alarmes = (b) => {
    $('#add-trap', b).addEventListener('click', () => {
      COLLECT.alarmes(b, true);
      draft.snmp.traps.targets.push({ host: '', port: 162 });
      render();
    });
    $$('[data-del]', b).forEach((x) =>
      x.addEventListener('click', () => {
        COLLECT.alarmes(b, true);
        draft.snmp.traps.targets.splice(Number(x.dataset.del), 1);
        render();
      })
    );
  };
  COLLECT.alarmes = (b, partial) => {
    const t = draft.snmp.traps;
    t.targets = $$('.trap-row', b).map((row) => ({ host: $('[name=host]', row).value.trim(), port: Number($('[name=port]', row).value) || 162 }));
    t.version = $('[name=version]', b).value;
    t.community = $('[name=community]', b).value.trim() || 'public';
    t.enabled = true;
    const num = (n, min, max, label) => {
      const el = $(`[name=${n}]`, b);
      if (!el) return undefined;
      const v = Number(el.value);
      if (!partial && (!Number.isFinite(v) || v < min || v > max)) throw new Error(`${label} deve ficar entre ${min} e ${max}.`);
      return v;
    };
    if (info.role === 'edge') {
      const d = draft.defaults;
      d.freeze.seconds = num('freeze', 1, 3600, 'O tempo de congelamento');
      d.black.seconds = num('black', 1, 3600, 'O tempo de tela preta');
      d.silence.seconds = num('silence', 1, 3600, 'O tempo de silêncio');
      d.silence.dbfs = num('dbfs', -120, 0, 'O limite de silêncio');
      draft.snmp.agent = { ...(draft.snmp.agent || {}), enabled: $('[name=agent]', b).checked, port: num('agentPort', 1, 65535, 'A porta do agente') };
    } else {
      draft.central = { ...(draft.central || {}), offlineSeconds: num('offline', 3, 600, 'O tempo sem comunicação') };
    }
    if (partial) return;
    t.targets = t.targets.filter((x) => x.host);
    for (const x of t.targets) if (!/^[A-Za-z0-9.:-]+$/.test(x.host)) throw new Error(`Endereço de trap inválido: ${x.host}`);
  };

  // ----- 4. Vídeo ao vivo (Pi de borda) -----
  RENDER.stream = () => {
    const s = draft.defaults.stream;
    const cur = PRESETS.find((p) => p.width === s.width && p.bitrate === s.bitrate) || null;
    const cards = PRESETS.map(
      (p) => `<label class="preset"><input type="radio" name="preset" value="${p.id}" ${cur === p ? 'checked' : ''}><span class="preset-name">${p.name}</span><span class="preset-note">${p.note}</span></label>`
    ).join('');
    return `
      <h1>Vídeo ao vivo</h1>
      <p class="lead">O Pi gera um stream para o painel e para o servidor central. Ele só passa pelo enlace quando alguém está assistindo, e uma vez só, mesmo com várias pessoas vendo.</p>
      <label class="check big"><input type="checkbox" name="enabled" ${s.enabled !== false ? 'checked' : ''}> Gerar vídeo ao vivo</label>
      <fieldset class="group" id="stream-opts">
        <legend>Qualidade</legend>
        <div class="presets">${cards}${cur ? '' : `<label class="preset"><input type="radio" name="preset" value="custom" checked><span class="preset-name">Personalizada</span><span class="preset-note">${s.width} px, ${esc(s.bitrate)}bit/s (definida no arquivo)</span></label>`}</div>
        <label class="field"><span>Quanto dá para voltar no player</span><select name="window">
          ${[30, 60, 120].map((w) => `<option value="${w}" ${Number(s.windowSeconds) === w ? 'selected' : ''}>${w} segundos</option>`).join('')}
        </select></label>
        <p class="hint">O stream fica na memória RAM do Pi, não no cartão SD. 120 s em qualidade alta ocupam cerca de 60 MB por canal.</p>
      </fieldset>`;
  };
  BIND.stream = (b) => {
    const en = $('[name=enabled]', b);
    const sync = () => ($('#stream-opts', b).disabled = !en.checked);
    en.addEventListener('change', sync);
    sync();
  };
  COLLECT.stream = (b) => {
    const s = draft.defaults.stream;
    s.enabled = $('[name=enabled]', b).checked;
    const p = PRESETS.find((x) => x.id === ($('[name=preset]:checked', b) || {}).value);
    if (p) Object.assign(s, { width: p.width, bitrate: p.bitrate, fps: p.fps });
    s.windowSeconds = Number($('[name=window]', b).value);
  };

  // ----- 5. Revisar -----
  function summary() {
    const rows = [['Nome do local', draft.siteName], ['Usuário do painel', `${draft.http.auth.user}${draft.http.auth.newPassword ? ' (senha nova)' : ''}`]];
    if (info.role === 'edge') {
      for (const c of draft.channels) {
        const m = toModel(c);
        const src =
          m.kind === 'device'
            ? `${m.device}, ${m.format.toUpperCase()} ${m.width}×${m.height} a ${nf.format(m.fps)} q/s, ${m.alsa ? `áudio ${m.alsa}` : 'sem áudio'}`
            : m.kind === 'url'
              ? m.url
              : 'configuração manual';
        rows.push([`Canal "${m.name}"`, src]);
      }
      const s = draft.defaults.stream;
      rows.push(['Vídeo ao vivo', s.enabled === false ? 'desligado' : `${(PRESETS.find((p) => p.width === s.width && p.bitrate === s.bitrate) || { name: 'personalizado' }).name}, janela de ${s.windowSeconds} s`]);
      const d = draft.defaults;
      rows.push(['Alarmes', `congelamento ${d.freeze.seconds} s, tela preta ${d.black.seconds} s, silêncio ${d.silence.seconds} s abaixo de ${d.silence.dbfs} dBFS`]);
    } else {
      rows.push(['Pis', draft.sites.length ? draft.sites.map((s) => `${s.name} (${s.url})`).join('; ') : 'nenhum']);
    }
    const t = draft.snmp.traps;
    rows.push(['Traps', t.targets.length ? `SNMPv${t.version} para ${t.targets.map((x) => `${x.host}:${x.port}`).join(', ')}` : 'nenhum destino']);
    return rows;
  }
  // JSON mostrado na revisão: sem nenhuma senha digitada.
  function exportable() {
    const c = JSON.parse(JSON.stringify(draft));
    if (c.http && c.http.auth) delete c.http.auth.newPassword;
    for (const s of c.sites || []) {
      delete s.password;
      delete s.hasPassword;
    }
    return c;
  }
  RENDER.revisar = () => {
    const rows = summary();
    return `
      <h1>Revisar e aplicar</h1>
      <p class="lead">Ao salvar, o LiveSafe reinicia para usar a configuração nova. A monitoração fica parada por alguns segundos.</p>
      <dl class="review">${rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>
      <details class="advanced" ${jsonEdited ? 'open' : ''}>
        <summary>Editar a configuração completa (JSON)</summary>
        <p class="hint">Para ajustes que o assistente não mostra. Senhas não aparecem aqui e são mantidas.</p>
        <textarea name="json" spellcheck="false" rows="18">${esc(jsonEdited || JSON.stringify(exportable(), null, 2))}</textarea>
      </details>`;
  };
  BIND.revisar = (b) => {
    $('[name=json]', b).addEventListener('input', (e) => (jsonEdited = e.target.value));
  };
  COLLECT.revisar = (b) => {
    const ta = $('[name=json]', b);
    if (jsonEdited) {
      let obj;
      try {
        obj = JSON.parse(ta.value);
      } catch (e) {
        throw new Error('O JSON editado tem um erro de sintaxe: ' + e.message);
      }
      const auth = draft.http.auth;
      const typed = new Map((draft.sites || []).filter((x) => x.password).map((x) => [x.url, x.password]));
      draft = obj;
      for (const x of draft.sites || []) if (!x.password && typed.has(x.url)) x.password = typed.get(x.url);
      draft.http = draft.http || {};
      draft.http.auth = { ...(draft.http.auth || {}), user: (draft.http.auth && draft.http.auth.user) || auth.user, ...(auth.newPassword ? { newPassword: auth.newPassword } : {}) };
    }
  };

  async function save() {
    if (info.role === 'edge' && !draft.channels.length) throw new Error('Configure pelo menos um canal na etapa "Entrada de sinal".');
    if (info.role === 'central' && !draft.sites.length) throw new Error('Cadastre pelo menos um Pi na etapa "Pis dos abrigos".');
    const cfg = JSON.parse(JSON.stringify(draft));
    cfg.role = info.role;
    // ids: os já gravados não mudam (histórico e links continuam valendo);
    // os novos saem do nome (ex.: "Receptor TV Gazeta" -> receptor-tv-gazeta).
    const assign = (list, saved) => {
      const keep = new Set((saved || []).map((x) => x.id).filter(Boolean));
      const used = new Set();
      const kept = new Set();
      for (const x of list) {
        if (x.id && keep.has(x.id) && !used.has(x.id)) {
          used.add(x.id);
          kept.add(x);
        }
      }
      for (const x of list) if (!kept.has(x)) x.id = slug(x.name, used);
    };
    assign(cfg.channels || [], info.config.channels);
    assign(cfg.sites || [], info.config.sites);
    $('#applying').hidden = false;
    $('#applying-text').textContent = 'Salvando e reiniciando o LiveSafe…';
    try {
      await api('api/setup/save', { config: cfg });
    } catch (e) {
      $('#applying').hidden = true;
      throw e;
    }
    // Espera o serviço voltar e abre o painel.
    const t0 = Date.now();
    await new Promise((r) => setTimeout(r, 2500));
    for (;;) {
      try {
        const r = await fetch('healthz', { cache: 'no-store' });
        if (r.ok) break;
      } catch (e) {}
      if (Date.now() - t0 > 60000) {
        $('#applying-text').textContent = 'O LiveSafe está demorando para voltar. Confira com: journalctl -u livesafe -n 50';
        return;
      }
      await new Promise((r) => setTimeout(r, 1000));
    }
    $('#applying-text').textContent = 'Pronto. Abrindo o painel…';
    location.href = './';
  }

  // ---------- navegação ----------
  $('#step').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!collect()) return;
    if (steps[step] === 'revisar') {
      const btn = $('#next');
      btn.disabled = true;
      try {
        await save();
      } catch (err) {
        showError(err.message);
      }
      btn.disabled = false;
      return;
    }
    go(step + 1);
  });
  $('#prev').addEventListener('click', () => {
    if (!collect()) return;
    go(step - 1);
  });

  // ---------- início ----------
  async function start() {
    try {
      info = await api('api/setup');
    } catch (e) {
      $('#loading').textContent = 'Não foi possível ler a configuração: ' + e.message;
      return;
    }
    const c = info.config;
    draft = {
      ...c,
      role: info.role,
      siteName: c.siteName || '',
      http: { ...(c.http || {}), auth: { user: (c.http && c.http.auth && c.http.auth.user) || 'admin' } },
      snmp: {
        traps: { enabled: true, targets: [], community: 'public', version: '1', sendStartup: true, ...((c.snmp && c.snmp.traps) || {}) },
        agent: { ...(info.role === 'edge' ? { enabled: false, port: 1161, community: 'public', address: '0.0.0.0' } : {}), ...((c.snmp && c.snmp.agent) || {}) },
      },
      defaults: JSON.parse(JSON.stringify(info.defaults)),
      // Cópias: o rascunho não pode alterar a configuração gravada (info.config).
      channels: JSON.parse(JSON.stringify(c.channels || [])),
      sites: JSON.parse(JSON.stringify(c.sites || [])),
    };
    // Mescla os padrões com o que já estava no arquivo.
    for (const [k, v] of Object.entries((c.defaults) || {})) {
      draft.defaults[k] = typeof v === 'object' && v && !Array.isArray(v) ? { ...draft.defaults[k], ...v } : v;
    }
    draft.snmp.traps.targets = JSON.parse(JSON.stringify(draft.snmp.traps.targets || []));
    if (info.role === 'central') delete draft.snmp.agent;
    steps = info.role === 'edge' ? ['local', 'entrada', 'alarmes', 'stream', 'revisar'] : ['local', 'pis', 'alarmes', 'revisar'];
    if (info.role === 'central' && !draft.sites.length) draft.sites.push({ name: '', url: '', user: 'admin' });
    if (!info.setupPending) visited = steps.length - 1;
    $('#role-label').textContent = info.role === 'edge' ? 'Configuração do Pi de borda' : 'Configuração do servidor central';
    if (info.setupPending) $('#back-link').hidden = true;
    const h = info.host;
    $('#host-card').innerHTML = `
      <div><dt>Equipamento</dt><dd>${esc(h.model)}</dd></div>
      <div><dt>Nome na rede</dt><dd>${esc(h.hostname)}</dd></div>
      <div><dt>IP</dt><dd>${h.ips.map((x) => esc(x.address)).join('<br>') || '—'}</dd></div>
      <div><dt>LiveSafe</dt><dd>${esc(info.version)}</dd></div>`;
    $('#loading').hidden = true;
    $('#setup').hidden = false;
    render();
  }
  start();
})();
