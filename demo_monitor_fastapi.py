"""
Demo de Monitor de Entradas con FastAPI
Aplicación de prueba que muestra cómo usar el monitor FastAPI
"""

import sys
import logging
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QGroupBox, QLineEdit
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont
from datetime import datetime

# Agregar el directorio raíz al path
sys.path.insert(0, '.')

from utils.monitor_entradas_fastapi import MonitorEntradasFastAPI
from database.postgres_manager import PostgresManager

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class DemoMonitorWindow(QMainWindow):
    """Ventana de demostración del monitor FastAPI"""
    
    def __init__(self):
        super().__init__()
        self.monitor = None
        self.postgres_manager = None
        self.init_ui()
        
    def init_ui(self):
        """Inicializar interfaz de usuario"""
        self.setWindowTitle("Demo Monitor de Entradas - FastAPI")
        self.setGeometry(100, 100, 800, 600)
        
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        layout = QVBoxLayout(central_widget)
        
        # Título
        title = QLabel("🏋️ Monitor de Entradas HTF Gimnasio")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Subtitle
        subtitle = QLabel("Versión FastAPI - Recibe notificaciones desde torniquete")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #666; margin-bottom: 20px;")
        layout.addWidget(subtitle)
        
        # Grupo de control
        control_group = QGroupBox("Control del Monitor")
        control_layout = QVBoxLayout()
        
        # Botones de control
        btn_layout = QHBoxLayout()
        
        self.btn_iniciar = QPushButton("▶ Iniciar Monitor")
        self.btn_iniciar.clicked.connect(self.iniciar_monitor)
        self.btn_iniciar.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 10px;
                font-size: 14px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        btn_layout.addWidget(self.btn_iniciar)
        
        self.btn_detener = QPushButton("⏸ Detener Monitor")
        self.btn_detener.clicked.connect(self.detener_monitor)
        self.btn_detener.setEnabled(False)
        self.btn_detener.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 10px;
                font-size: 14px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        btn_layout.addWidget(self.btn_detener)
        
        control_layout.addLayout(btn_layout)
        
        # Estado del monitor
        self.label_estado = QLabel("⚪ Estado: Detenido")
        self.label_estado.setStyleSheet("""
            padding: 10px;
            background-color: #f5f5f5;
            border-radius: 5px;
            font-size: 13px;
        """)
        control_layout.addWidget(self.label_estado)
        
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)
        
        # Grupo de información del servidor
        server_group = QGroupBox("Información del Servidor")
        server_layout = QVBoxLayout()
        
        self.label_servidor = QLabel("🌐 Servidor: http://127.0.0.1:8000")
        self.label_servidor.setStyleSheet("font-family: monospace; padding: 5px;")
        server_layout.addWidget(self.label_servidor)
        
        self.label_endpoint = QLabel("📡 Endpoint: POST /entrada")
        self.label_endpoint.setStyleSheet("font-family: monospace; padding: 5px;")
        server_layout.addWidget(self.label_endpoint)
        
        server_group.setLayout(server_layout)
        layout.addWidget(server_group)
        
        # Grupo de última entrada
        entrada_group = QGroupBox("Última Entrada Detectada")
        entrada_layout = QVBoxLayout()
        
        self.label_ultima_entrada = QLabel("Esperando entradas...")
        self.label_ultima_entrada.setStyleSheet("""
            padding: 15px;
            background-color: #e3f2fd;
            border-radius: 5px;
            font-size: 14px;
        """)
        self.label_ultima_entrada.setWordWrap(True)
        entrada_layout.addWidget(self.label_ultima_entrada)
        
        entrada_group.setLayout(entrada_layout)
        layout.addWidget(entrada_group)
        
        # Log de eventos
        log_group = QGroupBox("Log de Eventos")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
                border-radius: 5px;
                padding: 5px;
            }
        """)
        log_layout.addWidget(self.log_text)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        # Botón de limpiar log
        self.btn_limpiar = QPushButton("🗑 Limpiar Log")
        self.btn_limpiar.clicked.connect(self.log_text.clear)
        layout.addWidget(self.btn_limpiar)
        
        # Agregar mensaje inicial al log
        self.agregar_log("📋 Demo de Monitor FastAPI iniciado")
        self.agregar_log("📖 Para probar, usa el script: python torniquete_script.py")
        
    def iniciar_monitor(self):
        """Iniciar el monitor de entradas"""
        try:
            self.agregar_log("🔄 Iniciando monitor...")
            
            # Crear postgres_manager si no existe
            if not self.postgres_manager:
                from services.supabase_service import SupabaseService
                supabase_service = SupabaseService()
                
                self.postgres_manager = PostgresManager(
                    host=supabase_service.db_config.get('host'),
                    port=supabase_service.db_config.get('port'),
                    database=supabase_service.db_config.get('database'),
                    user=supabase_service.db_config.get('user'),
                    password=supabase_service.db_config.get('password')
                )
                self.agregar_log("✅ Conexión a base de datos establecida")
            
            # Crear monitor si no existe
            if not self.monitor:
                self.monitor = MonitorEntradasFastAPI(
                    postgres_manager=self.postgres_manager,
                    host="127.0.0.1",
                    port=8000
                )
                
                # Conectar señal de nueva entrada
                self.monitor.nueva_entrada_detectada.connect(self.on_nueva_entrada)
                self.agregar_log("✅ Monitor creado")
            
            # Iniciar monitor
            self.monitor.iniciar()
            
            # Actualizar UI
            self.btn_iniciar.setEnabled(False)
            self.btn_detener.setEnabled(True)
            self.label_estado.setText("🟢 Estado: Activo - Escuchando entradas")
            self.label_estado.setStyleSheet("""
                padding: 10px;
                background-color: #c8e6c9;
                border-radius: 5px;
                font-size: 13px;
            """)
            
            self.agregar_log("✅ Monitor iniciado correctamente")
            self.agregar_log("📡 Esperando peticiones POST en http://127.0.0.1:8000/entrada")
            
        except Exception as e:
            self.agregar_log(f"❌ Error iniciando monitor: {e}")
            logging.error(f"Error iniciando monitor: {e}", exc_info=True)
    
    def detener_monitor(self):
        """Detener el monitor de entradas"""
        try:
            self.agregar_log("🔄 Deteniendo monitor...")
            
            if self.monitor:
                self.monitor.detener()
            
            # Actualizar UI
            self.btn_iniciar.setEnabled(True)
            self.btn_detener.setEnabled(False)
            self.label_estado.setText("⚪ Estado: Detenido")
            self.label_estado.setStyleSheet("""
                padding: 10px;
                background-color: #f5f5f5;
                border-radius: 5px;
                font-size: 13px;
            """)
            
            self.agregar_log("✅ Monitor detenido")
            
        except Exception as e:
            self.agregar_log(f"❌ Error deteniendo monitor: {e}")
            logging.error(f"Error deteniendo monitor: {e}", exc_info=True)
    
    @Slot(dict)
    def on_nueva_entrada(self, entrada_data):
        """Manejar nueva entrada detectada"""
        try:
            # Extraer información
            id_entrada = entrada_data.get('id_entrada')
            nombres = entrada_data.get('nombres', '')
            apellido_paterno = entrada_data.get('apellido_paterno', '')
            apellido_materno = entrada_data.get('apellido_materno', '')
            tipo_acceso = entrada_data.get('tipo_acceso', '')
            fecha_entrada = entrada_data.get('fecha_entrada', '')
            
            nombre_completo = f"{nombres} {apellido_paterno} {apellido_materno}".strip()
            
            # Actualizar etiqueta de última entrada
            mensaje = f"""
            🎫 Entrada ID: {id_entrada}
            👤 Miembro: {nombre_completo}
            🔑 Tipo: {tipo_acceso}
            🕐 Fecha: {fecha_entrada}
            """
            
            self.label_ultima_entrada.setText(mensaje)
            
            # Agregar al log
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.agregar_log(f"[{timestamp}] ✅ Nueva entrada: {nombre_completo} (ID: {id_entrada})")
            
            logging.info(f"Entrada detectada: {nombre_completo} - ID: {id_entrada}")
            
        except Exception as e:
            self.agregar_log(f"❌ Error procesando entrada: {e}")
            logging.error(f"Error procesando entrada: {e}", exc_info=True)
    
    def agregar_log(self, mensaje):
        """Agregar mensaje al log"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_text.append(f"[{timestamp}] {mensaje}")
        # Auto-scroll al final
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
    
    def closeEvent(self, event):
        """Manejar cierre de ventana"""
        if self.monitor and self.monitor.activo:
            self.detener_monitor()
        
        if self.postgres_manager:
            self.postgres_manager.disconnect()
        
        event.accept()


def main():
    """Función principal"""
    app = QApplication(sys.argv)
    
    # Establecer estilo de aplicación
    app.setStyle('Fusion')
    
    window = DemoMonitorWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
