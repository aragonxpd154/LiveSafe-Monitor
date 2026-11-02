'use strict';
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const { logger } = require('./log');

const log = logger('instalador');
const ROOT = path.join(__dirname, '..');
// O que vai no pacote. Inclui node_modules: o Pi novo não precisa do npm.
const INCLUDE = ['src', 'public', 'deploy', 'scripts', 'node_modules', 'debs', 'package.json', 'package-lock.json', 'install.sh', 'config.edge.example.json', 'config.central.example.json', 'README.md', 'LICENSE'];
const TAR_EXCLUDES = ['--exclude=*.log', '--exclude=.git', '--exclude=*.map', '--exclude=node_modules/hls.js/src', '--exclude=node_modules/.cache'];

// Serve /instalar.sh e /pacote.tar.gz para instalar Pis novos a partir deste
// LiveSafe (normalmente o central), sem depender da internet para o código.
function createInstaller(version) {
  let pkg = null;
  let building = null;

  function build() {
    if (pkg) return Promise.resolve(pkg);
    if (building) return building;
    const items = INCLUDE.filter((f) => fs.existsSync(path.join(ROOT, f)));
    building = new Promise((resolve, reject) => {
      const p = spawn('tar', ['-czf', '-', ...TAR_EXCLUDES, '-C', ROOT, ...items], { stdio: ['ignore', 'pipe', 'pipe'] });
      const parts = [];
      let err = '';
      p.stdout.on('data', (d) => parts.push(d));
      p.stderr.on('data', (d) => (err += d));
      p.on('error', (e) => {
        building = null;
        reject(e);
      });
      p.on('close', (code) => {
        building = null;
        if (code !== 0) return reject(new Error('falha ao empacotar: ' + err.slice(0, 300)));
        pkg = Buffer.concat(parts);
        log.info(`pacote de instalação gerado (${(pkg.length / 1048576).toFixed(1)} MB)`);
        resolve(pkg);
      });
    });
    return building;
  }

  async function handle(p, req, res) {
    if (p === '/pacote.tar.gz') {
      // Com os pacotes offline (debs/, ~100 MB) o arquivo é grande demais para a
      // memória: vai em fluxo direto do tar para o Pi que está instalando.
      if (fs.existsSync(path.join(ROOT, 'debs', 'Packages'))) {
        const items = INCLUDE.filter((f) => fs.existsSync(path.join(ROOT, f)));
        res.writeHead(200, {
          'Content-Type': 'application/gzip',
          'Content-Disposition': `attachment; filename="livesafe-monitor-${version}-offline.tar.gz"`,
          'Cache-Control': 'no-store',
        });
        const t = spawn('nice', ['-n', '10', 'tar', '-czf', '-', ...TAR_EXCLUDES, '-C', ROOT, ...items], { stdio: ['ignore', 'pipe', 'ignore'] });
        t.stdout.pipe(res);
        req.on('close', () => t.kill());
        t.on('error', () => res.destroy());
        return;
      }
      const body = await build();
      res.writeHead(200, {
        'Content-Type': 'application/gzip',
        'Content-Length': body.length,
        'Content-Disposition': `attachment; filename="livesafe-monitor-${version}.tar.gz"`,
        'Cache-Control': 'no-store',
      });
      return res.end(body);
    }
    // /instalar.sh: o mesmo instalador do GitHub, já apontando para este servidor.
    const host = String(req.headers.host || '').replace(/[^A-Za-z0-9.:[\]-]/g, '');
    let script = fs.readFileSync(path.join(ROOT, 'install.sh'), 'utf8');
    script = script.replace(/^LIVESAFE_SOURCE_DEFAULT=.*$/m, `LIVESAFE_SOURCE_DEFAULT="http://${host}/pacote.tar.gz"`);
    script = script.replace(/^LIVESAFE_ROLE_DEFAULT=.*$/m, 'LIVESAFE_ROLE_DEFAULT="edge"');
    script = script.replace(/^LIVESAFE_CENTRAL_DEFAULT=.*$/m, `LIVESAFE_CENTRAL_DEFAULT="http://${host}"`);
    res.writeHead(200, { 'Content-Type': 'text/x-shellscript; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(script);
  }

  return { handle };
}

module.exports = { createInstaller };
