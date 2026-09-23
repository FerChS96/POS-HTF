"""
Configuración de la aplicación POS HTF
"""

import os
import logging
from dotenv import load_dotenv

class Config:
    def __init__(self):
        # Cargar variables de entorno
        load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'), encoding='utf-8')
        
        # Configuración de la base de datos SQLite
        self.DATABASE_PATH = os.path.join(os.path.dirname(__file__), '..', 'database', 'pos_htf.db')
        
        # Configuración de Supabase
        self.SUPABASE_URL = os.getenv('SUPABASE_URL', '')
        self.SUPABASE_KEY = os.getenv('SUPABASE_KEY', '')
        # SUPABASE_ROLE_KEY bypasea RLS; fallback a SUPABASE_KEY si no existe
        self.SUPABASE_ROLE_KEY = os.getenv('SUPABASE_ROLE_KEY', os.getenv('SUPABASE_KEY', ''))
        
        # Configuración de la aplicación
        self.APP_NAME = "HTF Gimnasio POS"
        self.APP_VERSION = "1.0.0"
        
        # Configuración de sincronización
        self.SYNC_INTERVAL = 300  # 5 minutos en segundos
        self.OFFLINE_MODE = True
        
        # Configuración de UI
        self.THEME_COLOR = "#2E86AB"
        self.SECONDARY_COLOR = "#A23B72"
        self.BACKGROUND_COLOR = "#F18F01"
        self.TEXT_COLOR = "#C73E1D"
        
        # Configuración de la base de datos PostgreSQL
        self.DB_HOST = os.getenv('DB_HOST', 'localhost')
        self.DB_PORT = os.getenv('DB_PORT', '5432')
        self.DB_NAME = os.getenv('DB_NAME', 'htf_gimnasio')
        self.DB_USER = os.getenv('DB_USER', 'postgres')
        # Eliminar comillas si las hay
        password = os.getenv('DB_PASSWORD', 'password')
        self.DB_PASSWORD = password.strip('"\'') if password else 'password'

    def get_missing_credentials(self):
        """
        Devolver la lista de credenciales de Supabase que faltan, por nombre.

        La app NO tiene un modo offline real: sin Supabase no puede leer ni
        escribir nada. Por eso esto es un fallo duro, no una advertencia.

        Returns:
            list[str]: nombres de las variables faltantes (vacía si todo está bien).
        """
        faltantes = []

        if not self.SUPABASE_URL:
            faltantes.append('SUPABASE_URL')

        # La llave de servicio bypasea RLS; si no está, SUPABASE_KEY sirve igual.
        if not (self.SUPABASE_ROLE_KEY or self.SUPABASE_KEY):
            faltantes.append('SUPABASE_ROLE_KEY (o SUPABASE_KEY)')

        return faltantes

    def validate_config(self):
        """
        Validar que existan las credenciales de Supabase.

        Returns:
            bool: True si la configuración está completa, False si falta algo.
        """
        faltantes = self.get_missing_credentials()

        if faltantes:
            logging.error(
                f"[ERROR] Variables de entorno faltantes: {', '.join(faltantes)}"
            )
            logging.error(
                "[ERROR] Configúralas en POS_HTF/.env; sin ellas el POS no puede "
                "conectarse a Supabase."
            )
            self.OFFLINE_MODE = True
            return False

        # Aviso no bloqueante: sin la llave de servicio, RLS puede bloquear
        # operaciones administrativas.
        if not os.getenv('SUPABASE_ROLE_KEY'):
            logging.warning(
                "[AVISO] SUPABASE_ROLE_KEY no está definida; se usará SUPABASE_KEY "
                "y RLS puede bloquear algunas operaciones."
            )

        self.OFFLINE_MODE = False
        logging.info("[OK] Credenciales de Supabase presentes")
        return True

    def get_database_path(self):
        """Obtener ruta completa de la base de datos"""
        return os.path.abspath(self.DATABASE_PATH)

    def get_supabase_config(self):
        """
        Obtener la configuración de Supabase como diccionario.

        Es lo que espera `PostgresManager` (lee `url` y `key` de su db_config).
        Se prefiere SUPABASE_ROLE_KEY (bypasea RLS) con respaldo a SUPABASE_KEY.

        Returns:
            dict: {'url': str, 'key': str}
        """
        return {
            'url': self.SUPABASE_URL,
            'key': self.SUPABASE_ROLE_KEY or self.SUPABASE_KEY,
        }

    def get_postgres_config(self):
        """
        OBSOLETO: configuración del PostgreSQL local (legacy muerto).

        La capa de datos usa exclusivamente el cliente REST de Supabase, y este
        diccionario NO contiene 'url' ni 'key', por lo que `PostgresManager`
        acabaría dependiendo de os.environ por efecto colateral de load_dotenv.
        Usa `get_supabase_config()` en su lugar.

        Se mantiene solo por compatibilidad con código antiguo.
        """
        return {
            'host': self.DB_HOST,
            'port': self.DB_PORT,
            'database': self.DB_NAME,
            'user': self.DB_USER,
            'password': self.DB_PASSWORD
        }
