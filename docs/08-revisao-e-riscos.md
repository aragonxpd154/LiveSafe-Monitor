# 08 — Revisão, riscos e próximos passos

> Projeto de **Marcos Silva dos Santos** (MarcosObel). Esta é a revisão **1.0**, gerada por código e ainda não
> fabricada. A lista abaixo é o que precisa de atenção antes de pagar um lote, em ordem de risco.

## Riscos técnicos

| # | Ponto | Risco | O que fazer antes de fabricar |
|---|---|---|---|
| 1 | **Rede de entrada de RF do Si2141** (`RF_IP`, `RF_IN`, `RF_REF`) | o circuito de aplicação só está no datasheet completo, sob NDA; uma ligação errada reduz a sensibilidade | pedir o *Si2141 Data Sheet* e o *AN* de layout à Skyworks (ou a um distribuidor) e conferir as posições alternativas da folha 6 |
| 2 | **Pares diferenciais** (HDMI, CSI-2, USB, Ethernet) | o roteamento automático não acopla os pares nem iguala comprimentos | abrir a placa no KiCad e refazer os pares com o roteador de par diferencial (≈ 1–2 h); conferir as larguras na calculadora da JLCPCB |
| 3 | **Footprints próprios** (TC358743, Si2141) | medidas de pad deduzidas do desenho resumido | imprimir 1:1 e conferir com a peça real; no Si2141, conferir L, b, L1 e b1 no desenho completo |
| 4 | **Rotações na montagem JLCPCB** | a biblioteca da JLCPCB usa outra orientação em alguns encapsulamentos | conferir peça a peça na pré-visualização da montagem |
| 5 | **Estoque** do Si2183-B60, Si2141-A10, GS2961A, TC358743XBG | peças de distribuição limitada; o TC358743 e o indutor SRP7028A-6R8M não têm estoque na LCSC | reservar antes de pagar a placa; usar a *Global Sourcing* da JLCPCB ou enviar como consignado (`pecas-fora-da-jlcpcb.csv`) |
| 6 | **Térmica** | CM4, LMR33630 de 5 V e GS2961A dentro de caixa fechada | medir no protótipo de bancada; a ventoinha (J10) e o EMC2301 estão previstos |
| 7 | **Trilhas no L3 (plano de 3,3 V)** | o roteador de reparo pode usar o L3 para pequenos saltos; cada trilha abre uma fenda no plano | conferir no KiCad (camada In2.Cu) que nenhuma fenda corta o caminho de retorno de um par diferencial; a faixa do 5 V é proibida para trilhas |
| 8 | **Centro do TC358743** | 5 bolas de GND do centro sem via própria (ligadas às vizinhas no L1) | aceitável para o núcleo de 1,2 V; conferir na revisão térmica e de retorno |
| 9 | **Firmware das FX2LP e serviços `livesafe-rf` / `livesafe-asi`** | ainda não escritos | desenvolver no protótipo de bancada (docs/07) com TBS 5520SE e um adaptador ASI |

## Revisão recomendada

1. **Revisão por um projetista de hardware** experiente em CM4 e vídeo (HDMI/CSI-2), com o esquemático em PDF e o
   projeto KiCad: alimentação, ESD, pares diferenciais, planos e retorno de corrente.
2. **Lote pequeno** (5 placas, montagem parcial) para a rodada de testes do docs/05.
3. Ajustes da rev. B registrados no `CHANGELOG.md`.

## Escolhas feitas nesta revisão

- **BNC 75 Ω no RF** em vez de conector F: footprint conferido na biblioteca do KiCad e o mesmo conector nas
  duas entradas. Cabo de antena com F usa um adaptador F/BNC.
- **Entradas com comum** (borne de 6 vias) e **relés num borne de 12 vias**, para caber no painel de 100 mm.
- **Micro-USB interno** para gravar o eMMC (uso só em manutenção, com a tampa aberta).
- **Sem furos de fixação**: a placa corre nos trilhos da caixa Hammond 1455N1601; só o CM4 é parafusado.
- **Plano de terra único** (sem separar terra analógico e digital), com o GS2961A e o RF em regiões próprias.
