"""Escritor do esquemático hierárquico KiCad 7 - placa LiveSafe (Marcos Silva dos Santos).

Uma folha raiz com os blocos (folhas filhas) e uma folha por bloco do
designs.py. As ligações são feitas por rótulos globais em cada pino e por
símbolos de alimentação nos trilhos principais. Dentro de cada folha os
componentes ficam agrupados por função, em quadros tracejados com título.
"""
import math
import os
import uuid

import parts
import symlib
from symlib import G, _f, esc, disp_len

AUTHOR = 'Marcos Silva dos Santos'
NICK = 'MarcosObel'
COMPANY = 'LiveSafe - monitoração de sinal de TV e rádio'
REPO = 'github.com/aragonxpd154/LiveSafe-Monitor'
DATE = '2026-11-23'
PROJECT = 'livesafe-placa'
POWER_NETS = ('GND', '+12V', '+5V', '+3V3', 'CM4_3V3')
PAPERS = [('A3', 420, 297), ('A2', 594, 420), ('A1', 841, 594)]


_NS = uuid.UUID('6b1c0f5e-3a51-4c7e-9a0e-11fe5afe0001')
_N = [0]


def U():
    """UUID determinístico (mesma ordem de geração = mesmos UUIDs): regerar o esquemático não quebra a
    ligação com a PCB já roteada."""
    _N[0] += 1
    return str(uuid.uuid5(_NS, f'{PROJECT}-{_N[0]}'))


def snap(v):
    return round(v / G) * G


def rot(x, y, ang):
    a = math.radians(ang)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)


def outward(pin_angle, sym_angle):
    """Direção (no esquema, y para baixo) em que o fio sai do pino."""
    a = math.radians(pin_angle + sym_angle)
    dx, dy = -math.cos(a), math.sin(a)
    return round(dx), round(dy)


def label_len(name):
    return disp_len(name) * 1.05 + 3.5


class Placed:
    """Uma unidade de símbolo a ser posicionada."""

    def __init__(self, comp, unit, sym, angle):
        self.comp, self.unit, self.sym, self.angle = comp, unit, sym, angle
        self.ext = self._extents()

    def pins(self):
        return [p for p in self.sym.pins if p.unit == self.unit]

    def _extents(self):
        x0, y0, x1, y1 = self.sym.bbox[self.unit]
        corners = [rot(x, y, self.angle) for x, y in ((x0, y0), (x0, y1), (x1, y0), (x1, y1))]
        xs = [c[0] for c in corners]
        ys = [-c[1] for c in corners]
        ex = [min(xs), min(ys) - 3.0, max(xs), max(ys) + 3.0]
        seen = set()
        for p in self.pins():
            px, py = rot(p.x, p.y, self.angle)
            px, py = px, -py
            if (round(px, 2), round(py, 2)) in seen:
                continue
            seen.add((round(px, 2), round(py, 2)))
            net = self.comp.pins.get(p.num)
            dx, dy = outward(p.angle, self.angle)
            if net is None:
                ext = 1.5
            elif net in POWER_NETS:
                ext = G + 4.5
            else:
                ext = G + label_len(net)
            if dx < 0:
                ex[0] = min(ex[0], px - ext)
            elif dx > 0:
                ex[2] = max(ex[2], px + ext)
            elif dy < 0:
                ex[1] = min(ex[1], py - ext)
            else:
                ex[3] = max(ex[3], py + ext)
        if self.sym.ref != '#PWR':
            # texto de referência/valor dos passivos girados fica embaixo
            vl = max(len(self.comp.value), len(self.comp.ref)) * 1.05
            if self.angle in (90, 270):
                ex[3] = max(ex[3], 6.0)
                ex[0] = min(ex[0], -vl / 2)
                ex[2] = max(ex[2], vl / 2)
        return ex

    @property
    def w(self):
        return self.ext[2] - self.ext[0]

    @property
    def h(self):
        return self.ext[3] - self.ext[1]


class SheetWriter:
    def __init__(self, board, sheet, root_uuid, sheet_uuid, page):
        self.b, self.s = board, sheet
        self.root, self.suid, self.page = root_uuid, sheet_uuid, page
        self.items = []
        self.used = set()
        self.npwr = 0
        self.uuids = {}

    # ---------------------------------------------------------------- itens
    def symbol(self, sym, ref, value, x, y, angle=0, unit=1, footprint='', fields=None, hide_ref=False,
               dnp=False, in_bom=True):
        self.used.add(sym.name)
        uid = U()
        rx, ry = sym.ref_pos.get(unit, (0, 0))
        vx, vy = sym.val_pos.get(unit, (0, -G))
        if angle in (90, 270) and not sym.power:
            # passivos girados: textos embaixo, na horizontal
            rpos, vpos = (x, y + 2.6, angle), (x, y + 4.4, angle)
        else:
            a, c = rot(rx, ry, angle), rot(vx, vy, angle)
            rpos, vpos = (x + a[0], y - a[1], 0), (x + c[0], y - c[1], 0)
        just = '' if angle in (90, 270) and not sym.power else (' (justify left)' if not sym.power else '')
        hr = ' hide' if hide_ref else ''
        o = [f'(symbol (lib_id "{symlib.LIBNAME}:{sym.name}") (at {_f(x)} {_f(y)} {angle}) (unit {unit})',
             f'(in_bom {"yes" if in_bom else "no"}) (on_board {"yes" if in_bom else "no"}) (dnp {"yes" if dnp else "no"})',
             f'(uuid {uid})',
             f'(property "Reference" "{ref}" (at {_f(rpos[0])} {_f(rpos[1])} {rpos[2]}) '
             f'(effects (font (size 1.27 1.27)){just}{hr}))',
             f'(property "Value" "{esc(value)}" (at {_f(vpos[0])} {_f(vpos[1])} {vpos[2]}) '
             f'(effects (font (size 1.27 1.27)){just}))',
             f'(property "Footprint" "{footprint}" (at {_f(x)} {_f(y)} 0) (effects (font (size 1.27 1.27)) hide))',
             f'(property "Datasheet" "" (at {_f(x)} {_f(y)} 0) (effects (font (size 1.27 1.27)) hide))']
        for k, v in (fields or {}).items():
            o.append(f'(property "{k}" "{esc(v)}" (at {_f(x)} {_f(y)} 0) (effects (font (size 1.27 1.27)) hide))')
        for p in sym.pins:
            o.append(f'(pin "{p.num}" (uuid {U()}))')
        o.append(f'(instances (project "{PROJECT}" (path "/{self.root}/{self.suid}" (reference "{ref}") (unit {unit}))))')
        o.append(')')
        self.items.append(' '.join(o))
        return uid

    def power(self, name, x, y, dx, dy):
        self.npwr += 1
        s = parts.SYMS[name]
        if name == 'GND':
            ang = {(0, 1): 0, (1, 0): 90, (0, -1): 180, (-1, 0): 270}[(dx, dy)]
        else:
            ang = {(0, -1): 0, (1, 0): 270, (0, 1): 180, (-1, 0): 90}[(dx, dy)]
        self.symbol(s, f'#PWR0{self.page:02d}{self.npwr:03d}', name, x, y, ang, hide_ref=True, in_bom=False)

    def flag(self, x, y):
        self.npwr += 1
        self.symbol(parts.SYMS['PWR_FLAG'], f'#FLG0{self.page:02d}{self.npwr:03d}', 'PWR_FLAG', x, y, 0,
                    hide_ref=True, in_bom=False)

    def wire(self, x1, y1, x2, y2):
        self.items.append(f'(wire (pts (xy {_f(x1)} {_f(y1)}) (xy {_f(x2)} {_f(y2)})) '
                          f'(stroke (width 0) (type default)) (uuid {U()}))')

    def glabel(self, name, x, y, dx, dy, shape='passive'):
        ang = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}[(dx, dy)]
        just = 'left' if ang in (0, 90) else 'right'
        self.items.append(f'(global_label "{esc(name)}" (shape {shape}) (at {_f(x)} {_f(y)} {ang}) (fields_autoplaced) '
                          f'(effects (font (size 1.27 1.27)) (justify {just})) (uuid {U()}) '
                          f'(property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {_f(x)} {_f(y)} 0) '
                          f'(effects (font (size 1.27 1.27)) hide)))')

    def noconn(self, x, y):
        self.items.append(f'(no_connect (at {_f(x)} {_f(y)}) (uuid {U()}))')

    def text(self, t, x, y, size=1.5, bold=False, italic=False):
        st = (' bold' if bold else '') + (' italic' if italic else '')
        self.items.append(f'(text "{esc(t)}" (at {_f(x)} {_f(y)} 0) (effects (font (size {size} {size}){st}) '
                          f'(justify left top)) (uuid {U()}))')

    def box(self, x0, y0, x1, y1, color='0 0 132 1'):
        self.items.append(f'(polyline (pts (xy {_f(x0)} {_f(y0)}) (xy {_f(x1)} {_f(y0)}) (xy {_f(x1)} {_f(y1)}) '
                          f'(xy {_f(x0)} {_f(y1)}) (xy {_f(x0)} {_f(y0)})) (stroke (width 0.2) (type dash) '
                          f'(color {color})) (uuid {U()}))')

    # ------------------------------------------------------------- conexões
    def connect(self, pl, X, Y):
        done = set()
        for p in pl.pins():
            px, py = rot(p.x, p.y, pl.angle)
            px, py = X + px, Y - py
            key = (round(px, 3), round(py, 3))
            if key in done:
                continue
            done.add(key)
            net = pl.comp.pins.get(p.num)
            dx, dy = outward(p.angle, pl.angle)
            if net is None:
                self.noconn(px, py)
                continue
            ex, ey = px + dx * G, py + dy * G
            self.wire(px, py, ex, ey)
            if net in POWER_NETS:
                self.power(net, ex, ey, dx, dy)
            else:
                self.glabel(net, ex, ey, dx, dy)

    # --------------------------------------------------------------- layout
    def placed_items(self, refs):
        out = []
        for ref in refs:
            c = self.b.comps[ref]
            s = parts.SYMS[c.sym]
            ang = 90 if len(s.pins) <= 2 and s.ref in ('R', 'C', 'L', 'FB', 'D', 'F') else 0
            for u in range(1, s.nunits + 1):
                out.append(Placed(c, u, s, ang))
        return out

    def layout_group(self, items, maxw):
        """Empacota os itens de um grupo em linhas. Retorna (w, h, [(item, ox, oy)])."""
        big = [i for i in items if i.sym.nunits > 1 or len(i.pins()) > 3]
        small = [i for i in items if i not in big]
        pos, x, y, rowh, W = [], 0.0, 0.0, 0.0, 0.0
        for it in big:
            if x > 0 and x + it.w > maxw:
                x, y, rowh = 0.0, y + rowh + 5.0, 0.0
            pos.append((it, x - it.ext[0], y - it.ext[1]))
            x += it.w + 6.0
            rowh = max(rowh, it.h)
            W = max(W, x)
        if small:
            # passivos à direita do CI enquanto couber na altura dele; depois embaixo, na largura toda
            big_h = y + rowh if big else 0.0
            x0 = W + 4.0 if big and maxw - W > 60 else 0.0
            if big and x0 == 0.0:
                y, rowh = big_h + 4.0, 0.0
            else:
                y, rowh = 0.0, 0.0
            x = x0
            for it in small:
                if x > x0 and x + it.w > maxw:
                    x, y, rowh = x0, y + rowh + 3.0, 0.0
                    if x0 > 0 and y > big_h:
                        x0 = 0.0
                        x, y = 0.0, max(y, big_h + 4.0)
                pos.append((it, x - it.ext[0], y - it.ext[1]))
                x += it.w + 3.0
                rowh = max(rowh, it.h)
                W = max(W, x)
            return W, max(y + rowh, big_h), pos
        return W, y + rowh, pos

    def build(self):
        header_h = 34 + 3.2 * len(self.s.notes)
        groups = []
        for title, refs in self.s.groups:
            groups.append((title, self.placed_items(refs)))
        for paper, PW, PH in PAPERS:
            maxw = PW - 40
            blocks = []
            for title, items in groups:
                gmax = min(maxw, 185)
                w, h, pos = self.layout_group(items, gmax)
                blocks.append((title, w + 8, h + 14, pos))
            # empacotamento das caixas em prateleiras
            x, y, rowh, ok, place = 20.0, 20.0 + header_h, 0.0, True, []
            for title, w, h, pos in blocks:
                if x > 20 and x + w > PW - 15:
                    x, y, rowh = 20.0, y + rowh + 6, 0.0
                if w > PW - 30 or y + h > PH - 38:
                    ok = False
                    break
                place.append((title, x, y, w, h, pos))
                x += w + 6
                rowh = max(rowh, h)
            if ok:
                break
        else:
            raise RuntimeError(f'folha {self.s.key} não coube no A1')
        self.paper, self.PW, self.PH = paper, PW, PH
        for title, gx, gy, w, h, pos in place:
            self.box(gx, gy, gx + w, gy + h)
            self.text(title, gx + 2, gy + 1.8, 2.0, bold=True)
            for it, ox, oy in pos:
                X, Y = snap(gx + 4 + ox), snap(gy + 10 + oy)
                c = it.comp
                fields = {'MPN': c.mpn, 'Fabricante': c.fab, 'LCSC': c.lcsc}
                if c.note:
                    fields['Nota'] = c.note
                fields = {k: v for k, v in fields.items() if v}
                uid = self.symbol(it.sym, c.ref, c.value + (' (NM)' if c.dnp else ''), X, Y, it.angle, it.unit,
                                  c.fp, fields, dnp=c.dnp)
                self.uuids.setdefault(c.ref, f'/{self.suid}/{uid}')
                self.connect(it, X, Y)
        # cabeçalho
        self.text(f'{self.s.title}', 20, 10, 3.5, bold=True)
        self.text(_wrap(self.s.desc, int((self.PW - 40) / 1.35)), 20, 17, 1.6)
        ny = 17 + 2.8 * (_wrap(self.s.desc, int((self.PW - 40) / 1.35)).count('\n') + 2)
        for n in self.s.notes:
            self.text('- ' + n, 20, ny, 1.5, italic=True)
            ny += 3.0
        self.text(f'{AUTHOR} ({NICK}) - {REPO} - CERN-OHL-S-2.0', 20, self.PH - 12, 1.5)

    def add_flags(self, nets):
        """PWR_FLAG nas redes desta folha que só têm entradas de alimentação."""
        if not nets:
            return
        x, y = 22.86, snap(self.PH - 20)
        for n in nets:
            self.flag(x, y)
            self.wire(x, y, x, y + G)
            if n in POWER_NETS:
                self.power(n, x, y + G, 0, 1)
            else:
                self.glabel(n, x, y + G, 0, 1)
            x += snap(max(8, label_len(n) * 0.5 + 6))

    def write(self, path, flags=()):
        self.build()
        self.add_flags(flags)
        o = ['(kicad_sch (version 20230121) (generator eeschema)', f'(uuid {self.suid})', f'(paper "{self.paper}")',
             '(title_block', f'(title "{esc(self.s.title)}")', f'(date "{DATE}")', f'(rev "{self.b.rev}")',
             f'(company "{COMPANY}")', f'(comment 1 "Projeto e PCB: {AUTHOR} ({NICK})")', f'(comment 2 "{REPO}")',
             '(comment 3 "Licença CERN-OHL-S-2.0 - gerado por tools/gerador-kicad")',
             f'(comment 4 "Folha {self.page}: {self.s.key}")', ')', '(lib_symbols']
        for name in sorted(self.used):
            o.append('  ' + parts.SYMS[name].sexpr(symlib.LIBNAME))
        o.append(')')
        o += self.items
        o.append(')')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(o) + '\n')


def _wrap(s, n):
    words, lines, cur = s.split(' '), [], ''
    for w in words:
        if len(cur) + len(w) + 1 > n:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + ' ' + w) if cur else w
    lines.append(cur)
    return '\n'.join(lines)


def flag_nets(board):
    """Redes com pino power_in e sem nenhum power_out: precisam de PWR_FLAG (ERC)."""
    info = {}
    for c in board.comps.values():
        s = parts.SYMS[c.sym]
        for p in s.pins:
            n = c.pins.get(p.num)
            if not n:
                continue
            d = info.setdefault(n, {'in': False, 'out': False, 'sheet': c.sheet})
            if p.etype == 'power_in':
                d['in'] = True
            if p.etype == 'power_out':
                d['out'] = True
    per = {}
    for n, d in info.items():
        if d['in'] and not d['out']:
            per.setdefault(d['sheet'], []).append(n)
    return per


def write_all(board, outdir):
    os.makedirs(outdir, exist_ok=True)
    root = U()
    flags = flag_nets(board)
    files, uuids = [], {}
    for i, s in enumerate(board.sheets, start=2):
        fname = f'{i - 1:02d}-{s.key}.kicad_sch'
        suid = U()
        w = SheetWriter(board, s, root, suid, i)
        w.write(os.path.join(outdir, fname), sorted(flags.get(s.key, [])))
        uuids.update(w.uuids)
        files.append((s, fname, suid, i))
    _write_root(board, outdir, root, files)
    return uuids, [f for _, f, _, _ in files]


def _write_root(board, outdir, root, files):
    W, H = 420, 297
    items = []
    t = lambda s, x, y, size=1.6, b=False: items.append(
        f'(text "{esc(s)}" (at {_f(x)} {_f(y)} 0) (effects (font (size {size} {size}){" bold" if b else ""}) '
        f'(justify left top)) (uuid {U()}))')
    t('Placa LiveSafe v1.0 - esquema elétrico', 20, 12, 4, True)
    t('Monitoração de sinal de TV e rádio nos abrigos: RF ISDB-Tb, HDMI e ASI num Raspberry Pi CM4 rodando o '
      'LiveSafe Monitor.', 20, 21, 1.8)
    t(f'Projeto e PCB: {AUTHOR} ({NICK}) - {REPO}', 20, 26, 1.8)
    bw, bh, gap = 88, 26, 10
    for k, (s, fname, suid, page) in enumerate(files):
        col, row = k % 4, k // 4
        x, y = 20 + col * (bw + gap), 40 + row * (bh + 22)
        items.append(
            f'(sheet (at {_f(x)} {_f(y)}) (size {bw} {bh}) (fields_autoplaced) (stroke (width 0.1524) (type solid)) '
            f'(fill (color 255 255 225 1.0000)) (uuid {suid}) '
            f'(property "Sheetname" "{esc(s.title)}" (at {_f(x)} {_f(y - 0.7)} 0) '
            f'(effects (font (size 1.6 1.6) bold) (justify left bottom))) '
            f'(property "Sheetfile" "{fname}" (at {_f(x)} {_f(y + bh + 0.6)} 0) '
            f'(effects (font (size 1.27 1.27)) (justify left top))) '
            f'(instances (project "{PROJECT}" (path "/{root}" (page "{page}")))))')
        t(_wrap(s.desc, 62)[:400] + ('...' if len(s.desc) > 400 else ''), x + 2, y + 2, 1.27)
    y0 = 40 + 2 * (bh + 22) + 4
    t('Trilhos de alimentação', 20, y0, 2.2, True)
    rails = ['+12V_IN -> PTC 2 A -> TVS SMBJ18A -> P-MOSFET (inversão) -> +12V',
             '+12V -> LMR33630 -> +5V (CM4, relés, USB-A, ponte DDC)',
             '+12V -> LMR33630 -> +3V3 (pontes, RF, ASI, hub, FX2LP)',
             '+5V -> TLV62569 -> +1V2 (núcleo do Si2183 e do GS2961A)',
             '+3V3 -> TLV73325/TLV73312 -> +2V5_TC/+1V2_TC (TC358743); TLV73318 -> +1V8_TUN (Si2141); '
             'TLV73312 -> ASI_1V2A (PLL do GS2961A)',
             'CM4_3V3: saída de 3,3 V do CM4, referência dos GPIO (GPIO_VREF), LEDs do RJ45 e do painel']
    for k, r in enumerate(rails):
        t('- ' + r, 22, y0 + 5 + k * 3.4, 1.6)
    y1 = y0 + 5 + len(rails) * 3.4 + 5
    t('Barramentos do CM4', 20, y1, 2.2, True)
    bus = ['I2C0 (GPIO44/45): TC358743 0x0F, RTC PCF85063A 0x51, ventoinha EMC2301 0x2F',
           'I2C1 (GPIO2/3): Si2183 0x64 -> (I2C mestre do demodulador) -> Si2141 0x60',
           'SPI0 (GPIO8-11): GS2961A (GSPI); CSI-2 CAM1 (4 vias): TC358743; I2S (GPIO18-20): áudio do HDMI',
           'USB 2.0: FSUSB42 -> hub USB2514B -> FX2LP #1 (TS RF), FX2LP #2 (ASI), USB-A; USB-C de serviço (rpiboot)']
    for k, r in enumerate(bus):
        t('- ' + r, 22, y1 + 5 + k * 3.4, 1.6)
    o = ['(kicad_sch (version 20230121) (generator eeschema)', f'(uuid {root})', f'(paper "A3")',
         '(title_block', '(title "Placa LiveSafe v1.0")', f'(date "{DATE}")', f'(rev "{board.rev}")',
         f'(company "{COMPANY}")', f'(comment 1 "Projeto e PCB: {AUTHOR} ({NICK})")', f'(comment 2 "{REPO}")',
         '(comment 3 "Licença CERN-OHL-S-2.0 - gerado por tools/gerador-kicad")', '(comment 4 "Folha 1: índice")', ')',
         '(lib_symbols)']
    o += items
    o.append('(sheet_instances (path "/" (page "1")))')
    o.append(')')
    with open(os.path.join(outdir, f'{PROJECT}.kicad_sch'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(o) + '\n')
