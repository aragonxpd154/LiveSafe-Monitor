@echo off
echo 🚀 Iniciando servidor Node.js (server.js)...
start cmd /k "node server.js"

timeout /t 2

echo 🚀 Iniciando live-server para html.html...
start cmd /k "live-server --port=5500 --entry-file=html.html"

echo ✅ Monitoramento iniciado!
pause
