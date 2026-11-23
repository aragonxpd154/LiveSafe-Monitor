#!/usr/bin/env python3
"""Leva para uma PCB já roteada o que mudou no designs.py sem mexer no cobre: valor, MPN, fabricante,
código LCSC e o caminho (UUID) de cada footprint no esquemático.

Uso: /usr/bin/python3 sincronizar.py <placa.kicad_pcb> <uuids.json>
Projeto: Marcos Silva dos Santos (MarcosObel) - CERN-OHL-S-2.0
"""
import json
import sys

import pcbnew

import designs


def main(pcb, uu):
    d = designs.build()
    uuids = json.load(open(uu))
    board = pcbnew.LoadBoard(pcb)
    n = 0
    for fp in board.GetFootprints():
        c = d.comps.get(fp.GetReference())
        if c is None:
            continue
        fp.SetValue(c.value)
        for k, v in (('MPN', c.mpn), ('Fabricante', c.fab), ('LCSC', c.lcsc)):
            if v:
                fp.SetProperty(k, v)
            elif fp.HasProperty(k):
                fp.RemoveProperty(k)
        if fp.GetReference() in uuids:
            fp.SetPath(pcbnew.KIID_PATH(uuids[fp.GetReference()]))
        n += 1
    pcbnew.SaveBoard(pcb, board)
    print(f'{n} footprints sincronizados')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
