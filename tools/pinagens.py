#!/usr/bin/env python3
"""Pinagens conferidas dos chips da placa LiveSafe - Marcos Silva dos Santos.

Fonte única das pinagens usadas pelo gerador do esquemático. Cada mapa foi lido
da figura de pinagem do datasheet (onde a numeração não fica embaralhada) e
cruzado com o texto do PDF. Rodar este arquivo grava ref/*_pins.json e repete
todas as checagens; com DATASHEETS=<pasta> ele também cruza com os PDFs.

    python3 tools/pinagens.py
    DATASHEETS=~/datasheets python3 tools/pinagens.py
"""
import json
import os
import re
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(AQUI, '..', 'ref')

SI2183 = {
    1: 'MP_A', 2: 'MP_B', 3: 'GPIO_0', 4: 'DISEQC_CMD', 5: 'DISEQC_IN', 6: 'DISEQC_OUT', 7: 'VDD_VCORE', 8: 'GND',
    9: 'VDD_VIO', 10: 'SCL_HOST', 11: 'SDA_HOST', 12: 'TS_VAL', 13: 'TS_SYNC', 14: 'TS_CLK', 15: 'TS_DATA0/TS_SER',
    16: 'TS_DATA1', 17: 'TS_DATA2', 18: 'TS_DATA3', 19: 'TS_DATA4', 20: 'VDD_VCORE', 21: 'GND', 22: 'VDD_VIO',
    23: 'TS_DATA5', 24: 'TS_DATA6', 25: 'TS_DATA7', 26: 'TS_ERR/GPIO_1', 27: 'GND', 28: 'VDD_VCORE', 29: 'MP_C',
    30: 'MP_D', 31: 'RESETB', 32: 'XTAL_O', 33: 'XTAL_I/CLK_IN', 34: 'ADDR', 35: 'GND', 36: 'VDD_VANA',
    37: 'S_ADC_IP', 38: 'S_ADC_IN', 39: 'S_ADC_QP', 40: 'S_ADC_QN', 41: 'TC_ADC_P', 42: 'TC_ADC_N', 43: 'NC',
    44: 'CLK_IN_OUT', 45: 'SDA_MAST', 46: 'SCL_MAST', 47: 'GND', 48: 'VDD_VCORE', 49: 'GND_PAD',
}

SI2141 = {
    1: 'GPIO2', 2: 'SDA', 3: 'SCL', 4: 'AGC2', 5: 'AGC1', 6: 'GND', 7: 'VDDL', 8: 'GND', 9: 'VDDH', 10: 'LIF_N',
    11: 'LIF_P', 12: 'XOUT', 13: 'XTAL_I', 14: 'XTAL_O', 15: 'VDDH', 16: 'GND', 17: 'VDDH', 18: 'NC', 19: 'RF_REF',
    20: 'RF_IP', 21: 'GND', 22: 'RF_IN', 23: 'ADDR', 24: 'GPIO1', 25: 'GND_PAD',
}

# GS2961A, mapa de esferas da pág. 7 (linhas A..K, colunas 1..10). Sinais
# ativos em nível baixo levam o sufixo _N (SDI_N = /SDI, SDO_N = /SDO).
_GRADE = """
VBG      LF       LB_CONT  VCO_VDD  STAT0    STAT1    IO_VDD       PCLK          DOUT18 DOUT17
A_VDD    PLL_VDD  RSV      VCO_GND  STAT2    STAT3    IO_GND       DOUT19        DOUT16 DOUT15
SDI      A_GND    PLL_VDD  PLL_VDD  STAT4    STAT5    RESET_TRST   DOUT12        DOUT14 DOUT13
SDI_N    A_GND    A_GND    PLL_GND  CORE_GND CORE_VDD SW_EN        JTAG/HOST     IO_GND IO_VDD
EQ_VDD   EQ_GND   A_GND    PLL_GND  CORE_GND CORE_VDD SDOUT_TDO    SDIN_TDI      DOUT10 DOUT11
AGCP     RSV      A_GND    PLL_GND  CORE_GND CORE_VDD CS_TMS       SCLK_TCK      DOUT8  DOUT9
AGCN     A_GND    RC_BYP   CORE_GND CORE_GND CORE_VDD SMPTE_BYPASS DVB_ASI       IO_GND IO_VDD
BUFF_VDD BUFF_GND CORE_GND RSV      TIM_861  XTAL_OUT 20BIT/10BIT  IOPROC_EN/DIS DOUT6  DOUT7
SDO      SDO_EN   RSV      RSV      RSV      XTAL2    IO_GND       DOUT1         DOUT4  DOUT5
SDO_N    STANDBY  RSV      RSV      RSV      XTAL1    IO_VDD       DOUT0         DOUT2  DOUT3
"""
GS2961A = {f'{lin}{col}': nome
           for lin, linha in zip('ABCDEFGHJK', _GRADE.strip().splitlines())
           for col, nome in enumerate(linha.split(), 1)}


def checar():
    assert len(SI2183) == 49 and sorted(SI2183) == list(range(1, 50))
    assert len(SI2141) == 25 and sorted(SI2141) == list(range(1, 26))
    assert len(GS2961A) == 100
    # Tabela 1-1 do GS2961A (págs. 7-13): cada grupo de esferas tem que bater com o mapa.
    grupos = {
        'IO_VDD': 'A7 D10 G10 K7', 'PLL_VDD': 'B2 C3 C4', 'RSV': 'B3 F2 H4 J3 J4 J5 K3 K4 K5',
        'IO_GND': 'B7 D9 G9 J7', 'A_GND': 'C2 D2 D3 E3 F3 G2', 'PLL_GND': 'D4 E4 F4',
        'CORE_GND': 'D5 E5 F5 G4 G5 H3', 'CORE_VDD': 'D6 E6 F6 G6',
    }
    for nome, esferas in grupos.items():
        achadas = sorted(k for k, v in GS2961A.items() if v == nome)
        assert achadas == sorted(esferas.split()), (nome, achadas)
    dout = dict(zip('A9 A10 B8 B9 B10 C8 C9 C10 E9 E10 F9 F10 H9 H10 J8 J9 J10 K8 K9 K10'.split(),
                    [18, 17, 19, 16, 15, 12, 14, 13, 10, 11, 8, 9, 6, 7, 1, 4, 5, 0, 2, 3]))
    for esfera, i in dout.items():
        assert GS2961A[esfera] == f'DOUT{i}', esfera
    # Contagem de alimentação do Si2183 e do Si2141 (figuras de pinagem).
    assert [p for p, n in SI2183.items() if n == 'VDD_VCORE'] == [7, 20, 28, 48]
    assert [p for p, n in SI2183.items() if n == 'VDD_VIO'] == [9, 22]
    assert [p for p, n in SI2141.items() if n == 'VDDH'] == [9, 15, 17]


def cruzar_pdfs(pasta):
    def texto(padrao):
        nomes = [f for f in os.listdir(pasta) if re.search(padrao, f, re.I)]
        if not nomes:
            print(f'  (sem PDF que case com {padrao} em {pasta}; pulando)')
            return None
        out = subprocess.run(['pdftotext', '-layout', os.path.join(pasta, nomes[0]), '-'],
                             capture_output=True, text=True, check=True).stdout
        return re.sub(r'\[(\d)\]', r'\1', out)

    t = texto(r'si2183.*\.pdf$')
    if t:  # as laterais (13-24 e 37-48) saem com número e nome na mesma linha
        for p in list(range(13, 25)) + list(range(37, 49)):
            n = re.escape(SI2183[p])
            assert re.search(rf'(\b{p}\s+{n}|{n}\s+{p}\b)', t), ('Si2183', p, SI2183[p])
        print('  Si2183: 24 pinos laterais conferidos com o texto do PDF')
    t = texto(r'si2141.*\.pdf$')
    if t:
        for p in (7, 8, 9, 10, 11, 12, 19, 20, 21, 22, 23, 24):
            n = re.escape(SI2141[p])
            assert re.search(rf'(\b{p}\s+{n}|{n}\s+{p}\b)', t), ('Si2141', p, SI2141[p])
        print('  Si2141: 12 pinos laterais conferidos com o texto do PDF')


def gravar():
    os.makedirs(REF, exist_ok=True)
    docs = {
        'si2183_pins.json': {
            'part': 'Si2183-B60-GM', 'lcsc': 'C2654249',
            'package': 'QFN-48 7x7 mm, passo 0,5 mm, pad exposto = GND (pino 49)',
            'fonte': 'Skyworks Si2183-B60 Data Short (28/11/2021), pág. 2 "Pin Assignments"',
            'alimentacao': {'VDD_VCORE': '1,14 / 1,20 / 1,30 V', 'VDD_VANA': '3,0 / 3,3 / 3,6 V',
                            'VDD_VIO': '3,0 / 3,3 / 3,6 V'},
            'clock': 'SDK Skyworks (Si2183_L1_API.c): CLK_CLKIO = pino 44, 24 MHz vindo do XOUT do sintonizador',
            'i2c': '0x64-0x67 (7 bits) conforme o nível do pino ADDR; base 0x64 (0xC8 em 8 bits)',
            'pins': {str(k): v for k, v in SI2183.items()},
        },
        'si2141_pins.json': {
            'part': 'Si2141-A10-GM', 'lcsc': 'C430209',
            'package': 'QFN-24 3x3 mm, passo 0,40 mm; pinos 1, 7, 13 e 19 são pads de canto (e1 = 0,45 mm); '
                       'pad exposto 1,70 mm = GND (pino 25)',
            'fonte': 'Skyworks Si2141 Data Short (09/08/2021), pág. 2 "Pin Assignments" e "Package Information"',
            'alimentacao': {'VDDH': '3,3 V', 'VDDL': '1,8 V externo, ou LDO interno a partir de VDDH'},
            'clock': 'cristal de 24 MHz em XTAL_I/XTAL_O; XOUT repassa o clock ao demodulador',
            'i2c': '0x60-0x63 (7 bits) conforme o nível do pino ADDR; base 0x60 (0xC0 em 8 bits)',
            'pins': {str(k): v for k, v in SI2141.items()},
        },
        'gs2961a_pins.json': {
            'part': 'GS2961AIBE3',
            'package': 'LBGA-100 11x11 mm, passo 1,00 mm, esfera 0,50 mm, MSL 3',
            'fonte': 'Semtech GS2961A Data Sheet 54385-2 (set/2012): págs. 7-13, 37, 99 e 101',
            'modo_asi': '20BIT/10BIT=0, SMPTE_BYPASS=0, DVB_ASI=1 e bit AUTO/MAN=0 por GSPI; byte do TS em '
                        'DOUT17..DOUT10 (H..A), DOUT19=WORD_ERR, DOUT18=SYNC_OUT, PCLK=27 MHz',
            'consumo_asi': '1,2 V: 130 mA típ. / 170 mA máx.; 3,3 V: 90 / 95 mA',
            'pins': GS2961A,
        },
    }
    for nome, doc in docs.items():
        with open(os.path.join(REF, nome), 'w', encoding='utf-8') as f:
            json.dump(doc, f, indent=1, ensure_ascii=False)
            f.write('\n')


if __name__ == '__main__':
    checar()
    pasta = os.environ.get('DATASHEETS')
    if pasta:
        cruzar_pdfs(os.path.expanduser(pasta))
    gravar()
    print('Pinagens OK: Si2183 (49), Si2141 (25), GS2961A (100). JSON gravados em ref/.')
    sys.exit(0)
