"""Biblioteca de símbolos da placa LiveSafe - Marcos Silva dos Santos.

Gera símbolos KiCad 7 (.kicad_sym) a partir de descrições em Python. Cada CI é
um retângulo com os pinos agrupados por função em cada lado (alimentação em
cima, terra embaixo, entradas à esquerda, saídas à direita). Pinos de mesmo
nome marcados como empilhados ficam na mesma posição, como nos símbolos dos
fabricantes. Símbolos grandes (CM4) são divididos em unidades.
"""
G = 2.54
LIBNAME = 'livesafe'
CHAR_W = 1.05  # largura média de um caractere do texto de 1,27 mm


def _f(v):
    s = f'{v:.4f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def esc(s):
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


def disp_len(name):
    return len(name.replace('~{', '').replace('}', ''))


class Pin:
    def __init__(self, num, name, x, y, angle, etype='passive', length=G, hide_name=False, unit=1):
        self.num, self.name, self.x, self.y, self.angle = str(num), name, x, y, angle
        self.etype, self.length, self.hide_name, self.unit = etype, length, hide_name, unit


class Symbol:
    def __init__(self, name, ref='U', footprint='', desc='', power=False):
        self.name, self.ref, self.footprint, self.desc, self.power = name, ref, footprint, desc, power
        self.pins = []
        self.graphics = {}  # unidade -> lista de s-expressions
        self.nunits = 1
        self.hide_pin_names = False
        self.hide_pin_numbers = False
        self.ref_pos = {1: (0, 0)}
        self.val_pos = {1: (0, -G)}
        self.bbox = {1: (-5, -5, 5, 5)}
        self.unit_names = {}

    def pin(self, num):
        for p in self.pins:
            if p.num == str(num):
                return p
        raise KeyError(f'{self.name}: pino {num} inexistente')

    def unit_pins(self, u):
        return [p for p in self.pins if p.unit == u]

    def sexpr(self, libname=None):
        full = f'{libname}:{self.name}' if libname else self.name
        o = [f'(symbol "{full}"']
        if self.power:
            o.append('(power)')
        if self.hide_pin_numbers:
            o.append('(pin_numbers hide)')
        o.append('(pin_names (offset 0) hide)' if self.hide_pin_names else '(pin_names (offset 0.762))')
        o.append('(in_bom yes) (on_board yes)')
        rx, ry = self.ref_pos[1]
        vx, vy = self.val_pos[1]
        hr = ' hide' if self.power else ''
        o.append(f'(property "Reference" "{self.ref}" (at {_f(rx)} {_f(ry)} 0) (effects (font (size 1.27 1.27)){hr}))')
        o.append(f'(property "Value" "{esc(self.name)}" (at {_f(vx)} {_f(vy)} 0) (effects (font (size 1.27 1.27))))')
        o.append(f'(property "Footprint" "{self.footprint}" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))')
        o.append('(property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))')
        if self.desc:
            o.append(f'(property "ki_description" "{esc(self.desc)}" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))')
        for u in range(1, self.nunits + 1):
            g = ' '.join(self.graphics.get(u, []))
            o.append(f'(symbol "{self.name}_{u}_0" {g})')
            ps = []
            for p in self.unit_pins(u):
                hide = ' hide' if p.hide_name else ''
                ps.append(f'(pin {p.etype} line (at {_f(p.x)} {_f(p.y)} {p.angle}) (length {_f(p.length)})'
                          f' (name "{esc(p.name)}" (effects (font (size 1.27 1.27)){hide}))'
                          f' (number "{p.num}" (effects (font (size 1.27 1.27)))))')
            o.append(f'(symbol "{self.name}_{u}_1" ' + ' '.join(ps) + ')')
        o.append(')')
        return ' '.join(o)


def rect(x1, y1, x2, y2, fill='background', w=0.254):
    return (f'(rectangle (start {_f(x1)} {_f(y1)}) (end {_f(x2)} {_f(y2)}) (stroke (width {w}) (type default)) '
            f'(fill (type {fill})))')


def poly(pts, fill='none', w=0.254):
    p = ' '.join(f'(xy {_f(x)} {_f(y)})' for x, y in pts)
    return f'(polyline (pts {p}) (stroke (width {w}) (type default)) (fill (type {fill})))'


def circle(x, y, r, fill='none', w=0.254):
    return f'(circle (center {_f(x)} {_f(y)}) (radius {_f(r)}) (stroke (width {w}) (type default)) (fill (type {fill})))'


def arc(sx, sy, mx, my, ex, ey, w=0.254):
    return (f'(arc (start {_f(sx)} {_f(sy)}) (mid {_f(mx)} {_f(my)}) (end {_f(ex)} {_f(ey)}) '
            f'(stroke (width {w}) (type default)) (fill (type none)))')


def text(t, x, y, size=1.27):
    return f'(text "{esc(t)}" (at {_f(x)} {_f(y)} 0) (effects (font (size {size} {size}))))'


# ----------------------------------------------------------------------------
# CI genérico
# ----------------------------------------------------------------------------
def _snap(v):
    return round(v / G) * G


def ic(name, pins, sides, footprint='', desc='', ref='U', stacked=(), units=None, min_w=0):
    """Cria um CI retangular.

    pins:   lista de (número, nome, tipo) - tipo: input, output, bidirectional,
            power_in, power_out, passive, open_collector, no_connect...
    sides:  {'L': [...], 'R': [...], 'T': [...], 'B': [...]} com nomes de pino
            (ou números como '#12' para escolher um pino específico) e None
            como espaço. Pinos não listados vão para a esquerda.
    stacked: nomes cujos pinos ficam empilhados na mesma posição.
    units:  lista de dicionários sides, um por unidade (símbolos grandes).
    """
    s = Symbol(name, ref, footprint, desc)
    bynum = {str(n): (str(n), nm, t) for n, nm, t in pins}
    byname = {}
    for n, nm, t in pins:
        byname.setdefault(nm, []).append(str(n))
    unit_sides = units or [sides]
    s.nunits = len(unit_sides)
    used = set()
    for ui, sd in enumerate(unit_sides, 1):
        # resolve nomes em listas de grupos de pinos (um grupo = uma posição)
        res = {}
        for side in 'LRTB':
            out = []
            for item in sd.get(side, []):
                if item is None:
                    out.append(None)
                    continue
                if item.startswith('#'):
                    nums = [item[1:]]
                else:
                    if item not in byname:
                        raise KeyError(f'{name}: pino "{item}" não existe')
                    nums = [n for n in byname[item] if n not in used]
                if item in stacked or (not item.startswith('#') and len(nums) > 1 and item in stacked):
                    out.append(nums)
                    used.update(nums)
                else:
                    for n in nums:
                        out.append([n])
                        used.add(n)
            res[side] = out
        if ui == len(unit_sides):
            rest = [n for n in bynum if n not in used]
            # pinos esquecidos: empilhados por nome se forem empilháveis
            for n in rest:
                if n in used:
                    continue
                nm = bynum[n][1]
                if nm in stacked:
                    grp = [m for m in byname[nm] if m not in used]
                    res['L'].append(grp)
                    used.update(grp)
                else:
                    res['L'].append([n])
                    used.add(n)
        _layout_unit(s, ui, res, bynum, min_w)
    missing = [n for n in bynum if n not in used]
    assert not missing, f'{name}: pinos sem posição {missing}'
    return s


def _layout_unit(s, u, res, bynum, min_w):
    def nmlen(side):
        lens = [disp_len(bynum[g[0]][1]) for g in res[side] if g]
        return max(lens) if lens else 0
    nl, nr = len(res['L']), len(res['R'])
    nt, nb = len(res['T']), len(res['B'])
    # largura: nomes da esquerda + direita, ou o espaço dos pinos de cima/baixo
    w_names = (nmlen('L') + nmlen('R')) * CHAR_W + 5
    w_tb = (max(nt, nb) + 1) * G
    w = _snap(max(w_names, w_tb, min_w, 10.16) + G / 2)
    if (w / G) % 2:
        w += G
    vt = nmlen('T') * CHAR_W + 2 if nt else 0
    vb = nmlen('B') * CHAR_W + 2 if nb else 0
    h_lr = (max(nl, nr) + 1) * G
    h = _snap(max(h_lr + vt + vb, 7.62) + G / 2)
    if (h / G) % 2:
        h += G
    x0, x1 = -w / 2, w / 2
    y1, y0 = h / 2, -h / 2  # y para cima
    L = G
    # lados esquerdo/direito: começam abaixo da área dos nomes de cima
    ytop = _snap(y1 - max(vt, 0) - G) if nt else y1 - G
    for i, g in enumerate(res['L']):
        if g:
            for k, n in enumerate(g):
                _add(s, u, bynum[n], x0 - L, ytop - i * G, 0, k)
    for i, g in enumerate(res['R']):
        if g:
            for k, n in enumerate(g):
                _add(s, u, bynum[n], x1 + L, ytop - i * G, 180, k)
    for side, yy, ang in (('T', y1 + L, 270), ('B', y0 - L, 90)):
        cnt = len(res[side])
        xs = _snap(-(cnt - 1) * G / 2)
        for i, g in enumerate(res[side]):
            if g:
                for k, n in enumerate(g):
                    _add(s, u, bynum[n], xs + i * G, yy, ang, k)
    s.graphics.setdefault(u, []).append(rect(x0, y0, x1, y1))
    s.bbox[u] = (x0 - L, y0 - L, x1 + L, y1 + L)
    s.ref_pos[u] = (x0, y1 + 1.27)
    s.val_pos[u] = (x0, y0 - 1.27)


def _add(s, u, pdesc, x, y, ang, k):
    num, nm, t = pdesc
    if k > 0 and t == 'power_in':
        t = 'passive'  # empilhados: só o primeiro é power_in
    s.pins.append(Pin(num, nm, round(x, 4), round(y, 4), ang, t, unit=u))


# ----------------------------------------------------------------------------
# Passivos e diversos (2 pinos verticais: pino 1 em cima)
# ----------------------------------------------------------------------------
def two_pin(name, ref, body, footprint='', desc='', etype='passive', pin_names=('~', '~'), length=None):
    s = Symbol(name, ref, footprint, desc)
    s.hide_pin_names = True
    s.hide_pin_numbers = True
    L = length or 1.27
    s.pins = [Pin(1, pin_names[0], 0, 3.81, 270, etype, length=L), Pin(2, pin_names[1], 0, -3.81, 90, etype, length=L)]
    s.graphics[1] = body
    s.bbox[1] = (-1.5, -3.81, 1.5, 3.81)
    s.ref_pos[1] = (2.0, 0.9)
    s.val_pos[1] = (2.0, -0.9)
    return s


def resistor(name='R', footprint='Resistor_SMD:R_0402_1005Metric'):
    return two_pin(name, 'R', [rect(-0.762, -2.54, 0.762, 2.54, 'none')], footprint, 'Resistor')


def capacitor(name='C', footprint='Capacitor_SMD:C_0402_1005Metric', polar=False):
    g = [poly([(-1.524, 0.508), (1.524, 0.508)], w=0.3), poly([(-1.524, -0.508), (1.524, -0.508)], w=0.3),
         poly([(0, 2.54), (0, 0.508)]), poly([(0, -2.54), (0, -0.508)])]
    if polar:
        g = [poly([(-1.524, 0.508), (1.524, 0.508)], w=0.3), arc(-1.524, -1.0, 0, -0.55, 1.524, -1.0, w=0.3),
             poly([(0, 2.54), (0, 0.508)]), poly([(0, -2.54), (0, -0.62)]), text('+', -1.6, 1.4, 1.0)]
    s = two_pin(name, 'C', g, footprint, 'Capacitor')
    s.pins[0].length = 1.27
    s.pins[1].length = 1.27
    return s


def inductor(name='L', footprint=''):
    g = [arc(0, 2.54, 0.635, 1.905, 0, 1.27), arc(0, 1.27, 0.635, 0.635, 0, 0),
         arc(0, 0, 0.635, -0.635, 0, -1.27), arc(0, -1.27, 0.635, -1.905, 0, -2.54)]
    return two_pin(name, 'L', g, footprint, 'Indutor')


def ferrite(name='FB', footprint='Inductor_SMD:L_0603_1608Metric'):
    g = [poly([(-1.4, -0.6), (0.2, 2.2), (1.4, 1.5), (-0.2, -1.3), (-1.4, -0.6)]),
         poly([(0, 2.54), (0, 1.85)]), poly([(0, -2.54), (0, -0.95)])]
    return two_pin(name, 'FB', g, footprint, 'Ferrite')


def diode(name='D', footprint='', kind='D'):
    """Diodo vertical: pino 1 = catodo (em cima), pino 2 = anodo."""
    g = [poly([(-1.27, -0.889), (1.27, -0.889), (0, 0.889), (-1.27, -0.889)], 'none'),
         poly([(-1.27, 0.889), (1.27, 0.889)]), poly([(0, 2.54), (0, -2.54)])]
    if kind == 'Z':
        g[1] = poly([(-1.27, 0.5), (-1.27, 0.889), (1.27, 0.889), (1.27, 1.27)])
    if kind == 'TVS':
        g = [poly([(-1.27, -2.0), (1.27, -2.0), (0, 0), (-1.27, -2.0)], 'none'),
             poly([(-1.27, 2.0), (1.27, 2.0), (0, 0), (-1.27, 2.0)], 'none'),
             poly([(-1.8, 0.4), (-1.27, 0), (1.27, 0), (1.8, -0.4)]), poly([(0, 2.54), (0, -2.54)])]
    if kind == 'LED':
        g += [poly([(1.6, 0.3), (2.6, 1.3)]), poly([(2.0, 1.3), (2.6, 1.3), (2.6, 0.7)]),
              poly([(1.6, -0.7), (2.6, 0.3)]), poly([(2.0, 0.3), (2.6, 0.3), (2.6, -0.3)])]
    s = two_pin(name, 'D', g, footprint, {'D': 'Diodo', 'Z': 'Zener', 'TVS': 'TVS', 'LED': 'LED'}[kind],
                pin_names=('K', 'A'))
    return s


def fuse(name='F', footprint=''):
    g = [rect(-0.762, -2.54, 0.762, 2.54, 'none'), poly([(0, 2.54), (0, -2.54)], w=0.15)]
    return two_pin(name, 'F', g, footprint, 'Fusível rearmável')


def testpoint(name='TP', footprint='TestPoint:TestPoint_Pad_D1.0mm'):
    s = Symbol(name, 'TP', footprint, 'Ponto de teste')
    s.hide_pin_names = True
    s.hide_pin_numbers = True
    s.pins = [Pin(1, '1', 0, -2.54, 90, 'passive', length=1.27)]
    s.graphics[1] = [circle(0, 0, 0.762)]
    s.bbox[1] = (-1, -2.54, 1, 1)
    s.ref_pos[1] = (1.5, 0.6)
    s.val_pos[1] = (1.5, -0.8)
    return s


def mounting_hole(name='MH', footprint='MountingHole:MountingHole_3.2mm_M3_Pad_Via'):
    s = Symbol(name, 'H', footprint, 'Furo de fixação aterrado')
    s.hide_pin_names = True
    s.hide_pin_numbers = True
    s.pins = [Pin(1, '1', 0, -2.54, 90, 'passive', length=1.27)]
    s.graphics[1] = [circle(0, 0, 1.0), circle(0, 0, 0.4)]
    s.bbox[1] = (-1.2, -2.54, 1.2, 1.2)
    s.ref_pos[1] = (1.8, 0.6)
    s.val_pos[1] = (1.8, -0.8)
    return s


def logo(name, footprint):
    s = Symbol(name, 'G', footprint, 'Logotipo / identificação na serigrafia')
    s.graphics[1] = [rect(-2, -1, 2, 1, 'none')]
    s.bbox[1] = (-2, -1, 2, 1)
    s.ref_pos[1] = (-2, 2)
    s.val_pos[1] = (-2, -2.2)
    return s


def power_sym(name, gnd=False):
    s = Symbol(name, '#PWR', '', f'Símbolo de alimentação {name}', power=True)
    s.hide_pin_numbers = True
    s.hide_pin_names = True
    if gnd:
        s.pins = [Pin(1, name, 0, 0, 270, 'power_in', length=0)]
        s.graphics[1] = [poly([(0, 0), (0, -1.27), (1.27, -1.27), (0, -2.54), (-1.27, -1.27), (0, -1.27)])]
        s.val_pos[1] = (0, -3.81)
        s.bbox[1] = (-1.3, -2.6, 1.3, 0)
    else:
        s.pins = [Pin(1, name, 0, 0, 90, 'power_in', length=0)]
        s.graphics[1] = [poly([(-0.762, 1.27), (0, 2.54)]), poly([(0, 0), (0, 2.54)]), poly([(0, 2.54), (0.762, 1.27)])]
        s.val_pos[1] = (0, 3.556)
        s.bbox[1] = (-1, 0, 1, 2.6)
    s.ref_pos[1] = (0, -6.35 if gnd else -3.81)
    return s


def pwr_flag():
    s = Symbol('PWR_FLAG', '#FLG', '', 'Marca a rede como alimentada (ERC)', power=True)
    s.hide_pin_numbers = True
    s.hide_pin_names = True
    s.pins = [Pin(1, 'pwr', 0, 0, 90, 'power_out', length=0)]
    s.graphics[1] = [poly([(0, 0), (0, 1.27), (-1.016, 1.905), (0, 2.54), (1.016, 1.905), (0, 1.27)])]
    s.val_pos[1] = (0, 3.81)
    s.ref_pos[1] = (0, 1.905)
    s.bbox[1] = (-1.1, 0, 1.1, 2.6)
    return s


def write_library(symbols, path):
    o = ['(kicad_symbol_lib (version 20220914) (generator gerador_livesafe)']
    for s in sorted(symbols.values(), key=lambda x: x.name):
        o.append('  ' + s.sexpr())
    o.append(')')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(o) + '\n')
