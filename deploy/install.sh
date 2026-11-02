#!/usr/bin/env bash
# Instala ou atualiza o LiveSafe Monitor no Raspberry Pi (Raspberry Pi OS / Debian).
# Uso:  sudo ./deploy/install.sh edge      (Pi no abrigo, com placa HDMI-USB)
#       sudo ./deploy/install.sh central   (servidor que reúne todos os Pis)
# Opção: --sem-watchdog-hw   não liga o watchdog de hardware do Raspberry Pi
# Rodar de novo atualiza o código e preserva /etc/livesafe/config.json.
set -euo pipefail

ROLE="edge"
HW_WATCHDOG=1
for arg in "$@"; do
  case "$arg" in
    edge | central) ROLE="$arg" ;;
    --sem-watchdog-hw) HW_WATCHDOG=0 ;;
    *)
      echo "Uso: sudo $0 edge|central [--sem-watchdog-hw]" >&2
      exit 1
      ;;
  esac
done

APP_DIR=/opt/livesafe
CONF_DIR=/etc/livesafe
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NEED_REBOOT=0

if [[ $EUID -ne 0 ]]; then
  echo "Rode com sudo: sudo $0 $*" >&2
  exit 1
fi

echo "==> Instalando dependências do sistema"
apt-get update -qq
if [[ "$ROLE" == "edge" ]]; then
  apt-get install -y -qq ffmpeg nodejs npm curl v4l-utils alsa-utils >/dev/null
else
  apt-get install -y -qq nodejs npm curl >/dev/null
fi

NODE_MAJOR=$(node -p 'process.versions.node.split(".")[0]')
if ((NODE_MAJOR < 18)); then
  echo "Node.js $NODE_MAJOR é antigo demais; o LiveSafe precisa do 18 ou mais novo (Raspberry Pi OS Bookworm já traz o 18)." >&2
  exit 1
fi

echo "==> Criando usuário de serviço 'livesafe'"
if ! id livesafe &>/dev/null; then
  useradd --system --home /var/lib/livesafe --shell /usr/sbin/nologin livesafe
fi
usermod -aG video,audio livesafe

echo "==> Copiando aplicação para $APP_DIR"
mkdir -p "$APP_DIR"
rm -rf "$APP_DIR/src" "$APP_DIR/public" "$APP_DIR/deploy"
cp -r "$SRC_DIR/src" "$SRC_DIR/public" "$SRC_DIR/deploy" "$SRC_DIR/package.json" "$APP_DIR/"
if [[ -f "$SRC_DIR/package-lock.json" ]]; then cp "$SRC_DIR/package-lock.json" "$APP_DIR/"; fi
chmod 755 "$APP_DIR/deploy/watchdog.sh"
cd "$APP_DIR"
if [[ -f package-lock.json ]]; then
  npm ci --omit=dev --no-audit --no-fund --loglevel=error
else
  npm install --omit=dev --no-audit --no-fund --loglevel=error
fi
chown -R root:root "$APP_DIR"

echo "==> Configuração em $CONF_DIR"
mkdir -p "$CONF_DIR"
if [[ ! -f "$CONF_DIR/config.json" ]]; then
  cp "$SRC_DIR/config.$ROLE.example.json" "$CONF_DIR/config.json"
  echo "    Criado $CONF_DIR/config.json a partir de config.$ROLE.example.json — ajuste antes de usar."
else
  echo "    Mantido o $CONF_DIR/config.json existente."
fi
chown root:livesafe "$CONF_DIR/config.json"
chmod 640 "$CONF_DIR/config.json"

echo "==> Validando configuração"
if ! sudo -u livesafe node -e "require('$APP_DIR/src/config').load('$CONF_DIR/config.json')"; then
  echo "    Corrija o config.json e rode: sudo systemctl restart livesafe" >&2
fi

echo "==> Instalando serviço e vigia (reinicia o LiveSafe se ele travar)"
install -m 644 "$SRC_DIR/deploy/livesafe.service" /etc/systemd/system/livesafe.service
install -m 644 "$SRC_DIR/deploy/livesafe-watchdog.service" /etc/systemd/system/livesafe-watchdog.service
install -m 644 "$SRC_DIR/deploy/livesafe-watchdog.timer" /etc/systemd/system/livesafe-watchdog.timer
systemctl daemon-reload
systemctl enable livesafe livesafe-watchdog.timer >/dev/null 2>&1
systemctl restart livesafe
systemctl restart livesafe-watchdog.timer

# Watchdog de hardware: se o Pi inteiro congelar (kernel travado, calor), o
# chip reinicia a placa sozinho. O systemd "alimenta" o watchdog a cada poucos
# segundos; se ele parar de alimentar por 14 s, o Pi reinicia.
if [[ $HW_WATCHDOG -eq 1 ]] && grep -qa "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
  echo "==> Ligando o watchdog de hardware do Raspberry Pi"
  BOOTCFG=/boot/firmware/config.txt
  [[ -f "$BOOTCFG" ]] || BOOTCFG=/boot/config.txt
  if [[ -f "$BOOTCFG" ]] && ! grep -q "^dtparam=watchdog=on" "$BOOTCFG"; then
    printf '\n# LiveSafe: watchdog de hardware\ndtparam=watchdog=on\n' >>"$BOOTCFG"
    [[ -e /dev/watchdog ]] || NEED_REBOOT=1
  fi
  mkdir -p /etc/systemd/system.conf.d
  cat >/etc/systemd/system.conf.d/livesafe-watchdog.conf <<'EOF'
# Instalado pelo LiveSafe. Para desligar, apague este arquivo e reinicie.
[Manager]
RuntimeWatchdogSec=14
RebootWatchdogSec=2min
EOF
  systemctl daemon-reexec
  if [[ -e /dev/watchdog ]]; then
    echo "    Ativo: o Pi reinicia sozinho se travar por 14 s."
  else
    echo "    Será ativado no próximo reboot."
  fi
fi

IP=$(hostname -I | awk '{print $1}')
PORT=$(node -p "try{require('$CONF_DIR/config.json').http.port||8080}catch(e){8080}")
echo
echo "Pronto. Painel: http://$IP:$PORT"
echo "Logs ao vivo:  journalctl -u livesafe -f   (vigia: journalctl -t livesafe-watchdog)"
if [[ "$ROLE" == "edge" ]]; then echo "Descobrir a placa HDMI-USB: $SRC_DIR/scripts/list-devices.sh"; fi
echo "Editar a configuração: sudo nano $CONF_DIR/config.json && sudo systemctl restart livesafe"
if [[ $NEED_REBOOT -eq 1 ]]; then echo "Reinicie o Pi uma vez (sudo reboot) para ativar o watchdog de hardware."; fi
