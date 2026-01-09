"""
Test específico para probar la notificación de uso de beneficios
"""

import sys
import os
from datetime import datetime
import pytz

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.supabase_service import SupabaseService

def get_current_time_mexico():
    """Obtener la hora actual en zona horaria de Ciudad de México"""
    mexico_tz = pytz.timezone('America/Mexico_City')
    return datetime.now(mexico_tz)

def test_uso_beneficio():
    """Probar inserción de entrada con tipo_acceso 'uso_beneficio'"""

    print("🧪 Probando notificación de uso de beneficios")
    print("=" * 50)

    try:
        # Inicializar servicio de Supabase
        supabase_service = SupabaseService()

        if not supabase_service.is_connected:
            print("❌ No se pudo conectar a Supabase")
            return 1

        print("✅ Conexión a Supabase exitosa")

        # Usar un miembro existente (ID 36 - Jesús Salazar)
        id_miembro = 36
        tipo_acceso = 'uso_beneficio'
        area_accedida = 'regaderas'  # Esto debería mostrar "Uso de Regaderas"

        # Preparar datos de entrada
        current_time = get_current_time_mexico()
        entrada_data = {
            'id_miembro': id_miembro,
            'tipo_acceso': tipo_acceso,
            'area_accedida': area_accedida,
            'dispositivo_registro': 'Test Beneficio Script',
            'notas': f'Prueba de uso de beneficio - {current_time.strftime("%Y-%m-%d %H:%M:%S")} (CDMX)',
            'autorizado_por': 'Sistema de Pruebas'
        }

        print("📝 Datos de entrada a insertar:")
        for key, value in entrada_data.items():
            print(f"   {key}: {value}")

        # Insertar entrada
        print("\n💾 Insertando entrada de beneficio...")
        response = supabase_service.client.table('registro_entradas').insert(entrada_data).execute()

        if response.data:
            id_entrada = response.data[0]['id_entrada']
            print("✅ ¡Entrada de beneficio insertada exitosamente!")
            print(f"   🆔 ID de entrada: {id_entrada}")
            print(f"   👤 Miembro ID: {id_miembro}")
            print(f"   🎁 Beneficio: {area_accedida}")
            print(f"   📅 Fecha: {current_time.strftime('%Y-%m-%d %H:%M:%S')} (CDMX)")

            print("\n🎉 ¡El monitor de entradas debería mostrar la notificación de beneficio!")
            print("   Si tienes la aplicación POS abierta, deberías ver:")
            print("   - Título: '🛁 USO DE BENEFICIOS'")
            print("   - Beneficio: 'Uso de Regaderas'")
            return 0
        else:
            print("❌ ERROR: No se pudo insertar la entrada")
            return 1

    except Exception as e:
        print(f"❌ Error en test de beneficio: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(test_uso_beneficio())