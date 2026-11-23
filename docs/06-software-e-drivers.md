# 06 — Software: Linux, drivers e o LiveSafe na placa

> Projeto de **Marcos Silva dos Santos** (MarcosObel). Este documento diz o que o sistema precisa para usar cada
> bloco da placa. O instalador do [LiveSafe Monitor](https://github.com/aragonxpd154/LiveSafe-Monitor) cuida da
> parte comum (Node.js, ffmpeg, serviço systemd, watchdogs); os itens abaixo são os específicos desta placa.

## Sistema

Raspberry Pi OS Lite 64 bits (Bookworm) gravado no eMMC do CM4:

1. Chave **GRAVAR** na posição de gravação e micro-USB interno ligado ao PC.
2. No PC: `sudo apt install rpiboot` (ou compilar o `usbboot`) e rodar `sudo rpiboot` — o eMMC aparece como pendrive.
3. Gravar com o Raspberry Pi Imager; voltar a chave para **OPERAÇÃO** e ligar a placa pela fonte de 12 V.

## `/boot/firmware/config.txt`

```ini
# USB do CM4 como host (hub USB2514B)
dtoverlay=dwc2,dr_mode=host
# HDMI -> CSI-2 (TC358743 no CAM1, 4 vias) e áudio I2S
dtoverlay=tc358743,4lane=1
dtoverlay=tc358743-audio
# I2C1 (Si2183/Si2141) e SPI0 (GS2961A)
dtparam=i2c_arm=on
dtparam=spi=on
# RTC no I2C0 do conector da câmera
dtoverlay=i2c-rtc,pcf85063a,i2c_csi_dsi
# watchdog de hardware (usado pelo LiveSafe)
dtparam=watchdog=on
```

## Cada bloco

| Bloco | Como aparece no Linux | O que o LiveSafe usa |
|---|---|---|
| HDMI (TC358743) | `/dev/video0` (driver `tc358743` + `unicam`), placa de som `tc358743` | `v4l2-ctl --set-edid` na partida, depois a mesma entrada V4L2/ALSA que já existe para captura USB |
| RF ISDB-Tb | I2C1 + FX2LP #1 (USB `04b4:8613` antes do firmware) | serviço `livesafe-rf`: carrega o firmware da FX2LP, liga e sintoniza o Si2183/Si2141, entrega o TS ao ffmpeg por um pipe e publica C/N, BER e travamento |
| ASI (GS2961A) | SPI0 + FX2LP #2 | serviço `livesafe-asi`: configura o GS2961A em modo manual DVB-ASI por SPI e lê os bytes do TS pela FX2LP #2 |
| Alarmes | GPIO (libgpiod) | entradas viram eventos; relés seguem os alarmes do canal (configurável) |
| RTC | `/dev/rtc0` | hora certa mesmo sem rede |
| Ventoinha | EMC2301 no I2C0 | `livesafe-fan` ajusta o PWM pela temperatura do SoC |

### Firmware das FX2LP

As duas FX2LP não têm EEPROM: a cada partida o Linux carrega o firmware na RAM delas (`fxload` ou `libusb`), em
modo *slave FIFO* de 8 bits, IFCLK externo, EP2 de entrada:

| | FX2LP #1 (RF) | FX2LP #2 (ASI) |
|---|---|---|
| IFCLK | `TS_CLK` do Si2183 (ajustar o TS para clock contínuo de 5 a 48 MHz) | `PCLK` de 27 MHz do GS2961A |
| SLWR | `TS_VAL` (ativo em 1) | `SYNC_OUT` (ativo em 0: só grava bytes que não são preenchimento K28.5) |
| Dados | `TS_DATA[7:0]` | `DOUT17..10` |
| Extras | `TS_SYNC` em PA0, `TS_ERR` em PA1 | `WORD_ERR` em PA0 |

As duas aparecem com o mesmo VID/PID; o software separa pela porta do hub (porta 1 = RF, porta 2 = ASI).

### Si2183 e Si2141

O controle segue o **SDK oficial da Skyworks** (`swks-mss/video_si21xx_superset`, Apache-2.0), que também traz o
*patch* de firmware do Si2183-B60. Pontos fixados pela placa:

- clock: `START_CLK` em modo `CLK_CLKIO` (pino 44), `POWER_UP` com 24 MHz;
- I2C: demodulador em `0x64`, sintonizador em `0x60` atrás do I2C mestre do demodulador;
- AGC: `DD_EXT_AGC_TER` com `AGC_2_MODE = MP_A`; no Si2141, `CONFIG_PINS` com `AGC1 = DTV_AGC`;
- TS: modo paralelo; para a FX2LP, clock contínuo (sem *gap*) acima de 5 MHz.

### GS2961A

1. Soltar o reset (GPIO5), esperar 1 ms.
2. GSPI (SPI modo 0, até 6,6 MHz): zerar o bit `AUTO/MAN` para passar ao modo manual; os pinos `DVB_ASI = 1` e
   `SMPTE_BYPASS = 0` já vêm por resistor.
3. `STAT3` (GPIO7) indica travamento no sinal ASI.
