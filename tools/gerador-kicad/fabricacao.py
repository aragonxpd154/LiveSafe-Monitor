#!/usr/bin/python3
"""Arquivos de fabricação e montagem JLCPCB - placa LiveSafe (Marcos Silva dos Santos).

Gera em hardware/fabricacao/livesafe-placa/:
  livesafe-placa-gerber.zip      Gerber das 4 camadas + máscara, pasta, serigrafia, contorno e furação
  bom-jlcpcb.csv                 lista de materiais no formato da montagem JLCPCB (sem os NM)
  cpl-jlcpcb.csv                 posição e rotação dos componentes (Designator, Mid X, Mid Y, Layer, Rotation)
  lista-de-materiais.csv         lista completa (inclui NM, fabricante e código)
  livesafe-placa.step            modelo 3D mecânico
  montagem-topo.pdf              desenho de montagem (pátios, referências e contorno)
  camadas.pdf                    uma página por camada de cobre
  relatorio-drc.txt              resultado do DRC

Uso: /usr/bin/python3 fabricacao.py <arquivo.kicad_pcb> <pasta_saida>
"""
import csv
import glob
import os
import re
import shutil
import subprocess
import sys
import zipfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import designs
import lcsc as LCSC_  # noqa: E402

LAYERS = 'F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts'


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(' '.join(cmd) + '\n' + r.stdout + r.stderr)
    return r


def natkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', s)]


def gerbers(pcb, out, base):
    g = os.path.join(out, 'gerber')
    shutil.rmtree(g, ignore_errors=True)
    os.makedirs(g)
    run(['kicad-cli', 'pcb', 'export', 'gerbers', '--layers', LAYERS, '--subtract-soldermask', '-o', g + '/', pcb])
    run(['kicad-cli', 'pcb', 'export', 'drill', '--format', 'excellon', '--excellon-units', 'mm',
         '--excellon-separate-th', '--generate-map', '--map-format', 'pdf', '-o', g + '/', pcb])
    zp = os.path.join(out, f'{base}-gerber.zip')
    with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(glob.glob(g + '/*')):
            if f.endswith('.pdf'):
                shutil.copy(f, os.path.join(out, 'mapa-de-furacao-' + ('npth' if 'NPTH' in f else 'pth') + '.pdf'))
                continue
            z.write(f, os.path.basename(f))
    shutil.rmtree(g)
    return zp


def bom_cpl(pcb, out):
    b = designs.build()
    board = pcbnew.LoadBoard(pcb)
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    # lista completa
    rows = {}
    for ref, c in b.comps.items():
        key = (c.value, c.fp, c.mpn, c.dnp)
        rows.setdefault(key, []).append(ref)
    with open(os.path.join(out, 'lista-de-materiais.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Qtd', 'Valor', 'Referências', 'Footprint', 'Fabricante', 'Código (MPN)', 'LCSC', 'Montar'])
        for (val, fp, mpn, dnp), refs in sorted(rows.items(), key=lambda x: natkey(sorted(x[1], key=natkey)[0])):
            c = b.comps[refs[0]]
            w.writerow([len(refs), val, ' '.join(sorted(refs, key=natkey)), fp.split(':')[-1], c.fab, mpn, c.lcsc,
                        'NÃO (NM)' if dnp else 'sim'])
    # BOM JLC (sem os NM): só o que tem código LCSC; o resto vai para pecas-fora-da-jlcpcb.csv
    fora = []
    montar = set()
    with open(os.path.join(out, 'bom-jlcpcb.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #', 'Manufacturer Part Number'])
        for (val, fp, mpn, dnp), refs in sorted(rows.items(), key=lambda x: natkey(sorted(x[1], key=natkey)[0])):
            if dnp or 'U1' in refs or not mpn:
                continue
            c = b.comps[refs[0]]
            if not c.lcsc:
                fora.append((val, refs, fp, c.fab, mpn))
                continue
            montar.update(refs)
            w.writerow([val, ','.join(sorted(refs, key=natkey)), fp.split(':')[-1], c.lcsc, mpn])
        # o CM4 é encaixado à mão; a JLCPCB monta só os dois conectores da placa
        w.writerow(['DF40C-100DS-0.4V(51)', 'CN1,CN2', 'Hirose_DF40C-100DS-0.4V', LCSC_.LCSC['DF40C-100DS-0.4V(51)'],
                    'DF40C-100DS-0.4V(51)'])
    with open(os.path.join(out, 'pecas-fora-da-jlcpcb.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Qtd', 'Valor', 'Referências', 'Footprint', 'Fabricante', 'Código (MPN)', 'Como entra'])
        for val, refs, fp, fab, mpn in fora:
            tht = any(k in fp for k in ('THT', 'Horizontal', 'Vertical', 'Molex_KK', 'PhoenixContact', 'BNC', 'RJ45'))
            w.writerow([len(refs), val, ' '.join(sorted(refs, key=natkey)), fp.split(':')[-1], fab, mpn,
                        'solda manual (THT)' if tht else 'Global Sourcing da JLCPCB ou peça consignada'])
        w.writerow([1, 'CM4104032', 'U1', 'Raspberry_Pi_CM4_DF40', 'Raspberry Pi', 'CM4104032',
                    'encaixado à mão nos conectores CN1/CN2'])
        w.writerow([1, 'CR1220', 'BT1 (bateria)', '-', '-', 'CR1220', 'colocada à mão no suporte'])
    # CPL (posições em mm, y para cima como no arquivo de posição do KiCad)
    with open(os.path.join(out, 'cpl-jlcpcb.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
        u1 = fps['U1']
        for cn, lo, hi in (('CN1', 1, 100), ('CN2', 101, 200)):
            ps = [p.GetPosition() for p in u1.Pads() if p.GetNumber().isdigit() and lo <= int(p.GetNumber()) <= hi]
            x = sum(pcbnew.ToMM(p.x) for p in ps) / len(ps)
            y = sum(pcbnew.ToMM(p.y) for p in ps) / len(ps)
            w.writerow([cn, f'{x:.3f}mm', f'{-y:.3f}mm', 'Top', f'{u1.GetOrientationDegrees() % 360:.1f}'])
        for ref in sorted(fps, key=natkey):
            c = b.comps.get(ref)
            if c is None or c.dnp or ref == 'U1' or ref not in montar:
                continue
            fp = fps[ref]
            p = fp.GetPosition()
            rot = fp.GetOrientationDegrees() % 360
            w.writerow([ref, f'{pcbnew.ToMM(p.x):.3f}mm', f'{-pcbnew.ToMM(p.y):.3f}mm',
                        'Top' if fp.GetLayer() == pcbnew.F_Cu else 'Bottom', f'{rot:.1f}'])


def pdfs(pcb, out):
    run(['kicad-cli', 'pcb', 'export', 'pdf', '--layers', 'F.Fab,F.CrtYd,Edge.Cuts,F.SilkS', '--include-border-title',
         '-o', os.path.join(out, 'montagem-topo.pdf'), pcb])
    pages = []
    for ly in ('F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu'):
        p = os.path.join(out, f'_camada-{ly}.pdf')
        run(['kicad-cli', 'pcb', 'export', 'pdf', '--layers', f'{ly},Edge.Cuts', '--include-border-title', '-o', p, pcb])
        pages.append(p)
    try:
        from pypdf import PdfWriter
        wtr = PdfWriter()
        for p in pages:
            wtr.append(p)
        wtr.write(os.path.join(out, 'camadas.pdf'))
    except ImportError:
        run(['pdfunite'] + pages + [os.path.join(out, 'camadas.pdf')])
    for p in pages:
        os.remove(p)


def step(pcb, out, base):
    dst = os.path.join(out, f'{base}.step')
    r = subprocess.run(['kicad-cli', 'pcb', 'export', 'step', '--subst-models', '--force', '-o', dst, pcb],
                       capture_output=True, text=True)
    return dst if os.path.exists(dst) else None


def drc(pcb, out):
    board = pcbnew.LoadBoard(pcb)
    rpt = os.path.join(out, 'relatorio-drc.txt')
    pcbnew.WriteDRCReport(board, rpt, pcbnew.EDA_UNITS_MILLIMETRES, True)
    t = open(rpt, encoding='utf-8', errors='replace').read()
    blocks = re.findall(r'^\[(\w+)\]:.*?Severity: (\w+)', t, re.M | re.S)
    errs = [k for k, sev in blocks if sev == 'error']
    nunc = re.search(r'\*\* Found (\d+) unconnected pads', t)
    return {'erros': len(errs), 'tipos': sorted(set(errs)), 'sem_conexao': int(nunc.group(1)) if nunc else -1}


def resumo_docs(pcb, res):
    """Escreve o resumo da placa e do último DRC no fim de docs/03-pcb.md."""
    import datetime
    board = pcbnew.LoadBoard(pcb)
    tr = [x for x in board.GetTracks() if x.GetClass() == 'PCB_TRACK']
    vias = [x for x in board.GetTracks() if x.GetClass() == 'PCB_VIA']
    comp = len(board.GetFootprints())
    comp_mm = sum(pcbnew.ToMM(x.GetLength()) for x in tr)
    nets = board.GetNetCount() - 1
    ok = res['erros'] == 0 and res['sem_conexao'] == 0
    txt = (f"\n## Resumo do último DRC\n\n"
           f"Gerado em {datetime.date.today():%d/%m/%Y} pelo `fabricacao.py` (KiCad {pcbnew.Version()}).\n\n"
           f"| Item | Valor |\n|---|---|\n"
           f"| Componentes | {comp} |\n| Redes | {nets} |\n| Trechos de trilha | {len(tr)} |\n"
           f"| Comprimento total de trilha | {comp_mm / 1000:.2f} m |\n| Vias | {len(vias)} |\n"
           f"| Erros de DRC | {res['erros']} |\n| Ligações sem conexão | {res['sem_conexao']} |\n\n"
           + ("Resultado: **DRC limpo** — nenhuma violação e nenhuma ligação pendente.\n" if ok else
              "Resultado: **há pendências** — ver `relatorio-drc.txt` antes de fabricar.\n"))
    doc = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       'docs', '03-pcb.md')
    d = open(doc, encoding='utf-8').read()
    d = d.split('\n## Resumo do último DRC')[0].rstrip('\n') + '\n' + txt
    open(doc, 'w', encoding='utf-8').write(d)


def export_all(pcb, out):
    os.makedirs(out, exist_ok=True)
    base = os.path.splitext(os.path.basename(pcb))[0]
    gerbers(pcb, out, base)
    bom_cpl(pcb, out)
    pdfs(pcb, out)
    step(pcb, out, base)
    res = drc(pcb, out)
    resumo_docs(pcb, res)
    return res


if __name__ == '__main__':
    print(export_all(sys.argv[1], sys.argv[2]))
