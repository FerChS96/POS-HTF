"""
Aplicación Principal del POS HTF Gimnasio
Sistema de Punto de Venta con sincronización offline
Usando PySide6 para la interfaz
"""

import sys
import os
import logging
import ctypes

# CONFIGURACIÓN DE LOGGING ANTES DE CUALQUIER OTRO IMPORT
import io

_handlers = []

# Configurar StreamHandler con encoding UTF-8 seguro
_console_stream = getattr(sys, 'stdout', None)
if _console_stream is not None:
    # Envolver stdout con TextIOWrapper UTF-8 para manejar caracteres especiales
    try:
        if hasattr(_console_stream, 'buffer'):
            # Si tiene buffer, envolver con UTF-8 y errors='replace'
            wrapped_stream = io.TextIOWrapper(
                _console_stream.buffer,
                encoding='utf-8',
                errors='replace',
                line_buffering=True
            )
            console_handler = logging.StreamHandler(wrapped_stream)
        else:
            # Si no tiene buffer, usar stream directo con handler que ignore errores
            console_handler = logging.StreamHandler(_console_stream)
            
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        _handlers.append(console_handler)
    except Exception as e:
        # Si falla la configuración avanzada, continuar sin console handler
        print(f"Advertencia: No se pudo configurar console logging: {e}")
        pass

# Agregar logging a archivo para depuración (especialmente útil con --windowed)
try:
    # Detectar si está ejecutándose como ejecutable empaquetado
    if getattr(sys, 'frozen', False):
        # Si está empaquetado, usar directorio del .exe
        app_dir = os.path.dirname(sys.executable)
    else:
        # Si es script Python normal, usar directorio del script
        app_dir = os.path.dirname(__file__)
    
    # Mantener .log histórico y también .txt para soporte/diagnóstico en sitio
    log_files = [
        os.path.join(app_dir, 'pos_htf.log'),
        os.path.join(app_dir, 'pos_htf.txt'),
    ]

    for log_file in log_files:
        file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a', errors='replace')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        _handlers.append(file_handler)
except Exception as e:
    print(f"No se pudo crear archivo de log: {e}")

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


_single_instance_mutex = None


def _acquire_single_instance_lock() -> bool:
    """Evitar múltiples instancias del POS en Windows."""
    global _single_instance_mutex

    if sys.platform != "win32":
        return True

    mutex_name = "Global\\HTF_Gimnasio_POS_SingleInstance"
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, mutex_name)

    if not mutex:
        return True

    last_error = kernel32.GetLastError()
    ERROR_ALREADY_EXISTS = 183
    if last_error == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(mutex)
        return False

    _single_instance_mutex = mutex
    return True


def _release_single_instance_lock() -> None:
    """Liberar mutex de instancia única al salir."""
    global _single_instance_mutex

    if sys.platform != "win32":
        return

    if _single_instance_mutex:
        try:
            ctypes.windll.kernel32.CloseHandle(_single_instance_mutex)
        except Exception:
            pass
        finally:
            _single_instance_mutex = None

try:
    from ui.login_window_pyside import LoginWindow
    from ui.main_pos_window import MainPOSWindow
    from ui.abrir_turno_dialog import AbrirTurnoDialog
    from database.postgres_manager import PostgresManager
    from services.supabase_service import SupabaseService
    from utils.config import Config
    from ui.components import show_warning_dialog, show_confirmation_dialog
    # Importar servidor FastAPI para que PyInstaller lo detecte
    from utils.fastapi_server_entradas import FastAPIServerThread, get_entrada_queue
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

            # Validar credenciales ANTES de intentar conectar: sin Supabase la
            # aplicación no puede operar (no existe un modo offline real).
            if not self.config.validate_config():
                faltantes = self.config.get_missing_credentials()
                lista_faltantes = "\n".join(f"  - {v}" for v in faltantes)
                mensaje = (
                    "No se encontraron las credenciales de Supabase.\n\n"
                    "Faltan estas variables:\n"
                    f"{lista_faltantes}\n\n"
                    "Configúralas en el archivo:\n"
                    f"{os.path.abspath(os.path.join(os.path.dirname(__file__), '.env'))}\n\n"
                    "Ejemplo:\n"
                    "  SUPABASE_URL=https://xxxxx.supabase.co\n"
                    "  SUPABASE_ROLE_KEY=eyJhbGciOiJIUzI1NiIs...\n\n"
                    "La aplicación no puede continuar sin estas credenciales."
                )
                logging.error(f"[ERROR] Credenciales faltantes: {', '.join(faltantes)}")
                QMessageBox.critical(None, "Configuración incompleta", mensaje)
                sys.exit(1)

            # Inicializar servicios
            try:
                # Se pasa explícitamente {'url', 'key'}: es lo que PostgresManager
                # lee. Antes se pasaba get_postgres_config() (sin 'url'/'key') y
                # solo funcionaba por el efecto colateral de load_dotenv().
                db_config = self.config.get_supabase_config()
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

            role = (self.current_user.get('rol') or '').lower()
            
            # Cerrar ventana de login
            self.login_window.close()

            # Roles administrativos: no requieren turno (ventas deshabilitadas en UI)
            if role in ('administrador', 'sistemas'):
                self.turno_id = None
                logging.info(f"Rol '{role}': no se abre/crea turno de caja")
                self.show_main_window()
                return
            
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
    if not _acquire_single_instance_lock():
        try:
            ctypes.windll.user32.MessageBoxW(
                0,
                "El POS HTF ya está ejecutándose en esta máquina.",
                "HTF Gimnasio POS",
                0x00000030
            )
        except Exception:
            pass
        sys.exit(1)

    try:
        app = POSApplication()
        sys.exit(app.run())
    finally:
        _release_single_instance_lock()
