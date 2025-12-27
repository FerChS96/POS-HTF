"""Script para generar ejecutable de Windows para POS HTF.

Nota: este script debe funcionar aunque lo ejecutes desde otro directorio.
Requiere: `pip install pyinstaller` en el mismo Python con el que corres este script.
"""

from __future__ import annotations

import os
import subprocess
import sys


def build_exe() -> bool:
    """Construir ejecutable (modo --onefile)."""

    # Siempre trabajar relativo a la carpeta de este script (POS_HTF)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    app_name = "HTF_Gimnasio_POS"
    main_script = "main.py"
    dist_dir = "dist"
    work_dir = "build_onefile"
    spec_dir = "spec_onefile"

    if not os.path.exists(main_script):
        print(f"❌ No se encontró {main_script} en: {base_dir}")
        return False

    # Separador de --add-data: Windows usa ';' y Linux/Mac ':'
    data_sep = ";" if os.name == "nt" else ":"

    # Ejecutar PyInstaller desde el mismo Python (evita problemas de PATH)
    # Importante: cuando usamos --specpath, PyInstaller puede resolver rutas de datas
    # relativo al directorio del .spec. Para evitarlo, usamos rutas absolutas en source.
    database_src = os.path.join(base_dir, "database")
    ui_src = os.path.join(base_dir, "ui")
    services_src = os.path.join(base_dir, "services")
    utils_src = os.path.join(base_dir, "utils")
    env_src = os.path.join(base_dir, ".env")

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--windowed",
        "--name",
        app_name,
        "--distpath",
        dist_dir,
        "--workpath",
        work_dir,
        "--specpath",
        spec_dir,
        "--clean",
        "--noconfirm",
        # Incluir carpetas del proyecto (sources absolutos)
        f"--add-data={database_src}{data_sep}database",
        f"--add-data={ui_src}{data_sep}ui",
        f"--add-data={services_src}{data_sep}services",
        f"--add-data={utils_src}{data_sep}utils",
        # .env es opcional; si no existe, PyInstaller fallará. Verificamos antes.
    ]

    if os.path.exists(env_src):
        command.append(f"--add-data={env_src}{data_sep}.")
    else:
        print("ℹ️ No encontré .env en POS_HTF; continúo sin incluirlo en el .exe")

    # Hidden imports (seguro/compat)
    command += [
        "--hidden-import=sqlite3",
        "--hidden-import=PySide6",
        "--hidden-import=dotenv",
        "--hidden-import=supabase",
        "--hidden-import=psycopg2",
        main_script,
    ]

    print("🔨 Construyendo ejecutable de Windows (onefile)...")
    print("📍 Directorio:", os.getcwd())
    print(f"📁 Nombre: {app_name}.exe")
    print(f"📄 Script principal: {main_script}")
    print("✓ Comando a ejecutar:")
    print(" ".join(command))
    print("\n" + "=" * 60 + "\n")

    try:
        result = subprocess.run(command, check=True)
        if result.returncode == 0:
            exe_path = os.path.join(dist_dir, f"{app_name}.exe")
            print("\n" + "=" * 60)
            print("✅ Ejecutable creado exitosamente!")
            print(f"📍 Ubicación: {exe_path}")
        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ Error construyendo ejecutable: {e}")
        return False

    except ModuleNotFoundError:
        print("❌ PyInstaller no está instalado en este Python.")
        print("Instala con: pip install pyinstaller")
        return False


if __name__ == "__main__":
    ok = build_exe()
    sys.exit(0 if ok else 1)