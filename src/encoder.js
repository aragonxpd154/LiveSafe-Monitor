'use strict';
const { spawnSync } = require('child_process');
const { logger } = require('./log');

const log = logger('encoder');

// Escolhe o encoder H.264 do stream ao vivo.
// No Raspberry Pi 4 o encoder por hardware (h264_v4l2m2m) praticamente não
// gasta CPU; se ele não estiver disponível (Pi 5, PC, VM), cai para o libx264
// em modo leve. O teste real (codificar 1 s) evita confiar só na lista de codecs.
function probe(ffmpegPath, name) {
  const args = ['-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=25', '-t', '1', '-pix_fmt', 'yuv420p', '-c:v', name];
  if (name === 'h264_v4l2m2m') args.push('-b:v', '1M');
  if (name === 'libx264') args.push('-preset', 'ultrafast');
  args.push('-f', 'null', '-');
  const r = spawnSync(ffmpegPath, args, { encoding: 'utf8', timeout: 15000 });
  return r.status === 0;
}

function resolve(ffmpegPath, wanted) {
  const order = wanted && wanted !== 'auto' ? [wanted] : ['h264_v4l2m2m', 'libx264'];
  for (const name of order) {
    if (probe(ffmpegPath, name)) {
      log.info(`stream ao vivo usando ${name}${name === 'h264_v4l2m2m' ? ' (hardware)' : ' (software)'}`);
      return name;
    }
    log.info(`${name} indisponível`);
  }
  log.warn('nenhum encoder H.264 funcionou; stream ao vivo desativado (a monitoração continua)');
  return null;
}

// Argumentos de codificação de vídeo para um encoder já escolhido.
function videoArgs(encoder, s) {
  const gop = String(Math.max(1, Math.round(s.fps * s.segmentSeconds)));
  const common = ['-g', gop, '-keyint_min', gop, '-force_key_frames', `expr:gte(t,n_forced*${s.segmentSeconds})`];
  if (encoder === 'h264_v4l2m2m') {
    return ['-c:v', 'h264_v4l2m2m', '-b:v', s.bitrate, '-maxrate', s.bitrate, '-bufsize', s.bitrate, ...common];
  }
  return ['-c:v', 'libx264', '-preset', s.preset, '-tune', 'zerolatency', '-profile:v', 'main', '-b:v', s.bitrate, '-maxrate', s.bitrate, '-bufsize', s.bitrate, '-sc_threshold', '0', ...common];
}

module.exports = { resolve, videoArgs };
