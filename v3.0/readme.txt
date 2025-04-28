Passos:

1. Execute 'requirements.bat' para instalar dependências (primeira vez).
2. Depois execute 'start-monitor.bat' para iniciar monitoramento.

O sistema detecta:
- Congelamento de vídeo: envia trap 1
- Tela preta: envia trap 2
- Ausência de áudio: envia trap 3

Traps SNMP são enviados automaticamente para 192.168.1.2.