# Changelog — LiveSafe

## Placa LiveSafe

### 1.0 (2026-11-23) — primeira revisão, não fabricada

- Arquitetura: Raspberry Pi CM4 + TC358743 (HDMI → CSI-2) + Si2141/Si2183-B60 (ISDB-Tb) + GS2961A (ASI) + 2× FX2LP + hub USB2514B.
- Pinagens do Si2183, Si2141 e GS2961A conferidas nos datasheets (`tools/pinagens.py`).
- Esquemático hierárquico de 9 folhas gerado por código, netlist conferida pelo KiCad.
- PCB 160 × 100 mm, 4 camadas JLC04161H-7628, planos de GND e alimentação, roteamento automático
  (Freerouting + roteador próprio `completar.py`); **DRC limpo: 0 erros, 0 ligações pendentes**.
- Planta revista para o roteamento: fileira de resistores do TS sob o Si2183, corredores livres, faixa livre em
  volta dos CIs de passo fino, cristal da FX2LP #1 à esquerda, 5 bolas de GND do centro do TC358743 ligadas no L1.
- Arquivos JLCPCB: Gerber, furação, BOM com código LCSC em todas as linhas, CPL, STEP, PDFs de conferência e
  `pecas-fora-da-jlcpcb.csv` (conectores de furo, TC358743 e indutor de 6,8 µH via Global Sourcing, CM4, bateria).
- Trocas por estoque na LCSC: fusível 2 A/24 V (SMD1812P200TF/24), ferrites BLM21AG102SN1D, 33 µF TDK 1206,
  16 pF FH 0402, LED amarelo 19-217/Y5C-AM1N1VY, 47 nF CL05B473KO5NNNC, cristal FC-12M 32.7680KA-A3.
- Pendências antes da produção: ver `docs/08-revisao-e-riscos.md`.

## Software

- **5.0.1 / 5.0.0 (2026-11-02)** — reescrita: Pi de borda + servidor central, streaming HLS, instalador e
  assistente no navegador. Detalhes no histórico do README.
