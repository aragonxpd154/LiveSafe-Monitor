"""Confere a netlist exportada pelo KiCad contra designs.py (Marcos Silva dos Santos).

Toda rede do designs.py tem que existir no KiCad com exatamente os mesmos
pinos, e o KiCad não pode ter rede a mais. É a garantia de que o desenho do
esquemático (rótulos, símbolos de alimentação, unidades do CM4) não trocou
nenhuma ligação.
"""
import re


def parse_kicad_net(path):
    t = open(path, encoding='utf-8').read()
    nets = {}
    for m in re.finditer(r'\(net \(code "\d+"\) \(name "([^"]*)"\)(.*?)(?=\(net \(code|\Z)', t, re.S):
        nodes = re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', m.group(2))
        nets[m.group(1)] = {(r, p) for r, p in nodes}
    return nets


def norm(name):
    return name.rsplit('/', 1)[-1] if name.startswith('/') else name


def design_nets(board):
    nets = {}
    for c in board.comps.values():
        for p, n in c.pins.items():
            if n:
                nets.setdefault(n, set()).add((c.ref, p))
    return nets


def compare(board, kicad_nets):
    errs = []
    want = design_nets(board)
    got = {}
    for n, nodes in kicad_nets.items():
        nodes = {x for x in nodes if not x[0].startswith('#')}
        if not nodes:
            continue
        if n.startswith('unconnected-') and len({r for r, _ in nodes}) == 1:
            continue  # pino solto (ou pinos empilhados de um mesmo CI, ex.: +1V8_OUT do CM4)
        got.setdefault(norm(n), set()).update(nodes)
    for n, nodes in want.items():
        if n not in got:
            errs.append(f'rede {n} ausente no KiCad')
        elif got[n] != nodes:
            errs.append(f'rede {n}: faltando {sorted(nodes - got[n])[:6]} sobrando {sorted(got[n] - nodes)[:6]}')
    for n in got:
        if n not in want:
            errs.append(f'rede extra no KiCad: {n} {sorted(got[n])[:6]}')
    return errs
