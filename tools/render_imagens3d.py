#!/usr/bin/env python3
"""Tira as imagens 3D da placa LiveSafe a partir do visualizador (docs/3d/visualizador.html).

Gera em docs/imagens/3d/: placa-3d.png, placa-topo.png, placa-fundo.png, placa-nua.png (PNG transparente).
Requer: pip install playwright && python3 -m playwright install chromium
Sem internet para o three.js: THREE_DIR=/caminho/node_modules/three python3 tools/render_imagens3d.py

Projeto: Marcos Silva dos Santos (MarcosObel) - CERN-OHL-S-2.0
"""
import os
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D3 = os.path.join(RAIZ, 'docs', '3d')
SAIDA = os.path.join(RAIZ, 'docs', 'imagens', '3d')
THREE_DIR = os.environ.get('THREE_DIR')


def main():
    os.makedirs(SAIDA, exist_ok=True)
    srv = subprocess.Popen([sys.executable, '-m', 'http.server', '8767', '-d', D3],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.8)
    try:
        with sync_playwright() as p:
            nav = p.chromium.launch(args=['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
                                          '--ignore-gpu-blocklist'])
            pg = nav.new_page(viewport={'width': 1600, 'height': 1050}, device_scale_factor=1)
            if THREE_DIR:
                def cdn(route):
                    rel = route.request.url.split('three@0.160.0/')[1]
                    route.fulfill(path=os.path.join(THREE_DIR, rel), content_type='application/javascript')
                pg.route('https://cdn.jsdelivr.net/npm/three@0.160.0/**', cdn)
            pg.goto('http://localhost:8767/visualizador.html?render')
            pg.wait_for_function('window.__pronto === "livesafe-placa"', timeout=180000)
            for nome, vista, comp in (('placa-3d', 'iso', True), ('placa-topo', 'topo', True),
                                      ('placa-fundo', 'fundo', True), ('placa-nua', 'iso', False)):
                pg.evaluate(f'window.__componentes({str(comp).lower()}); window.__vista("{vista}")')
                pg.wait_for_timeout(1200)
                pg.screenshot(path=os.path.join(SAIDA, nome + '.png'), omit_background=True)
                print(nome, flush=True)
            nav.close()
    finally:
        srv.terminate()
    from PIL import Image
    for f in os.listdir(SAIDA):
        if f.endswith('.png'):
            im = Image.open(os.path.join(SAIDA, f)).convert('RGBA')
            bb = im.getchannel('A').getbbox()
            if bb:
                im.crop((max(bb[0] - 10, 0), max(bb[1] - 10, 0), min(bb[2] + 10, im.width),
                         min(bb[3] + 10, im.height))).save(os.path.join(SAIDA, f), optimize=True)


if __name__ == '__main__':
    main()
