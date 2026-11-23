#!/usr/bin/env python3
"""Diagrama de blocos da placa LiveSafe (SVG/PNG/PDF) - Marcos Silva dos Santos.

Mesmo estilo visual do diagrama do Computador 8 Bits: caixas arredondadas,
cor por função e setas com o nome da interface.
"""
import os
import sys

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'docs', 'imagens')
plt.rcParams['font.family'] = ['Inter', 'DejaVu Sans']

AZUL, VERDE, LARANJA, CINZA, ROXO, VERMELHO, AMARELO = (
    '#2b6cb0', '#2f855a', '#c05621', '#4a5568', '#6b46c1', '#c53030', '#b7791f')


def bloco(ax, x, y, w, h, titulo, sub, cor, fs=11):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.02,rounding_size=0.15',
                                fc=cor + '22', ec=cor, lw=2))
    ax.text(x + w / 2, y + h * 0.66, titulo, ha='center', va='center', fontsize=fs, weight='bold', color='#1a202c')
    ax.text(x + w / 2, y + h * 0.30, sub, ha='center', va='center', fontsize=7.5, color='#2d3748', linespacing=1.35)


def seta(ax, p1, p2, cor, txt='', dupla=False, lado='cima', ls='-'):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle='<|-|>' if dupla else '-|>', mutation_scale=12, lw=1.8,
                                 color=cor, linestyle=ls, shrinkA=2, shrinkB=2))
    if txt:
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        if p1[1] == p2[1]:
            ax.text(mx, my + (0.09 if lado == 'cima' else -0.09), txt, ha='center',
                    va='bottom' if lado == 'cima' else 'top', fontsize=7, color=cor)
        else:
            ax.text(mx + 0.08, my, txt, ha='left', va='center', fontsize=7, color=cor)


def main():
    fig, ax = plt.subplots(figsize=(14, 10))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 10)
    ax.axis('off')
    ax.text(7, 9.72, 'Placa LiveSafe v1.0 - Diagrama de blocos', ha='center', fontsize=17, weight='bold')
    ax.text(7, 9.4, 'Autor: Marcos Silva dos Santos (MarcosObel) - monitoração de sinal de TV e rádio', ha='center',
            fontsize=9.5, color='#4a5568')

    # Coração: CM4
    bloco(ax, 6.55, 3.65, 2.9, 2.8, 'Raspberry Pi CM4',
          'BCM2711, 4 GB, eMMC\n2x Hirose DF40 (200 pinos)\nLinux + LiveSafe Monitor\n\nanálise, HLS, SNMP, web', ROXO, 13)

    # Entradas de sinal (esquerda)
    W, H = 3.2, 1.15
    bloco(ax, 0.3, 7.6, W, H, 'Entrada HDMI', 'conector HDMI tipo A\nTPD8S009 (ESD) + PCA9517 (DDC)', LARANJA)
    bloco(ax, 0.3, 5.95, W, H, 'Ponte HDMI → CSI-2', 'Toshiba TC358743XBG\n1080p60, áudio I2S', LARANJA)
    bloco(ax, 0.3, 4.3, W, H, 'Sintonizador UHF', 'Skyworks Si2141\nBNC 75 Ω, proteção ESD', AZUL)
    bloco(ax, 0.3, 2.65, W, H, 'Demodulador ISDB-Tb', 'Skyworks Si2183-B60\nC/N, BER por camada', AZUL)
    bloco(ax, 0.3, 1.0, W, H, 'Entrada ASI', 'BNC 75 Ω\nSemtech GS2961A (eq. + reclock)', VERDE)

    seta(ax, (1.9, 7.6), (1.9, 7.1), LARANJA, 'TMDS')
    seta(ax, (3.5, 6.52), (6.55, 5.95), LARANJA)
    ax.text(4.9, 6.42, 'CSI-2 (4 vias) + áudio I2S', fontsize=7, color=LARANJA, ha='center', rotation=-10.5)
    seta(ax, (1.9, 4.3), (1.9, 3.8), AZUL, 'IF baixa (diferencial)')

    # Pontes TS -> USB, alinhadas com as fontes
    bloco(ax, 4.05, 2.75, 2.15, 0.95, 'FX2LP #1', 'TS do Si2183 → USB', AZUL, 10)
    bloco(ax, 4.05, 1.1, 2.15, 0.95, 'FX2LP #2', 'bytes ASI → USB', VERDE, 10)
    seta(ax, (3.5, 3.22), (4.05, 3.22), AZUL)
    ax.text(3.77, 3.32, 'TS', fontsize=7, color=AZUL, ha='center')
    seta(ax, (3.5, 1.57), (4.05, 1.57), VERDE)
    ax.text(3.77, 1.67, 'ASI', fontsize=7, color=VERDE, ha='center')

    bloco(ax, 6.55, 1.5, 2.9, 1.0, 'Hub USB 2.0', 'Microchip USB2514B\n+ chave FSUSB42 (gravar eMMC)', CINZA, 10)
    seta(ax, (6.2, 3.1), (6.55, 2.35), CINZA)
    seta(ax, (6.2, 1.6), (6.55, 1.8), CINZA)
    seta(ax, (8.0, 2.5), (8.0, 3.65), CINZA, 'USB 2.0')

    # Saídas e serviços (direita)
    X = 10.5
    bloco(ax, X, 7.6, W, H, 'Ethernet Gigabit', 'RJ45 com magnéticos\nHLS, painel web, SNMP', CINZA)
    bloco(ax, X, 5.95, W, H, 'Alarmes (GPI/GPO)', '4 entradas optoacopladas\n4 relés NA/NF para a remota', VERMELHO)
    bloco(ax, X, 4.3, W, H, 'Serviço', 'USB-A, micro-USB interno\nLEDs, botões, RTC, ventoinha', CINZA)
    bloco(ax, X, 2.65, W, H, 'Controle', 'I2C: Si2183/Si2141, TC358743\nSPI: GS2961A', AZUL)
    bloco(ax, X, 1.0, W, H, 'Alimentação 12 V', 'proteção (inversão, surto, PTC)\n12→5 V AP64351; 3,3 / 2,5 / 1,2 V', AMARELO)

    seta(ax, (9.45, 6.2), (X, 8.0), CINZA, dupla=True)
    ax.text(9.85, 7.35, '1000BASE-T', fontsize=7, color=CINZA, ha='center', rotation=58)
    seta(ax, (9.45, 5.6), (X, 6.5), VERMELHO, dupla=True)
    ax.text(10.0, 6.25, 'GPIO', fontsize=7, color=VERMELHO, ha='center', rotation=30)
    seta(ax, (9.45, 4.87), (X, 4.87), CINZA, dupla=True)
    ax.text(9.97, 4.97, 'USB, GPIO', fontsize=7, color=CINZA, ha='center')
    seta(ax, (9.45, 4.1), (X, 3.3), AZUL, dupla=True)
    ax.text(9.95, 3.95, 'I2C / SPI', fontsize=7, color=AZUL, ha='center', rotation=-37)
    seta(ax, (X + W / 2, 2.15), (X + W / 2, 2.65), AMARELO)
    ax.text(X + W / 2 + 0.1, 2.4, 'trilhos para toda a placa', fontsize=7, color=AMARELO, va='center')

    ax.text(7, 0.25, 'Todo o vídeo sai pela rede em HLS (HTTP/TCP) — sem UDP no enlace com o servidor central.',
            ha='center', fontsize=8.5, color=ROXO)

    os.makedirs(OUT, exist_ok=True)
    for ext in ('png', 'svg', 'pdf'):
        fig.savefig(os.path.join(OUT, f'diagrama-blocos.{ext}'), dpi=110, bbox_inches='tight', facecolor='white')
    print('diagrama de blocos gerado em', os.path.abspath(OUT))


if __name__ == '__main__':
    main()
