#!/usr/bin/env bash
# LiveSafe Monitor — instalador com assistente
#
#   Do GitHub:          curl -fsSL https://raw.githubusercontent.com/aragonxpd154/LiveSafe-Monitor/main/install.sh | sudo bash
#   Do servidor central: curl -fsSL http://<ip-do-central>:8080/instalar.sh | sudo bash
#
# Pergunta se esta máquina é um Pi de abrigo ou o servidor central, o nome do
# local e a senha do painel; baixa o LiveSafe, instala tudo e deixa rodando.
# Sem terminal (automação), use variáveis:
#   LIVESAFE_ROLE=edge|central LIVESAFE_SITE="Pedra Azul" LIVESAFE_PASSWORD=... curl ... | sudo -E bash
set -euo pipefail

# Preenchidos automaticamente quando este script é servido pelo central.
LIVESAFE_SOURCE_DEFAULT=""
LIVESAFE_ROLE_DEFAULT=""
LIVESAFE_CENTRAL_DEFAULT=""

REPO="aragonxpd154/LiveSafe-Monitor"
RELEASE_URL="https://github.com/$REPO/releases/latest/download/livesafe-monitor.tar.gz"
BRANCH_URL="https://codeload.github.com/$REPO/tar.gz/refs/heads/main"
SOURCE="${LIVESAFE_SOURCE:-$LIVESAFE_SOURCE_DEFAULT}"
ROLE="${LIVESAFE_ROLE:-}"
SITE="${LIVESAFE_SITE:-}"
USER_NAME="${LIVESAFE_USER:-admin}"
PASSWORD="${LIVESAFE_PASSWORD:-}"
HW_FLAG=""
[[ "${LIVESAFE_HW_WATCHDOG:-1}" == "0" ]] && HW_FLAG="--sem-watchdog-hw"
LOG=/var/log/livesafe-install.log
TITLE="LiveSafe Monitor — instalador"

die() {
  if [[ $UI -eq 1 ]]; then
    wt --title "Não foi possível instalar" --msgbox "$1\n\nDetalhes em $LOG" 14 72 || true
  fi
  echo "ERRO: $1 (detalhes em $LOG)" >&2
  exit 1
}

if [[ $EUID -ne 0 ]]; then
  echo "Rode como administrador:  curl -fsSL <endereço>/install.sh | sudo bash" >&2
  exit 1
fi
command -v apt-get >/dev/null || {
  echo "Este instalador funciona em Raspberry Pi OS, Debian ou Ubuntu." >&2
  exit 1
}
: >"$LOG"
export DEBIAN_FRONTEND=noninteractive

# Interface: whiptail no terminal (funciona por SSH). Sem terminal, segue só com as variáveis.
UI=0
if [[ -z "${LIVESAFE_NONINTERACTIVE:-}" ]] && { : </dev/tty; } 2>/dev/null; then
  UI=1
  if ! command -v whiptail >/dev/null; then
    echo "Preparando o assistente…"
    HERE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
    if [[ -n "$HERE_DIR" && -f "$HERE_DIR/debs/Packages" && "$(cat "$HERE_DIR/debs/ARCH" 2>/dev/null)" == "$(dpkg --print-architecture)" ]]; then
      # Pacote offline: instala o whiptail do repositório local, sem internet.
      L=$(mktemp /tmp/livesafe-wt.XXXXXX.list)
      echo "deb [trusted=yes] file:$HERE_DIR/debs ./" >"$L"
      chmod -R a+rX "$HERE_DIR/debs"
      A=(-o "Dir::Etc::sourcelist=$L" -o "Dir::Etc::sourceparts=-" -o "APT::Get::List-Cleanup=0")
      { apt-get "${A[@]}" update -qq && apt-get "${A[@]}" install -y -qq --no-install-recommends whiptail; } >>"$LOG" 2>&1 || UI=0
      rm -f "$L"
    else
      { apt-get update -qq && apt-get install -y -qq whiptail; } >>"$LOG" 2>&1 || UI=0
    fi
  fi
fi
wt() { whiptail --backtitle "$TITLE" --ok-button "OK" --cancel-button "Cancelar" --yes-button "Sim" --no-button "Não" "$@" 3>&1 1>/dev/tty 2>&3 </dev/tty; }

EXISTING=0
if [[ -f /var/lib/livesafe/config.json || -f /etc/livesafe/config.json ]]; then EXISTING=1; fi
CURRENT_ROLE=""
if [[ $EXISTING -eq 1 ]]; then
  CURRENT_ROLE=$(grep -o '"role": *"[a-z]*"' /var/lib/livesafe/config.json /etc/livesafe/config.json 2>/dev/null | head -1 | sed 's/.*"\([a-z]*\)"$/\1/' || true)
fi

# ---------- perguntas ----------
if [[ $UI -eq 1 ]]; then
  if [[ $EXISTING -eq 1 ]]; then
    wt --title "Atualizar o LiveSafe" --yesno "O LiveSafe já está instalado nesta máquina.\n\nDeseja atualizar para a versão mais nova? A configuração, os canais e as senhas são mantidos." 12 72 || exit 0
    ROLE="${ROLE:-${CURRENT_ROLE:-edge}}"
  else
    wt --title "Bem-vindo" --msgbox "Este assistente instala o LiveSafe Monitor e deixa tudo pronto para uso.\n\nVai levar de 2 a 10 minutos, conforme a internet. Depois, a configuração da placa de captura ou dos Pis é feita pelo navegador." 13 72 || exit 0
    DEF="${ROLE:-${LIVESAFE_ROLE_DEFAULT:-edge}}"
    ROLE=$(wt --title "O que é esta máquina?" --default-item "$DEF" --menu "Escolha o papel deste equipamento:" 15 78 2 \
      edge "Pi de abrigo: recebe o sinal pela placa HDMI-USB" \
      central "Servidor central: reúne os Pis e redistribui o vídeo") || exit 0
    PROMPT="Nome do local onde esta máquina fica.\nAparece no painel, nas ocorrências e nas traps."
    [[ "$ROLE" == "edge" ]] && PROMPT="Nome do abrigo onde este Pi fica (ex.: Pedra Azul).\nAparece no servidor central, nas ocorrências e nas traps."
    while :; do
      SITE=$(wt --title "Nome do local" --inputbox "$PROMPT" 12 72 "${SITE:-$(hostname)}") || exit 0
      [[ -n "${SITE// /}" ]] && break
      wt --msgbox "Informe um nome." 8 40 || true
    done
    while [[ -z "$PASSWORD" ]]; do
      P1=$(wt --title "Senha do painel" --passwordbox "Crie a senha para entrar no painel (usuário: $USER_NAME).\nMínimo de 6 caracteres." 11 72) || exit 0
      if ((${#P1} < 6)); then
        wt --msgbox "A senha precisa ter pelo menos 6 caracteres." 8 56 || true
        continue
      fi
      P2=$(wt --title "Senha do painel" --passwordbox "Repita a senha." 9 72) || exit 0
      if [[ "$P1" != "$P2" ]]; then
        wt --msgbox "As senhas não conferem. Tente de novo." 8 56 || true
        continue
      fi
      PASSWORD="$P1"
    done
    if grep -qa "Raspberry Pi" /proc/device-tree/model 2>/dev/null && [[ -z "$HW_FLAG" ]]; then
      wt --title "Watchdog de hardware" --yes-button "Ligar" --no-button "Não ligar" --yesno "Ligar o watchdog de hardware do Raspberry Pi?\n\nSe o Pi travar por completo, ele se reinicia sozinho em cerca de 15 s. Recomendado para Pis em abrigos sem ninguém por perto." 13 72 || HW_FLAG="--sem-watchdog-hw"
    fi
  fi
else
  ROLE="${ROLE:-${CURRENT_ROLE:-${LIVESAFE_ROLE_DEFAULT:-}}}"
  [[ "$ROLE" == "edge" || "$ROLE" == "central" ]] || {
    echo "Sem terminal: defina LIVESAFE_ROLE=edge ou LIVESAFE_ROLE=central" >&2
    exit 1
  }
fi

# ---------- instalação ----------
WORK=$(mktemp -d /tmp/livesafe-install.XXXXXX)
trap 'rm -rf "$WORK"' EXIT

fetch() {
  # Pacote: local (rodando de dentro do projeto), central, release do GitHub ou branch main.
  local here
  here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
  if [[ -z "$SOURCE" && -n "$here" && -f "$here/src/index.js" && -f "$here/deploy/install.sh" ]]; then
    PKG_DIR="$here"
    return 0
  fi
  local urls=()
  if [[ -n "$SOURCE" ]]; then urls=("$SOURCE"); else urls=("$RELEASE_URL" "$BRANCH_URL"); fi
  if ! command -v curl >/dev/null || ! command -v tar >/dev/null; then
    apt-get update -qq && apt-get install -y -qq curl ca-certificates tar
  fi
  for u in "${urls[@]}"; do
    echo "Baixando $u"
    if curl -fsSL --retry 3 --connect-timeout 15 "$u" -o "$WORK/pkg.tar.gz"; then
      mkdir -p "$WORK/pkg"
      tar -xzf "$WORK/pkg.tar.gz" -C "$WORK/pkg"
      PKG_DIR=$(dirname "$(find "$WORK/pkg" -maxdepth 3 -path '*/deploy/install.sh' | head -1)")
      PKG_DIR=$(dirname "$PKG_DIR")
      [[ -f "$PKG_DIR/src/index.js" ]] && return 0
    fi
  done
  return 1
}

run_install() {
  echo "==> [2] Baixando o LiveSafe"
  fetch || {
    echo "LIVESAFE_FAIL=Não foi possível baixar o LiveSafe. Confira a internet ou o endereço do central."
    return 1
  }
  LIVESAFE_SITE="$SITE" LIVESAFE_USER="$USER_NAME" LIVESAFE_PASSWORD="$PASSWORD" \
    bash "$PKG_DIR/deploy/install.sh" "$ROLE" $HW_FLAG
}

RESULT="$WORK/result"
if [[ $UI -eq 1 ]]; then
  # Traduz as linhas "==> [NN] texto" do instalador em uma barra de progresso.
  set +e
  run_install 2>&1 | tee -a "$LOG" | tee "$RESULT" | while IFS= read -r line; do
    if [[ "$line" =~ ^==\>\ \[([0-9]+)\]\ (.*)$ ]]; then
      printf 'XXX\n%s\n%s\nXXX\n' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
    fi
  done | whiptail --backtitle "$TITLE" --title "Instalando" --gauge "Preparando…" 9 76 0 >/dev/tty
  STATUS=${PIPESTATUS[0]}
  set -e
else
  set +e
  run_install 2>&1 | tee -a "$LOG" | tee "$RESULT"
  STATUS=${PIPESTATUS[0]}
  set -e
fi

if [[ $STATUS -ne 0 ]] || ! grep -q '^==> \[100\]' "$RESULT"; then
  MSG=$(grep '^LIVESAFE_FAIL=' "$RESULT" | cut -d= -f2-)
  [[ -z "$MSG" ]] && MSG="A instalação parou com erro: $(grep -E 'ERRO|E:|error' "$RESULT" | tail -2 | tr '\n' ' ')"
  die "$MSG"
fi

URL=$(grep '^LIVESAFE_URL=' "$RESULT" | cut -d= -f2-)
GEN=$(grep '^LIVESAFE_GENERATED_PASSWORD=' "$RESULT" | cut -d= -f2- || true)
REBOOT=$(grep -c '^LIVESAFE_NEED_REBOOT=1' "$RESULT" || true)
NOSYS=$(grep -c '^LIVESAFE_NO_SYSTEMD=1' "$RESULT" || true)
[[ $EXISTING -eq 1 ]] && URL="${URL%/setup}"

if [[ $EXISTING -eq 1 ]]; then
  TEXT="O LiveSafe foi atualizado e já está rodando.\n\nPainel: $URL"
elif [[ "$ROLE" == "edge" ]]; then
  TEXT="O LiveSafe está instalado e rodando.\n\nAgora, no navegador do seu computador, abra:\n\n   $URL\n\nEntre com o usuário \"$USER_NAME\" e a senha que você criou. O assistente vai encontrar a placa HDMI-USB e mostrar uma imagem de teste."
  if [[ -n "$LIVESAFE_CENTRAL_DEFAULT" ]]; then
    IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    TEXT="$TEXT\n\nDepois, cadastre este Pi no servidor central ($LIVESAFE_CENTRAL_DEFAULT/setup) com o endereço ${IP:-deste Pi}."
  fi
else
  TEXT="O servidor central está instalado e rodando.\n\nAgora, no navegador do seu computador, abra:\n\n   $URL\n\nEntre com o usuário \"$USER_NAME\" e a senha que você criou, e cadastre os Pis dos abrigos."
fi
if [[ "$NOSYS" != "0" ]]; then
  # Sem systemd (ex.: contêiner): nada foi iniciado automaticamente.
  TEXT="${TEXT//e já está rodando/mas não foi iniciado}"
  TEXT="${TEXT//instalado e rodando/instalado, mas não foi iniciado}"
  TEXT="$TEXT\n\nEste sistema não usa systemd. Inicie com:\n  sudo runuser -u livesafe -- node /opt/livesafe/src/index.js /var/lib/livesafe/config.json"
fi
[[ -n "$GEN" ]] && TEXT="$TEXT\n\nSenha gerada para o painel: $GEN"
[[ "$REBOOT" != "0" ]] && TEXT="$TEXT\n\nReinicie o Pi uma vez (sudo reboot) para ativar o watchdog de hardware."

if [[ $UI -eq 1 ]]; then
  wt --title "Pronto" --msgbox "$TEXT" 19 76 || true
fi
echo
echo -e "$TEXT"
