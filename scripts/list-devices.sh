#!/usr/bin/env bash
# Lista placas de captura de vídeo (V4L2) e de áudio (ALSA) para montar o config.json.
set -u

echo "=== Vídeo (V4L2) ==="
if command -v v4l2-ctl >/dev/null; then
  v4l2-ctl --list-devices 2>/dev/null || echo "Nenhum dispositivo de vídeo encontrado."
  for dev in /dev/video*; do
    [[ -e "$dev" ]] || continue
    if v4l2-ctl -d "$dev" --list-formats-ext 2>/dev/null | grep -q "Size"; then
      echo
      echo "--- $dev (formatos e resoluções) ---"
      v4l2-ctl -d "$dev" --list-formats-ext 2>/dev/null | grep -E "\[[0-9]+\]|Size|Interval" | sed 's/^\s*/  /' | head -40
    fi
  done
else
  echo "Instale v4l-utils: sudo apt install v4l-utils"
fi

echo
echo "=== Áudio (ALSA) ==="
if command -v arecord >/dev/null; then
  arecord -l 2>/dev/null || echo "Nenhum dispositivo de captura de áudio."
  echo
  echo "Use no config.json algo como:  \"-f\", \"alsa\", \"-i\", \"hw:CARD=<nome>,DEV=0\""
  echo "Nomes de placa disponíveis:"
  arecord -L 2>/dev/null | grep -E "^hw:CARD" | sed 's/^/  /'
else
  echo "Instale alsa-utils: sudo apt install alsa-utils"
fi
