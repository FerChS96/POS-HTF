"""
Servidor FastAPI para recibir notificaciones de entradas del torniquete
El torniquete envía el ID de la entrada y este servidor la procesa

SEGURIDAD (ver .env.example):
  - TORNIQUETE_API_TOKEN: token compartido obligatorio. El torniquete debe
    enviarlo en la cabecera HTTP "X-API-Token" en cada POST.
  - TORNIQUETE_IPS_PERMITIDAS: lista opcional de IPs separadas por comas.
    Si está vacía no hay restricción por IP (se confía solo en el token).
  - TORNIQUETE_LISTEN_HOST: interfaz de escucha. Si no se define, el servidor
    escucha en 0.0.0.0 SOLO cuando hay token configurado; si no hay token se
    repliega a 127.0.0.1 (modo degradado, sin exposición a la red).
"""

from fastapi import FastAPI, HTTPException, Request, Depends, status
from pydantic import BaseModel
import uvicorn
import logging
from datetime import datetime
from typing import Optional
import threading
import queue
import os
import sys
import secrets

# Configurar logging con archivo para depuración
_log_handlers = []
try:
    # Detectar si está ejecutándose como ejecutable empaquetado
    if getattr(sys, 'frozen', False):
        # Si está empaquetado, usar directorio del .exe
        app_dir = os.path.dirname(sys.executable)
    else:
        # Si es script Python normal, usar directorio dos niveles arriba (POS_HTF/)
        app_dir = os.path.dirname(os.path.dirname(__file__))

    log_file = os.path.join(app_dir, 'fastapi_server.log')
    file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a', errors='replace')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    _log_handlers.append(file_handler)
except Exception as e:
    print(f"No se pudo crear archivo de log FastAPI: {e}")

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=_log_handlers if _log_handlers else None
)

# Cargar el .env de POS_HTF para que las variables de seguridad estén
# disponibles aunque el servidor se levante sin pasar por utils.config.
# override=False: nunca pisa variables ya definidas en el entorno real.
try:
    from dotenv import load_dotenv
    load_dotenv(
        dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),
        encoding='utf-8',
        override=False
    )
except Exception as e:
    logging.warning(f"[SERVIDOR] No se pudo cargar el archivo .env: {e}")


# ============================================================================
# CONFIGURACIÓN DE SEGURIDAD
# ============================================================================

# Nombre de la cabecera donde el torniquete envía el token compartido
CABECERA_TOKEN = "X-API-Token"

# Nombres de las variables de entorno
VAR_TOKEN = "TORNIQUETE_API_TOKEN"
VAR_IPS_PERMITIDAS = "TORNIQUETE_IPS_PERMITIDAS"
VAR_LISTEN_HOST = "TORNIQUETE_LISTEN_HOST"

# Puerto fijo acordado con el torniquete (8001 para evitar conflicto con IIS)
PUERTO_POR_DEFECTO = 8001

# Direcciones consideradas "la propia máquina del POS"
IPS_LOCALES = {"127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost"}

# Mensajes genéricos: nunca revelan si el token existía, si era incorrecto
# o si la IP estaba en la lista blanca.
MENSAJE_NO_AUTORIZADO = "No autorizado"
MENSAJE_ACCESO_DENEGADO = "Acceso denegado"


def obtener_token_configurado() -> str:
    """
    Token compartido configurado en el entorno (cadena vacía si no hay).

    Se lee en cada petición a propósito: permite corregir la configuración
    y reiniciar el POS sin recompilar, y facilita las pruebas.
    """
    return (os.getenv(VAR_TOKEN) or "").strip()


def obtener_ips_permitidas() -> list:
    """
    Lista blanca de IPs de origen (vacía = sin restricción por IP).
    Se acepta una lista separada por comas, ignorando espacios y vacíos.
    """
    crudo = os.getenv(VAR_IPS_PERMITIDAS) or ""
    return [ip.strip() for ip in crudo.split(",") if ip.strip()]


def obtener_ip_cliente(request: Request) -> str:
    """
    IP real del cliente TCP.

    IMPORTANTE: se usa request.client.host y NUNCA cabeceras tipo
    X-Forwarded-For, porque el torniquete conecta directo (sin proxy) y esas
    cabeceras las puede falsificar cualquiera en la red del gimnasio.
    request.client puede ser None en transportes sin dirección (ASGI).
    """
    cliente = getattr(request, "client", None)
    if cliente is None or not getattr(cliente, "host", None):
        return ""
    return cliente.host


def es_ip_local(ip: str) -> bool:
    """Indica si la IP corresponde a la propia máquina del POS."""
    return ip in IPS_LOCALES


def _tokens_coinciden(enviado: str, esperado: str) -> bool:
    """Comparación en tiempo constante (evita ataques de temporización)."""
    return secrets.compare_digest(
        (enviado or "").encode("utf-8"),
        (esperado or "").encode("utf-8")
    )


def verificar_acceso(request: Request):
    """
    Dependencia de seguridad para los endpoints que registran entradas.

    Reglas, aplicadas en conjunto (nunca una en lugar de la otra):
      1. Lista blanca de IPs (si TORNIQUETE_IPS_PERMITIDAS está definida).
      2. Token compartido en la cabecera X-API-Token.

    Si NO hay token configurado el servidor entra en modo degradado: rechaza
    toda petición que no venga de la propia máquina (127.0.0.1). No existe un
    modo "sin token" silencioso para la red local.
    """
    ip_cliente = obtener_ip_cliente(request)
    token_configurado = obtener_token_configurado()

    # --- 1. Lista blanca de IPs (opcional) ---
    ips_permitidas = obtener_ips_permitidas()
    if ips_permitidas and ip_cliente not in ips_permitidas:
        logging.warning(
            f"[SEGURIDAD] Petición rechazada: IP {ip_cliente or 'desconocida'} "
            f"fuera de {VAR_IPS_PERMITIDAS}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=MENSAJE_ACCESO_DENEGADO
        )

    # --- 2. Modo degradado: sin token solo se acepta localhost ---
    if not token_configurado:
        if es_ip_local(ip_cliente):
            logging.warning(
                f"[SEGURIDAD] {VAR_TOKEN} no configurado: se acepta esta petición "
                f"solo por venir de localhost. Configura el token en el archivo .env."
            )
            return True

        logging.error(
            f"[ERROR] [SEGURIDAD] Petición de red rechazada desde "
            f"{ip_cliente or 'desconocida'}: falta configurar {VAR_TOKEN} en el .env. "
            f"El torniquete NO funcionará hasta configurarlo."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=MENSAJE_NO_AUTORIZADO
        )

    # --- 3. Validación del token compartido ---
    token_enviado = request.headers.get(CABECERA_TOKEN, "")
    if not _tokens_coinciden(token_enviado, token_configurado):
        logging.warning(
            f"[SEGURIDAD] Token inválido o ausente desde {ip_cliente or 'desconocida'}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=MENSAJE_NO_AUTORIZADO
        )

    return True


def resolver_listen_host() -> str:
    """
    Interfaz donde debe escuchar el servidor.

    - Si TORNIQUETE_LISTEN_HOST está definida, manda esa (el operador decide).
    - Si hay token configurado: 0.0.0.0 (el torniquete de la red puede entrar).
    - Si NO hay token: 127.0.0.1, para no exponer un servidor sin autenticar
      a la red del gimnasio ni al WiFi de invitados.
    """
    host_env = (os.getenv(VAR_LISTEN_HOST) or "").strip()
    if host_env:
        return host_env
    return "0.0.0.0" if obtener_token_configurado() else "127.0.0.1"


def log_configuracion_seguridad(host: str = None, port: int = PUERTO_POR_DEFECTO):
    """Deja clarísimo en el log cómo quedó configurada la seguridad al arrancar."""
    token_configurado = bool(obtener_token_configurado())
    ips_permitidas = obtener_ips_permitidas()

    if token_configurado:
        logging.info(
            f"[SERVIDOR] [OK] Autenticación activa: se exige la cabecera "
            f"{CABECERA_TOKEN} en POST /entrada y POST /test-entrada"
        )
    else:
        logging.error(
            f"[ERROR] [SEGURIDAD] La variable {VAR_TOKEN} NO está configurada. "
            f"MODO DEGRADADO: solo se aceptan entradas desde 127.0.0.1 y el "
            f"servidor no se publica en la red. El torniquete dejará de "
            f"funcionar hasta que definas {VAR_TOKEN} en el archivo .env "
            f"(y lo configures igual en el torniquete). Ver .env.example."
        )

    if ips_permitidas:
        logging.info(
            f"[SERVIDOR] [OK] Lista blanca de IPs activa: {', '.join(ips_permitidas)}"
        )
    else:
        logging.info(
            f"[SERVIDOR] Sin lista blanca de IPs ({VAR_IPS_PERMITIDAS} vacía): "
            f"se confía solo en el token. Se recomienda fijar la IP del torniquete."
        )

    if host is not None:
        logging.info(f"[SERVIDOR] Interfaz de escucha: {host}:{port}")


app = FastAPI(title="Monitor de Entradas HTF Gimnasio", version="1.0.0")

# NOTA DE SEGURIDAD: se eliminó el middleware CORS a propósito.
# El torniquete es un cliente HTTP (no un navegador), así que nunca envía
# peticiones pre-flight ni cabecera Origin: CORS no aporta nada aquí.
# La configuración anterior (allow_origins=["*"] + allow_credentials=True) es
# además inválida para los navegadores y permitía que cualquier página web
# abierta en la red hablara con el POS. Si algún día se necesita un panel web
# local, agregar CORSMiddleware con orígenes explícitos de localhost.

# Cola thread-safe para comunicación entre FastAPI y Qt
entrada_queue = queue.Queue()


class EntradaNotification(BaseModel):
    """Modelo para la notificación de entrada desde el torniquete"""
    id_entrada: int
    dispositivo: Optional[str] = "torniquete"
    timestamp: Optional[str] = None


class EntradaResponse(BaseModel):
    """Respuesta al torniquete"""
    success: bool
    message: str
    id_entrada: int


@app.get("/")
async def root():
    """Endpoint raíz para verificar que el servidor esté activo (sin token)"""
    return {
        "service": "Monitor de Entradas HTF Gimnasio",
        "status": "active",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health")
async def health(request: Request):
    """
    Endpoint de salud del servicio (abierto, para diagnosticar en sitio).

    Solo informa que el servicio vive. El tamaño de la cola (queue_size) es
    información operativa —permitiría a un intruso confirmar que sus entradas
    falsas se encolaron— así que únicamente se incluye si la petición trae un
    token válido o viene de la propia máquina.
    """
    respuesta = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }

    try:
        token_configurado = obtener_token_configurado()
        token_enviado = request.headers.get(CABECERA_TOKEN, "")
        autorizado = (
            (token_configurado and _tokens_coinciden(token_enviado, token_configurado))
            or es_ip_local(obtener_ip_cliente(request))
        )

        if autorizado:
            try:
                respuesta["queue_size"] = entrada_queue.qsize() if entrada_queue else 0
            except Exception:
                respuesta["queue_size"] = 0
            respuesta["token_configurado"] = bool(token_configurado)
    except Exception as e:
        logging.error(f"[ERROR] Error evaluando detalle de /health: {e}")

    return respuesta


@app.post("/entrada", response_model=EntradaResponse)
async def registrar_entrada(
    entrada: EntradaNotification,
    autorizado: bool = Depends(verificar_acceso)
):
    """
    Recibe notificación de nueva entrada desde el torniquete.
    Requiere la cabecera X-API-Token (ver verificar_acceso).

    Args:
        entrada: Datos de la entrada (id_entrada, dispositivo, timestamp)

    Returns:
        EntradaResponse con confirmación del procesamiento
    """
    return _encolar_entrada(entrada)


def _encolar_entrada(entrada: EntradaNotification) -> EntradaResponse:
    """
    Encola la entrada para que el monitor Qt la procese.

    Se mantiene aparte del endpoint para que la autenticación se resuelva
    siempre en la capa HTTP (dependencia) y nunca se pueda saltar llamando
    a esta función desde otro endpoint.
    """
    try:
        logging.info(f"[ENTRADA] Recibida notificación de entrada ID: {entrada.id_entrada}")

        # Agregar a la cola para procesamiento por el monitor Qt
        entrada_data = {
            'id_entrada': entrada.id_entrada,
            'dispositivo': entrada.dispositivo,
            'timestamp': entrada.timestamp or datetime.now().isoformat()
        }

        entrada_queue.put(entrada_data)

        logging.info(f"[OK] Entrada {entrada.id_entrada} agregada a la cola de procesamiento")

        return EntradaResponse(
            success=True,
            message="Entrada recibida y procesada correctamente",
            id_entrada=entrada.id_entrada
        )

    except Exception as e:
        logging.error(f"[ERROR] Error procesando entrada: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error procesando entrada"
        )


@app.post("/test-entrada")
async def test_entrada(
    id_entrada: int = 1,
    autorizado: bool = Depends(verificar_acceso)
):
    """
    Endpoint de prueba para simular una entrada.
    Útil para testing sin necesidad del torniquete físico.
    Requiere el mismo token que /entrada.

    Args:
        id_entrada: ID de la entrada a simular
    """
    entrada = EntradaNotification(
        id_entrada=id_entrada,
        dispositivo="test",
        timestamp=datetime.now().isoformat()
    )

    return _encolar_entrada(entrada)


def get_entrada_queue():
    """
    Obtener la cola de entradas para uso externo.
    Esta función es llamada por el monitor Qt para obtener las entradas.
    """
    return entrada_queue


class FastAPIServerThread(threading.Thread):
    """Hilo para ejecutar el servidor FastAPI"""

    def __init__(self, host: str = None, port: int = PUERTO_POR_DEFECTO):
        super().__init__(daemon=True)
        # host=None -> se decide según la configuración de seguridad
        self.host = host or resolver_listen_host()
        self.port = port
        self.server = None
        self.should_exit = False
        self.startup_error = None

    def run(self):
        """Iniciar el servidor FastAPI"""
        try:
            import asyncio
            logging.info(f"[SERVIDOR] Iniciando FastAPI en {self.host}:{self.port}")
            log_configuracion_seguridad(self.host, self.port)

            # Detectar si está empaquetado con PyInstaller
            is_frozen = getattr(sys, 'frozen', False)

            # Crear configuración de Uvicorn
            # IMPORTANTE: log_config=None desactiva la configuración automática de logging
            # Esto evita errores cuando sys.stdout es None (ejecutables --windowed)
            config = uvicorn.Config(
                app,
                host=self.host,
                port=self.port,
                log_level="warning",  # Reducir verbosidad
                access_log=False,
                log_config=None  # Desactivar configuración automática de logging
            )

            # Crear servidor
            self.server = uvicorn.Server(config)

            # Ejecutar en el event loop del hilo
            asyncio.run(self.server.serve())

        except Exception as e:
            self.startup_error = str(e)
            if not self.should_exit:
                logging.error(f"[ERROR] Error en servidor FastAPI: {e}")
                import traceback
                logging.error(traceback.format_exc())

    def stop(self):
        """Detener el servidor FastAPI"""
        self.should_exit = True
        if self.server:
            logging.info("[SERVIDOR] Deteniendo servidor FastAPI...")
            self.server.should_exit = True


def ejecutar_servidor(host: str = None, port: int = PUERTO_POR_DEFECTO,
                      log_level: str = "info"):
    """
    Punto de entrada ÚNICO para levantar el servidor de forma independiente
    (sin el POS). Lo usan tanto este módulo como el re-exportador de la raíz,
    para que no existan dos formas de arrancar con configuraciones distintas.
    """
    host_real = host or resolver_listen_host()
    logging.info("[SERVIDOR] Iniciando servidor FastAPI de entradas...")
    log_configuracion_seguridad(host_real, port)
    uvicorn.run(app, host=host_real, port=port, log_level=log_level)


if __name__ == "__main__":
    ejecutar_servidor()
