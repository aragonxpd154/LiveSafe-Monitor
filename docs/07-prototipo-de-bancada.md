# 07 — Protótipo de bancada (módulos prontos)

> Projeto de **Marcos Silva dos Santos** (MarcosObel). Antes de fabricar a placa, monte o mesmo sistema com
> módulos comprados prontos. Isso valida o software (drivers, LiveSafe, alarmes) e mede consumo e temperatura,
> sem depender da PCB.

## Kit

| Bloco da placa | Equivalente pronto | Observação |
|---|---|---|
| CM4 + base | Raspberry Pi CM4 (4 GB, eMMC) + **CM4IO Board** oficial | mesmo SoC, mesmo conector CAM1 |
| HDMI → CSI-2 (TC358743) | placa **Geekworm C790** ou **Auvidea B101/B102** | mesmo chip e mesmo driver `tc358743`; o B102 tem 4 vias |
| RF ISDB-Tb (Si2141 + Si2183) | sintonizador **TBS 5520SE** (USB) | mesma dupla de chips; usa o driver da TBS ou o `coax` em espaço de usuário |
| ASI (GS2961A + FX2LP) | adaptador ASI→USB comercial (ex.: **DekTec DTU-245**) | só para validar o caminho do TS no LiveSafe |
| Alarmes | placa de relés de 4 canais 5 V + módulo optoacoplado de 4 canais | ligados aos mesmos GPIO da tabela do docs/02 |
| RTC | módulo **PCF85063** ou DS3231 no I2C | |
| Fonte | 12 V / 2,5 A + conversor 12→5 V 3 A | o CM4IO já aceita 12 V direto |

## Sequência de testes

1. **Sistema**: gravar o eMMC, instalar o LiveSafe com o instalador (`install.sh`).
2. **HDMI**: `v4l2-ctl --list-devices`, ligar um receptor de satélite/IRD na entrada e ver a imagem no painel do LiveSafe.
3. **RF**: TBS 5520SE na USB, sintonizar um canal local de ISDB-Tb, conferir C/N e BER.
4. **Alarmes**: forçar congelamento/silêncio e ver os relés mudarem; fechar uma entrada e ver o evento.
5. **Medidas**: consumo na entrada de 12 V (típico e pico), temperatura do SoC com a caixa fechada, tempo de
   recuperação depois de tirar a energia.

Os números medidos aqui substituem as estimativas do orçamento de potência (docs/01) antes da fabricação.
