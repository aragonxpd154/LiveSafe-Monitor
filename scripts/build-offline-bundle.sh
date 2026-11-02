#!/usr/bin/env bash
# Gera dist/livesafe-offline-<arquitetura>.tar.gz: o LiveSafe + todos os pacotes
# do sistema que ele precisa (ffmpeg, Node.js, utilitários de captura e as
# dependências deles), para instalar em Pis SEM internet — levando num pendrive
# ou deixando no servidor central, que repassa aos Pis.
#
# Dois modos:
#
#   ./scripts/build-offline-bundle.sh --pi
#       Em QUALQUER PC Debian/Ubuntu com internet (ex.: notebook com Zorin OS):
#       monta o pacote para Raspberry Pi OS Bookworm 64 bits (arm64). Não precisa
#       de Pi nem de sudo, e não instala nada no PC — usa um apt separado numa
#       pasta temporária, com os repositórios oficiais do Debian e do Raspberry Pi.
#
#   sudo ./scripts/build-offline-bundle.sh
#       Na própria máquina de destino (ex.: um Pi com internet): usa o apt do
#       sistema e gera o pacote para o sistema e a arquitetura dela.
#
# Opções avançadas: --arch ARQ --sources ARQUIVO.list (repositórios próprios).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist"
PKGS=(ffmpeg nodejs v4l-utils alsa-utils curl ca-certificates tar xz-utils whiptail)
MODE=native
ARCH=""
SOURCES=""
CODENAME=""

while (($#)); do
  case "$1" in
    --pi) MODE=cross; ARCH=arm64; CODENAME=bookworm ;;
    --arch) MODE=cross; ARCH="$2"; shift ;;
    --sources) MODE=cross; SOURCES="$2"; shift ;;
    -h | --help) sed -n '2,21p' "$0"; exit 0 ;;
    *) echo "Opção desconhecida: $1 (use --help)" >&2; exit 1 ;;
  esac
  shift
done

need() { command -v "$1" >/dev/null || { echo "Falta o programa '$1'. Instale com: sudo apt install $2" >&2; exit 1; }; }
need apt-get apt
need dpkg-scanpackages dpkg-dev
need curl curl

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

# ---------- apt usado para resolver e baixar ----------
APT_OPTS=()
if [[ $MODE == cross ]]; then
  [[ -n "$ARCH" ]] || { echo "Informe --arch (ex.: --arch arm64) ou use --pi" >&2; exit 1; }
  AR="$STAGE/apt"
  mkdir -p "$AR/etc/apt/apt.conf.d" "$AR/etc/apt/preferences.d" "$AR/etc/apt/sources.list.d" "$AR/keys" \
    "$AR/var/lib/apt/lists/partial" "$AR/var/cache/apt/archives/partial" "$AR/var/lib/dpkg"
  : >"$AR/var/lib/dpkg/status"
  if [[ -n "$SOURCES" ]]; then
    cp "$SOURCES" "$AR/etc/apt/sources.list"
  else
    # Raspberry Pi OS Bookworm = Debian Bookworm + repositório do Raspberry Pi.
    DEB_KEY=/usr/share/keyrings/debian-archive-keyring.gpg
    [[ -f "$DEB_KEY" ]] || { echo "Falta a chave do Debian. Instale com: sudo apt install debian-archive-keyring" >&2; exit 1; }
    need gpg gnupg
    echo "==> Baixando a chave do repositório do Raspberry Pi"
    if ! curl -fsSL https://archive.raspberrypi.com/debian/raspberrypi.gpg.key -o "$STAGE/raspberrypi.gpg.key"; then
      echo "Não consegui acessar archive.raspberrypi.com. Este PC está com internet?" >&2
      exit 1
    fi
    gpg --dearmor <"$STAGE/raspberrypi.gpg.key" >"$AR/keys/raspberrypi.gpg"
    cat >"$AR/etc/apt/sources.list" <<EOF
deb [arch=$ARCH signed-by=$DEB_KEY] http://deb.debian.org/debian $CODENAME main
deb [arch=$ARCH signed-by=$DEB_KEY] http://deb.debian.org/debian $CODENAME-updates main
deb [arch=$ARCH signed-by=$DEB_KEY] http://security.debian.org/debian-security $CODENAME-security main
deb [arch=$ARCH signed-by=$AR/keys/raspberrypi.gpg] http://archive.raspberrypi.com/debian $CODENAME main
EOF
  fi
  # Isolado de verdade: o APT_CONFIG faz o apt ignorar as configurações do PC
  # (/etc/apt/apt.conf.d), então nada daqui toca o apt do sistema.
  mkdir -p "$AR/etc/apt/trusted.gpg.d"
  cat >"$AR/etc/apt/apt.conf" <<CONF
Dir "$AR/";
Dir::State::status "$AR/var/lib/dpkg/status";
Dir::Etc::Parts "$AR/etc/apt/apt.conf.d";
Dir::Etc::Trusted "$AR/etc/apt/trusted.gpg";
Dir::Etc::TrustedParts "$AR/etc/apt/trusted.gpg.d";
APT::Architecture "$ARCH";
APT::Architectures { "$ARCH"; };
APT::Sandbox::User "$(id -un)";
Debug::NoLocking "true";
CONF
  export APT_CONFIG="$AR/etc/apt/apt.conf"
  echo "==> Lendo os repositórios para $ARCH (pasta temporária, nada é instalado neste PC)"
else
  [[ $EUID -eq 0 ]] || { echo "No modo nativo rode com sudo (ou use --pi para montar o pacote do Pi a partir deste PC)." >&2; exit 1; }
  ARCH=$(dpkg --print-architecture)
  CODENAME=$(. /etc/os-release && echo "${VERSION_CODENAME:-desconhecido}")
fi
apt-get "${APT_OPTS[@]}" update -qq
[[ -z "$CODENAME" ]] && CODENAME=$(sed -E 's/\[[^]]*\]//' "$AR/etc/apt/sources.list" | awk '$1 == "deb" { print $3; exit }')
echo "==> Alvo: $CODENAME, $ARCH"

# ---------- pacote da aplicação (já com node_modules) ----------
if [[ ! -f "$OUT/livesafe-monitor.tar.gz" ]]; then
  need npm npm
  bash "$ROOT/scripts/build-release.sh"
fi
tar -xzf "$OUT/livesafe-monitor.tar.gz" -C "$STAGE"
DEBS="$STAGE/livesafe-monitor/debs"
mkdir -p "$DEBS"

# ---------- dependências ----------
# Fecho completo (sem "recomendados"), incluindo o que já viria instalado no
# sistema base, para servir em qualquer Pi com a mesma versão do sistema.
echo "==> Calculando dependências de: ${PKGS[*]}"
mapfile -t ALL < <(apt-cache "${APT_OPTS[@]}" depends --recurse --no-recommends --no-suggests --no-conflicts \
  --no-breaks --no-replaces --no-enhances "${PKGS[@]}" | grep -E '^[a-z0-9]' | sort -u)
echo "    ${#ALL[@]} pacotes"

echo "==> Baixando (pode levar alguns minutos)"
[[ $EUID -eq 0 && $MODE == native ]] && chown _apt "$DEBS" 2>/dev/null || true
: >"$STAGE/failed"
(
  cd "$DEBS"
  # Em lotes de 40: bem mais rápido que um apt-get por pacote. Se um lote
  # falhar (ex.: um nome virtual no meio), o laço abaixo completa um a um.
  for ((i = 0; i < ${#ALL[@]}; i += 40)); do
    apt-get "${APT_OPTS[@]}" download -qq "${ALL[@]:i:40}" >/dev/null 2>&1 || true
  done
)
# Repete um a um o que faltou (pacotes virtuais não têm .deb e são ignorados).
for p in "${ALL[@]}"; do
  compgen -G "$DEBS/${p}_*.deb" >/dev/null && continue
  (cd "$DEBS" && apt-get "${APT_OPTS[@]}" download -qq "$p" >/dev/null 2>&1) || echo "$p" >>"$STAGE/failed"
done
for p in "${PKGS[@]}"; do
  compgen -G "$DEBS/${p}_*.deb" >/dev/null || { echo "Faltou o pacote principal $p — abortando." >&2; exit 1; }
done
if [[ -s "$STAGE/failed" ]]; then
  echo "    Sem .deb (virtuais ou sem candidato, normalmente inofensivo): $(tr '\n' ' ' <"$STAGE/failed")"
fi

# ---------- índice do repositório local (lido pelo deploy/install.sh) ----------
(cd "$DEBS" && dpkg-scanpackages --multiversion . /dev/null >Packages 2>/dev/null && gzip -9kf Packages)
echo "$ARCH" >"$DEBS/ARCH"
echo "$CODENAME" >"$DEBS/CODENAME"
chmod -R a+rX "$DEBS"

NAME="livesafe-offline-$ARCH.tar.gz"
mkdir -p "$OUT"
tar -czf "$OUT/$NAME" -C "$STAGE" livesafe-monitor
N=$(find "$DEBS" -name '*.deb' | wc -l)
echo
echo "Gerado $OUT/$NAME ($(du -h "$OUT/$NAME" | cut -f1), $N pacotes .deb para $CODENAME/$ARCH)"
echo "No Pi sem internet:  tar -xzf $NAME && sudo ./livesafe-monitor/install.sh"
