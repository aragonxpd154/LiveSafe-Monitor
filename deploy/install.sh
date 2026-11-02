#!/usr/bin/env bash
# Instala ou atualiza o LiveSafe Monitor (sem perguntas). Normalmente é chamado
# pelo instalador com assistente (install.sh na raiz), mas funciona sozinho:
#
#   sudo ./deploy/install.sh edge              Pi no abrigo, com placa HDMI-USB
#   sudo ./deploy/install.sh central           servidor que reúne os Pis
#
# Opções:   --sem-watchdog-hw   não liga o watchdog de hardware do Raspberry Pi
# Variáveis (só na primeira instalação):
#   LIVESAFE_SITE      nome do local         (padrão: nome da máquina)
#   LIVESAFE_USER      usuário do painel     (padrão: admin)
#   LIVESAFE_PASSWORD  senha do painel       (padrão: gerada e mostrada no fim)
#   LIVESAFE_PORT      porta do painel       (padrão: 8080)
#
# Rodar de novo atualiza o código e mantém a configuração. O progresso sai em
# linhas "==> [NN] mensagem", que o instalador com assistente usa na barra.
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
STATE_DIR=/var/lib/livesafe
CONFIG="$STATE_DIR/config.json"
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NODE_VERSION=22.11.0 # usado só se o Node da distribuição for antigo demais
NEED_REBOOT=0
GENERATED_PASSWORD=""

step() { echo "==> [$1] $2"; }
die() {
  echo "ERRO: $*" >&2
  exit 1
}

[[ $EUID -eq 0 ]] || die "rode com sudo: sudo $0 $*"
[[ -f "$SRC_DIR/src/index.js" ]] || die "não encontrei o LiveSafe em $SRC_DIR"
command -v apt-get >/dev/null || die "este instalador precisa de um sistema Debian (Raspberry Pi OS, Debian ou Ubuntu)"
export DEBIAN_FRONTEND=noninteractive

# ---------- pacotes ----------
# Pacote offline: traz uma pasta debs/ (repositório apt local) com o ffmpeg, o
# Node.js e as dependências. Se a arquitetura bater, instala só dali, sem internet.
APT=(apt-get)
OFFLINE=0
if [[ -f "$SRC_DIR/debs/Packages" ]]; then
  BUNDLE_ARCH=$(cat "$SRC_DIR/debs/ARCH" 2>/dev/null || echo "?")
  if [[ "$BUNDLE_ARCH" == "$(dpkg --print-architecture)" ]]; then
    OFFLINE=1
    LOCAL_LIST=$(mktemp /tmp/livesafe-offline.XXXXXX.list)
    echo "deb [trusted=yes] file:$SRC_DIR/debs ./" >"$LOCAL_LIST"
    APT=(apt-get -o "Dir::Etc::sourcelist=$LOCAL_LIST" -o "Dir::Etc::sourceparts=-" -o "APT::Get::List-Cleanup=0")
    chmod -R a+rX "$SRC_DIR/debs"
    DEB_COUNT=$(find "$SRC_DIR/debs" -maxdepth 1 -name '*.deb' | wc -l)
    echo "    Usando o pacote offline ($DEB_COUNT pacotes, $BUNDLE_ARCH)"
  else
    echo "    O pacote offline é para $BUNDLE_ARCH e esta máquina é $(dpkg --print-architecture); usando a internet."
  fi
fi
if [[ -z "${LIVESAFE_SKIP_APT:-}" ]]; then
  step 5 "Atualizando a lista de pacotes"
  "${APT[@]}" update -qq || die "não foi possível atualizar a lista de pacotes$([[ $OFFLINE -eq 1 ]] && echo ' do pacote offline' || echo '; confira a internet')"
  PKGS=(curl ca-certificates tar xz-utils)
  [[ $OFFLINE -eq 1 ]] && PKGS+=(nodejs)
  if [[ "$ROLE" == "edge" ]]; then
    step 15 "Instalando ffmpeg e utilitários de captura (pode levar alguns minutos)"
    PKGS+=(ffmpeg v4l-utils alsa-utils)
  else
    step 15 "Instalando dependências"
  fi
  "${APT[@]}" install -y -qq --no-install-recommends "${PKGS[@]}" >/dev/null || die "falha ao instalar: ${PKGS[*]}"
  [[ -n "${LOCAL_LIST:-}" ]] && rm -f "$LOCAL_LIST"
fi

# ---------- Node.js ----------
step 40 "Verificando o Node.js"
node_major() { node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0; }
if (($(node_major) < 18)) && [[ -z "${LIVESAFE_SKIP_APT:-}" && $OFFLINE -eq 0 ]]; then
  apt-get install -y -qq nodejs >/dev/null 2>&1 || true
fi
if (($(node_major) < 18)) && [[ $OFFLINE -eq 1 ]]; then
  die "o Node.js do pacote offline é antigo demais para este sistema; use o Raspberry Pi OS Bookworm (64 bits) ou instale com internet"
fi
if (($(node_major) < 18)); then
  case "$(uname -m)" in
    aarch64 | arm64) NODE_ARCH=arm64 ;;
    armv7l) NODE_ARCH=armv7l ;;
    x86_64) NODE_ARCH=x64 ;;
    *) die "arquitetura $(uname -m) sem Node.js oficial; use um Pi 3, 4 ou 5 (ou um PC 64 bits)" ;;
  esac
  step 45 "Baixando o Node.js $NODE_VERSION (o da distribuição é antigo demais)"
  mkdir -p "$APP_DIR/runtime"
  curl -fsSL "https://nodejs.org/dist/v$NODE_VERSION/node-v$NODE_VERSION-linux-$NODE_ARCH.tar.xz" | tar -xJ -C "$APP_DIR/runtime" --strip-components=1
  ln -sf "$APP_DIR/runtime/bin/node" /usr/local/bin/node
  ln -sf "$APP_DIR/runtime/bin/npm" /usr/local/bin/npm
  hash -r
fi
(($(node_major) >= 18)) || die "não foi possível instalar o Node.js 18 ou mais novo"

# ---------- usuário ----------
step 55 "Criando o usuário do serviço"
if ! id livesafe &>/dev/null; then
  useradd --system --home "$STATE_DIR" --shell /usr/sbin/nologin livesafe
fi
usermod -aG video,audio livesafe

# ---------- aplicação ----------
step 60 "Copiando o LiveSafe para $APP_DIR"
mkdir -p "$APP_DIR"
if [[ "$SRC_DIR" != "$APP_DIR" ]]; then
  rm -rf "$APP_DIR/src" "$APP_DIR/public" "$APP_DIR/deploy" "$APP_DIR/scripts"
  rm -rf "$APP_DIR/debs"
  # debs/ fica guardado para o central repassar a Pis sem internet.
  for f in src public deploy scripts debs package.json package-lock.json install.sh README.md LICENSE config.edge.example.json config.central.example.json; do
    [[ -e "$SRC_DIR/$f" ]] && cp -r "$SRC_DIR/$f" "$APP_DIR/"
  done
  if [[ -d "$SRC_DIR/node_modules" ]]; then
    rm -rf "$APP_DIR/node_modules"
    cp -r "$SRC_DIR/node_modules" "$APP_DIR/"
  fi
fi
chmod 755 "$APP_DIR/deploy/"*.sh "$APP_DIR/install.sh" 2>/dev/null || true
cd "$APP_DIR"
if [[ ! -d node_modules/net-snmp || ! -d node_modules/hls.js ]]; then
  step 70 "Instalando os módulos do Node (npm)"
  if ! command -v npm >/dev/null; then apt-get install -y -qq npm >/dev/null; fi
  npm ci --omit=dev --no-audit --no-fund --loglevel=error
fi
chown -R root:root "$APP_DIR"

# ---------- configuração ----------
step 80 "Preparando a configuração"
mkdir -p "$STATE_DIR"
chown livesafe:livesafe "$STATE_DIR"
chmod 750 "$STATE_DIR"
if [[ ! -f "$CONFIG" && -f /etc/livesafe/config.json ]]; then
  # Instalações anteriores guardavam em /etc; agora o painel precisa poder gravar.
  mv /etc/livesafe/config.json "$CONFIG"
  rmdir /etc/livesafe 2>/dev/null || true
  echo "    Configuração movida de /etc/livesafe para $CONFIG"
fi
if [[ ! -f "$CONFIG" ]]; then
  if [[ -z "${LIVESAFE_PASSWORD:-}" ]]; then
    GENERATED_PASSWORD=$(tr -dc 'A-HJ-NP-Za-km-z2-9' </dev/urandom | head -c 12)
    LIVESAFE_PASSWORD="$GENERATED_PASSWORD"
  fi
  LIVESAFE_ROLE="$ROLE" LIVESAFE_PASSWORD="$LIVESAFE_PASSWORD" LIVESAFE_SITE="${LIVESAFE_SITE:-$(hostname)}" \
    LIVESAFE_USER="${LIVESAFE_USER:-admin}" LIVESAFE_PORT="${LIVESAFE_PORT:-8080}" \
    node -e '
      const fs = require("fs");
      const { hashPassword } = require(process.argv[1] + "/src/auth.js");
      const e = process.env;
      const cfg = {
        role: e.LIVESAFE_ROLE,
        siteName: e.LIVESAFE_SITE,
        http: { host: "0.0.0.0", port: Number(e.LIVESAFE_PORT), auth: { user: e.LIVESAFE_USER, passwordHash: hashPassword(e.LIVESAFE_PASSWORD) } },
        snmp: { traps: { enabled: true, targets: [], community: "public", version: "1", sendStartup: true } },
        events: { file: process.argv[2] + "/events.jsonl" },
        channels: [],
        sites: [],
      };
      fs.writeFileSync(process.argv[3], JSON.stringify(cfg, null, 2) + "\n", { mode: 0o640 });
    ' "$APP_DIR" "$STATE_DIR" "$CONFIG"
  echo "    Configuração inicial criada; os canais e Pis são configurados pelo navegador."
else
  echo "    Mantida a configuração existente em $CONFIG"
fi
chown livesafe:livesafe "$CONFIG"
chmod 640 "$CONFIG"
if ! runuser -u livesafe -- node -e "require('$APP_DIR/src/config').load('$CONFIG')" 2>/tmp/livesafe-config-check; then
  echo "    Atenção: a configuração tem um problema: $(cat /tmp/livesafe-config-check)" >&2
fi
rm -f /tmp/livesafe-config-check

# ---------- serviços ----------
HAS_SYSTEMD=0
[[ -d /run/systemd/system ]] && HAS_SYSTEMD=1
step 88 "Instalando os serviços e o vigia"
install -m 644 "$APP_DIR/deploy/livesafe.service" /etc/systemd/system/livesafe.service
install -m 644 "$APP_DIR/deploy/livesafe-watchdog.service" /etc/systemd/system/livesafe-watchdog.service
install -m 644 "$APP_DIR/deploy/livesafe-watchdog.timer" /etc/systemd/system/livesafe-watchdog.timer
if [[ $HAS_SYSTEMD -eq 1 ]]; then
  systemctl daemon-reload
  systemctl enable livesafe livesafe-watchdog.timer >/dev/null 2>&1
else
  echo "    Este sistema não usa systemd (contêiner?). Inicie à mão: runuser -u livesafe -- node $APP_DIR/src/index.js $CONFIG"
fi

# Watchdog de hardware: se o Pi inteiro congelar, o chip reinicia a placa.
if [[ $HW_WATCHDOG -eq 1 ]] && grep -qa "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
  step 94 "Ligando o watchdog de hardware do Raspberry Pi"
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
  [[ $HAS_SYSTEMD -eq 1 ]] && systemctl daemon-reexec
fi

step 98 "Iniciando o LiveSafe"
if [[ $HAS_SYSTEMD -eq 1 ]]; then
  systemctl restart livesafe
  systemctl restart livesafe-watchdog.timer
fi

PORT=$(node -p "try{require('$CONFIG').http.port||8080}catch(e){8080}")
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
step 100 "Pronto"
# Linhas lidas pelo instalador com assistente:
echo "LIVESAFE_URL=http://${IP:-<ip>}:$PORT/setup"
[[ -n "$GENERATED_PASSWORD" ]] && echo "LIVESAFE_GENERATED_PASSWORD=$GENERATED_PASSWORD"
[[ $NEED_REBOOT -eq 1 ]] && echo "LIVESAFE_NEED_REBOOT=1"
[[ $HAS_SYSTEMD -eq 0 ]] && echo "LIVESAFE_NO_SYSTEMD=1"
echo
echo "Painel:        http://${IP:-<ip>}:$PORT  (configuração em /setup)"
echo "Logs ao vivo:  journalctl -u livesafe -f"
[[ "$ROLE" == "edge" ]] && echo "Placas ligadas: $APP_DIR/scripts/list-devices.sh"
exit 0
