#!/usr/bin/env python3
"""
Script para configurar credenciales de Supabase temporalmente
"""

import os

#!/usr/bin/env python3
"""
Script para configurar credenciales de Supabase temporalmente
"""

import os

def configurar_supabase():
    """Configura las credenciales de Supabase para esta sesión"""

    print("🔧 Configuración de Supabase para pruebas")
    print("=" * 50)

    # Verificar si ya hay variables configuradas
    existing_url = os.getenv('SUPABASE_URL')
    existing_key = os.getenv('SUPABASE_KEY') or os.getenv('SUPABASE_ROLE_KEY')

    if existing_url and existing_key:
        print("✅ Variables de entorno ya configuradas:")
        print(f"📍 SUPABASE_URL: {existing_url}")
        print(f"🔑 SUPABASE_KEY: {'Configurada' if existing_key else 'No configurada'}")
        print()
        respuesta = input("¿Quieres reconfigurar las credenciales? (s/n): ").strip().lower()
        if respuesta != 's' and respuesta != 'si':
            print("✅ Usando configuración existente")
            return True

    # Pedir credenciales al usuario
    print("\nIngresa tus nuevas credenciales:")
    url = input("SUPABASE_URL: ").strip()
    if not url:
        print("❌ URL requerida")
        return False

    key = input("SUPABASE_KEY (service_role): ").strip()
    if not key:
        print("❌ Key requerida")
        return False

    # Configurar variables de entorno
    os.environ['SUPABASE_URL'] = url
    os.environ['SUPABASE_KEY'] = key

    print("\n✅ Variables de entorno configuradas para esta sesión")
    print(f"📍 SUPABASE_URL: {url}")
    print(f"🔑 SUPABASE_KEY: {'*' * 20}...")

    # Verificar que se configuraron
    verificar = os.getenv('SUPABASE_URL') and os.getenv('SUPABASE_KEY')
    if verificar:
        print("\n🎉 ¡Listo! Ahora puedes ejecutar:")
        print("python test_supabase_connection.py")
        print("python test_monitor_entradas.py")
        return True
    else:
        print("\n❌ Error al configurar variables")
        return False

if __name__ == "__main__":
    success = configurar_supabase()
    if success:
        print("\n💡 Nota: Estas variables solo duran esta sesión de PowerShell")
        print("Para configurar permanentemente, edita las variables de entorno del sistema")
        input("\nPresiona Enter para continuar...")
    else:
        input("\nPresiona Enter para salir...")