"""
Aplicación Principal del POS HTF Gimnasio
Sistema de Punto de Venta con sincronización offline
Usando PySide6 para la interfaz
"""

import sys
import os
import logging

# CONFIGURACIÓN DE LOGGING ANTES DE CUALQUIER OTRO IMPORT
_handlers = []
_console_stream = getattr(sys, 'stdout', None)
if _console_stream is not None:
    _handlers.append(logging.StreamHandler(_console_stream))

# Configurar logging básico
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=_handlers,
)

# SUPRIMIR LOGS VERBOSOS DE LIBRERÍAS EXTERNAS ANTES DE IMPORTARLAS
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('supabase').setLevel(logging.WARNING)
logging.getLogger('websockets').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)

from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


def _best_text_stream(name: str):
    stream = getattr(sys, name, None)
    if stream is None:
        stream = getattr(sys, f"__{name}__", None)
    return stream


def _ensure_utf8_stdio_windows() -> None:
    """En ejecutables PyInstaller --windowed, stdout/stderr pueden ser None."""

    if sys.platform != "win32":
        return

    import io

    for name in ("stdout", "stderr"):
        stream = _best_text_stream(name)
        if stream is None:
            continue
        buffer = getattr(stream, "buffer", None)
        if buffer is None:
            continue
        setattr(sys, name, io.TextIOWrapper(buffer, encoding="utf-8", errors="replace"))

_ensure_utf8_stdio_windows()

try:
    from ui.login_window_pyside import LoginWindow
    from ui.main_pos_window import MainPOSWindow
    from ui.abrir_turno_dialog import AbrirTurnoDialog
    from database.postgres_manager import PostgresManager
    from services.supabase_service import SupabaseService
    from utils.config import Config
    from ui.components import show_warning_dialog, show_confirmation_dialog
except ImportError as e:
    logging.error(f"Error importando módulos: {e}")
    # Mostrar error al usuario si es GUI
    try:
        app = QApplication(sys.argv)
        QMessageBox.critical(None, "Error", f"Error al cargar la aplicación:\n{e}")
    except:
        pass
    sys.exit(1)


class POSApplication:
    def __init__(self):
        """Inicializar la aplicación POS"""
        try:
            # Crear aplicación Qt
            self.app = QApplication(sys.argv)
            self.app.setApplicationName("POS HTF Gimnasio")
            
            # Inicializar configuración
            self.config = Config()
            
            # Inicializar servicios
            try:
                db_config = self.config.get_postgres_config()
                self.postgres_manager = PostgresManager(db_config)
                if not self.postgres_manager.initialize_database():
                    logging.warning("Advertencia: BD no disponible, continuando en modo offline")
                    self.postgres_manager = None
            except Exception as e:
                logging.warning(f"Advertencia inicializando BD: {e}")
                self.postgres_manager = None
            
            try:
                self.supabase_service = SupabaseService()
            except Exception as e:
                logging.warning(f"Advertencia inicializando Supabase: {e}")
                self.supabase_service = None
            
            # Variable para usuario actual
            self.current_user = None
            self.main_window = None
            self.turno_id = None  # ID del turno activo
            
            # Mostrar ventana de login
            self.show_login()
            
        except Exception as e:
            logging.error(f"Error crítico en __init__: {e}")
            try:
                QMessageBox.critical(None, "Error Fatal", f"Error inicializando la aplicación:\n{e}")
            except:
                pass
            sys.exit(1)
        
    def show_login(self):
        """Mostrar ventana de login"""
        try:
            login_window = LoginWindow(self.postgres_manager, self.supabase_service)
            login_window.login_success.connect(self.on_login_success)
            login_window.show()
            
            # Guardar referencia para evitar que se destruya
            self.login_window = login_window
            
        except Exception as e:
            logging.error(f"Error al mostrar ventana de login: {e}")
            sys.exit(1)
    
    def on_login_success(self, user_data):
        """Manejar login exitoso"""
        try:
            self.current_user = user_data
            logging.info(f"Usuario autenticado: {self.current_user['username']}")
            
            # Cerrar ventana de login
            self.login_window.close()
            
            # Verificar si ya tiene un turno abierto
            turno_abierto = self.verificar_turno_abierto()
            
            if not turno_abierto:
                # Abrir diálogo para iniciar turno
                dialog = AbrirTurnoDialog(self.postgres_manager, self.current_user)
                if dialog.exec():
                    self.turno_id = dialog.get_turno_id()
                    logging.info(f"Turno {self.turno_id} abierto para usuario {self.current_user['nombre_completo']}")
                else:
                    # Usuario canceló la apertura del turno
                    logging.warning("Usuario canceló la apertura del turno, cerrando sesión")
                    self.current_user = None
                    self.show_login()
                    return
            else:
                # Ya tiene un turno abierto, usar ese
                self.turno_id = turno_abierto['id_turno']
                logging.info(f"Usuario tiene turno {self.turno_id} ya abierto")
            
            # Mostrar ventana principal
            self.show_main_window()
            
        except Exception as e:
            logging.error(f"Error al procesar login exitoso: {e}")
    
    def verificar_turno_abierto(self):
        """Verificar si el usuario tiene un turno abierto"""
        try:
            if not self.postgres_manager:
                return None
                
            response = self.postgres_manager.client.table('turnos_caja').select(
                'id_turno, fecha_apertura, monto_inicial'
            ).eq('id_usuario', self.current_user['id_usuario']).eq('cerrado', False).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
            
        except Exception as e:
            logging.error(f"Error verificando turno abierto: {e}")
            return None
    
    def show_main_window(self):
        """Mostrar ventana principal del POS"""
        try:
            self.main_window = MainPOSWindow(
                self.current_user,
                self.postgres_manager,
                self.supabase_service,
                self.turno_id  # Pasar ID del turno activo
            )
            self.main_window.logout_requested.connect(self.on_logout)
            self.main_window.show()
            
        except Exception as e:
            logging.error(f"Error al mostrar ventana principal: {e}")
    
    def on_logout(self):
        """Manejar cierre de sesión"""
        try:
            # Verificar si hay turno abierto
            if self.turno_id:
                turno_info = self.verificar_estado_turno()
                if turno_info and not turno_info.get('cerrado'):
                    # Mostrar advertencia
                    if self.main_window:
                        show_warning_dialog(
                            self.main_window,
                            "Turno Abierto",
                            f"ADVERTENCIA: Tienes un turno abierto\n\n"
                            f"Fecha apertura: {turno_info.get('fecha_apertura', 'N/A')}\n"
                            f"Monto inicial: ${float(turno_info.get('monto_inicial', 0)):.2f}\n\n"
                            f"Recuerda cerrar el turno antes de finalizar el día."
                        )
            
            # Cerrar ventana principal
            if self.main_window:
                self.main_window.close()
                self.main_window = None
            
            # Limpiar turno y usuario
            self.turno_id = None
            self.current_user = None
            
            # Volver a mostrar login
            self.show_login()
            
        except Exception as e:
            logging.error(f"Error al cerrar sesión: {e}")
    
    def verificar_estado_turno(self):
        """Verificar el estado actual del turno"""
        try:
            if not self.postgres_manager or not self.turno_id:
                return None
                
            response = self.postgres_manager.client.table('turnos_caja').select(
                'id_turno, fecha_apertura, monto_inicial, cerrado'
            ).eq('id_turno', self.turno_id).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
            
        except Exception as e:
            logging.error(f"Error verificando estado del turno: {e}")
            return None
    
    def run(self):
        """Ejecutar la aplicación"""
        try:
            return self.app.exec()
        except Exception as e:
            logging.error(f"Error durante ejecución: {e}")
            return 1
        finally:
            # Asegurar que el logging se cierre correctamente
            logging.shutdown()

if __name__ == "__main__":
    app = POSApplication()
    sys.exit(app.run())
