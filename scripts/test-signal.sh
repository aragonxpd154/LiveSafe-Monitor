#!/usr/bin/env bash
# Gera um sinal de teste em UDP com falhas programadas, para validar o LiveSafe
# sem placa de captura. Ciclo de ~53 s:
#   0–12 s  barras em movimento + tom de 1 kHz   (normal)
#  12–27 s  imagem congelada + tom               (alarme de congelamento)
#  27–41 s  tela preta + silêncio                (alarme de tela preta e silêncio)
#  41–53 s  normal de novo                       (normalizações)
#
# Uso: scripts/test-signal.sh [destino]   (padrão udp://127.0.0.1:5000)
# No config.json:  { "id": "teste", "name": "Sinal de teste", "url": "udp://127.0.0.1:5000" }
set -euo pipefail
DEST="${1:-udp://127.0.0.1:5000}"
DIR="$(mktemp -d)"
trap 'rm -rf "$DIR"' EXIT
cd "$DIR"

enc=(-c:v libx264 -preset ultrafast -pix_fmt yuv420p -g 30 -c:a aac -ac 2)
echo "Gerando trechos…"
ffmpeg -v error -y -f lavfi -i "testsrc2=size=1280x720:rate=30" -frames:v 1 still.png
ffmpeg -v error -y -f lavfi -i "testsrc2=size=1280x720:rate=30:duration=12" -f lavfi -i "sine=f=1000:r=48000:duration=12" "${enc[@]}" a.ts
ffmpeg -v error -y -loop 1 -framerate 30 -t 15 -i still.png -f lavfi -i "sine=f=600:r=48000:duration=15" "${enc[@]}" b.ts
ffmpeg -v error -y -f lavfi -i "color=c=black:size=1280x720:rate=30:duration=14" -f lavfi -i "anullsrc=r=48000:cl=stereo:d=14" "${enc[@]}" c.ts
printf "file a.ts\nfile b.ts\nfile c.ts\nfile a.ts\n" > list.txt
ffmpeg -v error -y -f concat -i list.txt -c copy program.ts

echo "Transmitindo para $DEST (Ctrl+C para parar; parar = teste de 'sem sinal')"
ffmpeg -v error -re -stream_loop -1 -i program.ts -c copy -f mpegts "$DEST?pkt_size=1316"
