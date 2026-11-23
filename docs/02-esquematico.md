# 02 — Esquemático

> Projeto de **Marcos Silva dos Santos** (MarcosObel). O esquema elétrico completo em PDF está em
> [`hardware/esquema-eletrico-completo.pdf`](../hardware/esquema-eletrico-completo.pdf); os arquivos do KiCad 7
> ficam em [`hardware/kicad/livesafe-placa/`](../hardware/kicad/livesafe-placa).

O esquemático é **gerado por código** (`tools/gerador-kicad/designs.py`), como no Computador 8 Bits: cada pino
de cada componente é ligado a uma rede com nome. Depois de desenhar as folhas, o gerador exporta a netlist pelo
próprio KiCad e compara rede por rede com o `designs.py`; se uma ligação mudar, a geração para com erro.

## As folhas

| Folha | Conteúdo |
|---|---|
| 1 — Índice | blocos, trilhos de alimentação e barramentos do CM4 |
| 2 — Alimentação 12 V | entrada com PTC 2 A, TVS SMBJ18A e P-MOSFET contra inversão; LMR33630 para 5 V e 3,3 V; TLV62569 para 1,2 V |
| 3 — Raspberry Pi CM4 | módulo (4 unidades no símbolo), desacoplamento, RESET, chave GRAVAR, pull-ups do I2C0 |
| 4 — Ethernet | RJ45 com magnéticos (Pulse JK0654219NL) e LEDs; o PHY está dentro do CM4 |
| 5 — Entrada HDMI | TC358743XBG, ESD TPD4E05U06, PCA9517 (DDC 5 V), LDOs de 2,5 V e 1,2 V, oscilador de 27 MHz |
| 6 — RF ISDB-Tb | BNC 75 Ω, Si2141 (sintonizador) e Si2183-B60 (demodulador), TS paralelo com resistores de série |
| 7 — Entrada ASI | BNC 75 Ω, GS2961A com o circuito típico da Semtech, LDO do PLL, TS de 8 bits com resistores de série |
| 8 — USB | FSUSB42 (chave de serviço), micro-USB interno, hub USB2514B, USB-A com TPS2051, 2× FX2LP |
| 9 — Alarmes e painel | 4 entradas optoacopladas, 4 relés SPDT com ULN2003A, LEDs, RTC PCF85063A com CR1220, ventoinha (EMC2301), console |

## Convenções

- Rótulos **globais** em todos os sinais: o nome da rede é o mesmo em qualquer folha.
- `+12V_IN` entrada bruta; `+12V` depois das proteções; `+5V`, `+3V3`, `+1V2` trilhos principais.
- `CM4_3V3` é a saída de 3,3 V do próprio módulo, usada como referência dos GPIO (`GPIO_VREF`) e nos LEDs.
- Sufixo `_N` = ativo em nível baixo. `(NM)` no valor = posição **não montada** (opção de projeto).
- Cada símbolo traz MPN, fabricante e, quando conhecido, o código LCSC (campos ocultos, usados na lista de materiais).

## Endereços e GPIO

| Barramento | Dispositivos |
|---|---|
| I2C0 (GPIO44/45, CSI) | TC358743 `0x0F`, RTC PCF85063A `0x51`, EMC2301 `0x2F` |
| I2C1 (GPIO2/3) | Si2183 `0x64`; o Si2141 `0x60` fica atrás do I2C mestre do Si2183 |
| SPI0 (GPIO8–11) | GS2961A (GSPI) |
| I2S (GPIO18–20) | áudio do HDMI (TC358743 é o mestre) |

| GPIO | Função | GPIO | Função |
|---|---|---|---|
| 4 | reset do Si2183 (`RF_RESET_N`) | 5 | reset do GS2961A |
| 6, 12, 25, 24 | entradas GPI1–4 (0 = ativa) | 13, 16, 17, 22 | relés GPO1–4 (1 = ligado) |
| 23 / 27 | LED OK / LED ALARME | 7 | `ASI_LOCK` (STAT3 do GS2961A) |
| 14 / 15 | console serial | 21 | `USB_RST_N` (reinicia hub e FX2LP) |
| 26 | interrupção do TC358743 | 2/3, 8–11, 18–20 | barramentos acima |

## Escolhas que dependem de confirmação

O esquemático deixa posições alternativas (marcadas `NM`) onde o datasheet público não fecha a questão:

| Ponto | Montado por padrão | Alternativa sem montar | Como confirmar |
|---|---|---|---|
| Entrada de RF do Si2141 | antena → 1 nF → `RF_IP`; `RF_IN` e `RF_REF` com 1 nF ao terra | antena direto no `RF_IN`; `RF_REF` direto ao terra | datasheet completo (Skyworks, sob NDA) ou a placa Si2183-B-EVB |
| LIF do Si2141 → Si2183 | 0 Ω (ligação direta) | trocar por capacitores de acoplamento | mesma fonte |
| AGC | `MP_A` → `AGC1` (padrão do SDK) | `MP_D` → `AGC2`, RC no AGC | testar na bancada; o software escolhe o pino |
| Clock do Si2183 | `XOUT` do Si2141 → pino 44 (`CLK_IN_OUT`) | `XOUT` → pino 33 | padrão do SDK Skyworks (24 MHz, CLK_CLKIO) |
| Cristal do Si2141 | sem capacitores externos (trim interno `XO_CAP`) | 8,2 pF nos dois lados | medir a frequência no protótipo |
| HPD do HDMI | comandado pelo `HPDO` do TC358743 (1 kΩ) | fixo em 5 V (como a Antmicro) | — |
| Reset do TC358743 | RC (10 kΩ + 100 nF) | também pelo `Camera_GPIO` do CM4 | — |

## Como regenerar

```bash
cd tools/gerador-kicad
/usr/bin/python3 gerar_tudo.py --so-esquema   # biblioteca, folhas, netlist conferida e PDF
python3 designs.py                            # lista os pinos sem conexão de cada CI, para revisão
```
