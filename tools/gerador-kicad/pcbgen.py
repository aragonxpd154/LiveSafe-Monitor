#!/usr/bin/python3
"""PCB da placa LiveSafe v1.0 (KiCad 7) - Marcos Silva dos Santos (MarcosObel).

Etapas: placa de 4 camadas (JLC04161H-7628), redes, footprints com campos de
fabricação, posicionamento (layouts.py + encaixe automático dos passivos),
contorno, planos (GND no In1, 3,3 V e 5 V no In2), vias de descida para os
planos, roteamento das demais redes com o Freerouting, preenchimento e DRC.

Rodar com o Python do sistema (módulo pcbnew):
    /usr/bin/python3 pcbgen.py <pasta_kicad> <uuids.json> [--noroute]
"""
import json
import math
import os
import re
import subprocess
import sys
import time

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import designs  # noqa: E402
import layouts as LY  # noqa: E402
import sch  # noqa: E402

FPDIR = os.environ.get('KICAD7_FOOTPRINT_DIR', '/usr/share/kicad/footprints')
LIBDIR = os.path.join(HERE, '..', '..', 'hardware', 'kicad', 'bibliotecas', 'livesafe.pretty')
FREEROUTING = os.environ.get('FREEROUTING_JAR', os.path.join(HERE, 'freerouting-1.9.0.jar'))
MM = pcbnew.FromMM
TO = pcbnew.ToMM
V = lambda x, y: pcbnew.VECTOR2I(MM(x), MM(y))

# regras (capacidade JLCPCB 4 camadas, com folga)
CLEAR = 0.1
TRACK = 0.127
VIA_D, VIA_DRILL = 0.45, 0.2
EDGE_CLEAR = 0.25
RAILS = {'GND', '+3V3', '+5V', '+12V', 'CM4_3V3', '+1V2'}
PLANE_NETS = ('GND', '+3V3', '+5V')
# classes de rede: nome -> (largura, folga, padrões)
CLASSES = {
    'Potencia': (0.5, 0.15, ['+12V', '+12V_IN', 'VIN_F', 'SW_5V', 'SW_3V3', '+5V', 'USB_A_VBUS']),
    'Alimentacao': (0.25, 0.12, ['+3V3', '+1V2', 'CM4_3V3', '+1V8_TUN', '+2V5_TC', '+1V2_TC', 'ASI_1V2A', 'ASI_3V3A',
                                'ASI_VCO', 'DEM_VCORE', 'DEM_VANA', 'TUN_VDDH', 'TC_*', 'OSC27_VDD', 'SW_1V2', 'RTC_VDD',
                                'VBAT', '+12V_AUX', 'HDMI_5V', 'USB_SERV_VBUS', 'K*_DRV', 'RLY*']),
    'Dif90_USB': (0.2, 0.12, [f'USB_{k}_{s}' for k in ('CM4', 'HUB', 'SERV', 'FX1', 'FX2', 'A') for s in 'PN']),
    'Dif100': (0.18, 0.12, ['HDMI_CK_*', 'HDMI_D?_*', 'CSI_*', 'ETH_P?_*']),
    'RF75': (0.16, 0.15, ['RF_ANT', 'TUN_RF*', 'ASI_IN', 'ASI_EQ', 'ASI_SDI_*', 'ASI_REF']),
}


def match(pattern, name):
    rx = '^' + re.escape(pattern).replace('\\*', '.*').replace('\\?', '.') + '$'
    return re.match(rx, name) is not None


def net_class(name):
    for cls, (_, _, pats) in CLASSES.items():
        if any(match(p, name) for p in pats):
            return cls
    return 'Default'


# ---------------------------------------------------------------------------
class Rect:
    __slots__ = ('x1', 'y1', 'x2', 'y2')

    def __init__(self, x1, y1, x2, y2):
        self.x1, self.y1, self.x2, self.y2 = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)

    def hits(self, o, m=0.0):
        return not (self.x2 + m <= o.x1 or o.x2 + m <= self.x1 or self.y2 + m <= o.y1 or o.y2 + m <= self.y1)

    def inside(self, o):
        return self.x1 >= o.x1 and self.y1 >= o.y1 and self.x2 <= o.x2 and self.y2 <= o.y2


def courtyard(fp):
    """Retângulo do pátio do footprint já posicionado (mm)."""
    xs, ys = [], []
    for g in fp.GraphicalItems():
        if g.GetLayer() == pcbnew.F_CrtYd:
            bb = g.GetBoundingBox()
            xs += [bb.GetX(), bb.GetRight()]
            ys += [bb.GetY(), bb.GetBottom()]
    if not xs:
        bb = fp.GetBoundingBox(False, False)
        xs, ys = [bb.GetX(), bb.GetRight()], [bb.GetY(), bb.GetBottom()]
    return Rect(TO(min(xs)), TO(min(ys)), TO(max(xs)), TO(max(ys)))


class Gen:
    def __init__(self, kd, uuids):
        self.kd = kd
        self.uuids = uuids
        self.d = designs.build()
        self.board = pcbnew.BOARD()
        self.fps = {}
        self.occ = []  # (Rect, ref)
        self.served = {}
        self.name = sch.PROJECT

    # ----------------------------------------------------------- placa e regras
    def setup(self):
        b = self.board
        b.SetCopperLayerCount(4)
        b.SetLayerName(pcbnew.In1_Cu, 'In1.Cu')
        b.SetLayerName(pcbnew.In2_Cu, 'In2.Cu')
        ds = b.GetDesignSettings()
        ds.m_MinClearance = MM(CLEAR)
        ds.m_TrackMinWidth = MM(0.1)
        ds.m_ViasMinSize = MM(0.4)
        ds.m_MinThroughDrill = MM(0.2)
        ds.m_HoleToHoleMin = MM(0.25)
        ds.m_CopperEdgeClearance = MM(EDGE_CLEAR)
        ds.m_HoleClearance = MM(0.2)
        ds.m_MinResolvedSpokes = 1
        ds.SetBoardThickness(MM(1.6))
        nc = ds.m_NetSettings.m_DefaultNetClass
        nc.SetClearance(MM(CLEAR))
        nc.SetTrackWidth(MM(TRACK))
        nc.SetViaDiameter(MM(VIA_D))
        nc.SetViaDrill(MM(VIA_DRILL))
        tb = b.GetTitleBlock()
        tb.SetTitle('Placa LiveSafe v1.0')
        tb.SetRevision(designs.Board.rev)
        tb.SetDate(sch.DATE)
        tb.SetCompany(sch.COMPANY)
        tb.SetComment(0, f'Projeto e PCB: {sch.AUTHOR} ({sch.NICK})')
        tb.SetComment(1, sch.REPO + ' - CERN-OHL-S-2.0')
        tb.SetComment(2, '4 camadas JLC04161H-7628, 1,6 mm: L1 sinal / L2 GND / L3 3,3 V e 5 V / L4 sinal')

    def nets(self):
        names = sorted({n for c in self.d.comps.values() for n in c.pins.values() if n})
        self.netinfo = {}
        for n in names:
            ni = pcbnew.NETINFO_ITEM(self.board, n)
            self.board.Add(ni)
            self.netinfo[n] = ni

    def load(self, fpid):
        lib, name = fpid.split(':')
        path = LIBDIR if lib == 'livesafe' else f'{FPDIR}/{lib}.pretty'
        fp = pcbnew.FootprintLoad(path, name)
        if fp is None:
            raise RuntimeError('footprint não encontrado: ' + fpid)
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        return fp

    def footprints(self):
        for ref, c in self.d.comps.items():
            fp = self.load(c.fp)
            fp.SetReference(ref)
            fp.SetValue(c.value)
            fp.Reference().SetTextSize(V(0.8, 0.8))
            fp.Reference().SetTextThickness(MM(0.12))
            fp.Value().SetVisible(False)
            fp.Value().SetLayer(pcbnew.F_Fab)
            for k, v in (('MPN', c.mpn), ('Fabricante', c.fab), ('LCSC', c.lcsc)):
                if v:
                    fp.SetProperty(k, v)
            if ref in self.uuids:
                fp.SetPath(pcbnew.KIID_PATH(self.uuids[ref]))
            fp.SetLocalClearance(0)
            for pad in fp.Pads():
                pad.SetLocalClearance(0)
            attrs = fp.GetAttributes()
            if c.dnp:
                attrs |= pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES
            fp.SetAttributes(attrs)
            for pad in fp.Pads():
                n = c.pins.get(pad.GetNumber())
                if n:
                    pad.SetNet(self.netinfo[n])
            self.board.Add(fp)
            self.fps[ref] = fp

    # -------------------------------------------------------------- posicionamento
    def set_center(self, fp, x, y, rot):
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(V(0, 0))
        r = courtyard(fp)
        cx, cy = (r.x1 + r.x2) / 2, (r.y1 + r.y2) / 2
        fp.SetPosition(V(x - cx, y - cy))

    def occupy(self, ref):
        self.occ.append((courtyard(self.fps[ref]), ref))

    def place_edges(self):
        for ref, (side, yc, over) in LY.EDGE.items():
            fp = self.fps[ref]
            fid = self.d.comps[ref].fp
            face = LY.FACE[fid]
            want = '-x' if side == 'R' else '+x'
            # rotação (anti-horário na tela) que leva a face ao lado pedido
            dirs = ['+x', '-y', '-x', '+y']
            rot = ((dirs.index(want) - dirs.index(face)) % 4) * 90
            fp.SetOrientationDegrees(rot)
            fp.SetPosition(V(0, 0))
            r = courtyard(fp)
            dx = (-over - r.x1) if side == 'R' else (LY.W + over - r.x2)
            dy = yc - (r.y1 + r.y2) / 2
            fp.SetPosition(V(dx, dy))
            self.occupy(ref)

    def place_fixed(self):
        for ref, spec in LY.FIXED.items():
            fp = self.fps[ref]
            if spec[0] == 'origin':
                _, x, y, rot = spec
                fp.SetOrientationDegrees(rot)
                fp.SetPosition(V(x, y))
            else:
                x, y, rot = spec
                self.set_center(fp, x, y, rot)
            if ref != 'U1':
                self.occupy(ref)
            else:
                for p in fp.Pads():
                    pass
                self.occupy(ref)
        for ref, (x, y) in LY.FRONT_LEDS.items():
            self.set_center(self.fps[ref], x, y, 90)
            self.occupy(ref)
        for k in LY.KEEPOUT_PARTS:
            self.occ.append((Rect(*k), 'KEEPOUT'))

    def pad_xy(self, pad):
        p = pad.GetPosition()
        return TO(p.x), TO(p.y)

    def target(self, ref):
        """Ponto onde o passivo deve ficar: o pad do CI (já posicionado) ligado a ele."""
        c = self.d.comps[ref]
        nets = [n for n in c.pins.values() if n]
        sig = [n for n in nets if n not in RAILS]
        group_refs = [r for s in self.d.sheets for g, rs in s.groups if g == c.group for r in rs]
        placed = [r for r in group_refs if r in self.placed and r != ref]
        anyplaced = [r for r in self.placed if r != ref]
        cands = []
        for pool, wt in ((placed, 0.0), (anyplaced, 3.0)):
            for r in pool:
                for pad in self.fps[r].Pads():
                    pn = pad.GetNetname()
                    if pn and pn in sig:
                        cands.append((wt, pad, r))
            if cands:
                break
        if not cands and nets:  # desacoplamento: pino de alimentação do CI do grupo
            rail = [n for n in nets if n != 'GND']
            for r in placed:
                if len(list(self.fps[r].Pads())) < 5:
                    continue
                for pad in self.fps[r].Pads():
                    if pad.GetNetname() in rail:
                        k = (r, pad.GetNumber())
                        cands.append((self.served.get(k, 0) * 1.5, pad, r))
        if not cands:
            reg = LY.REGIONS[c.group]
            return ((reg[0] + reg[2]) / 2, (reg[1] + reg[3]) / 2), None
        cands.sort(key=lambda t: t[0])
        wt, pad, r = cands[0]
        self.served[(r, pad.GetNumber())] = self.served.get((r, pad.GetNumber()), 0) + 1
        return self.pad_xy(pad), pad

    def free(self, rect, region):
        if not rect.inside(region):
            return False
        if rect.x1 < 0.5 or rect.y1 < 0.5 or rect.x2 > LY.W - 0.5 or rect.y2 > LY.H - 0.5:
            return False
        halo = getattr(LY, 'HALO', {})
        for o, ref in self.occ:
            if rect.hits(o, max(0.12, halo.get(ref, 0.0))):
                return False
        return True

    def place_auto(self):
        self.placed = set(LY.FIXED) | set(LY.EDGE) | set(LY.FRONT_LEDS)
        order = [r for s in self.d.sheets for g, rs in s.groups for r in rs if r not in self.placed]
        fails = []
        for ref in order:
            c = self.d.comps[ref]
            fp = self.fps[ref]
            reg = Rect(*LY.REGIONS[c.group])
            sp = getattr(LY, 'SPREAD', {}).get(c.group, 0.0)  # folga extra para abrir canais de roteamento
            (tx, ty), tpad = self.target(ref)
            tx = min(max(tx, reg.x1 + 0.5), reg.x2 - 0.5)
            ty = min(max(ty, reg.y1 + 0.5), reg.y2 - 0.5)
            best = None
            for rot in (0, 90):
                fp.SetOrientationDegrees(rot)
                fp.SetPosition(V(0, 0))
                r0 = courtyard(fp)
                r0 = Rect(r0.x1 - sp, r0.y1 - sp, r0.x2 + sp, r0.y2 + sp)
                w, h = r0.x2 - r0.x1, r0.y2 - r0.y1
                # pad deste componente que liga ao alvo
                own = None
                if tpad is not None:
                    for p in fp.Pads():
                        if p.GetNetname() == tpad.GetNetname():
                            own = self.pad_xy(p)
                ox, oy = own if own else ((r0.x1 + r0.x2) / 2, (r0.y1 + r0.y2) / 2)
                step = 0.25
                for ring in range(0, 120):
                    found = None
                    pts = [(0, 0)] if ring == 0 else \
                        [(i, -ring) for i in range(-ring, ring + 1)] + [(i, ring) for i in range(-ring, ring + 1)] + \
                        [(-ring, j) for j in range(-ring + 1, ring)] + [(ring, j) for j in range(-ring + 1, ring)]
                    pts.sort(key=lambda p: p[0] ** 2 + p[1] ** 2)
                    for i, j in pts:
                        px, py = tx + i * step - ox, ty + j * step - oy
                        rect = Rect(r0.x1 + px, r0.y1 + py, r0.x2 + px, r0.y2 + py)
                        if self.free(rect, reg):
                            found = (math.hypot(i, j) * step, rot, px, py, rect)
                            break
                    if found:
                        if best is None or found[0] < best[0]:
                            best = found
                        break
            if best is None:
                fails.append(ref)
                continue
            _, rot, px, py, rect = best
            fp.SetOrientationDegrees(rot)
            fp.SetPosition(V(px, py))
            self.occ.append((rect, ref))
            self.placed.add(ref)
        return fails

    # -------------------------------------------------------------- contorno
    def outline(self):
        r = 2.0
        W, H = LY.W, LY.H
        segs = [((r, 0), (W - r, 0)), ((W, r), (W, H - r)), ((W - r, H), (r, H)), ((0, H - r), (0, r))]
        for (x1, y1), (x2, y2) in segs:
            s = pcbnew.PCB_SHAPE(self.board, pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(V(x1, y1))
            s.SetEnd(V(x2, y2))
            s.SetLayer(pcbnew.Edge_Cuts)
            s.SetWidth(MM(0.1))
            self.board.Add(s)
        for cx, cy, sa in ((r, r, 180), (W - r, r, 270), (W - r, H - r, 0), (r, H - r, 90)):
            a = pcbnew.PCB_SHAPE(self.board, pcbnew.SHAPE_T_ARC)
            a.SetCenter(V(cx, cy))
            a.SetStart(V(cx + r * math.cos(math.radians(sa)), cy + r * math.sin(math.radians(sa))))
            a.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(90, pcbnew.DEGREES_T), True)
            a.SetLayer(pcbnew.Edge_Cuts)
            a.SetWidth(MM(0.1))
            self.board.Add(a)

    def zones(self):
        W, H, m = LY.W, LY.H, 0.25
        full = [(m, m), (W - m, m), (W - m, H - m), (m, H - m)]
        add_zone(self.board, 'GND', pcbnew.In1_Cu, full, 0, name='GND_L2')
        add_zone(self.board, '+3V3', pcbnew.In2_Cu, full, 0, name='3V3_L3')
        add_zone(self.board, '+5V', pcbnew.In2_Cu, LY.PLANE_5V, 1, name='5V_L3')

    # -------------------------------------------------------------- roteamento
    def dsn_classes(self):
        nets = sorted(self.netinfo)
        groups = {k: [] for k in CLASSES}
        groups['Default'] = []
        for n in nets:
            groups[net_class(n)].append(n)
        out = []
        for cls, members in groups.items():
            if not members:
                continue
            w, c = (TRACK, CLEAR + 0.01) if cls == 'Default' else CLASSES[cls][:2]
            q = ' '.join(f'"{m}"' if re.search(r'[\s()"]', m) else m for m in members)
            out.append(f'    (class {cls} {q}\n      (circuit\n        (use_via "Via[0-3]_450:200_um")\n      )\n'
                       f'      (rule\n        (width {w * 1000:.0f})\n        (clearance {c * 1000:.1f})\n      )\n    )')
        return '\n'.join(out)

    def fix_dsn(self, txt):
        for ly in ('In1.Cu', 'In2.Cu'):
            txt = txt.replace(f'(layer {ly}\n      (type signal)', f'(layer {ly}\n      (type power)')
        # 3,3 V no In2 = placa menos a área do 5 V
        m = 250
        x1, y1, x2, y2 = LY.PLANE_5V[0][0], LY.PLANE_5V[0][1], LY.PLANE_5V[2][0], LY.PLANE_5V[2][1]
        pts = [(m / 1000, m / 1000), (x1, m / 1000), (x1, y2), (x2, y2), (x2, m / 1000), (LY.W - m / 1000, m / 1000),
               (LY.W - m / 1000, LY.H - m / 1000), (m / 1000, LY.H - m / 1000), (m / 1000, m / 1000)]
        poly = ' '.join(f'{x * 1000:.0f} {-y * 1000:.0f}' for x, y in pts)
        txt = re.sub(r'\(plane \+3V3 \(polygon In2\.Cu 0 [^)]*\)\)', f'(plane +3V3 (polygon In2.Cu 0 {poly}))', txt)
        txt = self.filter_plane_pins(txt)
        for pn in PLANE_NETS:  # vias de descida (redes de plano): o roteador não mexe
            txt = txt.replace(f'(net {pn})(type route)', f'(net {pn})(type protect)')
            txt = txt.replace(f'(net "{pn}")(type route)', f'(net "{pn}")(type protect)')
        i = txt.index('    (class kicad_default')
        j = txt.index('  (wiring')
        net_end = txt.rindex('  )', i, j)
        txt = txt[:i] + self.dsn_classes() + '\n' + txt[net_end:]
        return txt

    def filter_plane_pins(self, txt):
        """Tira do roteador os pinos que já descem para o plano pela via; deixa os que falharam e,
        no 5 V, os pinos fora da área do plano (ligados por trilha a partir do indutor L1)."""
        failed = {(r, p) for r, p, n in getattr(self, 'fan_failed', [])}
        board = self.rboard
        x1, y1, x2, y2 = LY.PLANE_5V[0][0], LY.PLANE_5V[0][1], LY.PLANE_5V[2][0], LY.PLANE_5V[2][1]
        keep = {'GND': set(), '+3V3': set(), '+5V': {'L1-2'}}
        for pad, ref in ((p, fp.GetReference()) for fp in board.GetFootprints() for p in fp.Pads()):
            n = pad.GetNetname()
            if n not in keep:
                continue
            pin = f'{ref}-{pad.GetNumber()}'
            x, y = TO(pad.GetPosition().x), TO(pad.GetPosition().y)
            inside = x1 <= x <= x2 and y1 <= y <= y2
            tht = pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
            if (ref, pad.GetNumber()) in failed:
                keep[n].add(pin)
            elif n == '+5V' and not inside:
                keep[n].add(pin)
            elif n == '+3V3' and inside:
                keep[n].add(pin)
        for n, pins in keep.items():
            pat = re.compile(r'\(net ' + re.escape(n) + r'\n\s*\(pins [^)]*\)\n\s*\)')
            if len(pins) >= 2:
                txt = pat.sub(f'(net {n}\n      (pins {" ".join(sorted(pins))})\n    )', txt)
            else:
                txt = pat.sub('', txt)
        return txt

    def route(self, pcb, drop_pours=False):
        base = os.path.splitext(pcb)[0]
        dsn, ses = base + '.dsn', base + '.ses'
        board = pcbnew.LoadBoard(pcb)
        self.rboard = board
        assert pcbnew.ExportSpecctraDSN(board, dsn), 'falha exportando DSN'
        txt = self.fix_dsn(open(dsn).read())
        # preenchimentos de GND das faces externas não entram no roteador (voltam a ser preenchidos no fim)
        txt = re.sub(r'\(plane GND \(polygon [FB]\.Cu [^)]*\)\)\s*', '', txt)
        with open(dsn, 'w') as f:
            f.write(txt)
        passes = os.environ.get('FR_PASSES', '30')
        if '1.9' in os.path.basename(FREEROUTING):
            # o 1.9 respeita o limite de passadas (-mp); precisa de uma tela virtual (xvfb-run)
            cmd = ['xvfb-run', '-a', 'java', '-jar', FREEROUTING, '-de', dsn, '-do', ses, '-mp', passes, '-mt', '1', '-dct', '1']
        else:
            cmd = ['java', '-jar', FREEROUTING, '-de', dsn, '-do', ses, f'--router.max_passes={passes}', '-da',
                   '--gui.enabled=false']
        if os.path.exists(ses):
            os.remove(ses)
        t0 = time.time()
        log = open(base + '-freerouting.log', 'w')
        try:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=int(os.environ.get('FR_TIMEOUT', '5400')))
        except subprocess.TimeoutExpired:
            print('freerouting: tempo esgotado', file=sys.stderr)
        if not os.path.exists(ses) or os.path.getsize(ses) < 100:
            raise SystemExit('freerouting sem resultado')
        n = import_ses(board, ses)
        pcbnew.SaveBoard(pcb, board)
        return board, n, round(time.time() - t0)

    def save(self, path):
        pcbnew.SaveBoard(path, self.board)


def completar(pcb, ciclos=4):
    """Fecha as ligações que o Freerouting deixou, com o roteador em labirinto (completar.py).
    Primeiro sem mexer no que existe, depois com trilha fina; se ainda faltar, ciclos de 'rasgar e refazer'
    (os pares diferenciais e o RF nunca são rasgados). Fica com a melhor placa encontrada."""
    import shutil
    here = os.path.dirname(os.path.abspath(__file__))
    best = pcb + '.melhor'
    rpt = os.path.splitext(pcb)[0] + '-drc.rpt'

    def contar():  # DRC num processo novo: o LoadBoard repetido no mesmo processo pode ver a placa antiga
        r = subprocess.run([sys.executable, '-c', f'import sys; sys.path.insert(0, {here!r}); import pcbgen; '
                            f'print("UNC", pcbgen.drc({os.path.abspath(pcb)!r})[1])'],
                           capture_output=True, text=True, cwd=here, timeout=900)
        m = re.search(r'UNC (-?\d+)', r.stdout)
        return int(m.group(1)) if m else -1

    def rodar(extra):
        contar()
        subprocess.run([sys.executable, os.path.join(here, 'completar.py'), pcb, rpt] + extra,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3600)
        return contar()

    hist = [contar()]
    shutil.copy(pcb, best)
    for modos in [[[]], [['--fino']], [['--interna']]] + [[['--rasgar'], [], ['--fino'], ['--interna']]] * ciclos:
        if min(hist) == 0:
            break
        for extra in modos:
            u = rodar(extra)
        hist.append(u)
        print(f'completar: {u} sem conexão', flush=True)
        if 0 <= u <= min(hist):
            shutil.copy(pcb, best)
    shutil.copy(best, pcb)
    os.remove(best)
    contar()
    return hist


def main():
    kd, uu = sys.argv[1], sys.argv[2]
    if '--completar' in sys.argv:  # só o roteador em labirinto sobre a placa atual
        pcb = os.path.join(kd, sch.PROJECT + '.kicad_pcb')
        print(json.dumps({'sem_conexao_por_rodada': completar(pcb)}))
        return
    if '--continuar' in sys.argv:  # mais passadas do roteador a partir da placa atual
        pcb = os.path.join(kd, sch.PROJECT + '.kicad_pcb')
        g = Gen.__new__(Gen)
        g.kd, g.name = kd, sch.PROJECT
        g.d = designs.build()
        g.netinfo = {n: 1 for c in g.d.comps.values() for n in c.pins.values() if n}
        fpath = os.path.join(kd, '.fanout-falhas.json')
        g.fan_failed = json.load(open(fpath)) if os.path.exists(fpath) else []
        board, n, secs = g.route(pcb, drop_pours=True)
        finalize(board)
        pcbnew.SaveBoard(pcb, board)
        patch_pro(os.path.splitext(pcb)[0] + '.kicad_pro')
        errs, unc, rpt = drc(pcb)
        print(json.dumps({'segmentos_novos': n, 'freerouting_s': secs, 'drc_erros': errs, 'sem_conexao': unc}))
        return
    if '--finalizar' in sys.argv:  # só os passos finais sobre uma placa já roteada
        pcb = os.path.join(kd, sch.PROJECT + '.kicad_pcb')
        board = pcbnew.LoadBoard(pcb)
        finalize(board)
        pcbnew.SaveBoard(pcb, board)
        patch_pro(os.path.splitext(pcb)[0] + '.kicad_pro')
        errs, unc, rpt = drc(pcb)
        print(json.dumps({'drc_erros': errs, 'sem_conexao': unc}))
        return
    uuids = json.load(open(uu)) if os.path.exists(uu) else {}
    g = Gen(kd, uuids)
    g.setup()
    g.nets()
    g.footprints()
    g.place_edges()
    g.place_fixed()
    fails = g.place_auto()
    g.outline()
    g.zones()
    fo = Fanout(g.board, (LY.PLANE_5V[0][0], LY.PLANE_5V[0][1], LY.PLANE_5V[2][0], LY.PLANE_5V[2][1]))
    done, failed = fo.run()
    g.fan_failed = failed
    pcb = os.path.join(kd, g.name + '.kicad_pcb')
    g.save(pcb)
    json.dump(failed, open(os.path.join(kd, '.fanout-falhas.json'), 'w'))
    st = {'pcb': pcb, 'sem_lugar': fails, 'vias_descida': done, 'descida_falhou': len(failed)}
    if '--noroute' not in sys.argv:
        board, n, secs = g.route(pcb)
        # acabamento num processo novo (planos externos, textos, preenchimento e DRC); os planos precisam
        # estar preenchidos antes do completar, senão todo pino de GND/3V3 aparece como sem conexão
        fin = [sys.executable, os.path.abspath(__file__), kd, uu, '--finalizar']
        subprocess.run(fin, capture_output=True, text=True)
        st['rodadas_completar'] = completar(pcb)
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'limpar.py'), pcb],
                       capture_output=True, text=True)  # vias repetidas (fanout + Freerouting no mesmo ponto)
        r = subprocess.run(fin, capture_output=True, text=True)
        fim = json.loads([ln for ln in r.stdout.splitlines() if ln.startswith('{')][-1])
        st.update({'segmentos': n, 'freerouting_s': secs, 'drc_erros': fim['drc_erros'],
                   'sem_conexao': fim['sem_conexao']})
    print(json.dumps(st))



# ---------------------------------------------------------------------------
def add_zone(board, net, layer, pts, priority=0, clearance=0.2, min_w=0.2, thermal=True, name=''):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(board.FindNet(net))
    z.SetAssignedPriority(priority)
    z.SetLocalClearance(MM(clearance))
    z.SetMinThickness(MM(min_w))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL if thermal else pcbnew.ZONE_CONNECTION_FULL)
    z.SetThermalReliefGap(MM(0.25))
    z.SetThermalReliefSpokeWidth(MM(0.3))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    if name:
        z.SetZoneName(name)
    o = z.Outline()
    o.NewOutline()
    for x, y in pts:
        o.Append(MM(x), MM(y))
    board.Add(z)
    return z

# ---------------------------------------------------------------------------
# Vias de descida para os planos (GND no In1, 3,3 V / 5 V no In2)
class Spatial:
    def __init__(self, cell=2.0):
        self.cell, self.grid = cell, {}

    def _keys(self, x1, y1, x2, y2):
        c = self.cell
        for i in range(int(x1 // c), int(x2 // c) + 1):
            for j in range(int(y1 // c), int(y2 // c) + 1):
                yield (i, j)

    def add(self, obj, bb):
        for k in self._keys(*bb):
            self.grid.setdefault(k, []).append(obj)

    def near(self, bb):
        seen, out = set(), []
        for k in self._keys(*bb):
            for o in self.grid.get(k, ()):
                if id(o) not in seen:
                    seen.add(id(o))
                    out.append(o)
        return out


def _d_pt_rect(x, y, r):
    dx = max(r[0] - x, 0, x - r[2])
    dy = max(r[1] - y, 0, y - r[3])
    return math.hypot(dx, dy)


class Fanout:
    """Coloca uma via ao lado de cada pad SMD de rede de plano, sem invadir a folga de nada."""

    def __init__(self, board, region5v):
        self.board = board
        self.sp = Spatial()
        self.r5 = region5v
        self.vias = []
        for pad in board.GetPads():
            if not pad.IsOnCopperLayer():
                continue
            bb = pad.GetBoundingBox()
            r = (TO(bb.GetX()), TO(bb.GetY()), TO(bb.GetRight()), TO(bb.GetBottom()))
            circ = None
            if pad.GetShape() == pcbnew.PAD_SHAPE_CIRCLE:
                circ = (TO(pad.GetPosition().x), TO(pad.GetPosition().y), TO(pad.GetSize().x) / 2)
            o = ('pad', pad.GetNetname(), r, pad, circ)
            self.sp.add(o, r)

    def in5(self, x, y):
        x1, y1, x2, y2 = self.r5
        return x1 <= x <= x2 and y1 <= y <= y2

    def ok_circle(self, net, x, y, rad, clr=CLEAR):
        if x < 0.8 or y < 0.8 or x > LY.W - 0.8 or y > LY.H - 0.8:
            return False
        bb = (x - rad - 1, y - rad - 1, x + rad + 1, y + rad + 1)
        for o in self.sp.near(bb):
            if o[0] == 'pad':
                if o[1] == net and o[1] != '':
                    continue
                if _d_pad(x, y, o) < rad + clr:
                    return False
            elif o[0] == 'via':
                d = math.hypot(x - o[2], y - o[3])
                if d < rad + o[4] + (0.0 if o[1] == net else clr) + 0.05 or d < 0.5:
                    return False
            elif o[0] == 'trk' and o[1] != net:
                if _d_seg(x, y, o[2]) < rad + o[2][4] / 2 + clr:
                    return False
        return True

    def ok_seg(self, net, x1, y1, x2, y2, w, own):
        L = math.hypot(x2 - x1, y2 - y1)
        n = max(2, int(L / 0.05))
        bb = (min(x1, x2) - 1, min(y1, y2) - 1, max(x1, x2) + 1, max(y1, y2) + 1)
        objs = self.sp.near(bb)
        for i in range(n + 1):
            x, y = x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n
            for o in objs:
                if o[0] == 'pad' and o[3] is not own and (o[1] != net or o[1] == ''):
                    if _d_pad(x, y, o) < w / 2 + CLEAR:
                        return False
                elif o[0] == 'via' and o[1] != net:
                    if math.hypot(x - o[2], y - o[3]) < w / 2 + o[4] + CLEAR:
                        return False
                elif o[0] == 'trk' and o[1] != net:
                    if _d_seg(x, y, o[2]) < w / 2 + o[2][4] / 2 + CLEAR:
                        return False
        return True

    def add_via(self, net, x, y, d=VIA_D, drill=VIA_DRILL):
        v = pcbnew.PCB_VIA(self.board)
        v.SetPosition(V(x, y))
        v.SetWidth(MM(d))
        v.SetDrill(MM(drill))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNet(self.board.FindNet(net))
        self.board.Add(v)
        o = ('via', net, x, y, d / 2)
        self.sp.add(o, (x - d, y - d, x + d, y + d))
        self.vias.append((net, x, y))

    def add_trk(self, net, x1, y1, x2, y2, w):
        tr = pcbnew.PCB_TRACK(self.board)
        tr.SetStart(V(x1, y1))
        tr.SetEnd(V(x2, y2))
        tr.SetWidth(MM(w))
        tr.SetLayer(pcbnew.F_Cu)
        tr.SetNet(self.board.FindNet(net))
        self.board.Add(tr)
        o = ('trk', net, (x1, y1, x2, y2, w))
        self.sp.add(o, (min(x1, x2) - w, min(y1, y2) - w, max(x1, x2) + w, max(y1, y2) + w))

    def wants(self, pad):
        net = pad.GetNetname()
        if pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
            return None
        x, y = TO(pad.GetPosition().x), TO(pad.GetPosition().y)
        if net == 'GND':
            return net
        if net == '+3V3' and not self.in5(x, y):
            return net
        if net == '+5V' and self.in5(x, y):
            return net
        return None

    def run(self, bga_all=('U9', 'U15')):
        failed = []
        done = 0
        for fp in self.board.GetFootprints():
            ref = fp.GetReference()
            fname = fp.GetFPID().GetLibItemName().wx_str()
            bga = 'BGA' in fname
            fc = fp.GetPosition()
            fx, fy = TO(fc.x), TO(fc.y)
            pads = list(fp.Pads())
            pitch = 0.65 if 'P0.65' in fname or '0.65' in fname else 1.0
            nrow = None
            for pad in pads:
                net = self.wants(pad)
                if bga and ref in bga_all and not net:
                    # bolas internas de sinal/alimentação local também descem (escape do BGA)
                    name = pad.GetNumber()
                    row, col = 'ABCDEFGHJK'.index(name[0]), int(name[1:]) - 1
                    nb = 8 if pitch < 0.9 else 10
                    ring = min(row, col, nb - 1 - row, nb - 1 - col)
                    if ring >= 1 and pad.GetNetname():
                        net = pad.GetNetname()
                if not net:
                    continue
                px, py = TO(pad.GetPosition().x), TO(pad.GetPosition().y)
                ties = getattr(LY, 'BGA_TIES', {})
                if bga and pad.GetNumber() in ties.get(ref, {}):  # bola ligada à vizinha pelo F.Cu
                    q = fp.FindPadByNumber(ties[ref][pad.GetNumber()])
                    self.add_trk(net, px, py, TO(q.GetPosition().x), TO(q.GetPosition().y), 0.2)
                    done += 1
                    continue
                sx, sy = TO(pad.GetBoundingBox().GetWidth()), TO(pad.GetBoundingBox().GetHeight())
                if self.fan_pad(pad, net, px, py, sx, sy, fx, fy, bga, pitch):
                    done += 1
                else:
                    failed.append((ref, pad.GetNumber(), net))
            for a, b in getattr(LY, 'BGA_TIES', {}).get(ref + '+', []):
                pa, pb = fp.FindPadByNumber(a), fp.FindPadByNumber(b)
                self.add_trk(pa.GetNetname(), TO(pa.GetPosition().x), TO(pa.GetPosition().y),
                             TO(pb.GetPosition().x), TO(pb.GetPosition().y), 0.2)
        return done, failed

    def fan_pad(self, pad, net, px, py, sx, sy, fx, fy, bga, pitch):
        if bga:
            vd = 0.4 if pitch < 0.9 else VIA_D
            w = 0.1 if pitch < 0.9 else 0.15
            h = pitch / 2
            cands = [(px + a * h, py + b * h) for a in (-1, 1) for b in (-1, 1)]
            cands.sort(key=lambda c: -math.hypot(c[0] - fx, c[1] - fy))
            for vx, vy in cands:
                if self.ok_circle(net, vx, vy, vd / 2, 0.1) and self.ok_seg(net, px, py, vx, vy, w, pad):
                    self.add_trk(net, px, py, vx, vy, w)
                    self.add_via(net, vx, vy, vd)
                    return True
            return False
        # pad grande (pad exposto, capacitores grandes): vias dentro do pad
        fp_ = pad.GetParent()
        thermal = any(q.GetNumber() == pad.GetNumber() and q.GetDrillSize().x > 0 for q in fp_.Pads()) \
            if hasattr(fp_, 'Pads') else False
        if thermal:
            return True
        if sx >= 1.6 and sy >= 1.6:
            n = 0
            nx, ny = max(1, int((sx - 0.5) / 1.0)), max(1, int((sy - 0.5) / 1.0))
            for i in range(nx):
                for j in range(ny):
                    vx = px - (nx - 1) * 0.5 + i * 1.0
                    vy = py - (ny - 1) * 0.5 + j * 1.0
                    if self.ok_circle(net, vx, vy, VIA_D / 2):
                        self.add_via(net, vx, vy)
                        n += 1
            if n:
                return True
        w = min(0.25, max(0.15, min(sx, sy) * 0.8))
        ang0 = math.atan2(py - fy, px - fx)
        # eixo dominante para fora do componente primeiro
        if abs(px - fx) >= abs(py - fy):
            prim = [0 if px >= fx else math.pi]
        else:
            prim = [math.pi / 2 if py >= fy else -math.pi / 2]
        dirs = prim + [ang0] + [k * math.pi / 4 for k in range(8)]
        for extra in (0.0, 0.2, 0.45, 0.8, 1.2, 1.7, 2.3):
            for a in dirs:
                ux, uy = math.cos(a), math.sin(a)
                edge = abs(ux) * sx / 2 + abs(uy) * sy / 2
                dist = edge + CLEAR + VIA_D / 2 + 0.05 + extra
                vx, vy = px + ux * dist, py + uy * dist
                if self.ok_circle(net, vx, vy, VIA_D / 2) and self.ok_seg(net, px, py, vx, vy, w, pad):
                    self.add_trk(net, px, py, vx, vy, w)
                    self.add_via(net, vx, vy)
                    return True
        return False


def _d_pad(x, y, o):
    if o[4]:
        cx, cy, r = o[4]
        return math.hypot(x - cx, y - cy) - r
    return _d_pt_rect(x, y, o[2])


def _d_seg(x, y, s):
    x1, y1, x2, y2 = s[:4]
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    t = 0 if L2 == 0 else max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / L2))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


# ---------------------------------------------------------------------------
SILK = [
    # (texto, x, y, tamanho, rotação, camada)
    ('USB', 1.5, 1.6, 1.0, 0, 'F'), ('HDMI IN', 15.5, 19.0, 1.0, 0, 'F'), ('ETH', 35.0, 57.5, 1.0, 0, 'F'),
    ('RF IN 75R', 37.0, 59.5, 1.0, 0, 'F'), ('ASI IN 75R', 37.0, 77.0, 1.0, 0, 'F'),
    ('12V DC  + -', 146.0, 15.4, 1.0, 0, 'F'),
    ('IN1 IN2 IN3 IN4 COM +12V', 145.0, 17.0, 0.9, 270, 'F'),
    ('RELE1 C NA NF / RELE2 / RELE3 / RELE4', 145.0, 43.0, 0.9, 270, 'F'),
    ('PWR ACT OK ALM', 151.0, 91.6, 0.8, 0, 'F'),
    ('GRAVAR', 105.0, 34.0, 0.9, 0, 'F'), ('RESET', 106.0, 27.5, 0.9, 0, 'F'), ('CONSOLE', 97.5, 29.5, 0.8, 0, 'F'),
    ('LiveSafe v1.0', 100.0, 46.0, 2.2, 0, 'F'),
    ('Marcos Silva dos Santos (MarcosObel)', 100.0, 49.5, 1.1, 0, 'F'),
    ('github.com/aragonxpd154', 100.0, 52.0, 1.0, 0, 'F'),
    ('LiveSafe v1.0 - 4 camadas JLC04161H-7628', 80.0, 40.0, 1.6, 0, 'B'),
    ('Marcos Silva dos Santos (MarcosObel) - CERN-OHL-S-2.0', 80.0, 44.0, 1.2, 0, 'B'),
    ('JLCJLCJLCJLC', 80.0, 48.0, 1.0, 0, 'B'),
]


def finalize(board):
    """Planos de GND nas faces externas, textos de serigrafia, preenchimento."""
    W, H, m = LY.W, LY.H, 0.3
    full = [(m, m), (W - m, m), (W - m, H - m), (m, H - m)]
    names = {z.GetZoneName() for z in board.Zones()}
    texts = {d.GetText() for d in board.GetDrawings() if isinstance(d, pcbnew.PCB_TEXT)}
    for ly, nm in ((pcbnew.F_Cu, 'GND_L1'), (pcbnew.B_Cu, 'GND_L4')):
        if nm in names:
            continue
        add_zone(board, 'GND', ly, full, 0, clearance=0.25, min_w=0.25, name=nm)
    for txt, x, y, s, rot, side in SILK:
        if txt in texts:
            continue
        t = pcbnew.PCB_TEXT(board)
        t.SetText(txt)
        t.SetPosition(V(x, y))
        t.SetTextSize(V(s, s))
        t.SetTextThickness(MM(max(0.12, s * 0.15)))
        t.SetTextAngleDegrees(rot)
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
        if side == 'B':
            t.SetLayer(pcbnew.B_SilkS)
            t.SetMirrored(True)
            t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
        else:
            t.SetLayer(pcbnew.F_SilkS)
        board.Add(t)
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())


def patch_pro(pro):
    """Classes de rede no projeto do KiCad (para o DRC e para o roteador interativo de pares)."""
    d = json.load(open(pro))
    ns = d.setdefault('net_settings', {})
    base = {'clearance': CLEAR, 'track_width': TRACK, 'via_diameter': VIA_D, 'via_drill': VIA_DRILL,
            'microvia_diameter': 0.3, 'microvia_drill': 0.1, 'diff_pair_gap': 0.18, 'diff_pair_via_gap': 0.25,
            'diff_pair_width': 0.22, 'line_style': 0, 'wire_width': 6, 'bus_width': 12,
            'pcb_color': 'rgba(0, 0, 0, 0.000)', 'schematic_color': 'rgba(0, 0, 0, 0.000)'}
    classes = [dict(base, name='Default')]
    pats = []
    for name, (w, c, ps) in CLASSES.items():
        k = dict(base, name=name, track_width=w, clearance=CLEAR)  # roteador usou folgas maiores (DSN)
        if name == 'Dif100':
            k.update(diff_pair_width=0.22, diff_pair_gap=0.18)
        if name == 'Dif90_USB':
            k.update(diff_pair_width=0.26, diff_pair_gap=0.16)
        classes.append(k)
        pats += [{'netclass': name, 'pattern': p} for p in ps]
    ns['classes'] = classes
    ns['netclass_patterns'] = pats
    ns.setdefault('meta', {'version': 3})
    json.dump(d, open(pro, 'w'), indent=2)


def drc(pcb):
    board = pcbnew.LoadBoard(pcb)
    rpt = os.path.splitext(pcb)[0] + '-drc.rpt'
    pcbnew.WriteDRCReport(board, rpt, pcbnew.EDA_UNITS_MILLIMETRES, True)
    t = open(rpt, encoding='utf-8', errors='replace').read()
    blocks = re.findall(r'^\[(\w+)\]:.*?Severity: (\w+)', t, re.M | re.S)
    errs = {}
    for k, sev in blocks:
        if sev == 'error':
            errs[k] = errs.get(k, 0) + 1
    nunc = re.search(r'\*\* Found (\d+) unconnected pads', t)
    return errs, int(nunc.group(1)) if nunc else -1, rpt


def import_ses(board, ses):
    t = open(ses).read()
    m = re.search(r'\(resolution\s+(\w+)\s+(\d+)\)', t)
    scale = {'um': 1e-3, 'mm': 1.0, 'mil': 0.0254, 'inch': 25.4}[m.group(1)] / int(m.group(2))
    nb = board.GetNetsByName()
    have = set()
    for tr in board.GetTracks():
        if tr.GetClass() == 'PCB_VIA':
            have.add(('v', round(TO(tr.GetPosition().x), 3), round(TO(tr.GetPosition().y), 3)))
        else:
            a, b = tr.GetStart(), tr.GetEnd()
            k = tuple(sorted([(round(TO(a.x), 3), round(TO(a.y), 3)), (round(TO(b.x), 3), round(TO(b.y), 3))]))
            have.add(('t', tr.GetLayer(), k))
    layer = {'F.Cu': pcbnew.F_Cu, 'In1.Cu': pcbnew.In1_Cu, 'In2.Cu': pcbnew.In2_Cu, 'B.Cu': pcbnew.B_Cu}
    count = 0
    net_out = t[t.index('(network_out'):]
    for nm in re.finditer(r'\(net\s+("(?:[^"\\]|\\.)*"|[^\s()]+)(.*?)(?=\(net\s|\Z)', net_out, re.S):
        name = nm.group(1).strip('"')
        if not nb.has_key(name):
            print('rede SES desconhecida', name, file=sys.stderr)
            continue
        net = nb[name]
        body = nm.group(2)
        for w in re.finditer(r'\(path\s+(\S+)\s+([\d.]+)\s+([-\d.\s]+)\)', body):
            ly = layer[w.group(1)]
            width = float(w.group(2)) * scale
            c = [float(v) * scale for v in w.group(3).split()]
            pts = list(zip(c[0::2], c[1::2]))
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                k = tuple(sorted([(round(x1, 3), round(-y1, 3)), (round(x2, 3), round(-y2, 3))]))
                if ('t', ly, k) in have:
                    continue
                tr = pcbnew.PCB_TRACK(board)
                tr.SetStart(V(x1, -y1))
                tr.SetEnd(V(x2, -y2))
                tr.SetWidth(MM(width))
                tr.SetLayer(ly)
                tr.SetNet(net)
                board.Add(tr)
                count += 1
        for v in re.finditer(r'\(via\s+"?[^"\s]+"?\s+([-\d.]+)\s+([-\d.]+)', body):
            x, y = float(v.group(1)) * scale, float(v.group(2)) * scale
            if ('v', round(x, 3), round(-y, 3)) in have:
                continue
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(V(x, -y))
            via.SetDrill(MM(VIA_DRILL))
            via.SetWidth(MM(VIA_D))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetNet(net)
            board.Add(via)
    return count


if __name__ == '__main__':
    main()
