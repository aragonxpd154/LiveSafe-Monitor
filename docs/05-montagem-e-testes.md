# 05 — Montagem e primeiros testes da placa

> Projeto de **Marcos Silva dos Santos** (MarcosObel). Roteiro para a primeira placa que chega da JLCPCB. Faça na
> ordem: cada etapa só depende das anteriores.

## Antes de ligar

1. Inspeção visual (lupa): pontes de solda nos QFN e no USB2514B, polaridade dos LEDs, do D1 (TVS) e do C1.
2. Multímetro entre cada trilho e o GND, sem energia: `+12V`, `+5V`, `+3V3`, `+1V2`, `+2V5_TC`, `+1V2_TC`,
   `+1V8_TUN`, `ASI_1V2A`. Nenhum pode estar em curto (alguns ohms em `+1V2` é normal por causa dos núcleos).
3. **Sem o CM4 encaixado.**

## Alimentação (sem CM4)

1. Fonte de bancada em 12 V com limite de 300 mA.
2. Medir: 5,0 V (±3 %), 3,3 V (±3 %), 1,2 V, 2,5 V, 1,8 V. Consumo sem CM4: < 250 mA em 12 V.
3. Inverter a polaridade por 1 s: nada pode esquentar e o consumo fica em zero (Q1 bloqueia).
4. Subir para 18 V: os buck continuam regulando. Descer para 8 V: continua ligado; abaixo de ~7 V desliga (divisor do EN).

## CM4 e sistema

1. Encaixar o CM4 (com a placa desligada) e prender com os 4 parafusos M2,5 nos espaçadores de 1,5 mm.
2. Gravar o eMMC (docs/06). Ligar: LED PWR acende, ACT pisca, a rede sobe pelo RJ45 (LEDs do conector).
3. `lsusb`: hub Microchip `0424:2514`, duas FX2LP `04b4:8613`.
4. `i2cdetect -y 1`: `0x64` (Si2183). `i2cdetect -y 10` (ou o barramento do CSI): `0x0f`, `0x2f`, `0x51`.

## Bloco a bloco

| Bloco | Teste | Esperado |
|---|---|---|
| HDMI | ligar um notebook/IRD em 1080p60, `v4l2-ctl --query-dv-timings` | 1920×1080p60; imagem no LiveSafe; áudio no `arecord -l` |
| RF | antena ou gerador ISDB-Tb, `livesafe-rf scan` | canais encontrados, C/N > 20 dB num canal forte |
| ASI | saída ASI de um IRD/encoder, `livesafe-asi status` | `ASI_LOCK` = 1, taxa do TS coerente com a fonte |
| Entradas | fechar contato entre +12V(aux) e IN1 com COM no GND | GPIO6 vai a 0 |
| Relés | `gpioset` em GPIO13/16/17/22 | relé estala, LED amarelo acende, continuidade C–NA |
| RTC | `hwclock -w`, desligar 1 min, `hwclock -r` | hora preservada pela CR1220 |
| Ventoinha | `livesafe-fan test` | PWM varia, tacômetro lê RPM |

## Medidas que voltam para o projeto

- consumo típico e de pico em 12 V (com HDMI e RF ativos);
- temperatura do SoC, do LMR33630 de 5 V e do GS2961A depois de 1 h com a caixa fechada;
- espectro do cristal do Si2141 (24 MHz) e do oscilador de 27 MHz;
- qualidade do CSI-2 (sem erros `unicam` no `dmesg` depois de 24 h em 1080p60).

Anote os resultados no `CHANGELOG.md` e abra *issues* para o que precisar de revisão (rev. B).
