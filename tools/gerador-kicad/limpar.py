#!/usr/bin/env python3
"""Limpeza final da placa roteada: vias duplicadas (mesma posição e rede) e vias/trilhas soltas apontadas pelo
DRC (via_dangling, track_dangling). Rodar antes do --finalizar.

Uso: /usr/bin/python3 limpar.py <placa.kicad_pcb> [relatorio-drc.rpt]  (sem o relatório: só as vias duplicadas)
Projeto: Marcos Silva dos Santos (MarcosObel) - CERN-OHL-S-2.0
"""
import re
import sys

import pcbnew


def main(pcb, rpt):
    board = pcbnew.LoadBoard(pcb)
    kept, dup = [], []
    for t in board.GetTracks():
        if t.GetClass() == 'PCB_VIA':
            p = t.GetPosition()
            if any(n == t.GetNetCode() and abs(p.x - x) < 20000 and abs(p.y - y) < 20000 for x, y, n in kept):
                dup.append(t)  # mesma rede a menos de 20 µm: furo repetido
            else:
                kept.append((p.x, p.y, t.GetNetCode()))
    for t in dup:
        board.Delete(t)
    txt = open(rpt, encoding='utf-8', errors='replace').read() if rpt else ''
    soltos = []
    for kind, x, y in re.findall(r'^\[(via_dangling|track_dangling)\].*?\n.*?\n\s*@\(([\d.]+) mm, ([\d.]+) mm\)', txt, re.M):
        soltos.append((kind, float(x), float(y)))
    rem = 0
    for kind, x, y in soltos:
        P = pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))
        for t in list(board.GetTracks()):
            if kind == 'via_dangling' and t.GetClass() == 'PCB_VIA' and abs(t.GetPosition().x - P.x) < 2000 \
                    and abs(t.GetPosition().y - P.y) < 2000:
                vp = t.GetPosition()
                board.Delete(t)
                rem += 1
                # trilha curta (dog-bone) que só ia até a via
                for s in list(board.GetTracks()):
                    if s.GetClass() == 'PCB_TRACK' and (s.GetEnd() == vp or s.GetStart() == vp) and \
                            pcbnew.ToMM(s.GetLength()) < 0.8:
                        board.Delete(s)
                        rem += 1
                break
            if kind == 'track_dangling' and t.GetClass() == 'PCB_TRACK':
                a, b = t.GetStart(), t.GetEnd()
                if (abs(a.x - P.x) < 2000 and abs(a.y - P.y) < 2000) or (abs(b.x - P.x) < 2000 and abs(b.y - P.y) < 2000):
                    board.Delete(t)
                    rem += 1
                    break
    pcbnew.SaveBoard(pcb, board)
    print(f'vias duplicadas removidas: {len(dup)}; itens soltos removidos: {rem}')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
