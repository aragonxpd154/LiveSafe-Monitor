#!/usr/bin/env bash
# Gera dist/livesafe-monitor.tar.gz: o pacote que o instalador baixa.
# Já inclui node_modules (só JavaScript, serve para qualquer arquitetura),
# então o Pi não precisa do npm nem do registro npm na instalação.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

DEST="$STAGE/livesafe-monitor"
mkdir -p "$DEST" "$OUT"
for f in src public deploy scripts package.json package-lock.json install.sh README.md LICENSE config.edge.example.json config.central.example.json; do
  cp -r "$ROOT/$f" "$DEST/"
done
(cd "$DEST" && npm ci --omit=dev --no-audit --no-fund --loglevel=error)
# Do hls.js o painel só usa o build "light" minificado.
find "$DEST/node_modules/hls.js" -mindepth 1 -maxdepth 1 ! -name package.json ! -name dist ! -name LICENSE -exec rm -rf {} +
find "$DEST/node_modules/hls.js/dist" -type f ! -name 'hls.light.min.js' -delete
rm -f "$DEST/scripts/build-release.sh" "$DEST/scripts/build-offline-bundle.sh"
tar -czf "$OUT/livesafe-monitor.tar.gz" -C "$STAGE" livesafe-monitor
VERSION=$(node -p "require('$ROOT/package.json').version")
echo "Gerado $OUT/livesafe-monitor.tar.gz (versão $VERSION, $(du -h "$OUT/livesafe-monitor.tar.gz" | cut -f1))"
