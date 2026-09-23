"""
Script de diagnóstico para el servidor FastAPI de entradas
Verifica que todo esté funcionando correctamente
"""

import os
import requests
import time
import logging

try:
    from dotenv import load_dotenv
    load_dotenv(
        dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'),
        encoding='utf-8',
        override=False,
    )
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

FASTAPI_URL = "http://127.0.0.1:8001"

# El servidor exige token en los POST. Se toma del mismo .env que usa el POS.
CABECERA_TOKEN = "X-API-Token"


def obtener_cabeceras():
    """Cabeceras de autenticación para los POST de diagnóstico."""
    token = os.getenv("TORNIQUETE_API_TOKEN", "").strip()
    if not token:
        print("   ⚠️  TORNIQUETE_API_TOKEN no configurado: los POST darán 401")
        return {}
    return {CABECERA_TOKEN: token}

def diagnostico_completo():
    """Ejecutar diagnóstico completo del servidor"""
    
    print("=" * 70)
    print("DIAGNÓSTICO DEL SERVIDOR FASTAPI - MONITOR DE ENTRADAS")
    print("=" * 70)
    print()
    
    # Test 1: Conectividad básica
    print("📋 Test 1: Verificando conectividad básica...")
    try:
        response = requests.get(f"{FASTAPI_URL}/", timeout=3)
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Servidor respondiendo")
            print(f"   📌 Servicio: {data.get('service')}")
            print(f"   📌 Versión: {data.get('version')}")
            print(f"   📌 Status: {data.get('status')}")
        else:
            print(f"   ❌ Código de respuesta inesperado: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"   ❌ No se puede conectar al servidor en {FASTAPI_URL}")
        print(f"   💡 El servidor no está corriendo")
        print(f"   💡 Inicia el sistema POS con: python main.py")
        print(f"   💡 O el servidor standalone con: python fastapi_server_entradas.py")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False
    
    print()
    
    # Test 2: Endpoint de salud
    print("📋 Test 2: Verificando endpoint /health...")
    try:
        response = requests.get(f"{FASTAPI_URL}/health", timeout=3)
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Endpoint /health funcionando")
            print(f"   📌 Status: {data.get('status')}")
            print(f"   📌 Queue size: {data.get('queue_size')}")
            print(f"   📌 Timestamp: {data.get('timestamp')}")
        else:
            print(f"   ❌ Código de respuesta: {response.status_code}")
            print(f"   📄 Respuesta: {response.text}")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False
    
    print()
    
    # Test 3: Endpoint de entrada (POST)
    print("📋 Test 3: Verificando endpoint /entrada (POST)...")
    try:
        test_payload = {
            "id_entrada": 9999,
            "dispositivo": "test_diagnostico",
            "timestamp": "2026-02-15T12:00:00"
        }
        
        response = requests.post(
            f"{FASTAPI_URL}/entrada",
            json=test_payload,
            headers=obtener_cabeceras(),
            timeout=3
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Endpoint /entrada funcionando")
            print(f"   📌 Success: {data.get('success')}")
            print(f"   📌 Message: {data.get('message')}")
            print(f"   ⚠️  Nota: Entrada de prueba ID 9999 agregada a la cola")
        else:
            print(f"   ❌ Código de respuesta: {response.status_code}")
            print(f"   📄 Respuesta: {response.text}")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False
    
    print()
    
    # Test 4: Endpoint de test
    print("📋 Test 4: Verificando endpoint /test-entrada...")
    try:
        response = requests.post(
            f"{FASTAPI_URL}/test-entrada?id_entrada=9998",
            headers=obtener_cabeceras(),
            timeout=3
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Endpoint /test-entrada funcionando")
            print(f"   📌 Success: {data.get('success')}")
        else:
            print(f"   ⚠️  Código de respuesta: {response.status_code}")
    except Exception as e:
        print(f"   ⚠️  Error: {e}")
    
    print()
    
    # Test 5: Verificar cola después de tests
    print("📋 Test 5: Verificando estado de la cola...")
    try:
        time.sleep(0.5)  # Dar tiempo a que se procesen
        response = requests.get(f"{FASTAPI_URL}/health", timeout=3)
        if response.status_code == 200:
            data = response.json()
            queue_size = data.get('queue_size', 0)
            print(f"   📌 Tamaño de cola: {queue_size}")
            if queue_size > 0:
                print(f"   ⚠️  Hay {queue_size} entradas pendientes de procesar")
                print(f"   💡 El monitor Qt debería estar procesándolas")
            else:
                print(f"   ✅ Cola vacía (entradas procesadas o monitor no activo)")
    except Exception as e:
        print(f"   ⚠️  Error: {e}")
    
    print()
    print("=" * 70)
    print("✅ DIAGNÓSTICO COMPLETADO")
    print("=" * 70)
    print()
    print("💡 PRÓXIMOS PASOS:")
    print("   1. Si todos los tests pasaron, el servidor está funcionando")
    print("   2. Para probar con entradas reales, usa: python torniquete_script.py")
    print("   3. Asegúrate de que el sistema POS esté corriendo (main.py)")
    print()
    
    return True


if __name__ == "__main__":
    import sys
    
    print()
    resultado = diagnostico_completo()
    
    if resultado:
        sys.exit(0)
    else:
        print("❌ Algunos tests fallaron. Revisa los mensajes arriba.")
        sys.exit(1)
