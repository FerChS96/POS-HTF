"""
Servidor FastAPI para recibir notificaciones de entradas del torniquete
El torniquete envía el ID de la entrada y este servidor la procesa

NOTA: Este archivo ahora redirige a utils.fastapi_server_entradas
El módulo real está en utils/fastapi_server_entradas.py

No duplica la lógica de arranque: delega en ejecutar_servidor() para que
exista una sola forma (y una sola configuración de seguridad) de levantar
el servidor.
"""

# Re-exportar desde utils para compatibilidad con scripts existentes
from utils.fastapi_server_entradas import (
    app,
    entrada_queue,
    EntradaNotification,
    EntradaResponse,
    get_entrada_queue,
    FastAPIServerThread,
    ejecutar_servidor,
    resolver_listen_host,
    verificar_acceso,
    CABECERA_TOKEN,
    PUERTO_POR_DEFECTO
)

if __name__ == "__main__":
    # Ejecutar servidor directamente para pruebas (misma ruta que utils/)
    ejecutar_servidor()
