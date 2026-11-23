#!/usr/bin/python3
"""Completa as ligações que o Freerouting deixou em aberto - placa LiveSafe (Marcos Silva dos Santos).

Lê os pares "Missing connection" do relatório de DRC do KiCad e liga cada um com um
roteador de labirinto (A*) numa grade fina (0,05 mm), nas faces F.Cu e B.Cu, com troca de
face por via. Todo cobre de outra rede é obstáculo, inflado pela folga mínima. Os
preenchimentos de GND das faces externas são ignorados (são refeitos no fim).

Uso: /usr/bin/python3 completar.py <placa.kicad_pcb> <relatorio-drc.rpt>
"""
import heapq
import math
import re
import sys

import numpy as np
import pcbnew

MM = pcbnew.FromMM
TO = pcbnew.ToMM
V = lambda x, y: pcbnew.VECTOR2I(MM(x), MM(y))

G = 0.05            # passo da grade (mm)
TW = 0.12           # largura da trilha de complemento
CLR = 0.1           # folga mínima
VIA_D, VIA_DR = 0.45, 0.2
EDGE = 0.3
W, H = 160.0, 100.0
NX, NY = int(W / G) + 1, int(H / G) + 1
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)
# Com --interna o roteador também usa o In2.Cu (plano de 3,3 V/5 V) para pequenos saltos; o plano é
# repreenchido em volta da trilha depois. O In1.Cu (GND) nunca é usado: é a referência de tudo.
CUSTO_CAMADA = (1.0, 1.0, 4.0)


class Maps:
    """Para cada face, dois mapas com o código da rede dona de cada célula:
    'trk' (inflado para passar trilha) e 'via' (inflado para caber uma via)."""

    def __init__(self, board):
        self.board = board
        self.trk = [np.zeros((NY, NX), np.int32) for _ in LAYERS]
        self.via = [np.zeros((NY, NX), np.int32) for _ in LAYERS]
        self.strk = [np.zeros((NY, NX), np.int32) for _ in LAYERS]
        self.svia = [np.zeros((NY, NX), np.int32) for _ in LAYERS]
        global HARD
        if HARD is None:
            import fnmatch
            pats = ['GND', '+3V3', '+5V', 'USB_*_P', 'USB_*_N', 'HDMI_CK_*', 'HDMI_D?_*', 'CSI_*', 'ETH_P?_*',
                    'RF_ANT', 'TUN_RF*', 'ASI_IN', 'ASI_EQ', 'ASI_SDI_*', 'ASI_REF']
            HARD = {n.GetNetCode() for nm, n in board.GetNetsByName().items()
                    if any(fnmatch.fnmatchcase(str(nm), p) for p in pats)}  # nunca rasgadas (pares e RF)
        self.hard_nets = HARD
        self.inf_t = TW / 2 + CLR + 0.03
        self.inf_v = VIA_D / 2 + CLR + 0.03
        for li in range(len(LAYERS)):
            for m in (self.trk[li], self.via[li]):
                e = int(round(EDGE / G)) + 6
                m[:e, :] = -2
                m[-e:, :] = -2
                m[:, :e] = -2
                m[:, -e:] = -2
        self.drill = np.zeros((NY, NX), bool)
        self.netvias = {}
        for fp in board.GetFootprints():
            for p in fp.Pads():
                self.add_pad(p)
                if p.GetDrillSize().x > 0:
                    pos = p.GetPosition()
                    self.add_hole(TO(pos.x), TO(pos.y), TO(max(p.GetDrillSize().x, p.GetDrillSize().y)) / 2)
        for t in board.GetTracks():
            self.add_track(t)
        if len(LAYERS) > 2:  # no In2, a faixa do plano de 5 V fica proibida (não pode ser cortada)
            import layouts as LY
            xs = [p[0] for p in LY.PLANE_5V]
            ys = [p[1] for p in LY.PLANE_5V]
            i0, i1 = int((min(xs) - 0.3) / G), int((max(xs) + 0.3) / G) + 1
            j0, j1 = int((min(ys) - 0.3) / G), int((max(ys) + 0.3) / G) + 1
            self.trk[2][j0:j1, i0:i1] = -2

    def _stamp(self, li, net, shape, args, soft=False):
        mm = ((self.strk[li], self.inf_t), (self.svia[li], self.inf_v)) if soft else \
            ((self.trk[li], self.inf_t), (self.via[li], self.inf_v))
        for m, inf in mm:
            if shape == 'circle':
                cx, cy, r = args
                R = r + inf
                x0, x1, y0, y1 = cx - R, cx + R, cy - R, cy + R
            elif shape == 'rect':
                ax0, ay0, ax1, ay1 = args
                x0, x1, y0, y1 = ax0 - inf, ax1 + inf, ay0 - inf, ay1 + inf
            else:  # segmento (cápsula)
                sx0, sy0, sx1, sy1, w = args
                R = w / 2 + inf
                x0, x1, y0, y1 = min(sx0, sx1) - R, max(sx0, sx1) + R, min(sy0, sy1) - R, max(sy0, sy1) + R
            i0, i1 = max(0, int(x0 / G)), min(NX - 1, int(math.ceil(x1 / G)))
            j0, j1 = max(0, int(y0 / G)), min(NY - 1, int(math.ceil(y1 / G)))
            if i1 < i0 or j1 < j0:
                continue
            xs = np.arange(i0, i1 + 1) * G
            ys = np.arange(j0, j1 + 1) * G
            X, Y = np.meshgrid(xs, ys)
            if shape == 'circle':
                mask = np.hypot(X - cx, Y - cy) <= r + inf
            elif shape == 'rect':
                dx = np.maximum(np.maximum(ax0 - X, 0), X - ax1)
                dy = np.maximum(np.maximum(ay0 - Y, 0), Y - ay1)
                mask = np.hypot(dx, dy) <= inf
            else:
                vx, vy = sx1 - sx0, sy1 - sy0
                L2 = vx * vx + vy * vy
                tt = np.zeros_like(X) if L2 == 0 else np.clip(((X - sx0) * vx + (Y - sy0) * vy) / L2, 0, 1)
                mask = np.hypot(X - (sx0 + tt * vx), Y - (sy0 + tt * vy)) <= w / 2 + inf
            sub = m[j0:j1 + 1, i0:i1 + 1]
            cur = sub[mask]
            new = np.where(cur == 0, net, np.where(cur == net, net, -2))
            sub[mask] = new

    def add_pad(self, p):
        net = p.GetNetCode() or -1
        pos = p.GetPosition()
        cx, cy = TO(pos.x), TO(pos.y)
        for li, ly in enumerate(LAYERS):
            if not p.IsOnLayer(ly):
                continue
            if p.GetShape() == pcbnew.PAD_SHAPE_CIRCLE:
                self._stamp(li, net, 'circle', (cx, cy, TO(p.GetSize().x) / 2))
            else:
                bb = p.GetBoundingBox()
                self._stamp(li, net, 'rect', (TO(bb.GetX()), TO(bb.GetY()), TO(bb.GetRight()), TO(bb.GetBottom())))
            if p.GetDrillSize().x > 0:  # folga furo-cobre (0,2 mm) vale para qualquer rede
                d = TO(max(p.GetDrillSize().x, p.GetDrillSize().y)) / 2
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH or not p.GetNetCode():
                    self._stamp(li, -2, 'circle', (cx, cy, d + 0.12))

    def add_hole(self, x, y, r):
        R = r + VIA_DR / 2 + 0.3
        i0, i1 = max(0, int((x - R) / G)), min(NX - 1, int((x + R) / G) + 1)
        j0, j1 = max(0, int((y - R) / G)), min(NY - 1, int((y + R) / G) + 1)
        X, Y = np.meshgrid(np.arange(i0, i1 + 1) * G, np.arange(j0, j1 + 1) * G)
        self.drill[j0:j1 + 1, i0:i1 + 1] |= np.hypot(X - x, Y - y) <= R

    def add_track(self, t, net=None):
        net = net or t.GetNetCode() or -1
        soft = net not in self.hard_nets and t.m_Uuid.AsString() not in FRESH
        if t.GetClass() == 'PCB_VIA':
            pos = t.GetPosition()
            self.netvias.setdefault(net, set()).add((int(round(TO(pos.x) / G)), int(round(TO(pos.y) / G))))
            self.add_hole(TO(pos.x), TO(pos.y), TO(t.GetDrillValue()) / 2)
            for li in range(len(LAYERS)):
                self._stamp(li, net, 'circle', (TO(pos.x), TO(pos.y), TO(t.GetWidth()) / 2), soft)
            return
        if t.GetLayer() not in LAYERS:
            return
        li = LAYERS.index(t.GetLayer())
        a, b = t.GetStart(), t.GetEnd()
        self._stamp(li, net, 'seg', (TO(a.x), TO(a.y), TO(b.x), TO(b.y), TO(t.GetWidth())), soft)


HARD = None
FRESH = set()  # trechos feitos nesta rodada: não são rasgados de novo
VIA_COST_0 = 30.0
LIMITE = 1_500_000


def astar(maps, net, start, goal, margin=6.0, ripup=False, src=None, dst=None):
    """start/goal: (x, y, [faces]). Retorna lista de (i, j, face) ou None.
    src/dst (opcionais): células (x, y, face) de todo o cobre de cada ilha da rede; a busca sai de
    qualquer ponto da primeira e chega em qualquer ponto da segunda."""
    (sx, sy, sl), (gx, gy, gl) = start, goal
    xs_ = [sx, gx] + [c[0] for c in (src or [])] + [c[0] for c in (dst or [])]
    ys_ = [sy, gy] + [c[1] for c in (src or [])] + [c[1] for c in (dst or [])]
    x0, x1 = max(0, min(xs_) - margin), min(W, max(xs_) + margin)
    y0, y1 = max(0, min(ys_) - margin), min(H, max(ys_) + margin)
    i0, i1, j0, j1 = int(x0 / G), int(x1 / G), int(y0 / G), int(y1 / G)
    sl_ = (slice(j0, j1 + 1), slice(i0, i1 + 1))
    free = lambda m: (m[sl_] == 0) | (m[sl_] == net)
    ok = [free(m) for m in maps.trk]
    okv = ~maps.drill[sl_]
    for m in maps.via:
        okv &= free(m)
    if ripup:  # trilhas de sinal de outras redes podem ser atravessadas com custo
        pen = [np.where(free(m), 0.0, 60.0) for m in maps.strk]
        sv = np.ones_like(okv)
        for m in maps.svia:
            sv &= free(m)
        penv = np.where(sv, 0.0, 150.0)
    else:
        ok = [o & free(m) for o, m in zip(ok, maps.strk)]
        for m in maps.svia:
            okv = okv & free(m)
        pen = [np.zeros_like(ok[0], float)] * len(LAYERS)
        penv = np.zeros_like(okv, float)
    own = set()  # vias que já existem na própria rede: troca de face sem custo
    for (vi, vj) in maps.netvias.get(net, ()):
        if i0 <= vi <= i1 and j0 <= vj <= j1:
            own.add((vi - i0, vj - j0))
            okv[vj - j0, vi - i0] = True
            penv[vj - j0, vi - i0] = -VIA_COST_0
            for m in ok:
                m[vj - j0, vi - i0] = True
    si, sj = int(round(sx / G)) - i0, int(round(sy / G)) - j0
    gi, gj = int(round(gx / G)) - i0, int(round(gy / G)) - j0
    nyl, nxl = ok[0].shape
    for l in sl:
        ok[l][max(0, sj - 2):sj + 3, max(0, si - 2):si + 3] = True
    for l in gl:
        ok[l][max(0, gj - 2):gj + 3, max(0, gi - 2):gi + 3] = True
    VIA_COST = 30.0
    moves = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
             (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142)]
    wh = 1.6 if ripup else 1.0  # heurística ponderada no modo rasgar (busca menor)
    h = lambda i, j: wh * math.hypot(i - gi, j - gj)
    best = {}
    pq = []
    for l in sl:
        best[(si, sj, l)] = 0.0
        heapq.heappush(pq, (h(si, sj), 0.0, si, sj, l, None))
    came = {}
    goals = {(gi, gj, l) for l in gl}
    for (x, y, l) in (src or []):
        ci, cj = int(round(x / G)) - i0, int(round(y / G)) - j0
        if 0 <= ci < nxl and 0 <= cj < nyl and l < len(ok) and (ci, cj, l) not in best:
            ok[l][cj, ci] = True
            best[(ci, cj, l)] = 0.0
            heapq.heappush(pq, (h(ci, cj), 0.0, ci, cj, l, None))
    for (x, y, l) in (dst or []):
        ci, cj = int(round(x / G)) - i0, int(round(y / G)) - j0
        if 0 <= ci < nxl and 0 <= cj < nyl and l < len(ok):
            ok[l][cj, ci] = True
            goals.add((ci, cj, l))
    n = 0
    while pq:
        f, g, i, j, l, d = heapq.heappop(pq)
        if (i, j, l) in goals:
            path = [(i, j, l)]
            k = (i, j, l)
            while k in came:
                k = came[k]
                path.append(k)
            return [(a + i0, b + j0, c) for a, b, c in reversed(path)]
        if g > best.get((i, j, l), 1e18) + 1e-9:
            continue
        n += 1
        if n > (600_000 if ripup else LIMITE) or len(pq) > 6_000_000:
            return None
        for di, dj, c in moves:
            ni, nj = i + di, j + dj
            if 0 <= ni < nxl and 0 <= nj < nyl and ok[l][nj, ni]:
                if di and dj and not (ok[l][j, ni] and ok[l][nj, i]):
                    continue
                turn = 0.0 if d is None or d == (di, dj) else 0.3
                ng = g + c * CUSTO_CAMADA[l] + turn + pen[l][nj, ni]
                k = (ni, nj, l)
                if ng < best.get(k, 1e18):
                    best[k] = ng
                    came[k] = (i, j, l)
                    heapq.heappush(pq, (ng + h(ni, nj), ng, ni, nj, l, (di, dj)))
        if okv[j, i]:
            for nl in range(len(ok)):
                if nl == l or not ok[nl][j, i]:
                    continue
                ng = g + VIA_COST + penv[j, i]
                k = (i, j, nl)
                if ng < best.get(k, 1e18):
                    best[k] = ng
                    came[k] = (i, j, l)
                    heapq.heappush(pq, (ng + h(i, j), ng, i, j, nl, None))
    return None


def commit(board, maps, net, path):
    """Converte a sequência de células em trilhas (juntando trechos retos) e vias."""
    ni = board.FindNet(board.GetNetsByNetcode()[net].GetNetname())
    added = []
    segs = []
    cur = [path[0]]
    for a, b in zip(path, path[1:]):
        if a[2] != b[2]:
            segs.append(cur)
            if (a[0], a[1]) in maps.netvias.get(net, ()):
                cur = [b]
                continue
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(V(a[0] * G, a[1] * G))
            v.SetWidth(MM(VIA_D))
            v.SetDrill(MM(VIA_DR))
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetNet(ni)
            board.Add(v)
            added.append(v)
            cur = [b]
        else:
            cur.append(b)
    segs.append(cur)
    for run in segs:
        if len(run) < 2:
            continue
        pts = [run[0]]
        for k in range(1, len(run) - 1):
            p0, p1, p2 = pts[-1], run[k], run[k + 1]
            d1 = (p1[0] - p0[0], p1[1] - p0[1])
            d2 = (p2[0] - p1[0], p2[1] - p1[1])
            if d1[0] * d2[1] - d1[1] * d2[0] != 0:
                pts.append(p1)
        pts.append(run[-1])
        ly = LAYERS[run[0][2]]
        for p, q in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(V(p[0] * G, p[1] * G))
            t.SetEnd(V(q[0] * G, q[1] * G))
            t.SetWidth(MM(TW))
            t.SetLayer(ly)
            t.SetNet(ni)
            board.Add(t)
            added.append(t)
    for o in added:
        FRESH.add(o.m_Uuid.AsString())
        maps.add_track(o, net)
    return len(added)


def ripup(board, maps, net, path):
    """Remove trilhas/vias de outras redes de sinal que encostam no caminho escolhido."""
    cells = {}
    for i, j, l in path:
        cells.setdefault(l, []).append((i * G, j * G))
    vias = [(a[0] * G, a[1] * G) for a, b in zip(path, path[1:]) if a[2] != b[2]]
    victims = {}
    for tr in list(board.GetTracks()):
        n = tr.GetNetCode()
        if n == net or n in maps.hard_nets or tr.m_Uuid.AsString() in FRESH:
            continue
        if tr.GetClass() == 'PCB_VIA':
            p = tr.GetPosition()
            x, y, r = TO(p.x), TO(p.y), TO(tr.GetWidth()) / 2
            near = any(math.hypot(x - a, y - b) < r + TW / 2 + CLR + 0.05 for l in cells for a, b in cells[l])
            near |= any(math.hypot(x - a, y - b) < r + VIA_D / 2 + CLR + 0.05 for a, b in vias)
        else:
            if tr.GetLayer() not in LAYERS:
                continue
            l = LAYERS.index(tr.GetLayer())
            a_, b_ = tr.GetStart(), tr.GetEnd()
            s = (TO(a_.x), TO(a_.y), TO(b_.x), TO(b_.y))
            w = TO(tr.GetWidth())
            pts = cells.get(l, []) + vias
            lim = w / 2 + max(TW, VIA_D) / 2 + CLR + 0.05
            bx0, bx1 = min(s[0], s[2]) - lim, max(s[0], s[2]) + lim
            by0, by1 = min(s[1], s[3]) - lim, max(s[1], s[3]) + lim
            near = False
            for a, b in pts:
                if bx0 <= a <= bx1 and by0 <= b <= by1 and _dseg(a, b, s) < (w / 2 + (VIA_D if (a, b) in vias else TW) / 2 + CLR + 0.02):
                    near = True
                    break
        if near:
            victims[tr.m_Uuid.AsString()] = tr
    for tr in victims.values():
        board.Delete(tr)
    return len(victims)


def _dseg(x, y, s):
    x1, y1, x2, y2 = s
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    t = 0 if L2 == 0 else max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / L2))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def ilhas(board, net, a, b):
    """Células de cobre das duas ilhas da rede que contêm os pontos a e b (x, y em mm)."""
    itens = []  # (tipo, geometria, faces)
    for tr in board.GetTracks():
        if tr.GetNetCode() != net:
            continue
        if tr.GetClass() == 'PCB_VIA':
            p = tr.GetPosition()
            itens.append(('v', (TO(p.x), TO(p.y)), list(range(len(LAYERS)))))
        elif tr.GetLayer() in LAYERS:
            s, e = tr.GetStart(), tr.GetEnd()
            itens.append(('t', (TO(s.x), TO(s.y), TO(e.x), TO(e.y)), [LAYERS.index(tr.GetLayer())]))
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() == net:
                bb = p.GetBoundingBox()
                fl = [i for i, ly in enumerate(LAYERS) if p.IsOnLayer(ly)]
                itens.append(('p', (TO(bb.GetX()), TO(bb.GetY()), TO(bb.GetRight()), TO(bb.GetBottom())), fl))
    def pts(it):
        k, g, _ = it
        if k == 'v':
            return [g]
        if k == 't':
            return [(g[0], g[1]), (g[2], g[3])]
        return [((g[0] + g[2]) / 2, (g[1] + g[3]) / 2)]
    def toca(it, x, y, fl):
        k, g, f2 = it
        if not set(fl) & set(f2):
            return False
        if k == 'p':
            return g[0] - 0.01 <= x <= g[2] + 0.01 and g[1] - 0.01 <= y <= g[3] + 0.01
        if k == 'v':
            return math.hypot(x - g[0], y - g[1]) < 0.05
        return _dseg(x, y, g) < 0.02
    n = len(itens)
    pai = list(range(n))
    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i
    for i in range(n):
        for (x, y) in pts(itens[i]):
            for j in range(n):
                if i != j and toca(itens[j], x, y, itens[i][2]):
                    pai[raiz(i)] = raiz(j)
    def ilha(pt):
        x, y = pt[0], pt[1]
        best = min(range(n), key=lambda i: min(math.hypot(x - px, y - py) for px, py in pts(itens[i]))
                   if itens[i][0] != 't' else _dseg(x, y, itens[i][1]))
        r = raiz(best)
        cel = []
        for i in range(n):
            if raiz(i) != r:
                continue
            k, g, fl = itens[i]
            if k == 't':
                L = math.hypot(g[2] - g[0], g[3] - g[1])
                m = max(1, int(L / G))
                for s in range(m + 1):
                    cel += [(g[0] + (g[2] - g[0]) * s / m, g[1] + (g[3] - g[1]) * s / m, l) for l in fl]
            elif k == 'v':
                cel += [(g[0], g[1], l) for l in fl]
            else:
                cel += [((g[0] + g[2]) / 2, (g[1] + g[3]) / 2, l) for l in fl]
        return cel, r
    A, ra = ilha(a)
    B, rb = ilha(b)
    return (A, B) if ra != rb else (None, None)


def pairs(rpt):
    t = open(rpt, encoding='utf-8', errors='replace').read()
    sec = t[t.index('unconnected pads'):] if 'unconnected pads' in t else t
    out = []
    for b in re.split(r'\n(?=\[unconnected_items\])', sec)[1:]:
        it = re.findall(r'@\(([\d.]+) mm, ([\d.]+) mm\): (.*?)\[([^\]]*)\](.*)', b)
        if len(it) < 2:
            continue
        ends = []
        for x, y, kind, net, rest in it[:2]:
            if 'B.Cu' in rest and 'F.Cu' not in rest:
                fl = [1]
            elif 'F.Cu - B.Cu' in rest or 'PTH' in kind:
                fl = list(range(len(LAYERS)))
            else:
                fl = [0]
            ends.append((float(x), float(y), fl))
        out.append((it[0][3], ends[0], ends[1]))
    return out


def main():
    global TW, VIA_D
    pcb, rpt = sys.argv[1], sys.argv[2]
    if '--fino' in sys.argv:  # segunda rodada: trilha de 0,1 mm e via de 0,4 mm
        TW, VIA_D = 0.1, 0.4
    rip = '--rasgar' in sys.argv
    global LAYERS
    if '--interna' in sys.argv:
        LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu)
    global CUSTO_CAMADA
    if '--custo-interna' in sys.argv:  # ligações longas: o In2 fica barato e a busca vai direto para ele
        CUSTO_CAMADA = (1.0, 1.0, float(sys.argv[sys.argv.index('--custo-interna') + 1]))
    global LIMITE
    so = sys.argv[sys.argv.index('--rede') + 1] if '--rede' in sys.argv else None
    if '--limite' in sys.argv:
        LIMITE = int(sys.argv[sys.argv.index('--limite') + 1])
    board = pcbnew.LoadBoard(pcb)
    maps = Maps(board)
    byname = board.GetNetsByName()
    done, fail = 0, []
    for name, a, b in sorted(pairs(rpt), key=lambda p: math.hypot(p[1][0] - p[2][0], p[1][1] - p[2][1])):
        if so and name != so:
            continue
        net = byname[name].GetNetCode()
        path = None
        for margin in ((2.0, 5.0) if so else (4.0, 10.0)):
            path = astar(maps, net, a, b, margin)
            if path:
                break
        if not path and '--ilhas' in sys.argv:  # de qualquer ponto de uma ilha a qualquer ponto da outra
            A, B = ilhas(board, net, a, b)
            if A:
                path = astar(maps, net, a, b, 3.0, src=A, dst=B)
        ripped = 0
        if not path and rip:
            path = astar(maps, net, a, b, 6.0, ripup=True)
            if path:
                ripped = ripup(board, maps, net, path)
                maps = Maps(board)  # refaz os mapas sem as trilhas removidas
        if path:
            commit(board, maps, net, path)
            if ripped:
                print(f'   (removidos {ripped} trechos de outras redes para passar)')
            done += 1
        else:
            fail.append(name)
        print(f'{name:14} {"ok" if path else "FALHOU"}', flush=True)
    pcbnew.SaveBoard(pcb, board)
    print(f'ligadas {done}, falharam {len(fail)}: {fail}')


if __name__ == '__main__':
    main()
