"""
Script de ejemplo para torniquete - Envía notificaciones de entrada vía HTTP POST
Este script simula cómo el torniquete físico enviaría notificaciones al sistema POS
"""

import os
import requests
import logging
from datetime import datetime
import time

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Configuración del servidor FastAPI
FASTAPI_URL = os.getenv("TORNIQUETE_URL", "http://192.168.1.162:8001")
ENTRADA_ENDPOINT = f"{FASTAPI_URL}/entrada"

# El servidor exige un token compartido en esta cabecera. Debe coincidir con
# TORNIQUETE_API_TOKEN del .env del POS; sin él, el servidor responde 401.
CABECERA_TOKEN = "X-API-Token"


def obtener_cabeceras():
    """
    Construir las cabeceras de autenticación para el servidor de entradas.

    Returns:
        dict: cabeceras a enviar; vacío si no hay token configurado.
    """
    token = os.getenv("TORNIQUETE_API_TOKEN", "").strip()
    if not token:
        logging.error(
            "[ERROR] TORNIQUETE_API_TOKEN no está configurado; el servidor "
            "rechazará las notificaciones con 401."
        )
        return {}
    return {CABECERA_TOKEN: token}


def enviar_notificacion_entrada(id_entrada, dispositivo="torniquete"):
    """
    Enviar notificación de entrada al servidor FastAPI.
    
    Args:
        id_entrada: ID del registro de entrada en la base de datos
        dispositivo: Identificador del dispositivo que registra la entrada
        
    Returns:
        bool: True si se envió exitosamente, False en caso contrario
    """
    try:
        # Preparar datos de la notificación
        payload = {
            "id_entrada": id_entrada,
            "dispositivo": dispositivo,
            "timestamp": datetime.now().isoformat()
        }
        
        # Enviar POST request
        logging.info(f"Enviando notificación de entrada ID: {id_entrada}")
        response = requests.post(
            ENTRADA_ENDPOINT,
            json=payload,
            headers=obtener_cabeceras(),
            timeout=5  # 5 segundos de timeout
        )
        
        # Verificar respuesta
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                logging.info(f"✅ Entrada {id_entrada} enviada exitosamente")
                logging.info(f"   Mensaje: {data.get('message')}")
                return True
            else:
                logging.error(f"❌ Error en respuesta: {data}")
                return False
        else:
            logging.error(f"❌ Error HTTP {response.status_code}: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        logging.error(f"❌ No se pudo conectar al servidor FastAPI en {FASTAPI_URL}")
        logging.error("   Asegúrate de que el servidor esté corriendo")
        return False
    except requests.exceptions.Timeout:
        logging.error(f"❌ Timeout esperando respuesta del servidor")
        return False
    except Exception as e:
        logging.error(f"❌ Error enviando notificación: {e}")
        return False


def verificar_servidor():
    """
    Verificar que el servidor FastAPI esté activo.
    
    Returns:
        bool: True si el servidor responde, False en caso contrario
    """
    try:
        response = requests.get(f"{FASTAPI_URL}/health", timeout=3)
        if response.status_code == 200:
            data = response.json()
            logging.info(f"✅ Servidor FastAPI activo")
            logging.info(f"   Status: {data.get('status')}")
            logging.info(f"   Queue size: {data.get('queue_size')}")
            return True
        else:
            logging.error(f"❌ Servidor respondió con código: {response.status_code}")
            try:
                logging.error(f"   Respuesta: {response.text}")
            except:
                pass
            return False
    except requests.exceptions.ConnectionError as e:
        logging.error(f"❌ No se pudo conectar al servidor: {e}")
        return False
    except Exception as e:
        logging.error(f"❌ Servidor no disponible: {e}")
        return False


def simular_entrada(id_entrada):
    """
    Simular una entrada del torniquete para pruebas.
    
    Args:
        id_entrada: ID de la entrada a simular
    """
    logging.info("=" * 60)
    logging.info("SIMULACIÓN DE ENTRADA DE TORNIQUETE")
    logging.info("=" * 60)
    
    # Verificar servidor
    logging.info("\n1. Verificando servidor FastAPI...")
    if not verificar_servidor():
        logging.error("\n❌ No se puede continuar sin servidor activo")
        logging.info("\nPara iniciar el sistema POS (que incluye el servidor):")
        logging.info("   python main.py")
        logging.info("\nO si prefieres ejecutar el servidor por separado:")
        logging.info("   python fastapi_server_entradas.py")
        logging.info("\nEspera unos segundos después de iniciar para que el servidor esté listo.")
        return
    
    # Enviar notificación
    logging.info(f"\n2. Enviando notificación de entrada ID: {id_entrada}")
    success = enviar_notificacion_entrada(id_entrada, "torniquete_simulado")
    
    if success:
        logging.info("\n✅ Simulación completada exitosamente")
        logging.info("   La ventana de entrada debería aparecer en el monitor POS")
    else:
        logging.error("\n❌ Simulación falló")
    
    logging.info("=" * 60)


# Ejemplo de uso: Clase para torniquete real
class TorniqueteHTF:
    """
    Clase de ejemplo para integración con torniquete físico.
    Adaptarla según el hardware específico del torniquete.
    """
    
    def __init__(self, servidor_url="http://127.0.0.1:8000", nombre_dispositivo="torniquete_1"):
        """
        Args:
            servidor_url: URL del servidor FastAPI
            nombre_dispositivo: Identificador único del torniquete
        """
        self.servidor_url = servidor_url
        self.nombre_dispositivo = nombre_dispositivo
        self.endpoint = f"{servidor_url}/entrada"
        
        logging.info(f"Torniquete '{nombre_dispositivo}' inicializado")
        logging.info(f"Servidor: {servidor_url}")
    
    def registrar_entrada(self, id_entrada):
        """
        Registrar una entrada en el sistema.
        Esta función se llamaría cuando el torniquete detecte un acceso válido.
        
        Args:
            id_entrada: ID del registro de entrada creado en la BD
            
        Returns:
            bool: True si se notificó exitosamente
        """
        try:
            payload = {
                "id_entrada": id_entrada,
                "dispositivo": self.nombre_dispositivo,
                "timestamp": datetime.now().isoformat()
            }
            
            response = requests.post(
                self.endpoint,
                json=payload,
                headers=obtener_cabeceras(),
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('success', False)
            else:
                logging.error(f"Error HTTP {response.status_code}")
                return False
                
        except Exception as e:
            logging.error(f"Error registrando entrada: {e}")
            return False
    
    def test_conexion(self):
        """Probar conexión con el servidor"""
        try:
            response = requests.get(f"{self.servidor_url}/health", timeout=3)
            return response.status_code == 200
        except:
            return False


if __name__ == "__main__":
    """
    Ejemplos de uso del script
    """
    
    print("\n" + "=" * 60)
    print("SCRIPT DE TORNIQUETE - HTF GIMNASIO")
    print("=" * 60)
    print("\nOpciones:")
    print("1. Simular entrada manual")
    print("2. Simular múltiples entradas")
    print("3. Test de conexión con servidor")
    print("4. Salir")
    print("=" * 60)
    
    while True:
        try:
            opcion = input("\nSelecciona una opción (1-4): ").strip()
            
            if opcion == "1":
                id_entrada = input("Ingresa el ID de entrada a simular: ").strip()
                if id_entrada.isdigit():
                    simular_entrada(int(id_entrada))
                else:
                    print("❌ ID debe ser un número")
                    
            elif opcion == "2":
                id_inicio = input("ID inicial: ").strip()
                cantidad = input("Cantidad de entradas: ").strip()
                
                if id_inicio.isdigit() and cantidad.isdigit():
                    id_inicio = int(id_inicio)
                    cantidad = int(cantidad)
                    
                    print(f"\nSimulando {cantidad} entradas desde ID {id_inicio}...")
                    for i in range(cantidad):
                        id_entrada = id_inicio + i
                        enviar_notificacion_entrada(id_entrada, "torniquete_simulado")
                        time.sleep(0.5)  # Pausa de 500ms entre entradas
                    
                    print(f"✅ {cantidad} entradas simuladas")
                else:
                    print("❌ Valores deben ser números")
                    
            elif opcion == "3":
                print("\nVerificando conexión con servidor...")
                if verificar_servidor():
                    print("✅ Conexión exitosa")
                else:
                    print("❌ No se pudo conectar")
                    
            elif opcion == "4":
                print("\n👋 Saliendo...")
                break
                
            else:
                print("❌ Opción inválida")
                
        except KeyboardInterrupt:
            print("\n\n👋 Saliendo...")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
