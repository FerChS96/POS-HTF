"""
Script de diagnóstico para impresora térmica (Windows + ESC/POS)

Uso rápido:
    python diagnostico_impresora_termica.py
    python diagnostico_impresora_termica.py --probar-impresion --modo windows
    python diagnostico_impresora_termica.py --probar-impresion --modo escpos --puerto COM3
"""

from __future__ import annotations

import argparse
import platform
import sys
from datetime import datetime

from services.printing.escpos_printer import TicketPrinter
from services.printing.windows_printer_manager import (
    TicketPrinterWindows,
    WindowsPrinterManager,
)


def _build_datos_ticket_prueba() -> dict:
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    return {
        "tienda": "HTF GIMNASIO",
        "subtitulo": "DIAGNOSTICO IMPRESORA",
        "numero_ticket": 999999,
        "fecha_hora": ahora,
        "cajero": "SISTEMA",
        "productos": [
            {"nombre": "PRUEBA DE IMPRESION", "cantidad": 1, "precio": 0.00, "subtotal": 0.00},
        ],
        "total": 0.00,
        "metodo_pago": "TEST",
        "abrir_caja": False,
        "cortar": True,
    }


def _test_basicos() -> tuple[list[str], list[str], list[str]]:
    errores = []
    advertencias = []
    com_ports = []

    print("=" * 70)
    print("DIAGNOSTICO IMPRESORA TERMICA - HTF")
    print("=" * 70)
    print()

    print("📋 Test 1: Verificando sistema operativo...")
    so = platform.system()
    print(f"   📌 SO detectado: {so}")
    if so != "Windows":
        advertencias.append("Este script está optimizado para Windows")
        print("   ⚠️ Script optimizado para Windows")
    else:
        print("   ✅ Entorno Windows detectado")
    print()

    print("📋 Test 2: Detectando puertos COM (ESC/POS)...")
    try:
        com_ports = TicketPrinter.obtener_puertos_preferidos("COM3")
        if com_ports:
            print(f"   ✅ Puertos detectados ({len(com_ports)}): {', '.join(com_ports)}")
        else:
            advertencias.append("No se detectaron puertos COM")
            print("   ⚠️ No se detectaron puertos COM")
    except Exception as e:
        errores.append(f"Error al listar puertos COM: {e}")
        print(f"   ❌ Error al listar puertos COM: {e}")
    print()

    print("📋 Test 3: Detectando impresoras instaladas en Windows...")
    impresoras = []
    try:
        impresoras = WindowsPrinterManager.obtener_impresoras_instaladas(force_refresh=True)
        if impresoras:
            print(f"   ✅ Impresoras detectadas ({len(impresoras)}):")
            for idx, nombre in enumerate(impresoras, 1):
                print(f"      {idx}. {nombre}")
        else:
            advertencias.append("No se detectaron impresoras instaladas en Windows")
            print("   ⚠️ No se detectaron impresoras instaladas")
    except Exception as e:
        errores.append(f"Error al listar impresoras de Windows: {e}")
        print(f"   ❌ Error al listar impresoras de Windows: {e}")
    print()

    print("📋 Test 4: Buscando impresora Generic/Text Only en cualquier USB...")
    try:
        generic_usb = WindowsPrinterManager.obtener_impresora_generic_usb()
        if generic_usb:
            print(f"   ✅ Impresora Generic USB detectada: {generic_usb}")
        else:
            advertencias.append("No se encontró impresora Generic/Text Only en puertos USB")
            print("   ⚠️ No se encontró Generic/Text Only en puertos USB")
    except Exception as e:
        advertencias.append(f"No se pudo buscar Generic USB: {e}")
        print(f"   ⚠️ No se pudo buscar Generic USB: {e}")
    print()

    return errores, advertencias, com_ports


def _probar_impresion_windows(nombre_impresora: str | None) -> bool:
    print("🖨️ Prueba de impresión: modo Windows")

    nombre = nombre_impresora
    if not nombre:
        nombre = WindowsPrinterManager.obtener_impresora_generic_usb()
    if not nombre:
        nombre = WindowsPrinterManager.obtener_impresora_por_tipo("Generic")

    if not nombre:
        print("   ❌ No se encontró impresora para prueba en modo Windows")
        return False

    print(f"   📌 Impresora objetivo: {nombre}")
    printer = TicketPrinterWindows(nombre)

    try:
        if not printer.conectar():
            print("   ❌ No se pudo conectar con la impresora de Windows")
            return False

        ok = printer.imprimir_ticket(_build_datos_ticket_prueba())
        if ok:
            print("   ✅ Ticket de prueba enviado")
            return True

        print("   ❌ Error al enviar ticket de prueba")
        return False
    except Exception as e:
        print(f"   ❌ Error en prueba de impresión Windows: {e}")
        return False
    finally:
        printer.desconectar()


def _probar_impresion_escpos(puerto: str | None, baudrate: int) -> bool:
    print("🖨️ Prueba de impresión: modo ESC/POS")

    puerto_objetivo = puerto
    if not puerto_objetivo:
        candidatos = TicketPrinter.obtener_puertos_preferidos("COM3")
        puerto_objetivo = candidatos[0] if candidatos else None

    if not puerto_objetivo:
        print("   ❌ No hay puerto COM disponible para prueba ESC/POS")
        return False

    print(f"   📌 Puerto objetivo: {puerto_objetivo} @ {baudrate} bps")
    printer = TicketPrinter(puerto_objetivo)
    printer.baudrate = baudrate

    try:
        if not printer.conectar():
            print("   ❌ No se pudo conectar al puerto ESC/POS")
            return False

        ok = printer.imprimir_ticket(_build_datos_ticket_prueba())
        if ok:
            print("   ✅ Ticket de prueba enviado")
            return True

        print("   ❌ Error al enviar ticket de prueba")
        return False
    except Exception as e:
        print(f"   ❌ Error en prueba de impresión ESC/POS: {e}")
        return False
    finally:
        printer.desconectar()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnóstico de impresora térmica")
    parser.add_argument(
        "--probar-impresion",
        action="store_true",
        help="Envía ticket de prueba real a la impresora seleccionada",
    )
    parser.add_argument(
        "--modo",
        choices=["windows", "escpos"],
        default="windows",
        help="Modo de impresión para la prueba real (default: windows)",
    )
    parser.add_argument(
        "--impresora",
        default=None,
        help="Nombre exacto de impresora de Windows (solo modo windows)",
    )
    parser.add_argument(
        "--puerto",
        default=None,
        help="Puerto COM para ESC/POS, por ejemplo COM3",
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=115200,
        help="Baudrate para ESC/POS (default: 115200)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    errores, advertencias, _ = _test_basicos()

    impresion_ok = None
    if args.probar_impresion:
        print("📋 Test 5: Enviando ticket de prueba...")
        if args.modo == "windows":
            impresion_ok = _probar_impresion_windows(args.impresora)
        else:
            impresion_ok = _probar_impresion_escpos(args.puerto, args.baudrate)
        print()

    print("=" * 70)
    print("RESUMEN DIAGNOSTICO")
    print("=" * 70)

    if errores:
        print(f"❌ Errores críticos: {len(errores)}")
        for item in errores:
            print(f"   - {item}")
    else:
        print("✅ Errores críticos: 0")

    if advertencias:
        print(f"⚠️ Advertencias: {len(advertencias)}")
        for item in advertencias:
            print(f"   - {item}")
    else:
        print("✅ Advertencias: 0")

    if impresion_ok is True:
        print("✅ Prueba de impresión: exitosa")
    elif impresion_ok is False:
        print("❌ Prueba de impresión: fallida")
    else:
        print("ℹ️ Prueba de impresión: no ejecutada")

    print()
    print("💡 Siguientes pasos sugeridos:")
    print("   1) Si usas Windows spooler, instala/selecciona 'Generic / Text Only'")
    print("   2) Si usas ESC/POS serial, valida puerto COM y baudrate")
    print("   3) Ejecuta con prueba real: --probar-impresion")
    print()

    if errores:
        return 1
    if impresion_ok is False:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
