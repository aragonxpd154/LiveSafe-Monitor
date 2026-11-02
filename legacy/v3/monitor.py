import subprocess
import cv2
import numpy as np
import threading
import time
import json
import logging
from pysnmp.hlapi import sendNotification, SnmpEngine, CommunityData, UdpTransportTarget, ContextData, NotificationType, ObjectIdentity, ObjectType

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('monitor_hdmi.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Carregar configurações
def carregar_configuracoes():
    config_padrao = {
        "IP_DESTINO": "192.168.1.2",
        "OID": "1.3.6.1.4.1.53864.1.1",
        "COMUNIDADE": "public",
        "TEMPO_VERIFICACAO": 1.0,
        "LIMIAR_SILENCIO": 500,
        "VIDEO_DEVICE_NAME": "USB Video",
        "AUDIO_DEVICE_NAME": "Microfone (USB Audio Device)",
        "VIDEO_WIDTH": 1280,
        "VIDEO_HEIGHT": 720,
        "THRESHOLD_CONGELADO": 100,
        "THRESHOLD_PRETO": 5
    }
    
    try:
        with open('config.json') as f:
            config = json.load(f)
            logger.info("Configurações carregadas do arquivo config.json")
            return {**config_padrao, **config}  # Mescla com as padrão
    except FileNotFoundError:
        logger.warning("Arquivo config.json não encontrado, usando configurações padrão")
        return config_padrao
    except Exception as e:
        logger.error(f"Erro ao carregar configurações: {e}, usando configurações padrão")
        return config_padrao

config = carregar_configuracoes()

class EstadoMonitoramento:
    def __init__(self):
        self.ultimo_audio_ok = time.time()
        self.ultimo_video_ok = time.time()
        self.alarme_audio = False
        self.alarme_congelado = False
        self.alarme_preto = False
        self.last_frame = None
        self.frame_atual = None
        self.lock = threading.Lock()
        self.executando = True

estado = EstadoMonitoramento()

def enviar_trap(valor):
    try:
        errorIndication, errorStatus, errorIndex, varBinds = next(
            sendNotification(
                SnmpEngine(),
                CommunityData(config["COMUNIDADE"]),
                UdpTransportTarget((config["IP_DESTINO"], 162)),
                ContextData(),
                'trap',
                NotificationType(
                    ObjectIdentity(config["OID"]),
                    ObjectType(ObjectIdentity(config["OID"]), Integer(valor))
            )
        )
        )
        if errorIndication:
            logger.error(f"Erro ao enviar trap SNMP: {errorIndication}")
        else:
            logger.info(f"Trap SNMP enviada com valor {valor}")
    except Exception as e:
        logger.error(f"Erro crítico ao enviar trap: {str(e)}")

def verificar_dispositivos():
    try:
        # Verifica dispositivos de vídeo disponíveis
        result = subprocess.run(["ffmpeg", "-list_devices", "true", "-f", "dshow", "-i", "dummy"], 
                              stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        
        if config["VIDEO_DEVICE_NAME"] not in result.stderr:
            logger.error(f"Dispositivo de vídeo '{config['VIDEO_DEVICE_NAME']}' não encontrado")
            return False
        
        if config["AUDIO_DEVICE_NAME"] not in result.stderr:
            logger.error(f"Dispositivo de áudio '{config['AUDIO_DEVICE_NAME']}' não encontrado")
            return False
        
        return True
    except Exception as e:
        logger.error(f"Erro ao verificar dispositivos: {e}")
        return False

def capturar_audio():
    logger.info("Thread de áudio iniciada")
    ffmpeg_audio = None
    try:
        ffmpeg_audio = subprocess.Popen([
            "ffmpeg", 
            "-f", "dshow", 
            "-i", f"audio={config['AUDIO_DEVICE_NAME']}",
            "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "1", "-f", "s16le", "-"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)

        while estado.executando:
            try:
                data = ffmpeg_audio.stdout.read(4096)
                if not data:
                    time.sleep(0.1)
                    continue

                audio_np = np.frombuffer(data, dtype=np.int16)
                rms = np.sqrt(np.mean(audio_np**2))

                if rms > config["LIMIAR_SILENCIO"]:
                    estado.ultimo_audio_ok = time.time()
                    if estado.alarme_audio:
                        estado.alarme_audio = False
                        logger.info("Áudio restabelecido")
                else:
                    if not estado.alarme_audio and time.time() - estado.ultimo_audio_ok > config["TEMPO_VERIFICACAO"]:
                        enviar_trap(3)  # 3 = Falta de áudio
                        estado.alarme_audio = True
                        logger.warning("Falta de áudio detectada")
            except Exception as e:
                logger.error(f"Erro na captura de áudio: {e}")
                time.sleep(1)

    except Exception as e:
        logger.error(f"Erro na thread de áudio: {e}")
    finally:
        if ffmpeg_audio:
            ffmpeg_audio.terminate()
        logger.info("Thread de áudio finalizada")

def capturar_video():
    logger.info("Thread de vídeo iniciada")
    ffmpeg_video = None
    try:
        ffmpeg_video = subprocess.Popen([
            "ffmpeg",
            "-f", "dshow",
            "-i", f"video={config['VIDEO_DEVICE_NAME']}",
            "-pix_fmt", "bgr24",
            "-vcodec", "rawvideo",
            "-s", f"{config['VIDEO_WIDTH']}x{config['VIDEO_HEIGHT']}",
            "-an",
            "-sn",
            "-f", "rawvideo",
            "-"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)

        frame_size = config["VIDEO_WIDTH"] * config["VIDEO_HEIGHT"] * 3

        while estado.executando:
            try:
                raw_frame = ffmpeg_video.stdout.read(frame_size)
                if len(raw_frame) != frame_size:
                    time.sleep(0.1)
                    continue

                frame = np.frombuffer(raw_frame, np.uint8).reshape((config["VIDEO_HEIGHT"], config["VIDEO_WIDTH"], 3))

                with estado.lock:
                    estado.frame_atual = frame.copy()
            except Exception as e:
                logger.error(f"Erro na captura de vídeo: {e}")
                time.sleep(1)

    except Exception as e:
        logger.error(f"Erro na thread de vídeo: {e}")
    finally:
        if ffmpeg_video:
            ffmpeg_video.terminate()
        logger.info("Thread de vídeo finalizada")

def main():
    if not verificar_dispositivos():
        logger.error("Dispositivos não encontrados. Verifique a configuração.")
        return

    threads = []
    try:
        # Inicializar Threads
        threads = [
            threading.Thread(target=capturar_audio, daemon=True),
            threading.Thread(target=capturar_video, daemon=True),
            threading.Thread(target=monitorar_video, daemon=True)
        ]

        for t in threads:
            t.start()

        # Configura janela de exibição
        cv2.namedWindow('Monitoramento HDMI', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('Monitoramento HDMI', config["VIDEO_WIDTH"], config["VIDEO_HEIGHT"])

        logger.info("Monitoramento iniciado. Pressione 'q' para sair.")

        # Loop principal de exibição
        while estado.executando:
            with estado.lock:
                if estado.frame_atual is None:
                    time.sleep(0.1)
                    continue
                frame = estado.frame_atual.copy()

            cv2.imshow('Monitoramento HDMI', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                estado.executando = False
                break

    except KeyboardInterrupt:
        logger.info("Recebido sinal de interrupção")
    except Exception as e:
        logger.error(f"Erro no main: {e}")
    finally:
        estado.executando = False
        cv2.destroyAllWindows()
        
        # Aguardar threads finalizarem
        for t in threads:
            if t.is_alive():
                t.join(timeout=2)
        
        logger.info("Monitoramento encerrado")

def monitorar_video():
    logger.info("Iniciando monitoramento de vídeo")
    while estado.executando:
        try:
            with estado.lock:
                if estado.frame_atual is None:
                    time.sleep(0.1)
                    continue
                frame = estado.frame_atual.copy()

            if estado.last_frame is not None:
                # Verifica vídeo congelado
                diff = cv2.absdiff(estado.last_frame, frame)
                gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
                _, thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)
                non_zero = np.count_nonzero(thresh)
                congelado = non_zero < config["THRESHOLD_CONGELADO"]

                if congelado:
                    if not estado.alarme_congelado and time.time() - estado.ultimo_video_ok > config["TEMPO_VERIFICACAO"]:
                        enviar_trap(1)  # 1 = Vídeo congelado
                        estado.alarme_congelado = True
                        logger.warning("Vídeo congelado detectado")
                else:
                    estado.ultimo_video_ok = time.time()
                    if estado.alarme_congelado:
                        estado.alarme_congelado = False
                        logger.info("Vídeo normalizado")

                # Verifica tela preta
                gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                media = np.mean(gray_frame)
                if media < config["THRESHOLD_PRETO"]:
                    if not estado.alarme_preto and time.time() - estado.ultimo_video_ok > config["TEMPO_VERIFICACAO"]:
                        enviar_trap(2)  # 2 = Tela preta
                        estado.alarme_preto = True
                        logger.warning("Tela preta detectada")
                else:
                    if estado.alarme_preto:
                        estado.alarme_preto = False
                        logger.info("Tela normalizada")

            estado.last_frame = frame
            time.sleep(config["TEMPO_VERIFICACAO"])

        except Exception as e:
            logger.error(f"Erro no monitoramento de vídeo: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()
