#!/usr/bin/env python3
"""
Script para insertar múltiples entradas de prueba automáticamente
sin confirmación del usuario - útil para testing continuo
"""

import sys
import os
import random
from datetime import datetime

# Agregar el directorio raíz del proyecto al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Cargar variables de entorno desde .env
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ Variables de entorno cargadas desde .env")
except ImportError:
    print("⚠️ python-dotenv no instalado. Usando variables de entorno del sistema.")

from services.supabase_service import SupabaseService


def insertar_entrada_aleatoria(supabase_service, miembros):
    """Insertar una entrada con un miembro aleatorio"""

    # Seleccionar miembro aleatorio
    miembro_seleccionado = random.choice(miembros)
    nombre_completo = f"{miembro_seleccionado['nombres']} {miembro_seleccionado['apellido_paterno']} {miembro_seleccionado.get('apellido_materno', '')}".strip()

    # Preparar datos de entrada
    entrada_data = {
        'id_miembro': miembro_seleccionado['id_miembro'],
        'tipo_acceso': 'miembro',
        'area_accedida': 'Gimnasio',
        'dispositivo_registro': 'Test Script Automático',
        'notas': f'Entrada de prueba automática - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
        'autorizado_por': 'Sistema de Pruebas Automáticas'
    }

    try:
        # Insertar entrada
        response = supabase_service.client.table('registro_entradas').insert(entrada_data).execute()

        if response.data:
            id_entrada = response.data[0]['id_entrada']
            print(f"✅ Entrada #{id_entrada} insertada - {nombre_completo}")
            return True
        else:
            print("❌ ERROR: No se pudo insertar la entrada")
            return False

    except Exception as e:
        print(f"❌ ERROR insertando entrada: {e}")
        return False


def main():
    """Función principal para insertar múltiples entradas de prueba"""

    print("🔄 Insertando múltiples entradas de prueba automáticamente")
    print("=" * 70)

    try:
        # Inicializar servicios
        print("Inicializando servicios...")

        # Verificar variables de entorno
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_ROLE_KEY') or os.getenv('SUPABASE_KEY')

        if not supabase_url or not supabase_key:
            print("❌ ERROR: Variables de entorno de Supabase no configuradas")
            return 1

        # Supabase service
        supabase_service = SupabaseService(url=supabase_url, key=supabase_key)
        if not supabase_service.is_connected:
            print("❌ ERROR: No se pudo conectar a Supabase")
            return 1

        print("✅ Conexión a Supabase exitosa")

        # Consultar miembros disponibles
        print("\n👥 Consultando miembros disponibles...")
        try:
            response = supabase_service.client.table('miembros').select(
                'id_miembro, nombres, apellido_paterno, apellido_materno'
            ).execute()

            if not response.data:
                print("❌ ERROR: No se encontraron miembros en la tabla 'miembros'")
                return 1

            miembros = response.data
            print(f"✅ Encontrados {len(miembros)} miembros")

        except Exception as e:
            print(f"❌ ERROR consultando miembros: {e}")
            return 1

        # Pedir cantidad de entradas a insertar
        try:
            cantidad = input(f"\n📊 ¿Cuántas entradas deseas insertar? (1-{len(miembros)*3}, default: 3): ").strip()
            if not cantidad:
                cantidad = 3
            else:
                cantidad = int(cantidad)

            if cantidad < 1 or cantidad > len(miembros) * 3:
                print(f"❌ Cantidad inválida. Debe ser entre 1 y {len(miembros)*3}")
                return 1

        except ValueError:
            print("❌ Cantidad inválida")
            return 1

        # Pedir intervalo entre inserciones
        try:
            intervalo = input("⏱️  Intervalo entre inserciones en segundos (default: 2): ").strip()
            if not intervalo:
                intervalo = 2
            else:
                intervalo = int(intervalo)

            if intervalo < 0:
                intervalo = 0

        except ValueError:
            intervalo = 2

        print(f"\n🚀 Insertando {cantidad} entradas con intervalo de {intervalo} segundos...")
        print("Presiona Ctrl+C para detener")

        import time

        entradas_insertadas = 0
        for i in range(cantidad):
            try:
                if insertar_entrada_aleatoria(supabase_service, miembros):
                    entradas_insertadas += 1

                # Esperar antes de la siguiente inserción (excepto la última)
                if i < cantidad - 1 and intervalo > 0:
                    print(f"⏳ Esperando {intervalo} segundos...")
                    time.sleep(intervalo)

            except KeyboardInterrupt:
                print(f"\n⏹️  Proceso detenido por el usuario")
                break

        print("\n📊 Resumen:")
        print(f"   ✅ Entradas insertadas: {entradas_insertadas}")
        print(f"   📅 Fecha/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        if entradas_insertadas > 0:
            print("\n🎉 ¡Las entradas deberían aparecer en el monitor de tiempo real!")
            print("   Si tienes el test_monitor_entradas.py corriendo, deberías ver las notificaciones.")
            print("   Si tienes la aplicación POS abierta, deberías ver las notificaciones emergentes.")
        return 0

    except KeyboardInterrupt:
        print("\n⏹️  Operación cancelada por el usuario")
        return 0
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())