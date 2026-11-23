#!/usr/bin/python3
"""Gera todo o hardware da placa LiveSafe v1.0 (Marcos Silva dos Santos):
biblioteca, esquemático hierárquico, verificação da netlist, PCB 4 camadas
roteada, DRC e arquivos de fabricação JLCPCB.

Uso (Zorin OS / Ubuntu com KiCad 7, Java 21, xvfb e o freerouting-1.9.0.jar nesta pasta):
    /usr/bin/python3 gerar_tudo.py                 # tudo
    /usr/bin/python3 gerar_tudo.py --so-esquema    # só biblioteca + esquemático + netlist
    /usr/bin/python3 gerar_tudo.py --sem-rotear    # PCB só posicionada (sem Freerouting)
    FR_PASSES=14 /usr/bin/python3 gerar_tudo.py    # passadas do roteador (padrão 8; ~4 min cada)
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
import designs  # noqa: E402
import footprints  # noqa: E402
import parts  # noqa: E402
import sch  # noqa: E402
import symlib  # noqa: E402
import verify  # noqa: E402

PROJ = sch.PROJECT
KD = os.path.join(ROOT, 'hardware', 'kicad', PROJ)
LIB = os.path.join(ROOT, 'hardware', 'kicad', 'bibliotecas')
FAB = os.path.join(ROOT, 'hardware', 'fabricacao')
TMP = os.environ.get('TMPDIR', '/tmp')


def tables(d):
    with open(os.path.join(d, 'sym-lib-table'), 'w') as f:
        f.write('(sym_lib_table\n  (lib (name "livesafe")(type "KiCad")'
                '(uri "${KIPRJMOD}/../bibliotecas/livesafe.kicad_sym")(options "")(descr "Placa LiveSafe"))\n)\n')
    with open(os.path.join(d, 'fp-lib-table'), 'w') as f:
        f.write('(fp_lib_table\n  (lib (name "livesafe")(type "KiCad")'
                '(uri "${KIPRJMOD}/../bibliotecas/livesafe.pretty")(options "")(descr "Placa LiveSafe"))\n)\n')


def project_file(d):
    pro = {
        'board': {'design_settings': {'defaults': {'board_outline_line_width': 0.1}}},
        'meta': {'filename': f'{PROJ}.kicad_pro', 'version': 1},
        'net_settings': {'classes': [{'name': 'Default', 'clearance': 0.127, 'track_width': 0.15,
                                      'via_diameter': 0.45, 'via_drill': 0.2}]},
        'text_variables': {'AUTOR': 'Marcos Silva dos Santos (MarcosObel)', 'REV': designs.Board.rev},
        'sheets': [],
    }
    path = os.path.join(d, f'{PROJ}.kicad_pro')
    if os.path.exists(path):  # já existe (regras da placa gravadas pelo pcbgen): só atualiza as variáveis
        old = json.load(open(path))
        old['text_variables'] = pro['text_variables']
        pro = old
    with open(path, 'w') as f:
        json.dump(pro, f, indent=2)


def esquema():
    os.makedirs(KD, exist_ok=True)
    os.makedirs(LIB, exist_ok=True)
    b = designs.build()
    symlib.write_library(parts.SYMS, os.path.join(LIB, 'livesafe.kicad_sym'))
    footprints.write_all(os.path.join(LIB, 'livesafe.pretty'))
    footprints.write_3d(os.path.join(LIB, 'livesafe.3dshapes'))
    tables(KD)
    project_file(KD)
    for f in os.listdir(KD):
        if f.endswith('.kicad_sch'):
            os.remove(os.path.join(KD, f))
    uuids, files = sch.write_all(b, KD)
    root = os.path.join(KD, f'{PROJ}.kicad_sch')
    net = os.path.join(TMP, f'{PROJ}.net')
    subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadsexpr', '-o', net, root],
                   check=True, capture_output=True)
    errs = verify.compare(b, verify.parse_kicad_net(net))
    fd = os.path.join(FAB, PROJ)
    os.makedirs(fd, exist_ok=True)
    subprocess.run(['kicad-cli', 'sch', 'export', 'pdf', '-o', os.path.join(ROOT, 'hardware', 'esquema-eletrico-completo.pdf'),
                    root], check=True, capture_output=True)
    json.dump(uuids, open(os.path.join(TMP, f'{PROJ}-uuids.json'), 'w'))
    st = {'componentes': len(b.comps), 'redes': len(verify.design_nets(b)), 'folhas': len(b.sheets),
          'netlist_erros': len(errs)}
    if errs:
        print('\n'.join(errs[:40]))
        raise SystemExit('netlist do KiCad diferente do designs.py')
    return b, st


def main():
    t0 = time.time()
    b, st = esquema()
    print('esquemático:', json.dumps(st, ensure_ascii=False), flush=True)
    if '--so-esquema' in sys.argv:
        return
    cmd = ['/usr/bin/python3', os.path.join(HERE, 'pcbgen.py'), KD, os.path.join(TMP, f'{PROJ}-uuids.json')]
    if '--sem-rotear' in sys.argv:
        cmd.append('--noroute')
    r = subprocess.run(cmd, text=True)
    if r.returncode:
        raise SystemExit('falha na PCB')
    if '--sem-rotear' not in sys.argv:
        subprocess.run(['/usr/bin/python3', os.path.join(HERE, 'fabricacao.py'), os.path.join(KD, f'{PROJ}.kicad_pcb'),
                        os.path.join(FAB, PROJ)], check=True)
    print(f'pronto em {time.time() - t0:.0f} s')


if __name__ == '__main__':
    main()
