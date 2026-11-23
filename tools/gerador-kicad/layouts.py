"""Planta da placa LiveSafe v1.0 (160 x 100 mm) - Marcos Silva dos Santos.

Origem no canto superior esquerdo, x para a direita, y para baixo.
  x = 0    painel traseiro: USB-A, HDMI, RJ45, BNC RF, BNC ASI
  x = 160  painel frontal:  12 V, entradas, relés, LEDs
O CM4 fica no meio (rotação 90): o conector 101-200 (CSI, USB) em cima e o
1-100 (Ethernet, GPIO, 5 V) embaixo, ambos em x = 62..82. Embaixo do módulo
não vai componente, só trilhas e vias.

EDGE:   conectores de painel -> (lado 'R' traseiro / 'F' frontal, centro em y).
        A face de encaixe (FACE, no sistema do footprint) é virada para fora.
FIXED:  centro do pátio (courtyard) e rotação dos demais componentes principais.
REGIONS: área onde os passivos de cada grupo do designs.py são encaixados,
        o mais perto possível do pino que atendem.
"""
W, H = 160.0, 100.0

# direção da face de encaixe no footprint original
FACE = {
    'Connector_HDMI:HDMI_A_Molex_208658-1001_Horizontal': '+x',
    'Connector_RJ:RJ45_Pulse_JK0654219NL_Horizontal': '+x',
    'Connector_USB:USB_A_Molex_67643_Horizontal': '+y',
    'Connector_Coaxial:BNC_Amphenol_B6252HB-NPP3G-50_Horizontal': '-y',
    'Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_2-G-5,08_1x02_P5.08mm_Horizontal': '+y',
    'Connector_Phoenix_MC:PhoenixContact_MC_1,5_6-G-3.81_1x06_P3.81mm_Horizontal': '+y',
    'Connector_Phoenix_MC:PhoenixContact_MC_1,5_12-G-3.81_1x12_P3.81mm_Horizontal': '+y',
}
# quanto o pátio passa da borda (a face do conector fica rente ao painel)
EDGE = {
    'J7': ('R', 8.9, 0.6), 'J3': ('R', 28.2, 0.6), 'J2': ('R', 48.0, 0.3),
    'J4': ('R', 67.2, 0.9), 'J5': ('R', 86.3, 0.9),
    'J1': ('F', 7.4, 0.5), 'J8': ('F', 28.0, 0.5), 'J9': ('F', 66.0, 0.5),
}

FIXED = {
    # módulo (origem do footprint, não o centro)
    'U1': ('origin', 93.5, 56.5, 90),
    # HDMI -> CSI
    'J3_esd': None,
    'U5': (17.6, 23.8, 0), 'U6': (17.6, 28.2, 0), 'U7': (17.6, 33.6, 0),
    'U9': (29.5, 28.5, 0), 'U8': (38.6, 41.0, 90), 'Y1': (38.0, 22.0, 0), 'U10': (38.0, 34.0, 90),
    'U11': (38.0, 29.0, 90),
    # USB (faixa de cima, à esquerda)
    'U20': (21.0, 4.0, 0), 'U21': (22.5, 13.0, 90),
    'U19': (45.0, 10.0, 0), 'Y4': (37.5, 6.0, 0), 'U17': (59.0, 15.5, 0), 'U18': (52.5, 10.0, 90),
    'J6': (55.0, 4.0, 0),
    # alimentação (faixa de cima, à direita)
    'F1': (141.0, 3.2, 0), 'D1': (141.0, 9.0, 0), 'Q1': (133.5, 5.0, 0), 'D2': (133.5, 11.0, 0),
    'C1': (125.0, 7.0, 0),
    'U2': (86.0, 9.0, 90), 'L1': (76.0, 6.5, 0),
    'U3': (111.0, 9.0, 90), 'L2': (101.0, 6.5, 0),
    'U4': (92.5, 93.5, 0),
    # RF
    'U12': (45.0, 67.0, 0), 'Y2': (44.5, 73.5, 0), 'U13': (50.5, 63.5, 0),
    'U14': (57.5, 71.5, 0),
    # ASI
    'U15': (48.5, 89.5, 0), 'Y3': (39.8, 97.2, 0), 'U16': (58.5, 97.2, 0), 'TP1': (39.5, 80.0, 0),
    # pontes FX2LP
    'U22': (77.0, 71.5, 0), 'Y5': (70.6, 71.0, 90),  # cristal à esquerda: a borda de baixo é do TS
    'U23': (75.0, 91.5, 0), 'Y6': (83.5, 96.5, 0),
    # alarmes e painel
    'U24': (131.0, 19.0, 0), 'U25': (131.0, 25.5, 0), 'U26': (131.0, 32.0, 0), 'U27': (131.0, 38.5, 0),
    'K1': (135.5, 51.0, 0), 'K2': (135.5, 64.5, 0), 'K3': (135.5, 78.0, 0), 'K4': (135.5, 91.4, 0),
    'U28': (121.0, 66.0, 0),
    'U29': (104.0, 79.0, 0), 'Y7': (104.0, 82.6, 0), 'D17': (108.5, 82.6, 0), 'BT1': (112.0, 92.3, 0),
    'U30': (104.0, 70.0, 0), 'J10': (104.0, 64.0, 0),
    'J11': (101.5, 24.0, 0), 'SW1': (110.5, 23.5, 0), 'SW2': (110.5, 31.0, 0),
}
FIXED = {k: v for k, v in FIXED.items() if v}

# Folga extra (mm) em volta de cada peça de alguns grupos, para abrir canais de roteamento nas regiões
# mais densas (barramentos de TS entre o demodulador / GS2961A e as FX2LP).
SPREAD = {
    'Bytes do TS (resistores de série)': 0.15,
    'Sintonizador Si2141': 0.2,
}

# Faixa livre (mm) em volta dos CIs de passo fino: os passivos ficam perto, mas deixam um corredor para a
# saída das trilhas dos pinos (QFN de 0,4/0,5 mm e BGA de 0,65 mm).
HALO = {'U12': 0.9, 'U14': 0.75, 'U9': 0.6, 'U15': 0.5, 'U22': 0.5, 'U23': 0.5}

# Resistores de série do TS do demodulador: uma fileira logo abaixo do Si2183 (os pinos do TS estão na borda de
# baixo do QFN), na ordem dos pinos, perto da fonte como pede a terminação série. Cada um em pé (90°).
_TS1 = ['R58', 'R57', 'R56', 'R48', 'R49', 'R50', 'R51', 'R52', 'R53', 'R54', 'R55', 'R59']
TS1_ROW = {r: (54.4 + 1.2 * k, 78.6, 90) for k, r in enumerate(_TS1)}

REGIONS = {
    'Entrada e proteção': (112, 0.6, 147, 17.5),
    'Buck 12 V para 5V': (68, 0.6, 94, 18.5),
    'Buck 12 V para 3V3': (94, 0.6, 118, 18.5),
    'Buck 5 V para 1,2 V (núcleos)': (86, 87, 99, 99.4),
    'Módulo': (42, 20, 97, 60),
    'Desacoplamento do CM4': (70, 61, 98, 66),
    'Reset, gravação e I2C0': (98, 19, 122, 40),
    'RJ45 com magnéticos': (34.5, 38, 42, 60),
    'Conector e proteção': (14, 19, 22, 44),
    'DDC, HPD e detecção de 5 V': (20, 30, 41.4, 47.5),
    'Ponte TC358743XBG': (21, 19, 41.4, 40),
    'Alimentação da ponte': (21, 18.5, 41.4, 46),
    'Relógio de 27 MHz': (32.5, 18.0, 41.4, 27.5),
    'Entrada de antena': (36.5, 60, 42, 76),
    'Sintonizador Si2141': (38, 60, 53, 79),
    'Ligações sintonizador - demodulador': (44, 61, 62, 80),
    'Demodulador Si2183-B60': (50, 61, 67, 81),
    'TS paralelo (resistores de série)': (63, 61, 72, 82),
    'Entrada BNC 75 Ohm': (36.5, 77, 43, 95),
    'Receptor GS2961A': (38, 79, 59, 99.4),
    'Alimentação do GS2961A': (38, 78, 66, 99.4),
    'Bytes do TS (resistores de série)': (59, 79, 69, 99.4),
    'Chave USB e porta de serviço (interna)': (46, 0.6, 66, 19.5),
    'Hub USB2514B': (28, 0.6, 58, 19.5),
    'Reset do USB': (28, 0.6, 66, 19.5),
    'Porta USB-A': (17, 0.6, 28, 18),
    'Ponte FX2LP #1 (TS do demodulador)': (68, 61, 90, 85),
    'Ponte FX2LP #2 (bytes ASI)': (66, 82, 90, 99.4),
    'Entradas optoacopladas': (118, 14, 147, 46),
    'Relés': (112, 44, 147, 99.4),
    'LEDs do painel': (147, 93, 159.4, 99.4),
    'Relógio de tempo real': (98, 76, 118, 99.4),
    'Ventoinha': (98, 60, 114, 78),
    'Console e fixação': (98, 19, 108, 30),
}

KEEPOUT_PARTS = [(41.6, 20.4, 97.4, 60.6),   # embaixo do CM4
                 (53.4, 75.5, 68.5, 77.6),   # corredor do TS entre o Si2183 e a fileira de resistores
                 (72.5, 75.9, 81.5, 78.2)]   # corredor do TS embaixo da FX2LP #1

# Bolas de GND do centro do TC358743 que não ganham via própria: ligam na bola vizinha pelo F.Cu. Isso abre
# espaço no B.Cu, no meio do BGA, para as alimentações internas (VDDMIPI, AVDD33, VDDC2) se encontrarem.
BGA_TIES = {'U9': {'C5': 'C4', 'D4': 'C4', 'D5': 'D6', 'E4': 'E3', 'E6': 'E5'},
            'U9+': [('D4', 'D5'), ('E4', 'E5')]}

# LEDs do painel encostados na borda frontal (atrás de guias de luz)
FRONT_LEDS = {'D15': (157.4, 93.4), 'D16': (157.4, 97.4), 'D13': (154.4, 93.4), 'D14': (154.4, 97.4)}

# Plano de 5 V no In2 (o resto do In2 é 3,3 V): buck de 5 V e pinos de 5 V do CM4. Fica só na faixa de cima
# e no centro para o 3,3 V continuar inteiro em volta (passa por baixo do CM4).
PLANE_5V = [(66, 0.5), (96, 0.5), (96, 62), (66, 62)]

FIXED.update(TS1_ROW)
