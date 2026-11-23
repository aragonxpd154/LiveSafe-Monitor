"""Placa LiveSafe v1.0 descrita como código - Marcos Silva dos Santos (MarcosObel).

Cada componente tem cada pino ligado a uma rede com nome. As folhas do
esquemático seguem os blocos do diagrama. Pinos não citados ficam sem conexão
(marcados com X no esquemático) e aparecem na listagem de revisão
(python3 designs.py).

Convenções de nomes de rede:
  +12V_IN  entrada bruta     +12V  depois da proteção     +5V, +3V3, +1V2  trilhos
  CM4_3V3  saída de 3,3 V do próprio CM4 (referência dos GPIO)
  *_N      sinal ativo em nível baixo
"""
import parts
import lcsc as LCSC_

GROUPS_ORDER = []


class Comp:
    def __init__(self, ref, sym, value, pins, sheet, group, mpn='', lcsc='', fab='', dnp=False, fp=None, note=''):
        self.ref, self.sym, self.value, self.pins = ref, sym, value, pins
        self.sheet, self.group, self.dnp, self.note = sheet, group, dnp, note
        info = parts.PARTS[sym]
        self.fp = fp or info['fp']
        self.mpn = mpn or info['mpn']
        self.lcsc = lcsc if lcsc is not None else info['lcsc']
        if not lcsc:
            self.lcsc = info['lcsc'] if not mpn else ''
        self.fab = fab or info['fab']
        size = sym.split('_')[-1]
        if sym.startswith('R_') and not self.mpn and (value, size) in LCSC_.RES:
            self.mpn, self.lcsc = LCSC_.RES[(value, size)]
            self.fab = next((f for k, f in LCSC_.FAB.items() if self.mpn.startswith(k)), '')
        if not self.lcsc:
            self.lcsc = LCSC_.LCSC.get(self.mpn, '')


class Sheet:
    def __init__(self, key, title, desc, notes=()):
        self.key, self.title, self.desc, self.notes = key, title, desc, list(notes)
        self.groups = []  # (titulo, [refs])


class Board:
    title = 'Placa LiveSafe'
    rev = '1.0'

    def __init__(self):
        self.sheets = []
        self.comps = {}
        self.cur = None
        self.grp = None
        self.count = {}

    # --- organização ---
    def sheet(self, key, title, desc, notes=()):
        self.cur = Sheet(key, title, desc, notes)
        self.sheets.append(self.cur)
        return self.cur

    def group(self, title):
        self.grp = (title, [])
        self.cur.groups.append(self.grp)

    def _add(self, c):
        assert c.ref not in self.comps, f'referência repetida {c.ref}'
        self.comps[c.ref] = c
        self.grp[1].append(c.ref)
        return c

    RESERVED = {'U1', 'Q1'} | {f'J{i}' for i in range(1, 13)}

    def nextref(self, prefix):
        while True:
            self.count[prefix] = self.count.get(prefix, 0) + 1
            ref = f'{prefix}{self.count[prefix]}'
            if ref not in self.comps and ref not in self.RESERVED:
                return ref

    # --- componentes ---
    def part(self, sym, value, nets, ref=None, **kw):
        """nets: {nome_do_pino ou '#numero': rede}. Nome repetido liga todos os pinos com esse nome."""
        s = parts.SYMS[sym]
        pins = {}
        for key, net in nets.items():
            if key.startswith('#'):
                pins[key[1:]] = net
                continue
            nums = [p.num for p in s.pins if p.name == key]
            assert nums, f'{sym}: pino {key} não existe'
            for n in nums:
                pins[n] = net
        for p in s.pins:
            pins.setdefault(p.num, None)
        ref = ref or self.nextref(s.ref)
        return self._add(Comp(ref, sym, value, pins, self.cur.key, self.grp[0], **kw))

    def two(self, sym, value, a, b, prefix, **kw):
        return self._add(Comp(self.nextref(prefix), sym, value, {'1': a, '2': b}, self.cur.key, self.grp[0], **kw))

    def R(self, value, a, b, size='0402', **kw):
        return self.two(f'R_{size}', value, a, b, 'R', **kw)

    def C(self, value, a, b='GND', size='0402', **kw):
        return self.two(f'C_{size}' if size != 'CP' else 'CP_8x10', value, a, b, 'C', **kw)

    def FB(self, value, a, b, size='0603', **kw):
        return self.two(f'FB_{size}', value, a, b, 'FB', **kw)

    def L(self, sym, value, a, b, **kw):
        return self.two(sym, value, a, b, 'L', **kw)

    def D(self, sym, value, k, a, **kw):
        return self.two(sym, value, k, a, 'D', **kw)

    def decouple(self, net, values, size='0402'):
        for v in values:
            sz = size
            if v in ('4.7uF', '10uF') and size == '0402':
                sz = '0603'
            if v in ('22uF', '47uF') and size in ('0402', '0603'):
                sz = '0805' if v == '22uF' else '1206'
            self.C(v, net, 'GND', sz, mpn=CAPS.get((v, sz), ''))


CAPS = {
    ('100nF', '0402'): 'CL05B104KO5NNNC', ('10nF', '0402'): 'CL05B103KB5NNNC', ('1uF', '0402'): 'CL05A105KA5NQNC',
    ('470pF', '0402'): 'CL05B471KB5NNNC', ('47pF', '0402'): 'CL05C470JB5NNNC', ('4.7uF', '0603'): 'CL10A475KO8NNNC',
    ('10uF', '0603'): 'CL10A106KP8NNNC', ('22uF', '0805'): 'CL21A226MAQNNNE', ('47uF', '1206'): 'CL31A476MPHNNNE',
}


def build():
    parts.build()
    b = Board()
    alimentacao(b)
    cm4(b)
    ethernet(b)
    hdmi(b)
    rf(b)
    asi(b)
    usb(b)
    io(b)
    check(b)
    return b


# =============================================================================
# 1. Alimentação
# =============================================================================
def alimentacao(b):
    b.sheet('alimentacao', 'Alimentação 12 V',
            'Entrada de 12 V (9 a 18 V) com fusível rearmável, TVS e proteção contra inversão; dois buck LMR33630 '
            'geram 5 V e 3,3 V (3 A cada) e um TLV62569 gera 1,2 V para os núcleos do demodulador e do receptor ASI.',
            ['EN dos dois buck por divisor: ligam acima de ~7,2 V de entrada.',
             'Q1 (P-MOSFET) conduz pelo diodo interno e satura com VGS = -10 V (DZ1); entrada invertida = Q1 cortado.'])
    b.group('Entrada e proteção')
    b.part('TERM_2P_508', '12 V DC', {'1': '+12V_IN', '2': 'GND'}, ref='J1')
    b.two('PTC_1812', '2 A', '+12V_IN', 'VIN_F', 'F', mpn='SMD1812P200TF/24', fab='RUILON')
    b.D('TVS_SMB', 'SMBJ18A', 'VIN_F', 'GND', mpn='SMBJ18A', fab='Jingdao')
    b.part('AO3401A', 'AO3401A', {'G': 'Q1_G', 'D': 'VIN_F', 'S': '+12V'}, ref='Q1')
    b.D('DZ_SOD123', 'BZT52C10', '+12V', 'Q1_G', mpn='BZT52C10-7-F', fab='Diodes Inc.')
    b.R('100k', 'Q1_G', 'GND')
    b.C('100uF 35V', '+12V', 'GND', 'CP', mpn='EEE-FK1V101P', fab='Panasonic')
    b.C('10uF 50V', '+12V', 'GND', '1210', mpn='GRM32ER71H106KA12L', fab='Murata')
    b.R('100k', '+12V', 'BUCK_EN')
    b.R('20k', 'BUCK_EN', 'GND')

    for name, vout, lval, rbot, lmpn in (('5V', '+5V', '6.8uH', '24.9k', 'SRP7028A-6R8M'),
                                          ('3V3', '+3V3', '4.7uH', '43.2k', 'SRP7028A-4R7M')):
        b.group(f'Buck 12 V para {vout[1:]}')
        sw, fb, bst, vcc = f'SW_{name}', f'FB_{name}', f'BST_{name}', f'VCC_{name}'
        b.part('LMR33630ADDA', 'LMR33630ADDA',
               {'VIN': '+12V', 'EN': 'BUCK_EN', 'PG': None, 'FB': fb, 'VCC': vcc, 'BOOT': bst, 'SW': sw, 'GND': 'GND'})
        b.C('10uF 50V', '+12V', 'GND', '1210', mpn='GRM32ER71H106KA12L', fab='Murata')
        b.C('100nF 50V', '+12V', 'GND', '0603', mpn='CL10B104KB8NNNC')
        b.C('1uF', vcc, 'GND', '0402', mpn=CAPS[('1uF', '0402')])
        b.C('100nF', bst, sw, '0402', mpn=CAPS[('100nF', '0402')])
        b.L('L_SRP7028', lval, sw, vout, mpn=lmpn, fab='Bourns')
        b.R('100k 1%', vout, fb)
        b.R(f'{rbot} 1%', fb, 'GND')
        b.decouple(vout, ['22uF', '22uF', '22uF', '100nF'])

    b.group('Buck 5 V para 1,2 V (núcleos)')
    b.part('TLV62569DBV', 'TLV62569DBV', {'VIN': '+5V', 'EN': '+5V', 'SW': 'SW_1V2', 'FB': 'FB_1V2', 'GND': 'GND'})
    b.decouple('+5V', ['10uF'])
    b.L('L_0806', '2.2uH', 'SW_1V2', '+1V2', mpn='LQH32PN2R2NN0L', fab='Murata',
        fp='Inductor_SMD:L_1210_3225Metric')
    b.R('100k 1%', '+1V2', 'FB_1V2')
    b.R('100k 1%', 'FB_1V2', 'GND')
    b.decouple('+1V2', ['22uF', '22uF'])


# =============================================================================
# 2. CM4
# =============================================================================
def cm4(b):
    b.sheet('cm4', 'Raspberry Pi CM4',
            'O módulo CM4 (BCM2711, 4 GB, eMMC) roda o Linux e o LiveSafe Monitor. Os GPIO trabalham em 3,3 V '
            '(GPIO_VREF ligado à saída de 3,3 V do próprio CM4).',
            ['config.txt: dtoverlay=dwc2,dr_mode=host (USB do CM4 como host do hub), dtoverlay=tc358743, '
             'dtoverlay=tc358743-audio, dtparam=i2c_arm=on, dtparam=spi=on, dtoverlay=i2c-rtc,pcf85063a,i2c_csi_dsi',
             'Chave GRAVAR: leva nRPIBOOT a 0 e passa a USB do CM4 para o micro-USB interno (rpiboot / gravar o eMMC).'])
    b.group('Módulo')
    gpio = {'GPIO2': 'RF_SDA', 'GPIO3': 'RF_SCL', 'GPIO4': 'RF_RESET_N', 'GPIO5': 'ASI_RESET_N', 'GPIO6': 'GPI1',
            'GPIO12': 'GPI2', 'GPIO25': 'GPI3', 'GPIO24': 'GPI4', 'GPIO13': 'GPO1', 'GPIO16': 'GPO2', 'GPIO17': 'GPO3',
            'GPIO22': 'GPO4', 'GPIO23': 'LED_OK', 'GPIO27': 'LED_ALM', 'GPIO14': 'CON_TX', 'GPIO15': 'CON_RX',
            'GPIO18': 'I2S_BCK', 'GPIO19': 'I2S_LRCK', 'GPIO20': 'I2S_DIN', 'GPIO26': 'HDMI_INT', 'GPIO8': 'ASI_CS_N',
            'GPIO9': 'ASI_MISO', 'GPIO10': 'ASI_MOSI', 'GPIO11': 'ASI_SCK', 'GPIO7': 'ASI_LOCK', 'GPIO21': 'USB_RST_GPIO'}
    nets = {'+5V_IN': '+5V', 'GND': 'GND', 'GPIO_VREF': 'CM4_3V3', '+3V3_OUT': 'CM4_3V3', 'RUN_PG': 'CM4_RUN',
            'nRPIBOOT': 'BOOT_N', 'nPI_LED_PWR': 'LED_PWR_N', 'PI_nLED_Activity': 'LED_ACT_N', 'SCL0': 'I2C0_SCL',
            'SDA0': 'I2C0_SDA', 'Camera_GPIO': 'CAM_GPIO', 'USB2_P': 'USB_CM4_P', 'USB2_N': 'USB_CM4_N',
            'USB_OTG_ID': 'GND', 'ETH_nLED1': 'ETH_nLED1', 'ETH_nLED2': 'ETH_nLED2',
            'CAM1_C_P': 'CSI_C_P', 'CAM1_C_N': 'CSI_C_N'}
    for i in range(4):
        nets[f'ETH_P{i}_P'] = f'ETH_P{i}_P'
        nets[f'ETH_P{i}_N'] = f'ETH_P{i}_N'
        nets[f'CAM1_D{i}_P'] = f'CSI_D{i}_P'
        nets[f'CAM1_D{i}_N'] = f'CSI_D{i}_N'
    nets.update(gpio)
    b.part('RPi_CM4', 'CM4104032', nets, ref='U1')
    b.group('Desacoplamento do CM4')
    b.decouple('+5V', ['47uF', '47uF', '100nF'])
    b.decouple('CM4_3V3', ['10uF', '100nF'])
    b.group('Reset, gravação e I2C0')
    b.part('SW_PUSH', 'RESET', {'1': 'CM4_RUN', '2': 'GND'})
    b.part('SW_SPDT', 'GRAVAR (eMMC)', {'C': 'BOOT_N', 'A': 'GND', 'B': None})
    b.R('10k', 'CM4_3V3', 'BOOT_N')
    b.C('100nF', 'CM4_RUN', 'GND', mpn=CAPS[('100nF', '0402')])
    b.R('4.7k', 'CM4_3V3', 'I2C0_SDA')
    b.R('4.7k', 'CM4_3V3', 'I2C0_SCL')
    b.R('1k', 'USB_RST_GPIO', 'USB_RST_N')


# =============================================================================
# 3. Ethernet
# =============================================================================
def ethernet(b):
    b.sheet('ethernet', 'Ethernet Gigabit',
            'O PHY BCM54210PE está dentro do CM4; aqui ficam só o RJ45 com magnéticos e os LEDs. Pares diferenciais '
            'de 100 Ohm, iguais em comprimento, sem vias.',
            ['Derivações centrais (MXCTx) desacopladas para o terra, como pede o PHY em modo tensão do CM4.'])
    b.group('RJ45 com magnéticos')
    nets = {'SHIELD': 'GND', 'LED1+': 'ETH_LED1_A', 'LED1-': 'ETH_nLED1', 'LED2+': 'ETH_LED2_A', 'LED2-': 'ETH_nLED2'}
    for i in range(4):
        nets[f'MX{i + 1}+'] = f'ETH_P{i}_P'
        nets[f'MX{i + 1}-'] = f'ETH_P{i}_N'
        nets[f'MXCT{i + 1}'] = f'ETH_CT{i + 1}'
    b.part('RJ45_JK0654219NL', 'JK0654219NL', nets, ref='J2')
    for i in range(4):
        b.C('100nF', f'ETH_CT{i + 1}', 'GND', mpn=CAPS[('100nF', '0402')])
    b.R('330', 'CM4_3V3', 'ETH_LED1_A')
    b.R('330', 'CM4_3V3', 'ETH_LED2_A')


# =============================================================================
# 4. HDMI -> CSI-2
# =============================================================================
def hdmi(b):
    b.sheet('hdmi', 'Entrada HDMI (TC358743XBG)',
            'Ponte HDMI 1.4 para MIPI CSI-2 de 4 vias (CAM1 do CM4) com áudio I2S. Circuito de referência da Antmicro '
            '(hdmi-mipi-bridge, Apache-2.0) adaptado: proteção ESD TPD4E05U06 e HPD comandado pelo HPDO.',
            ['Linux: driver tc358743 (dtoverlay=tc358743,4lane=1 e tc358743-audio). EDID interno, gravado pelo driver.',
             'R do HPD: 1 k a partir do HPDO (padrão); a opção de HPD fixo em 5 V fica sem montar.'])
    b.group('Conector e proteção')
    b.part('HDMI_A_IN', 'HDMI tipo A', {'CK+': 'HDMI_CK_P', 'CK-': 'HDMI_CK_N', 'D0+': 'HDMI_D0_P', 'D0-': 'HDMI_D0_N',
                                        'D1+': 'HDMI_D1_P', 'D1-': 'HDMI_D1_N', 'D2+': 'HDMI_D2_P', 'D2-': 'HDMI_D2_N',
                                        'CKS': 'GND', 'D0S': 'GND', 'D1S': 'GND', 'D2S': 'GND', 'DDC_GND': 'GND',
                                        'SCL': 'HDMI_SCL5', 'SDA': 'HDMI_SDA5', 'CEC': 'HDMI_CEC', 'HPD': 'HDMI_HPD',
                                        '+5V': 'HDMI_5V', 'UTILITY': None, 'SHIELD': 'HDMI_SH'}, ref='J3')
    b.FB('120R 3A', 'HDMI_SH', 'GND', mpn='BLM18SG121TN1D', fab='Murata')
    for a, c in (('CK', 'D0'), ('D1', 'D2')):
        b.part('TPD4E05U06DQA', 'TPD4E05U06', {'D1+': f'HDMI_{a}_P', 'D1-': f'HDMI_{a}_N', 'D2+': f'HDMI_{c}_P',
                                               'D2-': f'HDMI_{c}_N', 'GND': 'GND'})
    b.part('TPD4E05U06DQA', 'TPD4E05U06', {'D1+': 'HDMI_SCL5', 'D1-': 'HDMI_SDA5', 'D2+': 'HDMI_CEC', 'D2-': 'HDMI_HPD',
                                           'GND': 'GND'})
    b.group('DDC, HPD e detecção de 5 V')
    b.part('PCA9517D', 'PCA9517D', {'VCCA': '+3V3', 'VCCB': '+5V', 'SCLA': 'HDMI_SCL', 'SDAA': 'HDMI_SDA',
                                    'SCLB': 'HDMI_SCL5', 'SDAB': 'HDMI_SDA5', 'EN': 'HDMI_DDC_EN', 'GND': 'GND'})
    b.decouple('+5V', ['100nF'])
    b.decouple('+3V3', ['100nF'])
    b.R('10k', '+3V3', 'HDMI_DDC_EN')
    b.R('10k', '+3V3', 'HDMI_SCL')
    b.R('10k', '+3V3', 'HDMI_SDA')
    b.R('10k', '+5V', 'HDMI_SCL5')
    b.R('10k', '+5V', 'HDMI_SDA5')
    b.R('0', 'HDMI_5V', 'HDMI_HPDI', '0603')
    b.R('1k', 'HDMI_HPDO', 'HDMI_HPD')
    b.R('100k', 'HDMI_HPD', 'GND')
    b.R('0', 'HDMI_5V', 'HDMI_HPD', '0603', dnp=True, note='HPD fixo (opção Antmicro)')
    b.C('100nF', 'HDMI_5V', 'GND', mpn=CAPS[('100nF', '0402')])
    b.group('Ponte TC358743XBG')
    tc = {'HDMIC_P': 'HDMI_CK_P', 'HDMIC_N': 'HDMI_CK_N', 'DDC_SDA': 'HDMI_SDA', 'DDC_SCL': 'HDMI_SCL',
          'HPDI': 'HDMI_HPDI', 'CEC': 'HDMI_CEC', 'REFCLK': 'HDMI_REFCLK', 'RESETN': 'HDMI_RESET_N',
          'I2C_SDA': 'I2C0_SDA', 'I2C_SCL': 'I2C0_SCL', 'TEST': 'GND', 'VPGM': 'GND', 'GND': 'GND',
          'CSIC_P': 'CSI_C_P', 'CSIC_N': 'CSI_C_N', 'INT': 'HDMI_INT', 'HPDO': 'HDMI_HPDO', 'A_SCK': 'I2S_BCK',
          'A_WFS': 'I2S_LRCK', 'A_SD': 'I2S_DIN', 'REXT': 'TC_REXT', 'BIASDA': 'TC_BIASDA', 'DAOUT': 'TC_DAOUT',
          'PCKIN': 'TC_PCKIN', 'AVDD33': 'TC_AVDD33', 'VDDIO1': 'TC_VDDIO1', 'VDDIO2': 'TC_VDDIO2',
          'AVDD25': 'TC_AVDD25', 'AVDD12': 'TC_AVDD12', 'VDD_MIPI': 'TC_VDDMIPI', 'VDDC1': 'TC_VDDC1',
          'VDDC2': 'TC_VDDC2'}
    for i in range(3):
        tc[f'HDMID{i}_P'] = f'HDMI_D{i}_P'
        tc[f'HDMID{i}_N'] = f'HDMI_D{i}_N'
    for i in range(4):
        tc[f'CSID{i}_P'] = f'CSI_D{i}_P'
        tc[f'CSID{i}_N'] = f'CSI_D{i}_N'
    b.part('TC358743XBG', 'TC358743XBG', tc)
    b.R('2k 1%', 'TC_AVDD33', 'TC_REXT')
    for n in ('TC_BIASDA', 'TC_DAOUT', 'TC_PCKIN'):
        b.C('100nF', n, 'GND', mpn=CAPS[('100nF', '0402')])
    b.R('10k', '+3V3', 'HDMI_RESET_N')
    b.C('100nF', 'HDMI_RESET_N', 'GND', mpn=CAPS[('100nF', '0402')])
    b.R('0', 'CAM_GPIO', 'HDMI_RESET_N', dnp=True, note='reset por software (opcional)')
    b.group('Alimentação da ponte')
    for n in ('TC_AVDD33', 'TC_VDDIO1', 'TC_VDDIO2'):
        b.R('0', '+3V3', n, '0603')
        b.C('100nF', n, 'GND', mpn=CAPS[('100nF', '0402')])
    b.part('TLV73325PDBV', 'TLV73325', {'IN': '+3V3', 'EN': '+3V3', 'OUT': '+2V5_TC', 'GND': 'GND'})
    b.part('TLV73312PDBV', 'TLV73312', {'IN': '+3V3', 'EN': '+3V3', 'OUT': '+1V2_TC', 'GND': 'GND'})
    b.decouple('+3V3', ['10uF', '10uF'])
    b.decouple('+2V5_TC', ['10uF'])
    b.decouple('+1V2_TC', ['10uF'])
    for net, src in (('TC_AVDD25', '+2V5_TC'), ('TC_AVDD12', '+1V2_TC'), ('TC_VDDMIPI', '+1V2_TC'), ('TC_VDDC1', '+1V2_TC')):
        b.FB('1k@100MHz', src, net, '0805', mpn='BLM21AG102SN1D', fab='Murata')
        b.decouple(net, ['470pF', '4.7uF'])
    b.R('0', 'TC_VDDC1', 'TC_VDDC2', '0603')
    b.C('100nF', 'TC_VDDC2', 'GND', mpn=CAPS[('100nF', '0402')])
    b.group('Relógio de 27 MHz')
    b.part('OSC_4P', '27 MHz', {'VDD': 'OSC27_VDD', 'EN': 'OSC27_VDD', 'OUT': 'OSC27_OUT', 'GND': 'GND'})
    b.FB('600R', '+3V3', 'OSC27_VDD', mpn='BLM18AG601SN1D', fab='Murata')
    b.decouple('OSC27_VDD', ['100nF', '47pF'])
    b.R('22', 'OSC27_OUT', 'HDMI_REFCLK')
    b.C('47pF', 'OSC27_OUT', 'GND', mpn=CAPS[('47pF', '0402')])
    b.C('47pF', 'HDMI_REFCLK', 'GND', mpn=CAPS[('47pF', '0402')])


# =============================================================================
# 5. RF ISDB-Tb
# =============================================================================
def rf(b):
    b.sheet('rf', 'Recepção ISDB-Tb (Si2141 + Si2183)',
            'Antena (75 Ohm) -> sintonizador Si2141 (IF baixa) -> demodulador Si2183-B60 -> TS paralelo para a '
            'FX2LP #1. Controle pelo I2C1 do CM4; o Si2141 fica atrás do I2C mestre do Si2183. Clock único: '
            'cristal de 24 MHz no Si2141, repassado pelo XOUT ao pino 44 do Si2183 (padrão do SDK Skyworks).',
            ['Endereços: Si2183 0x64 (ADDR em 0), Si2141 0x60 (ADDR em 0). Opções sem montar mudam os níveis.',
             'Rede de entrada: R/C em posições alternativas, a confirmar com o datasheet completo do Si2141 '
             '(Skyworks, sob NDA) ou com a placa de avaliação Si2183-B-EVB antes da produção.',
             'AGC: MP_A do Si2183 no AGC1 do Si2141 (padrão do SDK); MP_D -> AGC2 como opção.'])
    b.group('Entrada de antena')
    b.part('BNC_75R', 'RF IN 75 Ohm', {'IN': 'RF_ANT', 'SHIELD': 'GND'}, ref='J4')
    b.D('TVS_0402', 'PESD0402-140', 'RF_ANT', 'GND', mpn='PESD0402-140', fab='Littelfuse')
    b.C('1nF C0G', 'RF_ANT', 'TUN_RFIP', '0402', mpn='GRM1555C1H102JA01D', fab='Murata')
    b.R('0', 'RF_ANT', 'TUN_RFIN', dnp=True, note='opção: entrada pelo RF_IN')
    b.C('1nF C0G', 'TUN_RFIN', 'GND', '0402', mpn='GRM1555C1H102JA01D', fab='Murata')
    b.C('1nF C0G', 'TUN_RFREF', 'GND', '0402', mpn='GRM1555C1H102JA01D', fab='Murata')
    b.R('0', 'TUN_RFREF', 'GND', dnp=True, note='opção: RF_REF direto ao terra')
    b.group('Sintonizador Si2141')
    b.part('Si2141-A10', 'Si2141-A10', {'RF_IP': 'TUN_RFIP', 'RF_IN': 'TUN_RFIN', 'RF_REF': 'TUN_RFREF',
                                        'XTAL_I': 'TUN_XI', 'XTAL_O': 'TUN_XO', 'SDA': 'TUN_SDA', 'SCL': 'TUN_SCL',
                                        'ADDR': 'TUN_ADDR', 'AGC1': 'TUN_AGC1', 'AGC2': 'TUN_AGC2',
                                        'LIF_P': 'TUN_LIF_P', 'LIF_N': 'TUN_LIF_N', 'XOUT': 'TUN_XOUT',
                                        'VDDH': 'TUN_VDDH', 'VDDL': '+1V8_TUN', 'GND': 'GND'})
    b.part('XTAL_4P', '24 MHz', {'X1': 'TUN_XI', 'X2': 'TUN_XO', 'GND': 'GND'}, mpn='X322524MOB4SI', fab='Yangxing')
    b.C('8.2pF', 'TUN_XI', 'GND', dnp=True, note='trim interno do Si2141 (XO_CAP)')
    b.C('8.2pF', 'TUN_XO', 'GND', dnp=True, note='trim interno do Si2141 (XO_CAP)')
    b.R('0', 'TUN_ADDR', 'GND')
    b.R('0', 'TUN_ADDR', 'TUN_VDDH', dnp=True)
    b.R('4.7k', '+3V3', 'TUN_SDA')
    b.R('4.7k', '+3V3', 'TUN_SCL')
    b.FB('600R', '+3V3', 'TUN_VDDH', mpn='BLM18AG601SN1D', fab='Murata')
    b.decouple('TUN_VDDH', ['100nF', '100nF', '100nF', '10uF'])
    b.part('TLV73318PDBV', 'TLV73318', {'IN': '+3V3', 'EN': '+3V3', 'OUT': '+1V8_TUN', 'GND': 'GND'})
    b.decouple('+1V8_TUN', ['1uF', '100nF'])
    b.decouple('+3V3', ['1uF'])
    b.group('Ligações sintonizador - demodulador')
    b.R('0', 'TUN_LIF_P', 'DEM_ADC_P', note='pode virar capacitor de acoplamento')
    b.R('0', 'TUN_LIF_N', 'DEM_ADC_N', note='pode virar capacitor de acoplamento')
    b.R('0', 'TUN_XOUT', 'DEM_CLKIN')
    b.R('0', 'TUN_XOUT', 'DEM_XTALI', dnp=True, note='clock pelo pino 33 (CLK_XTAL_IN)')
    b.R('0', 'DEM_MPA', 'TUN_AGC1')
    b.R('0', 'DEM_MPD', 'TUN_AGC2', dnp=True, note='AGC pelo MP_D (opção)')
    b.C('10nF', 'TUN_AGC1', 'GND', dnp=True, note='filtro RC do AGC (opção)')
    b.group('Demodulador Si2183-B60')
    dem = {'TC_ADC_P': 'DEM_ADC_P', 'TC_ADC_N': 'DEM_ADC_N', 'CLK_IN_OUT': 'DEM_CLKIN', 'XTAL_I/CLK_IN': 'DEM_XTALI',
           'SDA_HOST': 'RF_SDA', 'SCL_HOST': 'RF_SCL', 'ADDR': 'DEM_ADDR', 'RESETB': 'RF_RESET_N',
           'TS_CLK': 'DEM_TSCLK', 'TS_SYNC': 'DEM_TSSYNC', 'TS_VAL': 'DEM_TSVAL', 'TS_ERR/GPIO_1': 'DEM_TSERR',
           'SDA_MAST': 'TUN_SDA', 'SCL_MAST': 'TUN_SCL', 'MP_A': 'DEM_MPA', 'MP_D': 'DEM_MPD',
           'VDD_VCORE': 'DEM_VCORE', 'VDD_VANA': 'DEM_VANA', 'VDD_VIO': '+3V3', 'GND': 'GND',
           'TS_DATA0/TS_SER': 'DEM_TSD0'}
    for i in range(1, 8):
        dem[f'TS_DATA{i}'] = f'DEM_TSD{i}'
    b.part('Si2183-B60', 'Si2183-B60', dem)
    b.R('0', 'DEM_ADDR', 'GND')
    b.R('0', 'DEM_ADDR', '+3V3', dnp=True)
    b.R('10k', '+3V3', 'RF_RESET_N')
    b.FB('600R', '+1V2', 'DEM_VCORE', mpn='BLM18AG601SN1D', fab='Murata')
    b.decouple('DEM_VCORE', ['100nF', '100nF', '100nF', '100nF', '10uF'])
    b.FB('600R', '+3V3', 'DEM_VANA', mpn='BLM18AG601SN1D', fab='Murata')
    b.decouple('DEM_VANA', ['100nF', '4.7uF'])
    b.decouple('+3V3', ['100nF', '100nF'])
    b.group('TS paralelo (resistores de série)')
    pairs = [(f'DEM_TSD{i}', f'TS1_D{i}') for i in range(8)] + [('DEM_TSCLK', 'TS1_CLK'), ('DEM_TSSYNC', 'TS1_SYNC'),
                                                                  ('DEM_TSVAL', 'TS1_VAL'), ('DEM_TSERR', 'TS1_ERR')]
    for a, c in pairs:
        b.R('33', a, c)


# =============================================================================
# 6. ASI
# =============================================================================
def asi(b):
    b.sheet('asi', 'Entrada ASI (GS2961A)',
            'Receptor SDI/ASI Semtech GS2961A: equalizador de cabo, reclocker e decodificação 8b/10b. Em modo DVB-ASI '
            'o byte do TS sai em DOUT17..10 com PCLK de 27 MHz; DOUT18 (SYNC_OUT) marca as palavras de '
            'preenchimento e vira o SLWR da FX2LP #2 (ativo em nível baixo).',
            ['Modo manual pelo GSPI (bit AUTO/MAN = 0): DVB_ASI = 1 (R para 3,3 V) e SMPTE_BYPASS = 0 (R para o terra).',
             'Valores do circuito típico da Semtech (pág. 99): 75 Ohm + 6,2 nH na entrada, 470 nF no AGC, '
             'VCO por 105 Ohm + 33 uF. Saída de laço SDO desligada (SDO_EN = 0).',
             'Plano de terra único (A_GND e GND unidos); ver o guia de layout no docs/04.'])
    b.group('Entrada BNC 75 Ohm')
    b.part('BNC_75R', 'ASI IN 75 Ohm', {'IN': 'ASI_IN', 'SHIELD': 'GND'}, ref='J5')
    b.D('TVS_0402', 'PESD0402-140', 'ASI_IN', 'GND', dnp=True, mpn='PESD0402-140', fab='Littelfuse')
    b.L('L_0402', '6.2nH', 'ASI_IN', 'ASI_EQ', mpn='LQG15HS6N2S02D', fab='Murata')
    b.R('75 1%', 'ASI_IN', 'ASI_EQ')
    b.R('75 1%', 'ASI_EQ', 'GND')
    b.C('1uF', 'ASI_EQ', 'ASI_SDI_P', mpn=CAPS[('1uF', '0402')])
    b.C('1uF', 'ASI_SDI_N', 'ASI_REF', mpn=CAPS[('1uF', '0402')])
    b.R('37.4 1%', 'ASI_REF', 'GND')
    b.group('Receptor GS2961A')
    gs = {'SDI': 'ASI_SDI_P', 'SDI_N': 'ASI_SDI_N', 'AGCP': 'ASI_AGCP', 'AGCN': 'ASI_AGCN', 'XTAL1': 'ASI_X1',
          'XTAL2': 'ASI_X2', 'XTAL_OUT': 'ASI_XOUT', 'VBG': 'ASI_VBG', 'LF': 'ASI_LF', 'LB_CONT': 'ASI_LBCONT',
          'RESET_TRST': 'ASI_RESET_N', 'JTAG/HOST': 'GND', 'CS_TMS': 'ASI_CS_N', 'SCLK_TCK': 'ASI_SCK',
          'SDIN_TDI': 'ASI_MOSI', 'SDOUT_TDO': 'ASI_MISO', 'SMPTE_BYPASS': 'ASI_SMPTE_BYP', 'DVB_ASI': 'ASI_DVBASI',
          '20BIT/10BIT': 'GND', 'IOPROC_EN/DIS': 'GND', 'RC_BYP': '+3V3', 'TIM_861': 'GND', 'SW_EN': 'GND',
          'STANDBY': 'GND', 'SDO_EN': 'GND', 'PCLK': 'GS_PCLK', 'STAT3': 'ASI_LOCK', 'DOUT18': 'GS_SYNC',
          'DOUT19': 'GS_WERR', 'IO_VDD': '+3V3', 'CORE_VDD': '+1V2', 'PLL_VDD': 'ASI_1V2A', 'VCO_VDD': 'ASI_VCO',
          'A_VDD': 'ASI_3V3A', 'EQ_VDD': 'ASI_3V3A', 'BUFF_VDD': 'ASI_3V3A'}
    for g in ('IO_GND', 'CORE_GND', 'PLL_GND', 'A_GND', 'VCO_GND', 'EQ_GND', 'BUFF_GND'):
        gs[g] = 'GND'
    for i in range(8):
        gs[f'DOUT{10 + i}'] = f'GS_D{i}'
    b.part('GS2961A', 'GS2961AIBE3', gs)
    b.C('470nF', 'ASI_AGCP', 'ASI_AGCN', mpn='CL05A474KP5NNNC')
    b.C('470nF', 'ASI_AGCN', 'GND', mpn='CL05A474KP5NNNC')
    b.C('1uF', 'ASI_VBG', 'GND', mpn=CAPS[('1uF', '0402')])
    b.C('47nF', 'ASI_LF', 'GND', mpn='CL05B473KO5NNNC')
    b.R('NM', 'ASI_LBCONT', 'ASI_3V3A', dnp=True, note='DNP no circuito da Semtech')
    b.R('NM', 'ASI_LBCONT', 'GND', dnp=True, note='DNP no circuito da Semtech')
    b.part('XTAL_4P', '27 MHz', {'X1': 'ASI_X1', 'X2': 'ASI_X2', 'GND': 'GND'}, mpn='X322527MOB4SI', fab='Yangxing')
    b.C('16pF', 'ASI_X1', 'GND', mpn='0402CG160J500NT', fab='FH')
    b.C('16pF', 'ASI_X2', 'GND', mpn='0402CG160J500NT', fab='FH')
    b.two('TP', 'XTAL_OUT', 'ASI_XOUT', None, 'TP')
    b.comps[list(b.comps)[-1]].pins = {'1': 'ASI_XOUT'}
    b.R('10k', '+3V3', 'ASI_DVBASI')
    b.R('10k', 'ASI_SMPTE_BYP', 'GND')
    b.R('10k', '+3V3', 'ASI_RESET_N')
    b.group('Alimentação do GS2961A')
    b.R('0', '+3V3', 'ASI_3V3A', '0603')
    b.decouple('ASI_3V3A', ['1uF', '10nF', '10nF', '10nF', '10nF'])
    b.part('TLV73312PDBV', 'TLV73312', {'IN': '+3V3', 'EN': '+3V3', 'OUT': 'ASI_1V2A', 'GND': 'GND'})
    b.decouple('ASI_1V2A', ['1uF', '10nF', '10nF', '10nF'])
    b.R('105 1%', 'ASI_1V2A', 'ASI_VCO')
    b.C('33uF', 'ASI_VCO', 'GND', '1206', mpn='C3216X5R1C336MTJ00N', fab='TDK')
    b.decouple('+1V2', ['1uF', '10nF', '10nF', '10nF', '10nF'])
    b.decouple('+3V3', ['1uF', '10nF', '10nF', '10nF', '10nF'])
    b.group('Bytes do TS (resistores de série)')
    for i in range(8):
        b.R('33', f'GS_D{i}', f'TS2_D{i}')
    b.R('33', 'GS_PCLK', 'TS2_CLK')
    b.R('33', 'GS_SYNC', 'TS2_SYNC')
    b.R('33', 'GS_WERR', 'TS2_WERR')


# =============================================================================
# 7. USB
# =============================================================================
def usb(b):
    b.sheet('usb', 'USB: chave de serviço, hub e pontes FX2LP',
            'A única USB 2.0 do CM4 passa pela chave FSUSB42: em operação vai ao hub USB2514B; com a chave GRAVAR '
            'vai ao micro-USB interno de serviço. O hub atende a FX2LP #1 (TS do demodulador), a FX2LP #2 (bytes ASI) e a '
            'porta USB-A; a porta 4 fica desligada por strap.',
            ['FX2LP sem EEPROM: o firmware é carregado pelo Linux a cada partida (fxload / libusb).',
             'USB_RST_N reinicia o hub e as duas FX2LP (RC de 10 ms + GPIO21 do CM4, para recuperação por software).'])
    b.group('Chave USB e porta de serviço (interna)')
    b.part('FSUSB42MX', 'FSUSB42MUX', {'VCC': '+3V3', 'GND': 'GND', 'D+': 'USB_CM4_P', 'D-': 'USB_CM4_N',
                                       'SEL': 'BOOT_N', 'OE_N': 'GND', 'HSD1+': 'USB_SERV_P', 'HSD1-': 'USB_SERV_N',
                                       'HSD2+': 'USB_HUB_P', 'HSD2-': 'USB_HUB_N'})
    b.decouple('+3V3', ['100nF'])
    b.part('USB_MICRO_V', 'USB serviço', {'D+': 'USB_SERV_P', 'D-': 'USB_SERV_N', 'VBUS': 'USB_SERV_VBUS', 'ID': None,
                                          'GND': 'GND', 'SHIELD': 'GND'}, ref='J6')
    b.part('USBLC6-2SC6', 'USBLC6-2SC6', {'IO1a': 'USB_SERV_P', 'IO1b': 'USB_SERV_P', 'IO2a': 'USB_SERV_N',
                                          'IO2b': 'USB_SERV_N', 'VBUS': 'USB_SERV_VBUS', 'GND': 'GND'})
    b.group('Hub USB2514B')
    hub = {'UP_DP': 'USB_HUB_P', 'UP_DM': 'USB_HUB_N', 'XTALIN': 'HUB_XI', 'XTALOUT': 'HUB_XO',
           'RESET_N': 'USB_RST_N', 'VBUS_DET': '+3V3', 'RBIAS': 'HUB_RBIAS', 'CRFILT': 'HUB_CRFILT',
           'PLLFILT': 'HUB_PLLFILT', 'TEST': 'GND', 'SCL/CFG_SEL0': 'HUB_CFG0', 'HS_IND/CFG_SEL1': 'HUB_CFG1',
           'SDA/NON_REM1': 'HUB_NONREM1', 'SUSP_IND/NON_REM0': 'HUB_NONREM0',
           'DN1_DP': 'USB_FX1_P', 'DN1_DM': 'USB_FX1_N', 'DN2_DP': 'USB_FX2_P', 'DN2_DM': 'USB_FX2_N',
           'DN3_DP': 'USB_A_P', 'DN3_DM': 'USB_A_N', 'DN4_DP': '+3V3', 'DN4_DM': '+3V3',
           'PRTPWR3': 'USB_A_EN', 'OCS_N1': 'HUB_OCS_PU', 'OCS_N2': 'HUB_OCS_PU', 'OCS_N3': 'USB_A_FLT_N',
           'OCS_N4': 'HUB_OCS_PU', 'VDD33': '+3V3', 'VDDA33': '+3V3', 'VSS': 'GND'}
    b.part('USB2514B', 'USB2514B-I/M2', hub)
    b.part('XTAL_4P', '24 MHz', {'X1': 'HUB_XI', 'X2': 'HUB_XO', 'GND': 'GND'}, mpn='X322524MOB4SI', fab='Yangxing')
    b.C('18pF', 'HUB_XI', 'GND', mpn='CL05C180JB5NNNC')
    b.C('18pF', 'HUB_XO', 'GND', mpn='CL05C180JB5NNNC')
    b.R('1M', 'HUB_XI', 'HUB_XO')
    b.R('12k 1%', 'HUB_RBIAS', 'GND')
    b.C('1uF', 'HUB_CRFILT', 'GND', mpn=CAPS[('1uF', '0402')])
    b.C('1uF', 'HUB_PLLFILT', 'GND', mpn=CAPS[('1uF', '0402')])
    b.R('10k', 'HUB_CFG0', 'GND')
    b.R('10k', 'HUB_CFG1', 'GND')
    b.R('10k', '+3V3', 'HUB_NONREM1')
    b.R('10k', 'HUB_NONREM0', 'GND')
    b.R('10k', '+3V3', 'HUB_OCS_PU')
    b.R('10k', '+3V3', 'USB_A_FLT_N')
    b.decouple('+3V3', ['100nF'] * 6 + ['4.7uF'])
    b.group('Reset do USB')
    b.R('10k', '+3V3', 'USB_RST_N')
    b.C('1uF', 'USB_RST_N', 'GND', mpn=CAPS[('1uF', '0402')])
    b.group('Porta USB-A')
    b.part('TPS2051CDBV', 'TPS2051C', {'IN': '+5V', 'EN': 'USB_A_EN', 'OUT': 'USB_A_VBUS', 'FLT': 'USB_A_FLT_N',
                                       'GND': 'GND'})
    b.decouple('+5V', ['1uF'])
    b.decouple('USB_A_VBUS', ['47uF', '47uF', '100nF'])
    b.part('USB_A_HOST', 'USB-A', {'VBUS': 'USB_A_VBUS', 'D+': 'USB_A_P', 'D-': 'USB_A_N', 'GND': 'GND',
                                   'SHIELD': 'GND'}, ref='J7')
    b.part('USBLC6-2SC6', 'USBLC6-2SC6', {'IO1a': 'USB_A_P', 'IO1b': 'USB_A_P', 'IO2a': 'USB_A_N',
                                          'IO2b': 'USB_A_N', 'VBUS': 'USB_A_VBUS', 'GND': 'GND'})
    for k, ts, slwr, pa0, pa1 in ((1, 'TS1', 'TS1_VAL', 'TS1_SYNC', 'TS1_ERR'), (2, 'TS2', 'TS2_SYNC', 'TS2_WERR', None)):
        b.group(f'Ponte FX2LP #{k} ({"TS do demodulador" if k == 1 else "bytes ASI"})')
        fx = {'D+': f'USB_FX{k}_P', 'D-': f'USB_FX{k}_N', 'XTALIN': f'FX{k}_XI', 'XTALOUT': f'FX{k}_XO',
              'RESETN': 'USB_RST_N', 'WAKEUP': f'FX{k}_PU', 'SCL': f'FX{k}_SCL', 'SDA': f'FX{k}_SDA',
              'RESERVED': 'GND', 'IFCLK': f'{ts}_CLK', 'RDY1/SLWR': slwr, 'RDY0/SLRD': f'FX{k}_PU',
              'PA0/INT0': pa0, 'PA1/INT1': pa1, 'PA2/SLOE': f'FX{k}_PU', 'PA4/FIFOADR0': f'FX{k}_PD',
              'PA5/FIFOADR1': f'FX{k}_PD', 'PA6/PKTEND': f'FX{k}_PU', 'VCC': '+3V3', 'AVCC': '+3V3',
              'GND': 'GND', 'AGND': 'GND'}
        for i in range(8):
            fx[f'PB{i}/FD{i}'] = f'{ts}_D{i}'
        b.part('CY7C68013A-56LTX', 'CY7C68013A-56LTXC', fx)
        b.part('XTAL_4P', '24 MHz', {'X1': f'FX{k}_XI', 'X2': f'FX{k}_XO', 'GND': 'GND'}, mpn='X322524MOB4SI',
               fab='Yangxing')
        b.C('12pF', f'FX{k}_XI', 'GND', mpn='CL05C120JB5NNNC')
        b.C('12pF', f'FX{k}_XO', 'GND', mpn='CL05C120JB5NNNC')
        b.R('10k', '+3V3', f'FX{k}_PU')
        b.R('10k', f'FX{k}_PD', 'GND')
        b.R('2.2k', '+3V3', f'FX{k}_SCL')
        b.R('2.2k', '+3V3', f'FX{k}_SDA')
        b.decouple('+3V3', ['100nF'] * 8 + ['4.7uF'])


# =============================================================================
# 8. Alarmes, painel, RTC, ventoinha
# =============================================================================
def io(b):
    b.sheet('io', 'Alarmes, painel, RTC e ventoinha',
            '4 entradas optoacopladas com comum (12-24 V, ou contato seco usando o +12 V auxiliar), 4 relés SPDT para a '
            'remota do abrigo, LEDs do painel, relógio de tempo real com bateria, controle da ventoinha e console serial.',
            ['Entrada ativa = GPIO em 0. Relé ligado = GPIO em 1 (ULN2003A).',
             'Borne J8: IN1 IN2 IN3 IN4 COM +12V(aux, 100 mA). Contato seco: ligar entre +12V(aux) e INx, '
             'com COM no GND; sinal externo de 12-24 V: INx positivo e COM negativo.',
             'Borne J9: C/NA/NF dos relés 1 a 4, nessa ordem.'])
    b.group('Entradas optoacopladas')
    b.part('TERM_6P_381', 'ENTRADAS', {'1': 'IN1_P', '2': 'IN2_P', '3': 'IN3_P', '4': 'IN4_P', '5': 'IN_COM',
                                       '6': '+12V_AUX'}, ref='J8')
    b.two('PTC_1812', '0,1 A', '+12V', '+12V_AUX', 'F', mpn='1812L010/60DR', fab='Littelfuse')
    for i in range(1, 5):
        b.R('3.3k', f'IN{i}_P', f'OPTO{i}_A', '1206')
        b.D('D_SOD123', '1N4148W', f'OPTO{i}_A', 'IN_COM', mpn='1N4148W-7-F', fab='Diodes Inc.')
        b.part('LTV-817S', 'LTV-817S', {'A': f'OPTO{i}_A', 'K': 'IN_COM', 'C': f'GPI{i}', 'E': 'GND'})
        b.R('10k', '+3V3', f'GPI{i}')
    b.group('Relés')
    uln = {'I1': 'GPO1', 'I2': 'GPO2', 'I3': 'GPO3', 'I4': 'GPO4', 'I5': 'GND', 'I6': 'GND', 'I7': 'GND',
           'O1': 'K1_DRV', 'O2': 'K2_DRV', 'O3': 'K3_DRV', 'O4': 'K4_DRV', 'COM': '+5V', 'GND': 'GND'}
    b.part('ULN2003A', 'ULN2003A', uln)
    b.decouple('+5V', ['10uF', '100nF'])
    for i in range(1, 5):
        b.part('G5V-1', 'G5V-1 5V', {'COIL+': '+5V', 'COIL-': f'K{i}_DRV', 'COM': f'RLY{i}_C', 'NO': f'RLY{i}_NA',
                                     'NC': f'RLY{i}_NF'})
        b.R('1k', '+5V', f'K{i}_LED')
        b.D('LED_0603', 'amarelo', f'K{i}_DRV', f'K{i}_LED', mpn='19-217/Y5C-AM1N1VY/3T', fab='Everlight')
        b.R('10k', f'GPO{i}', 'GND')
    rl = {}
    for i in range(1, 5):
        rl[str(3 * i - 2)], rl[str(3 * i - 1)], rl[str(3 * i)] = f'RLY{i}_C', f'RLY{i}_NA', f'RLY{i}_NF'
    b.part('TERM_12P_381', 'RELÉS', rl, ref='J9')
    b.group('LEDs do painel')
    for net, cor, mpn in (('LED_OK', 'verde', '19-217/GHC-YR1S2/3T'), ('LED_ALM', 'vermelho', '19-217/R6C-AL1M2VY/3T')):
        b.R('330', net, f'{net}_A')
        b.D('LED_0603', cor, 'GND', f'{net}_A', mpn=mpn, fab='Everlight')
    b.R('1k', 'CM4_3V3', 'LED_PWR_A')
    b.D('LED_0603', 'verde (PWR)', 'LED_PWR_N', 'LED_PWR_A', mpn='19-217/GHC-YR1S2/3T', fab='Everlight')
    b.R('1k', 'CM4_3V3', 'LED_ACT_A')
    b.D('LED_0603', 'amarelo (ACT)', 'LED_ACT_N', 'LED_ACT_A', mpn='19-217/Y5C-AM1N1VY/3T', fab='Everlight')
    b.group('Relógio de tempo real')
    b.part('PCF85063ATL', 'PCF85063A', {'OSCI': 'RTC_XI', 'OSCO': 'RTC_XO', 'CLKOE': 'GND', 'VSS': 'GND',
                                        'SDA': 'I2C0_SDA', 'SCL': 'I2C0_SCL', 'VDD': 'RTC_VDD'})
    b.part('XTAL_2P', '32.768 kHz', {'X1': 'RTC_XI', 'X2': 'RTC_XO'})
    b.part('BAT54C', 'BAT54C', {'A1': '+3V3', 'A2': 'VBAT', 'K': 'RTC_VDD'})
    b.part('BAT_CR1220', 'CR1220', {'+': 'VBAT', '-': 'GND'})
    b.decouple('RTC_VDD', ['100nF'])
    b.group('Ventoinha')
    b.part('EMC2301', 'EMC2301', {'SDA': 'I2C0_SDA', 'SCL': 'I2C0_SCL', 'VDD': '+3V3', 'GND': 'GND', 'PWM': 'FAN_PWM',
                                  'TACH': 'FAN_TACH', 'CLK': 'GND'})
    b.decouple('+3V3', ['100nF'])
    b.R('10k', '+3V3', 'FAN_TACH')
    b.part('FAN_4P', 'VENTOINHA 12 V', {'GND': 'GND', '+12V': '+12V', 'TACH': 'FAN_TACH', 'PWM': 'FAN_PWM'}, ref='J10')
    b.group('Console e fixação')
    b.part('HDR_1x03', 'CONSOLE', {'1': 'GND', '2': 'CON_TX', '3': 'CON_RX'}, ref='J11')


# =============================================================================
def nets_of(b):
    nets = {}
    for c in b.comps.values():
        for p, n in c.pins.items():
            if n:
                nets.setdefault(n, []).append((c.ref, p))
    return nets


def check(b):
    nets = nets_of(b)
    single = {n: v for n, v in nets.items() if len(v) < 2}
    assert not single, f'redes com um pino só: {single}'
    # todos os pinos de alimentação ligados
    for c in b.comps.values():
        s = parts.SYMS[c.sym]
        for p in s.pins:
            if p.etype in ('power_in',) and not c.pins.get(p.num):
                raise AssertionError(f'{c.ref} {p.name}: pino de alimentação solto')
    return nets


def review(b):
    print(f'{len(b.comps)} componentes, {len(nets_of(b))} redes, {len(b.sheets)} folhas')
    for c in b.comps.values():
        s = parts.SYMS[c.sym]
        nc = [p.name for p in s.pins if not c.pins.get(p.num) and p.etype != 'no_connect']
        if nc and len(s.pins) > 3:
            print(f'  {c.ref:5} {c.sym:18} sem conexão: {", ".join(sorted(set(nc)))[:300]}')


if __name__ == '__main__':
    review(build())
