"""Catálogo de componentes da placa LiveSafe - Marcos Silva dos Santos.

Cada componente tem: pinagem (número, nome, tipo elétrico), arrumação dos pinos
no símbolo, footprint, fabricante/código (MPN) e, quando conhecido com certeza,
o código LCSC usado pela montagem da JLCPCB.

Origem das pinagens:
- Si2183, Si2141, GS2961A: tools/pinagens.py (conferidas nos datasheets);
- TC358743XBG: mapa de esferas da Toshiba, igual ao circuito da Antmicro;
- Raspberry Pi CM4: biblioteca oficial da placa CM4IO;
- demais CIs: bibliotecas oficiais do KiCad 7 (mesma numeração dos footprints).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import pinagens  # noqa: E402
import symlib as S  # noqa: E402

REF = os.path.join(HERE, '..', '..', 'ref')
P, I, O, B, PW, PO, NC, OC = ('passive', 'input', 'output', 'bidirectional', 'power_in', 'power_out',
                              'no_connect', 'open_collector')

PARTS = {}   # nome do símbolo -> dict(sym, fp, mpn, lcsc, fab, desc)
SYMS = {}


def reg(sym, fp, mpn='', lcsc='', fab='', desc=''):
    sym.footprint = fp
    if desc:
        sym.desc = desc
    SYMS[sym.name] = sym
    PARTS[sym.name] = dict(fp=fp, mpn=mpn, lcsc=lcsc, fab=fab, desc=desc or sym.desc)
    return sym


def _t(name):
    n = name.upper()
    if n in ('GND', 'VSS', 'AGND', 'GND_PAD', 'EP') or n.endswith('_GND'):
        return PW
    return B


# ----------------------------------------------------------------------------
# Raspberry Pi CM4 (4 unidades)
# ----------------------------------------------------------------------------
def _cm4():
    raw = json.load(open(os.path.join(REF, 'cm4_pins.json')))
    ren = {'+5v_(Input)': '+5V_IN', '+3.3v_(Output)': '+3V3_OUT', '+1.8v_(Output)': '+1V8_OUT',
           'GPIO_VREF(1.8v/3.3v_Input)': 'GPIO_VREF', 'WiFi_nDisable': 'WiFi_nDisable', 'BT_nDisable': 'BT_nDisable'}
    pins = []
    for num, name, et, _u in raw:
        nm = ren.get(name, name)
        nm = nm.replace('Ethernet_Pair', 'ETH_P').replace('Ethernet_', 'ETH_').replace('(3.3v)', '').replace('(1.8v)', '')
        if nm == 'Reserved':
            nm = f'RSVD_{num}'
        et = {'power_in': PW, 'power_out': PO, 'output': O, 'input': I, 'bidirectional': B,
              'open_collector': OC}.get(et, P)
        if nm in ('WiFi_nDisable', 'BT_nDisable'):
            et = I
        pins.append((num, nm, et))
    gp = lambda *n: [f'GPIO{i}' for i in n]
    u1 = {'T': ['+5V_IN', None, 'GPIO_VREF'], 'B': ['GND'],
          'L': ['Global_EN', 'RUN_PG', 'nRPIBOOT', 'nEXTRST', None, 'EEPROM_nWP', 'WiFi_nDisable', 'BT_nDisable',
                None, 'SD_VDD_Override', 'SD_PWR_ON', 'AnalogIP0', 'AnalogIP1', 'RSVD_76'],
          'R': ['+3V3_OUT', '+1V8_OUT', None, 'nPI_LED_PWR', 'PI_nLED_Activity', None, 'SD_CLK', 'SD_CMD',
                'SD_DAT0', 'SD_DAT1', 'SD_DAT2', 'SD_DAT3', 'SD_DAT4', 'SD_DAT5', 'SD_DAT6', 'SD_DAT7']}
    u2 = {'L': gp(2, 3) + [None] + gp(4, 5, 6, 7, 8, 9, 10, 11, 12, 13) + [None, 'ID_SD', 'ID_SC'],
          'R': gp(14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27) + [None, 'SCL0', 'SDA0', 'Camera_GPIO']}
    eth = []
    for i in range(4):
        eth += [f'ETH_P{i}_P', f'ETH_P{i}_N']
    u3 = {'L': eth, 'R': ['ETH_nLED1', 'ETH_nLED2', 'ETH_nLED3', None, 'ETH_SYNC_IN', 'ETH_SYNC_OUT']}
    cam1 = ['CAM1_C_P', 'CAM1_C_N'] + sum([[f'CAM1_D{i}_P', f'CAM1_D{i}_N'] for i in range(4)], [])
    cam0 = ['CAM0_C_P', 'CAM0_C_N'] + sum([[f'CAM0_D{i}_P', f'CAM0_D{i}_N'] for i in range(2)], [])
    hd = lambda k: [f'HDMI{k}_CLK_P', f'HDMI{k}_CLK_N'] + sum([[f'HDMI{k}_TX{i}_P', f'HDMI{k}_TX{i}_N'] for i in range(3)], []) + \
        [f'HDMI{k}_SDA', f'HDMI{k}_SCL', f'HDMI{k}_CEC', f'HDMI{k}_HOTPLUG']
    dsi0 = ['DSI0_C_P', 'DSI0_C_N', 'DSI0_D0_P', 'DSI0_D0_N', 'DSI0_D1_P', 'DSI0_D1_N']
    dsi1 = ['DSI1_C_P', 'DSI1_C_N'] + sum([[f'DSI1_D{i}_P', f'DSI1_D{i}_N'] for i in range(4)], [])
    pcie = ['PCIe_CLK_P', 'PCIe_CLK_N', 'PCIe_TX_P', 'PCIe_TX_N', 'PCIe_RX_P', 'PCIe_RX_N', 'PCIe_nRST', 'PCIe_CLK_nREQ']
    u4 = {'L': cam1 + [None] + ['USB2_P', 'USB2_N', 'USB_OTG_ID'] + [None] + cam0 + [None] + pcie + [None, 'VDAC_COMP',
                                                                                                        'RSVD_104', 'RSVD_106'],
          'R': hd(0) + [None] + hd(1) + [None] + dsi0 + [None] + dsi1}
    s = S.ic('RPi_CM4', pins, None, ref='U', stacked=('GND', '+5V_IN', '+3V3_OUT', '+1V8_OUT'), units=[u1, u2, u3, u4])
    s.unit_names = {1: 'Alimentação e controle', 2: 'GPIO', 3: 'Ethernet', 4: 'Alta velocidade'}
    return reg(s, 'livesafe:Raspberry_Pi_CM4_DF40', 'CM4104032', '', 'Raspberry Pi',
               'Raspberry Pi Compute Module 4 (4 GB RAM, 32 GB eMMC) - encaixe em 2x Hirose DF40C-100DS-0.4V')


# ----------------------------------------------------------------------------
# Vídeo, RF e ASI
# ----------------------------------------------------------------------------
def _tc358743():
    raw = json.load(open(os.path.join(REF, 'tc358743_pins.json')))
    pins = []
    for ball, name, et, _ in raw:
        nm = name.replace('~{RESET}', 'RESETN')
        et = {'power_in': PW, 'output': O, 'input': I, 'bidirectional': B}.get(et, P)
        if nm == 'GND':
            et = PW
        if nm in ('AVDD33', 'AVDD12', 'VDDC2', 'VDD_MIPI'):
            et = PW
        pins.append((ball, nm, et))
    sides = {'T': ['AVDD33', 'AVDD25', 'AVDD12', 'VDDC1', 'VDDC2', 'VDD_MIPI', 'VDDIO1', 'VDDIO2'], 'B': ['GND'],
             'L': ['HDMIC_P', 'HDMIC_N', 'HDMID0_P', 'HDMID0_N', 'HDMID1_P', 'HDMID1_N', 'HDMID2_P', 'HDMID2_N', None,
                   'DDC_SDA', 'DDC_SCL', 'HPDI', 'CEC', None, 'EDID_SDA', 'EDID_SCL', None, 'REFCLK', 'RESETN',
                   'I2C_SDA', 'I2C_SCL', None, 'IR', 'TEST', 'VPGM'],
             'R': ['CSIC_P', 'CSIC_N', 'CSID0_P', 'CSID0_N', 'CSID1_P', 'CSID1_N', 'CSID2_P', 'CSID2_N', 'CSID3_P',
                   'CSID3_N', None, 'INT', 'HPDO', None, 'A_SCK', 'A_WFS', 'A_SD', 'A_OSCK', None, 'REXT', 'BIASDA',
                   'DAOUT', 'PCKIN', 'PFIL']}
    s = S.ic('TC358743XBG', pins, sides, stacked=('GND', 'AVDD33', 'AVDD12', 'VDDC2', 'VDD_MIPI'))
    return reg(s, 'livesafe:Toshiba_P-TFBGA64-0606-0.65', 'TC358743XBG', '', 'Toshiba',
               'Ponte HDMI para MIPI CSI-2 com áudio I2S')


def _si2183():
    pins = []
    for n, nm in pinagens.SI2183.items():
        nm = {'GND_PAD': 'GND'}.get(nm, nm)
        et = PW if nm.startswith('VDD') or nm == 'GND' else (NC if nm == 'NC' else B)
        if nm in ('RESETB', 'SCL_HOST', 'ADDR', 'TC_ADC_P', 'TC_ADC_N'):
            et = I
        if nm.startswith('TS_') and nm != 'TS_ERR/GPIO_1':
            et = O
        pins.append((n, nm, et))
    sides = {'T': ['VDD_VCORE', 'VDD_VANA', 'VDD_VIO'], 'B': ['GND'],
             'L': ['TC_ADC_P', 'TC_ADC_N', None, 'CLK_IN_OUT', 'XTAL_I/CLK_IN', 'XTAL_O', None, 'SDA_HOST',
                   'SCL_HOST', 'ADDR', 'RESETB', None, 'S_ADC_IP', 'S_ADC_IN', 'S_ADC_QP', 'S_ADC_QN', 'NC'],
             'R': ['TS_DATA0/TS_SER', 'TS_DATA1', 'TS_DATA2', 'TS_DATA3', 'TS_DATA4', 'TS_DATA5', 'TS_DATA6',
                   'TS_DATA7', 'TS_CLK', 'TS_SYNC', 'TS_VAL', 'TS_ERR/GPIO_1', None, 'SDA_MAST', 'SCL_MAST', None,
                   'MP_A', 'MP_B', 'MP_C', 'MP_D', 'GPIO_0', None, 'DISEQC_CMD', 'DISEQC_IN', 'DISEQC_OUT']}
    s = S.ic('Si2183-B60', pins, sides, stacked=('GND', 'VDD_VCORE', 'VDD_VIO'))
    return reg(s, 'Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.15x5.15mm', 'Si2183-B60-GM', 'C2654249', 'Skyworks',
               'Demodulador ISDB-T / DVB-T2/C2/S2X, TS paralelo')


def _si2141():
    pins = []
    for n, nm in pinagens.SI2141.items():
        nm = {'GND_PAD': 'GND'}.get(nm, nm)
        et = PW if nm.startswith('VDD') or nm == 'GND' else (NC if nm == 'NC' else B)
        if nm in ('LIF_P', 'LIF_N', 'XOUT'):
            et = O
        if nm.startswith('RF_') or nm in ('SCL', 'ADDR', 'AGC1', 'AGC2', 'XTAL_I'):
            et = I if nm != 'RF_REF' else P
        pins.append((n, nm, et))
    sides = {'T': ['VDDH', 'VDDL'], 'B': ['GND'],
             'L': ['RF_IP', 'RF_IN', 'RF_REF', None, 'XTAL_I', 'XTAL_O', None, 'SDA', 'SCL', 'ADDR', None, 'AGC1', 'AGC2'],
             'R': ['LIF_P', 'LIF_N', None, 'XOUT', None, 'GPIO1', 'GPIO2', 'NC']}
    s = S.ic('Si2141-A10', pins, sides, stacked=('GND', 'VDDH'))
    return reg(s, 'livesafe:Skyworks_QFN-24_3x3mm_P0.4mm_EP1.7mm_CornerPads', 'Si2141-A10-GM', 'C430209', 'Skyworks',
               'Sintonizador de TV digital 42-1002 MHz, saída IF baixa')


def _gs2961a():
    pins = []
    for ball, nm in pinagens.GS2961A.items():
        if nm in ('IO_GND', 'CORE_GND', 'PLL_GND', 'A_GND', 'VCO_GND', 'EQ_GND', 'BUFF_GND') or nm.endswith('VDD'):
            et = PW
        elif nm == 'RSV':
            et = NC
        elif nm.startswith('DOUT') or nm.startswith('STAT') or nm in ('PCLK', 'SDO', 'SDO_N', 'SDOUT_TDO', 'XTAL_OUT'):
            et = O
        elif nm in ('SMPTE_BYPASS', 'DVB_ASI'):
            et = B
        else:
            et = I
        pins.append((ball, nm, et))
    dout = [f'DOUT{i}' for i in range(19, -1, -1)]
    sides = {'T': ['IO_VDD', 'CORE_VDD', 'PLL_VDD', 'VCO_VDD', 'A_VDD', 'EQ_VDD', 'BUFF_VDD'],
             'B': ['IO_GND', 'CORE_GND', 'PLL_GND', 'A_GND', 'VCO_GND', 'EQ_GND', 'BUFF_GND'],
             'L': ['SDI', 'SDI_N', 'AGCP', 'AGCN', None, 'XTAL1', 'XTAL2', 'XTAL_OUT', None, 'VBG', 'LF', 'LB_CONT',
                   None, 'RESET_TRST', 'JTAG/HOST', 'CS_TMS', 'SCLK_TCK', 'SDIN_TDI', 'SDOUT_TDO', None, 'SMPTE_BYPASS',
                   'DVB_ASI', '20BIT/10BIT', 'IOPROC_EN/DIS', 'RC_BYP', 'TIM_861', 'SW_EN', 'STANDBY', 'SDO_EN'],
             'R': dout + ['PCLK', None, 'STAT0', 'STAT1', 'STAT2', 'STAT3', 'STAT4', 'STAT5', None, 'SDO', 'SDO_N',
                          None, 'RSV']}
    s = S.ic('GS2961A', pins, sides, stacked=('IO_VDD', 'CORE_VDD', 'PLL_VDD', 'IO_GND', 'CORE_GND', 'PLL_GND',
                                              'A_GND', 'RSV'))
    return reg(s, 'Package_BGA:BGA-100_11.0x11.0mm_Layout10x10_P1.0mm_Ball0.5mm_Pad0.4mm_NSMD', 'GS2961AIBE3', '',
               'Semtech', 'Receptor SDI 3G/HD/SD com equalizador, reclocker e modo DVB-ASI')


# ----------------------------------------------------------------------------
# USB
# ----------------------------------------------------------------------------
def _fx2lp():
    pins = [(1, 'RDY0/SLRD', I), (2, 'RDY1/SLWR', I), (3, 'AVCC', PW), (4, 'XTALOUT', O), (5, 'XTALIN', I),
            (6, 'AGND', PW), (7, 'AVCC', P), (8, 'D+', B), (9, 'D-', B), (10, 'AGND', P), (11, 'VCC', PW),
            (12, 'GND', PW), (13, 'IFCLK', B), (14, 'RESERVED', I), (15, 'SCL', I), (16, 'SDA', B), (17, 'VCC', P)]
    pins += [(18 + i, f'PB{i}/FD{i}', B) for i in range(8)]
    pins += [(26, 'GND', P), (27, 'VCC', P), (28, 'GND', P), (29, 'CTL0/FLAGA', O), (30, 'CTL1/FLAGB', O),
             (31, 'CTL2/FLAGC', O), (32, 'VCC', P), (33, 'PA0/INT0', B), (34, 'PA1/INT1', B), (35, 'PA2/SLOE', B),
             (36, 'PA3/WU2', B), (37, 'PA4/FIFOADR0', B), (38, 'PA5/FIFOADR1', B), (39, 'PA6/PKTEND', B),
             (40, 'PA7/FLAGD/SLCS', B), (41, 'GND', P), (42, 'RESETN', I), (43, 'VCC', P), (44, 'WAKEUP', I)]
    pins += [(45 + i, f'PD{i}/FD{8 + i}', B) for i in range(8)]
    pins += [(53, 'GND', P), (54, 'CLKOUT', O), (55, 'VCC', P), (56, 'GND', P), (57, 'GND', P)]
    sides = {'T': ['VCC', 'AVCC'], 'B': ['GND', 'AGND'],
             'L': ['D+', 'D-', None, 'XTALIN', 'XTALOUT', None, 'RESETN', 'WAKEUP', 'SCL', 'SDA', 'RESERVED', None,
                   'IFCLK', 'RDY0/SLRD', 'RDY1/SLWR', 'CTL0/FLAGA', 'CTL1/FLAGB', 'CTL2/FLAGC', 'CLKOUT'],
             'R': [f'PB{i}/FD{i}' for i in range(8)] + [None] + ['PA0/INT0', 'PA1/INT1', 'PA2/SLOE', 'PA3/WU2',
                                                                'PA4/FIFOADR0', 'PA5/FIFOADR1', 'PA6/PKTEND',
                                                                'PA7/FLAGD/SLCS'] + [None] + [f'PD{i}/FD{8 + i}' for i in range(8)]}
    s = S.ic('CY7C68013A-56LTX', pins, sides, stacked=('VCC', 'AVCC', 'GND', 'AGND'))
    return reg(s, 'Package_DFN_QFN:QFN-56-1EP_8x8mm_P0.5mm_EP4.5x5.2mm', 'CY7C68013A-56LTXC', '', 'Infineon (Cypress)',
               'EZ-USB FX2LP: USB 2.0 com FIFO escrava de 8 bits')


def _usb2514():
    pins = [(1, 'DN1_DM', B), (2, 'DN1_DP', B), (3, 'DN2_DM', B), (4, 'DN2_DP', B), (5, 'VDDA33', PW),
            (6, 'DN3_DM', B), (7, 'DN3_DP', B), (8, 'DN4_DM', B), (9, 'DN4_DP', B), (10, 'VDDA33', P),
            (11, 'TEST', I), (12, 'PRTPWR1', O), (13, 'OCS_N1', I), (14, 'CRFILT', P), (15, 'VDD33', PW),
            (16, 'PRTPWR2', O), (17, 'OCS_N2', I), (18, 'PRTPWR3', O), (19, 'OCS_N3', I), (20, 'PRTPWR4', O),
            (21, 'OCS_N4', I), (22, 'SDA/NON_REM1', B), (23, 'VDD33', P), (24, 'SCL/CFG_SEL0', B),
            (25, 'HS_IND/CFG_SEL1', B), (26, 'RESET_N', I), (27, 'VBUS_DET', I), (28, 'SUSP_IND/NON_REM0', B),
            (29, 'VDDA33', P), (30, 'UP_DM', B), (31, 'UP_DP', B), (32, 'XTALOUT', O), (33, 'XTALIN', I),
            (34, 'PLLFILT', P), (35, 'RBIAS', P), (36, 'VDDA33', P), (37, 'VSS', PW)]
    sides = {'T': ['VDD33', 'VDDA33'], 'B': ['VSS'],
             'L': ['UP_DP', 'UP_DM', None, 'XTALIN', 'XTALOUT', None, 'RESET_N', 'VBUS_DET', None, 'RBIAS', 'CRFILT',
                   'PLLFILT', 'TEST', None, 'SCL/CFG_SEL0', 'HS_IND/CFG_SEL1', 'SDA/NON_REM1', 'SUSP_IND/NON_REM0'],
             'R': ['DN1_DP', 'DN1_DM', 'DN2_DP', 'DN2_DM', 'DN3_DP', 'DN3_DM', 'DN4_DP', 'DN4_DM', None,
                   'PRTPWR1', 'OCS_N1', 'PRTPWR2', 'OCS_N2', 'PRTPWR3', 'OCS_N3', 'PRTPWR4', 'OCS_N4']}
    s = S.ic('USB2514B', pins, sides, stacked=('VDD33', 'VDDA33'))
    return reg(s, 'Package_DFN_QFN:QFN-36-1EP_6x6mm_P0.5mm_EP3.7x3.7mm', 'USB2514B-I/M2', '', 'Microchip',
               'Hub USB 2.0 de 4 portas')


def _small():
    def mk(name, pins, sides, fp, mpn, lcsc='', fab='', desc='', stacked=(), ref='U'):
        return reg(S.ic(name, pins, sides, stacked=stacked, ref=ref), fp, mpn, lcsc, fab, desc)

    mk('LMR33630ADDA', [(1, 'GND', PW), (2, 'VIN', PW), (3, 'EN', I), (4, 'PG', OC), (5, 'FB', I), (6, 'VCC', PO),
                        (7, 'BOOT', I), (8, 'SW', O), (9, 'GND', P)],
       {'L': ['VIN', 'EN', None, 'VCC'], 'R': ['BOOT', 'SW', None, 'FB', 'PG'], 'B': ['GND']},
       'Package_SO:Texas_HSOP-8-1EP_3.9x4.9mm_P1.27mm_ThermalVias', 'LMR33630ADDAR', '', 'Texas Instruments',
       'Buck síncrono 3,8-36 V / 3 A, 400 kHz, compensação interna', stacked=('GND',))
    for v in ('12', '18', '25'):
        mk(f'TLV733{v}PDBV', [(1, 'IN', PW), (2, 'GND', PW), (3, 'EN', I), (4, 'NC', NC), (5, 'OUT', PO)],
           {'L': ['IN', 'EN'], 'R': ['OUT', 'NC'], 'B': ['GND']}, 'Package_TO_SOT_SMD:SOT-23-5', f'TLV733{v}PDBVR', '',
           'Texas Instruments', f'LDO {v[0]},{v[1]} V / 300 mA')
    mk('TLV62569DBV', [(1, 'EN', I), (2, 'GND', PW), (3, 'SW', O), (4, 'VIN', PW), (5, 'FB', I)],
       {'L': ['VIN', 'EN'], 'R': ['SW', 'FB'], 'B': ['GND']}, 'Package_TO_SOT_SMD:SOT-23-5', 'TLV62569DBVR', '',
       'Texas Instruments', 'Buck síncrono 2,5-5,5 V / 2 A, 1,5 MHz')
    mk('PCF85063ATL', [(1, 'OSCI', I), (2, 'OSCO', O), (3, 'CLKOE', I), (4, 'INT', OC), (5, 'VSS', PW), (6, 'SDA', B),
                       (7, 'SCL', I), (8, 'NC', NC), (9, 'CLKOUT', O), (10, 'VDD', PW), (11, 'VSS', P)],
       {'L': ['OSCI', 'OSCO', None, 'CLKOE'], 'R': ['SDA', 'SCL', 'INT', 'CLKOUT', 'NC'], 'T': ['VDD'], 'B': ['VSS']},
       'Package_DFN_QFN:DFN-10-1EP_2.6x2.6mm_P0.5mm_EP1.3x2.2mm', 'PCF85063ATL/1,118', '', 'NXP', 'Relógio de tempo real I2C',
       stacked=('VSS',))
    mk('ULN2003A', [(i, f'I{i}', I) for i in range(1, 8)] + [(8, 'GND', PW), (9, 'COM', P)] +
       [(17 - i, f'O{i}', OC) for i in range(1, 8)],
       {'L': [f'I{i}' for i in range(1, 8)], 'R': [f'O{i}' for i in range(1, 8)], 'T': ['COM'], 'B': ['GND']},
       'Package_SO:SOIC-16_3.9x9.9mm_P1.27mm', 'ULN2003ADR', '', 'Texas Instruments', 'Driver Darlington de 7 canais')
    mk('LTV-817S', [(1, 'A', P), (2, 'K', P), (3, 'E', P), (4, 'C', P)],
       {'L': ['A', 'K'], 'R': ['C', 'E']}, 'Package_DIP:SMDIP-4_W9.53mm', 'LTV-817S', '', 'Lite-On', 'Optoacoplador',
       ref='U')
    mk('TPD4E05U06DQA', [(1, 'D1+', P), (2, 'D1-', P), (3, 'GND', PW), (4, 'D2+', P), (5, 'D2-', P), (6, 'NC6', NC),
                         (7, 'NC7', NC), (8, 'GND', P), (9, 'NC9', NC), (10, 'NC10', NC)],
       {'L': ['D1+', 'D1-', 'D2+', 'D2-'], 'R': ['NC6', 'NC7', 'NC9', 'NC10'], 'B': ['GND']},
       'Package_SON:USON-10_2.5x1.0mm_P0.5mm', 'TPD4E05U06DQAR', '', 'Texas Instruments',
       'Proteção ESD de 4 vias para HDMI/USB (0,5 pF)', stacked=('GND',))
    mk('USBLC6-2SC6', [(1, 'IO1a', P), (2, 'GND', PW), (3, 'IO2a', P), (4, 'IO2b', P), (5, 'VBUS', P), (6, 'IO1b', P)],
       {'L': ['IO1a', 'IO2a'], 'R': ['IO1b', 'IO2b'], 'T': ['VBUS'], 'B': ['GND']}, 'Package_TO_SOT_SMD:SOT-23-6',
       'USBLC6-2SC6', 'C7519', 'STMicroelectronics', 'Proteção ESD USB 2.0')
    mk('TPS2051CDBV', [(1, 'OUT', PO), (2, 'GND', PW), (3, 'FLT', OC), (4, 'EN', I), (5, 'IN', PW)],
       {'L': ['IN', 'EN'], 'R': ['OUT', 'FLT'], 'B': ['GND']}, 'Package_TO_SOT_SMD:SOT-23-5', 'TPS2051CDBVR', '',
       'Texas Instruments', 'Chave de alimentação USB 0,5 A com limite de corrente')
    mk('FSUSB42MX', [(1, 'VCC', PW), (2, 'SEL', I), (3, 'D+', B), (4, 'D-', B), (5, 'GND', PW), (6, 'HSD1-', B),
                     (7, 'HSD1+', B), (8, 'HSD2-', B), (9, 'HSD2+', B), (10, 'OE_N', I)],
       {'L': ['D+', 'D-', None, 'SEL', 'OE_N'], 'R': ['HSD1+', 'HSD1-', 'HSD2+', 'HSD2-'], 'T': ['VCC'], 'B': ['GND']},
       'Package_SO:MSOP-10_3x3mm_P0.5mm', 'FSUSB42MUX', '', 'onsemi',
       'Chave analógica USB 2.0 1:2 (SEL=0: HSD1, SEL=1: HSD2)')
    mk('EMC2301', [(1, 'SDA', B), (2, 'SCL', I), (3, 'VDD', PW), (4, 'GND', PW), (5, 'PWM', O), (6, 'TACH', I),
                   (7, 'CLK', I), (8, 'ALERT_N', OC)],
       {'L': ['SDA', 'SCL', 'ALERT_N', 'CLK'], 'R': ['PWM', 'TACH'], 'T': ['VDD'], 'B': ['GND']},
       'Package_SO:MSOP-8_3x3mm_P0.65mm', 'EMC2301-1-ACZL-TR', '', 'Microchip', 'Controlador de ventoinha PWM com tacômetro')
    mk('PCA9517D', [(1, 'VCCA', PW), (2, 'SCLA', B), (3, 'SDAA', B), (4, 'GND', PW), (5, 'EN', I), (6, 'SDAB', B),
                    (7, 'SCLB', B), (8, 'VCCB', PW)],
       {'L': ['SDAA', 'SCLA', 'EN'], 'R': ['SDAB', 'SCLB'], 'T': ['VCCA', 'VCCB'], 'B': ['GND']},
       'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm', 'PCA9517D,118', '', 'NXP', 'Repetidor I2C com conversão de nível (DDC 5 V)')
    mk('AO3401A', [(1, 'G', I), (2, 'S', P), (3, 'D', P)], {'L': ['G'], 'R': ['S', None, 'D']},
       'Package_TO_SOT_SMD:SOT-23', 'AO3401A', 'C15127', 'Alpha & Omega', 'MOSFET canal P -30 V / -4 A', ref='Q')
    mk('BAT54C', [(1, 'A1', P), (2, 'A2', P), (3, 'K', P)], {'L': ['A1', 'A2'], 'R': ['K']},
       'Package_TO_SOT_SMD:SOT-23', 'BAT54C,215', '', 'Nexperia', 'Dois diodos Schottky, catodo comum', ref='D')
    mk('OSC_4P', [(1, 'EN', I), (2, 'GND', PW), (3, 'OUT', O), (4, 'VDD', PW)],
       {'L': ['EN'], 'R': ['OUT'], 'T': ['VDD'], 'B': ['GND']}, 'Oscillator:Oscillator_SMD_Abracon_ASE-4Pin_3.2x2.5mm',
       'ASE-27.000MHZ-LC-T', '', 'Abracon', 'Oscilador 27 MHz 3,3 V', ref='Y')
    mk('XTAL_4P', [(1, 'X1', P), (2, 'GND', P), (3, 'X2', P), (4, 'GND', P)],
       {'L': ['X1'], 'R': ['X2'], 'B': ['GND']}, 'Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm', '', '', '',
       'Cristal SMD 3225', stacked=('GND',), ref='Y')
    mk('XTAL_2P', [(1, 'X1', P), (2, 'X2', P)], {'L': ['X1'], 'R': ['X2']},
       'Crystal:Crystal_SMD_2012-2Pin_2.0x1.2mm', 'FC-12M 32.7680KA-A3', '', 'Epson', 'Cristal 32,768 kHz', ref='Y')


# ----------------------------------------------------------------------------
# Conectores, chaves, relés
# ----------------------------------------------------------------------------
def _connectors():
    def mk(name, pins, sides, fp, mpn, lcsc='', fab='', desc='', stacked=(), ref='J'):
        return reg(S.ic(name, pins, sides, stacked=stacked, ref=ref), fp, mpn, lcsc, fab, desc)

    mk('HDMI_A_IN', [(1, 'D2+', P), (2, 'D2S', P), (3, 'D2-', P), (4, 'D1+', P), (5, 'D1S', P), (6, 'D1-', P),
                     (7, 'D0+', P), (8, 'D0S', P), (9, 'D0-', P), (10, 'CK+', P), (11, 'CKS', P), (12, 'CK-', P),
                     (13, 'CEC', P), (14, 'UTILITY', P), (15, 'SCL', P), (16, 'SDA', P), (17, 'DDC_GND', P),
                     (18, '+5V', P), (19, 'HPD', P), ('SH', 'SHIELD', P)],
       {'R': ['CK+', 'CK-', 'D0+', 'D0-', 'D1+', 'D1-', 'D2+', 'D2-', None, 'SCL', 'SDA', 'CEC', 'HPD', 'UTILITY', '+5V'],
        'B': ['CKS', 'D0S', 'D1S', 'D2S', 'DDC_GND', 'SHIELD']},
       'Connector_HDMI:HDMI_A_Molex_208658-1001_Horizontal', '2086581001', '', 'Molex', 'Receptáculo HDMI tipo A')
    jk = [(1, 'MXCT3', P), (2, 'MX3-', P), (3, 'MX3+', P), (4, 'MX2+', P), (5, 'MX2-', P), (6, 'MXCT2', P),
          (7, 'MXCT4', P), (8, 'MX4+', P), (9, 'MX4-', P), (10, 'MX1-', P), (11, 'MX1+', P), (12, 'MXCT1', P),
          (13, 'LED2-', P), (14, 'LED2+', P), (15, 'LED1-', P), (16, 'LED1+', P), ('SH', 'SHIELD', P)]
    mk('RJ45_JK0654219NL', jk, {'L': ['MX1+', 'MX1-', 'MXCT1', 'MX2+', 'MX2-', 'MXCT2', 'MX3+', 'MX3-', 'MXCT3', 'MX4+',
                                      'MX4-', 'MXCT4'],
                                'R': ['LED1+', 'LED1-', 'LED2+', 'LED2-'], 'B': ['SHIELD']},
       'Connector_RJ:RJ45_Pulse_JK0654219NL_Horizontal', 'JK0654219NL', '', 'Pulse',
       'RJ45 com magnéticos 10/100/1000BASE-T e LEDs')
    mk('BNC_75R', [(1, 'IN', P), (2, 'SHIELD', P)], {'R': ['IN'], 'B': ['SHIELD']},
       'Connector_Coaxial:BNC_Amphenol_B6252HB-NPP3G-50_Horizontal', 'B6252HB-NPP3G-75', '', 'Amphenol RF',
       'BNC fêmea 75 Ohm, 90 graus, para placa (12G)')
    mk('USB_MICRO_V', [(1, 'VBUS', P), (2, 'D-', P), (3, 'D+', P), (4, 'ID', P), (5, 'GND', P), (6, 'SHIELD', P)],
       {'R': ['VBUS', 'D+', 'D-', 'ID'], 'B': ['GND', 'SHIELD']},
       'Connector_USB:USB_Micro-B_Wuerth_614105150721_Vertical', '614105150721', '', 'Wurth',
       'Micro-USB vertical (porta interna de serviço: rpiboot / gravar eMMC)')
    mk('USB_A_HOST', [(1, 'VBUS', P), (2, 'D-', P), (3, 'D+', P), (4, 'GND', P), (5, 'SHIELD', P)],
       {'R': ['VBUS', 'D+', 'D-'], 'B': ['GND', 'SHIELD']}, 'Connector_USB:USB_A_Molex_67643_Horizontal',
       '67643-0910', '', 'Molex', 'USB-A fêmea (serviço / pendrive)')
    mk('TERM_2P_508', [(1, '1', P), (2, '2', P)], {'R': ['1', '2']},
       'Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_2-G-5,08_1x02_P5.08mm_Horizontal', 'MSTBA 2,5/2-G-5,08', '',
       'Phoenix Contact', 'Borne plugável 2 vias 5,08 mm (alimentação)')
    mk('TERM_10P_381', [(i, str(i), P) for i in range(1, 11)], {'R': [str(i) for i in range(1, 11)]},
       'Connector_Phoenix_MC:PhoenixContact_MC_1,5_10-G-3.81_1x10_P3.81mm_Horizontal', 'MC 1,5/10-G-3,81', '',
       'Phoenix Contact', 'Borne plugável 10 vias 3,81 mm (alarmes)')
    mk('TERM_6P_381', [(i, str(i), P) for i in range(1, 7)], {'R': [str(i) for i in range(1, 7)]},
       'Connector_Phoenix_MC:PhoenixContact_MC_1,5_6-G-3.81_1x06_P3.81mm_Horizontal', 'MC 1,5/6-G-3,81', '',
       'Phoenix Contact', 'Borne plugável 6 vias 3,81 mm (relés)')
    mk('TERM_12P_381', [(i, str(i), P) for i in range(1, 13)], {'R': [str(i) for i in range(1, 13)]},
       'Connector_Phoenix_MC:PhoenixContact_MC_1,5_12-G-3.81_1x12_P3.81mm_Horizontal', 'MC 1,5/12-G-3,81', '',
       'Phoenix Contact', 'Borne plugável 12 vias 3,81 mm (relés)')
    mk('HDR_1x03', [(1, '1', P), (2, '2', P), (3, '3', P)], {'R': ['1', '2', '3']},
       'Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical', 'PZ254V-11-03P', '', '',
       'Barra de pinos 1x3 (console serial)')
    mk('FAN_4P', [(1, 'GND', P), (2, '+12V', P), (3, 'TACH', P), (4, 'PWM', P)],
       {'R': ['+12V', 'TACH', 'PWM', 'GND']}, 'Connector_Molex:Molex_KK-254_AE-6410-04A_1x04_P2.54mm_Vertical',
       '22-27-2041', '', 'Molex', 'Conector de ventoinha 4 fios (PWM)')
    mk('G5V-1', [(1, 'NC', P), (2, 'COIL+', P), (5, 'COM', P), (6, 'COM', P), (9, 'COIL-', P), (10, 'NO', P)],
       {'L': ['COIL+', 'COIL-'], 'R': ['COM', 'NO', 'NC']}, 'Relay_THT:Relay_SPDT_Omron_G5V-1', 'G5V-1 DC5', '',
       'Omron', 'Relé de sinal SPDT, bobina 5 V', stacked=('COM',), ref='K')
    mk('SW_SPDT', [(1, 'A', P), (2, 'C', P), (3, 'B', P)], {'L': ['C'], 'R': ['A', 'B']},
       'Button_Switch_SMD:SW_SPDT_PCM12', 'PCM12SMTR', '', 'C&K', 'Chave deslizante SPDT', ref='SW')
    mk('SW_PUSH', [(1, '1', P), (2, '2', P)], {'L': ['1'], 'R': ['2']}, 'Button_Switch_SMD:SW_SPST_TL3342',
       'TL3342F160QG', '', 'E-Switch', 'Botão tátil', ref='SW')
    mk('BAT_CR1220', [(1, '+', P), (2, '-', P)], {'T': ['+'], 'B': ['-']},
       'Battery:BatteryHolder_Keystone_3000_1x12mm', '3000', '', 'Keystone', 'Suporte de bateria CR1220', ref='BT')


def build():
    if SYMS:
        return SYMS
    _cm4()
    _tc358743()
    _si2183()
    _si2141()
    _gs2961a()
    _fx2lp()
    _usb2514()
    _small()
    _connectors()
    smd = lambda s: s
    for size in ('0402', '0603', '0805', '1206'):
        met = {'0402': '1005', '0603': '1608', '0805': '2012', '1206': '3216'}[size]
        reg(S.resistor(f'R_{size}', f'Resistor_SMD:R_{size}_{met}Metric'), f'Resistor_SMD:R_{size}_{met}Metric',
            desc=f'Resistor {size}')
        reg(S.capacitor(f'C_{size}', f'Capacitor_SMD:C_{size}_{met}Metric'), f'Capacitor_SMD:C_{size}_{met}Metric',
            desc=f'Capacitor cerâmico {size}')
    reg(S.capacitor('C_1210', 'Capacitor_SMD:C_1210_3225Metric'), 'Capacitor_SMD:C_1210_3225Metric',
        desc='Capacitor cerâmico 1210')
    reg(S.capacitor('CP_8x10', 'Capacitor_SMD:CP_Elec_8x10', polar=True), 'Capacitor_SMD:CP_Elec_8x10',
        desc='Capacitor eletrolítico SMD 8x10 mm')
    reg(S.ferrite('FB_0603'), 'Inductor_SMD:L_0603_1608Metric', desc='Ferrite 0603')
    reg(S.ferrite('FB_0805'), 'Inductor_SMD:L_0805_2012Metric', desc='Ferrite 0805')
    reg(S.inductor('L_SRP7028'), 'Inductor_SMD:L_Bourns_SRP7028A_7.3x6.6mm', desc='Indutor de potência 7x7 mm')
    reg(S.inductor('L_0806'), 'Inductor_SMD:L_0805_2012Metric', desc='Indutor 2,2 uH 0805 (2 A)')
    reg(S.inductor('L_0402'), 'Inductor_SMD:L_0402_1005Metric', desc='Indutor 0402 (casamento de impedância)')
    reg(S.diode('D_SOD123'), 'Diode_SMD:D_SOD-123', desc='Diodo SOD-123')
    reg(S.diode('DZ_SOD123', kind='Z'), 'Diode_SMD:D_SOD-123', desc='Zener SOD-123')
    reg(S.diode('TVS_SMB', kind='Z'), 'Diode_SMD:D_SMB', desc='TVS unidirecional SMB 600 W')
    reg(S.diode('TVS_0402', kind='TVS'), 'Diode_SMD:D_0402_1005Metric', desc='ESD 0402 de baixa capacitância')
    reg(S.diode('LED_0603', kind='LED'), 'LED_SMD:LED_0603_1608Metric', desc='LED 0603')
    reg(S.testpoint(), 'TestPoint:TestPoint_Pad_D1.0mm', desc='Ponto de teste')
    reg(S.mounting_hole(), 'MountingHole:MountingHole_3.2mm_M3_Pad_Via', desc='Furo M3 aterrado')
    reg(S.mounting_hole('MH_CM4', 'MountingHole:MountingHole_2.7mm_M2.5_Pad_Via'),
        'MountingHole:MountingHole_2.7mm_M2.5_Pad_Via', desc='Furo M2,5 de fixação do CM4')
    reg(S.fuse('PTC_1812'), 'Fuse:Fuse_1812_4532Metric', desc='Fusível rearmável 1812')
    for name in ('GND', '+12V', '+5V', '+3V3', 'CM4_3V3'):
        SYMS[name] = S.power_sym(name, gnd=(name == 'GND'))
    SYMS['PWR_FLAG'] = S.pwr_flag()
    return SYMS


if __name__ == '__main__':
    syms = build()
    print(len(syms), 'símbolos')
    for k in ('RPi_CM4', 'GS2961A', 'TC358743XBG', 'Si2183-B60', 'Si2141-A10', 'CY7C68013A-56LTX', 'USB2514B'):
        s = syms[k]
        print(k, len(s.pins), 'pinos', s.nunits, 'unidade(s)', [tuple(round(v, 1) for v in s.bbox[u]) for u in s.bbox])
