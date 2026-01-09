#!/usr/bin/env python3
"""
Script para insertar una entrada de prueba en la tabla registro_entradas
con un miembro seleccionado por el usuario de la tabla miembros.
Soporta visitas normales y uso de beneficios.
"""

import sys
import os
import random
from datetime import datetime

# Agregar zona horaria de Ciudad de México
try:
    import pytz
    mexico_tz = pytz.timezone('America/Mexico_City')
    print("✅ Zona horaria de Ciudad de México configurada")
except ImportError:
    print("⚠️ pytz no instalado. Usando hora UTC. Instala con: pip install pytz")
    mexico_tz = None

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


def get_current_time_mexico():
    """Obtener la fecha/hora actual en zona horaria de Ciudad de México"""
    if mexico_tz:
        return datetime.now(mexico_tz)
    else:
        # Fallback a UTC si no hay pytz
        return datetime.now()


def main():
    """Función principal para insertar una entrada de prueba con miembro seleccionado por usuario"""

    print("🧪 Insertando entrada de prueba en registro_entradas (visita normal o beneficio)")
    print("=" * 80)

    try:
        # Inicializar servicios
        print("Inicializando servicios...")

        # Verificar variables de entorno
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_ROLE_KEY') or os.getenv('SUPABASE_KEY')

        if not supabase_url or not supabase_key:
            print("❌ ERROR: Variables de entorno de Supabase no configuradas")
            print()
            print("Configura las siguientes variables de entorno:")
            print("  SUPABASE_URL=https://tu-proyecto.supabase.co")
            print("  SUPABASE_KEY=tu_service_role_key")
            print("  o SUPABASE_ROLE_KEY=tu_service_role_key")
            print()
            print("Opcionalmente, puedes editar directamente las variables en este archivo:")
            print("  supabase_url = 'tu_url_aqui'")
            print("  supabase_key = 'tu_key_aqui'")
            print()
            print("Obtén tus credenciales en: https://supabase.com/dashboard/project/_/settings/api")
            return 1

        print(f"✅ Variables de entorno encontradas")
        print(f"📍 URL: {supabase_url}")
        print(f"🔑 Key: {'Configurada' if supabase_key else 'No configurada'}")

        # Supabase service con credenciales explícitas
        supabase_service = SupabaseService(url=supabase_url, key=supabase_key)
        if not supabase_service.is_connected:
            print("❌ ERROR: No se pudo conectar a Supabase")
            print("Posibles causas:")
            print("  - URL o KEY incorrectas")
            print("  - Sin conexión a internet")
            print("  - Supabase no disponible")
            print("  - La tabla 'usuarios' no existe o no hay permisos")
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

            # Mostrar todos los miembros disponibles
            print("\n📋 Miembros disponibles:")
            for i, miembro in enumerate(miembros):
                nombre_completo = f"{miembro['nombres']} {miembro['apellido_paterno']} {miembro.get('apellido_materno', '')}".strip()
                print(f"  {i+1:2d}. {nombre_completo} (ID: {miembro['id_miembro']})")

        except Exception as e:
            print(f"❌ ERROR consultando miembros: {e}")
            return 1

        # Seleccionar miembro por ID del usuario
        while True:
            try:
                print(f"\n🔍 Ingresa el ID del miembro para la entrada de prueba (1-{len(miembros)}): ", end="")
                id_input = input().strip()
                
                if not id_input:
                    print("❌ ID no puede estar vacío. Intenta de nuevo.")
                    continue
                
                # Buscar miembro por ID
                miembro_seleccionado = None
                for miembro in miembros:
                    if str(miembro['id_miembro']) == id_input:
                        miembro_seleccionado = miembro
                        break
                
                if miembro_seleccionado:
                    nombre_completo = f"{miembro_seleccionado['nombres']} {miembro_seleccionado['apellido_paterno']} {miembro_seleccionado.get('apellido_materno', '')}".strip()
                    print(f"\n✅ Miembro seleccionado:")
                    print(f"   👤 {nombre_completo}")
                    print(f"   🆔 ID: {miembro_seleccionado['id_miembro']}")
                    break
                else:
                    print(f"❌ ID '{id_input}' no encontrado. Los IDs válidos son: {', '.join(str(m['id_miembro']) for m in miembros[:10])}{'...' if len(miembros) > 10 else ''}")
                    
            except KeyboardInterrupt:
                print("\n⏹️  Operación cancelada por el usuario")
                return 0
            except Exception as e:
                print(f"❌ Error procesando entrada: {e}")
                continue

        # Seleccionar tipo de acceso
        print("\n🎯 Selecciona el tipo de acceso:")
        print("  1. Visita normal al gimnasio")
        print("  2. Uso de beneficio (regaderas, vapores, acompañante, etc.)")
        
        tipo_acceso_seleccionado = None
        beneficio_seleccionado = None
        
        while True:
            try:
                print(f"\n🔍 Selecciona el tipo de acceso (1-2): ", end="")
                tipo_input = input().strip()
                
                if tipo_input == '1':
                    tipo_acceso_seleccionado = 'miembro'
                    beneficio_seleccionado = 'Gimnasio'
                    print("✅ Tipo seleccionado: Visita normal al gimnasio")
                    break
                elif tipo_input == '2':
                    tipo_acceso_seleccionado = 'uso_beneficio'
                    print("✅ Tipo seleccionado: Uso de beneficio")
                    
                    # Seleccionar tipo de beneficio
                    print("\n🛁 Selecciona el tipo de beneficio:")
                    print("  1. Regaderas")
                    print("  2. Vapores/Sauna")
                    print("  3. Acompañante")
                    print("  4. Invitado")
                    print("  5. Otro beneficio")
                    
                    while True:
                        print(f"🔍 Selecciona el beneficio (1-5): ", end="")
                        beneficio_input = input().strip()
                        
                        if beneficio_input == '1':
                            beneficio_seleccionado = 'Regaderas'
                            break
                        elif beneficio_input == '2':
                            beneficio_seleccionado = 'Vapores'
                            break
                        elif beneficio_input == '3':
                            beneficio_seleccionado = 'Acompañante'
                            break
                        elif beneficio_input == '4':
                            beneficio_seleccionado = 'Invitado'
                            break
                        elif beneficio_input == '5':
                            print("Especifica el beneficio: ", end="")
                            beneficio_seleccionado = input().strip()
                            if beneficio_seleccionado:
                                break
                            else:
                                print("❌ El beneficio no puede estar vacío")
                        else:
                            print("❌ Opción no válida. Selecciona 1-5.")
                    
                    print(f"✅ Beneficio seleccionado: {beneficio_seleccionado}")
                    break
                else:
                    print("❌ Opción no válida. Selecciona 1 o 2.")
                    
            except KeyboardInterrupt:
                print("\n⏹️  Operación cancelada por el usuario")
                return 0
            except Exception as e:
                print(f"❌ Error procesando selección: {e}")
                continue

        # Preparar datos de entrada
        current_time = get_current_time_mexico()
        entrada_data = {
            'id_miembro': miembro_seleccionado['id_miembro'],
            'tipo_acceso': tipo_acceso_seleccionado,
            'area_accedida': beneficio_seleccionado,
            'fecha_entrada': current_time.strftime('%Y-%m-%d %H:%M:%S'),  # Fecha sin zona horaria
            'dispositivo_registro': 'Test Script',
            'notas': f'Entrada de prueba generada automáticamente - {current_time.strftime("%Y-%m-%d %H:%M:%S")} (CDMX)',
            'autorizado_por': 'Sistema de Pruebas'
        }

        print("\n📝 Datos de entrada a insertar:")
        for key, value in entrada_data.items():
            print(f"   {key}: {value}")

        # Confirmar antes de insertar
        print("\n⚠️  ¿Insertar esta entrada? (s/n): ", end="")
        respuesta = input().strip().lower()

        if respuesta not in ['s', 'si', 'y', 'yes']:
            print("❌ Operación cancelada por el usuario")
            return 0

        # Insertar entrada
        print("\n💾 Insertando entrada...")
        try:
            response = supabase_service.client.table('registro_entradas').insert(entrada_data).execute()

            if response.data:
                id_entrada = response.data[0]['id_entrada']
                tipo_acceso_texto = "visita normal" if tipo_acceso_seleccionado == 'miembro' else f"uso de beneficio ({beneficio_seleccionado})"
                print("✅ ¡Entrada insertada exitosamente!")
                print(f"   🆔 ID de entrada: {id_entrada}")
                print(f"   👤 Miembro: {nombre_completo}")
                print(f"   🎯 Tipo: {tipo_acceso_texto}")
                print(f"   📅 Fecha: {current_time.strftime('%Y-%m-%d %H:%M:%S')} (CDMX)")

                print("\n🎉 ¡El monitor de entradas debería detectar esta nueva entrada!")
                print("   Si tienes el test_monitor_entradas.py corriendo, deberías ver la notificación.")
                print("   Si tienes la aplicación POS abierta, deberías ver la notificación emergente.")
                return 0
            else:
                print("❌ ERROR: No se pudo insertar la entrada")
                return 1

        except Exception as e:
            print(f"❌ ERROR insertando entrada: {e}")
            return 1

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