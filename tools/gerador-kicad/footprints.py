"""Footprints próprios da placa LiveSafe - Marcos Silva dos Santos.

  Raspberry_Pi_CM4_DF40             cópia do footprint oficial da CM4IO (2x DF40, 4 furos M2,5)
  Toshiba_P-TFBGA64-0606-0.65       TC358743XBG: 8x8 esferas, passo 0,65 mm, corpo 6x6 mm
  Skyworks_QFN-24_3x3mm_...         Si2141: QFN-24 passo 0,4 mm com pads nos 4 cantos (e1 = 0,45 mm)

Os demais vêm das bibliotecas oficiais do KiCad 7.
"""
import os
import re
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
CM4IO = os.environ.get('CM4IO_PRETTY', os.path.join(ROOT, 'ref', 'CM4IO.pretty'))


def U():
    return str(uuid.uuid4())


def f(v):
    s = f'{v:.4f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def line(x1, y1, x2, y2, layer, w=0.12):
    return (f'  (fp_line (start {f(x1)} {f(y1)}) (end {f(x2)} {f(y2)}) (stroke (width {w}) (type solid)) '
            f'(layer "{layer}") (tstamp {U()}))')


def rect(x1, y1, x2, y2, layer, w=0.12):
    return [line(x1, y1, x2, y1, layer, w), line(x2, y1, x2, y2, layer, w), line(x2, y2, x1, y2, layer, w),
            line(x1, y2, x1, y1, layer, w)]


def circle(x, y, r, layer, w=0.12, fill=False):
    fl = ' (fill solid)' if fill else ' (fill none)'
    return (f'  (fp_circle (center {f(x)} {f(y)}) (end {f(x + r)} {f(y)}) (stroke (width {w}) (type solid)){fl} '
            f'(layer "{layer}") (tstamp {U()}))')


def texts(ref_y, val_y):
    return [f'  (fp_text reference "REF**" (at 0 {f(ref_y)}) (layer "F.SilkS") '
            f'(effects (font (size 1 1) (thickness 0.15))) (tstamp {U()}))',
            f'  (fp_text value "VAL**" (at 0 {f(val_y)}) (layer "F.Fab") '
            f'(effects (font (size 1 1) (thickness 0.15))) (tstamp {U()}))',
            f'  (fp_text user "${{REFERENCE}}" (at 0 0) (layer "F.Fab") '
            f'(effects (font (size 0.5 0.5) (thickness 0.08))) (tstamp {U()}))']


def smd(num, x, y, w, h, shape='roundrect', layers='"F.Cu" "F.Paste" "F.Mask"', extra=''):
    rr = ' (roundrect_rratio 0.25)' if shape == 'roundrect' else ''
    return (f'  (pad "{num}" smd {shape} (at {f(x)} {f(y)}) (size {f(w)} {f(h)}) (layers {layers}){rr}{extra} '
            f'(tstamp {U()}))')


def header(name, desc, tags, attr='smd'):
    return [f'(footprint "{name}" (version 20221018) (generator gerador_livesafe)', '  (layer "F.Cu")',
            f'  (descr "{desc}")', f'  (tags "{tags}")', f'  (attr {attr})']


def model(path, offset=(0, 0, 0), rotate=(0, 0, 0)):
    return [f'  (model "{path}"', f'    (offset (xyz {f(offset[0])} {f(offset[1])} {f(offset[2])}))',
            '    (scale (xyz 1 1 1))', f'    (rotate (xyz {f(rotate[0])} {f(rotate[1])} {f(rotate[2])}))', '  )']


# ---------------------------------------------------------------------------
def tc358743():
    name = 'Toshiba_P-TFBGA64-0606-0.65'
    o = header(name, 'Toshiba P-TFBGA64-0606-0.65-001 (TC358743XBG), 8x8 esferas, passo 0,65 mm, pad NSMD 0,30 mm',
               'BGA 64 0.65 TC358743')
    body, p = 6.0, 0.65
    h = body / 2
    o += texts(-h - 1.2, h + 1.2)
    o += rect(-h, -h, h, h, 'F.Fab', 0.1)
    o.append(line(-h, -h + 1, -h + 1, -h, 'F.Fab', 0.1))
    s = h + 0.11
    for x1, y1, x2, y2 in ((-s, -s + 0.6, -s, -s), (-s, -s, -s + 0.6, -s), (s - 0.6, -s, s, -s), (s, -s, s, -s + 0.6),
                           (s, s - 0.6, s, s), (s, s, s - 0.6, s), (-s + 0.6, s, -s, s), (-s, s, -s, s - 0.6)):
        o.append(line(x1, y1, x2, y2, 'F.SilkS'))
    o.append(circle(-s - 0.35, -s - 0.35, 0.12, 'F.SilkS', 0.12, True))
    o += rect(-h - 0.5, -h - 0.5, h + 0.5, h + 0.5, 'F.CrtYd', 0.05)
    rows = 'ABCDEFGH'
    for r, rn in enumerate(rows):
        for c in range(8):
            x, y = (c - 3.5) * p, (r - 3.5) * p
            o.append(f'  (pad "{rn}{c + 1}" smd circle (at {f(x)} {f(y)}) (size 0.3 0.3) '
                     f'(layers "F.Cu" "F.Paste" "F.Mask") (solder_mask_margin 0.05) (tstamp {U()}))')
    o += model('${KICAD7_3DMODEL_DIR}/Package_BGA.3dshapes/TFBGA-64_5x5mm_Layout8x8_P0.5mm.wrl')
    o.append(')')
    return name, '\n'.join(o) + '\n'


def si2141():
    name = 'Skyworks_QFN-24_3x3mm_P0.4mm_EP1.7mm_CornerPads'
    o = header(name, 'Skyworks Si2141 QFN-24 3x3 mm, passo 0,4 mm, pads de canto 1/7/13/19 (e1 = 0,45 mm), '
                     'pad exposto 1,70 mm. Conferir L, b, L1 e b1 no desenho completo antes da produção.',
               'QFN 24 Si2141 Skyworks')
    h, pitch, pl, pw, pc = 1.5, 0.4, 0.60, 0.20, 1.45
    o += texts(-h - 1.3, h + 1.3)
    o += rect(-h, -h, h, h, 'F.Fab', 0.1)
    o.append(line(-h, h - 0.6, -h + 0.6, h, 'F.Fab', 0.1))
    s = h + 0.11
    for x1, y1, x2, y2 in ((s - 0.15, -s, s, -s), (s, -s, s, -s + 0.15), (-s + 0.15, -s, -s, -s),
                           (-s, -s, -s, -s + 0.15), (s - 0.15, s, s, s), (s, s, s, s - 0.15)):
        o.append(line(x1, y1, x2, y2, 'F.SilkS'))
    o.append(circle(-s - 0.3, s + 0.3, 0.12, 'F.SilkS', 0.12, True))  # pino 1: canto inferior esquerdo
    o += rect(-h - 0.55, -h - 0.55, h + 0.55, h + 0.55, 'F.CrtYd', 0.05)
    xs = [(-2 + i) * pitch for i in range(5)]
    for i, x in enumerate(xs):  # baixo: 2..6, esquerda -> direita
        o.append(smd(2 + i, x, pc, pw, pl))
    for i, y in enumerate(reversed(xs)):  # direita: 8..12, de baixo para cima
        o.append(smd(8 + i, pc, y, pl, pw))
    for i, x in enumerate(reversed(xs)):  # cima: 14..18, direita -> esquerda
        o.append(smd(14 + i, x, -pc, pw, pl))
    for i, y in enumerate(xs):  # esquerda: 20..24, de cima para baixo
        o.append(smd(20 + i, -pc, y, pl, pw))
    c = 0.8 + 0.45
    for num, x, y in ((1, -c, c), (7, c, c), (13, c, -c), (19, -c, -c)):
        o.append(smd(num, x, y, 0.28, 0.28))
    o.append(smd(25, 0, 0, 1.7, 1.7, 'roundrect', '"F.Cu" "F.Mask"', ' (zone_connect 2)'))
    for x in (-0.42, 0.42):
        for y in (-0.42, 0.42):
            o.append(smd(25, x, y, 0.68, 0.68, 'roundrect', '"F.Paste"'))
    o += model('${KICAD7_3DMODEL_DIR}/Package_DFN_QFN.3dshapes/QFN-24-1EP_3x3mm_P0.4mm_EP1.75x1.6mm.wrl')
    o.append(')')
    return name, '\n'.join(o) + '\n'


def cm4():
    name = 'Raspberry_Pi_CM4_DF40'
    src = os.path.join(CM4IO, 'Raspberry-Pi-4-Compute-Module.kicad_mod')
    t = open(src, encoding='utf-8').read()
    t = re.sub(r'^\(footprint "[^"]+"', f'(footprint "{name}"', t, count=1)
    t = re.sub(r'^\(module "?[^" ]+"?', f'(footprint "{name}"', t, count=1)
    t = re.sub(r'\n\s*\(model .*?\n\s*\)\n', '\n', t, flags=re.S)
    t = t.rstrip()
    assert t.endswith(')')
    t = t[:-1] + '\n' + '\n'.join(model('${KIPRJMOD}/../bibliotecas/livesafe.3dshapes/RPi_CM4.wrl')) + '\n)\n'
    t = t.replace('(descr "', '(descr "Raspberry Pi CM4 - footprint oficial da placa CM4IO (Raspberry Pi Ltd). ', 1)
    return name, t


def write_all(outdir):
    os.makedirs(outdir, exist_ok=True)
    out = []
    for fn in (tc358743, si2141, cm4):
        name, txt = fn()
        with open(os.path.join(outdir, name + '.kicad_mod'), 'w', encoding='utf-8') as fh:
            fh.write(txt)
        out.append(name)
    return out


if __name__ == '__main__':
    import sys
    print(write_all(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'hardware', 'kicad', 'bibliotecas',
                                                                      'livesafe.pretty')))


# ---------------------------------------------------------------------------
# Modelo 3D simplificado do CM4 montado (VRML 2.0, unidade KiCad = 2,54 mm)
def _box(x1, y1, z1, x2, y2, z2, rgb, shin=0.2):
    s = 1 / 2.54
    X1, X2 = x1 * s, x2 * s
    Y1, Y2 = -y2 * s, -y1 * s  # footprint: y para baixo; VRML: y para cima
    Z1, Z2 = z1 * s, z2 * s
    pts = [(X1, Y1, Z1), (X2, Y1, Z1), (X2, Y2, Z1), (X1, Y2, Z1), (X1, Y1, Z2), (X2, Y1, Z2), (X2, Y2, Z2), (X1, Y2, Z2)]
    faces = '0,3,2,1,-1,4,5,6,7,-1,0,1,5,4,-1,1,2,6,5,-1,2,3,7,6,-1,3,0,4,7,-1'
    p = ', '.join(f'{a:.4f} {b:.4f} {c:.4f}' for a, b, c in pts)
    r, g, b = rgb
    return (f'Shape {{ appearance Appearance {{ material Material {{ diffuseColor {r} {g} {b} shininess {shin} '
            f'specularColor 0.2 0.2 0.2 }} }} geometry IndexedFaceSet {{ coord Coordinate {{ point [ {p} ] }} '
            f'coordIndex [ {faces} ] }} }}')


def cm4_wrl():
    """CM4 sobre os 2 conectores DF40 (altura de encaixe 1,5 mm). Coordenadas do footprint CM4IO:
    contorno x -3,5..36,5, y -51,5..3,5; conectores em x -0,5 e 33,5, y -32,9..-10,1."""
    z0, t = 1.5, 1.2
    green, black, silver, gold = (0.05, 0.36, 0.18), (0.08, 0.08, 0.09), (0.75, 0.76, 0.78), (0.85, 0.65, 0.2)
    shapes = [
        _box(-1.9, -32.9, 0, 0.9, -10.1, z0, (0.9, 0.9, 0.88)),       # DF40 da placa (bege)
        _box(32.1, -32.9, 0, 34.9, -10.1, z0, (0.9, 0.9, 0.88)),
        _box(-3.5, -51.5, z0, 36.5, 3.5, z0 + t, green),              # placa do CM4
        _box(8.5, -40.0, z0 + t, 23.5, -25.0, z0 + t + 1.4, silver),  # SoC BCM2711 (tampa metálica)
        _box(8.0, -21.5, z0 + t, 22.0, -11.5, z0 + t + 1.0, black),   # LPDDR4
        _box(24.5, -22.0, z0 + t, 34.0, -10.0, z0 + t + 1.0, black),  # eMMC
        _box(26.0, -45.0, z0 + t, 32.0, -39.0, z0 + t + 0.9, black),  # PHY Ethernet
        _box(0.5, -46.0, z0 + t, 6.5, -40.0, z0 + t + 0.9, black),    # PMIC
        _box(0.5, -8.0, z0 + t, 4.5, -4.0, z0 + t + 0.8, black),      # EEPROM / RTC
    ]
    for hx, hy in ((0, 0), (33, 0), (0, -48), (33, -48)):           # furos M2,5 com anel dourado
        shapes.append(_box(hx - 1.6, hy - 1.6, z0 + t, hx + 1.6, hy + 1.6, z0 + t + 0.02, gold))
    return '#VRML V2.0 utf8\n# Raspberry Pi CM4 (modelo simplificado) - placa LiveSafe\n' + '\n'.join(shapes) + '\n'


def write_3d(outdir):
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, 'RPi_CM4.wrl'), 'w') as f:
        f.write(cm4_wrl())
