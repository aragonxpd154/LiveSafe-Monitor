# 04 — Fabricação e montagem na JLCPCB

> Projeto de **Marcos Silva dos Santos** (MarcosObel). Todos os arquivos ficam em
> [`hardware/fabricacao/livesafe-placa/`](../hardware/fabricacao/livesafe-placa).

## Arquivos

| Arquivo | Para que serve |
|---|---|
| `livesafe-placa-gerber.zip` | Gerber das 4 camadas de cobre, máscara, pasta, serigrafia, contorno e furação (PTH e NPTH) |
| `bom-jlcpcb.csv` | lista de materiais no formato da montagem JLCPCB, **com o código LCSC de cada linha** |
| `pecas-fora-da-jlcpcb.csv` | o que não entra na montagem automática: conectores de furo, CM4, bateria e as peças sem estoque na LCSC |
| `cpl-jlcpcb.csv` | posição e rotação de cada componente (Designator, Mid X, Mid Y, Layer, Rotation) |
| `lista-de-materiais.csv` | lista completa, com fabricante, MPN e as posições `NM` |
| `livesafe-placa.step` | modelo 3D mecânico (FreeCAD, Fusion, KiCad) |
| `montagem-topo.pdf`, `camadas.pdf`, `mapa-de-furacao-*.pdf` | conferência visual |
| `relatorio-drc.txt` | resultado do DRC do KiCad |

## Pedido da placa (PCB)

| Opção no site | Valor |
|---|---|
| Layers | **4** |
| Dimensions | 160 × 100 mm |
| PCB Thickness | 1,6 mm |
| Impedance Control | **Yes** — empilhamento **JLC04161H-7628** |
| Material | FR-4 TG155 |
| Via Covering | Epoxy Filled & Capped (recomendado pelo BGA de 0,65 mm) ou Tented |
| Min via hole / diameter | 0,2 mm / 0,45 mm |
| Surface Finish | ENIG (recomendado para BGA e QFN de passo fino) |
| Outer / Inner copper | 1 oz / 0,5 oz |
| Remove Order Number | Specify a location (há um campo `JLCJLCJLCJLC` na serigrafia de baixo) |

### Empilhamento e impedâncias

| Camada | Uso |
|---|---|
| L1 (F.Cu) | sinais, pares diferenciais, componentes |
| L2 (In1.Cu) | **GND contínuo** |
| L3 (In2.Cu) | 3,3 V (maior parte) e 5 V (área do CM4 e do buck de 5 V) |
| L4 (B.Cu) | sinais e GND preenchido |

| Classe | Largura / espaço usados | Alvo | Redes |
|---|---|---|---|
| Dif100 | 0,18 / 0,12 mm | 100 Ω diferencial | HDMI, CSI-2, Ethernet |
| Dif90_USB | 0,2 / 0,12 mm | 90 Ω diferencial | USB |
| RF75 | 0,16 / 0,15 mm | 75 Ω (microfita) | antena, entrada ASI |
| Potência | 0,5 / 0,15 mm | — | 12 V, 5 V, chaveamento dos buck |
| Default | 0,127 / 0,1 mm | — | demais sinais (dentro da capacidade 4 camadas da JLCPCB: 0,09 / 0,09 mm) |

> Antes de pedir, confira as larguras na **calculadora de impedância da JLCPCB** para o JLC04161H-7628 (a
> conta acima usa as fórmulas do IPC-2141) e ajuste a classe no `pcbgen.py` se precisar.

## Montagem (PCBA)

1. Em *PCB Assembly*, escolha **Standard**, lado **Top**.
2. Envie `bom-jlcpcb.csv` e `cpl-jlcpcb.csv`. Todas as linhas têm o código LCSC, conferido em 23/11/2026
   (tabela em `tools/gerador-kicad/lcsc.py`). Confira estoque e preço no dia do pedido; peças marcadas
   *Extended* têm taxa de carregamento.
3. O que não está na BOM da JLCPCB está em `pecas-fora-da-jlcpcb.csv`:
   - **conectores de furo** (bornes Phoenix, RJ45, BNC, micro-USB, USB-A, ventoinha) — solda manual ou montagem
     *THT* da JLCPCB, se o conector estiver na biblioteca dela;
   - **TC358743XBG** e o indutor **SRP7028A-6R8M** — sem estoque na LCSC: use a *Global Sourcing* da JLCPCB
     (compra na Digi-Key/Mouser) ou envie como peça consignada;
   - **CM4** e **bateria CR1220** — à mão, depois.
4. **Confira as rotações na pré-visualização** — a JLCPCB usa a orientação dos footprints dela, que em alguns
   encapsulamentos (SOT-23, QFN, BGA, conectores) difere da biblioteca do KiCad.
5. Os dois conectores do CM4 aparecem na BOM como **CN1/CN2 — Hirose DF40C-100DS-0.4V(51)**. O CM4 é encaixado
   depois, à mão.
6. Os relés G5V-1 e o HDMI (Molex 208658) têm código LCSC e vão na montagem da JLCPCB.

### Atenção a peças críticas

| Peça | Por quê |
|---|---|
| Si2183-B60, Si2141-A10 | distribuição limitada; confirme estoque (LCSC C2654249 e C430209) antes de pagar a placa |
| GS2961AIBE3 | BGA de 1 mm, MSL 3 — pedir com secagem (*baking*) |
| TC358743XBG | BGA de 0,65 mm — exige ENIG e via preenchida sob o chip |
| CY7C68013A-56LTXC | conferir se é a versão **LTXC** (QFN-56 8×8) |
