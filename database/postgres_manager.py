"""
Gestor de Base de Datos Supabase para Sistema de Gimnasio
Reemplaza PostgreSQL local con Supabase (PostgreSQL en la nube)
Compatible con el esquema HTF_sql.txt
ACTUALIZADO: Usa Supabase como backend único
"""

import logging
import bcrypt
import os
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from decimal import Decimal
import sys
import io

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logging.warning("Supabase no está instalado. Instala con: pip install supabase")

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class PostgresManager:
    """Gestor de conexión y operaciones con Supabase"""
    
    def __init__(self, db_config: Dict[str, str]):
        """
        Inicializar conexión a Supabase
        
        Args:
            db_config: Diccionario con la configuración de conexión
                {
                    'url': 'https://xxxx.supabase.co',
                    'key': 'eyJhbGciOiJIUzI1NiIs...',
                    # Los parámetros de PostgreSQL se ignoran ahora
                    'host': 'ignorado',
                    'port': 'ignorado',
                    'database': 'ignorado',
                    'user': 'ignorado',
                    'password': 'ignorado'
                }
        """
        self.db_config = db_config
        self.client: Optional[Client] = None
        self.supabase_key = None  # Almacenar la key para llamadas HTTP
        self.is_connected = False
        self.connect()
    
    def connect(self):
        """Establecer conexión con Supabase"""
        try:
            if not SUPABASE_AVAILABLE:
                logging.error("Supabase no está disponible. Instala con: pip install supabase")
                raise ImportError("Supabase library not installed")
            
            # Obtener credenciales de Supabase
            url = self.db_config.get('url') or os.getenv('SUPABASE_URL')
            # Usar SUPABASE_ROLE_KEY (service role) para bypasear RLS, fallback a SUPABASE_KEY
            key = self.db_config.get('key') or os.getenv('SUPABASE_ROLE_KEY') or os.getenv('SUPABASE_KEY')
            
            if not url or not key:
                logging.error("Credenciales de Supabase no configuradas. Configura SUPABASE_URL y SUPABASE_ROLE_KEY (o SUPABASE_KEY)")
                raise ValueError("Missing Supabase credentials")
            
            # Almacenar la key para uso en llamadas HTTP
            self.supabase_key = key
            
            # Crear cliente de Supabase
            self.client = create_client(url, key)
            
            # Probar conexión
            response = self.client.table('usuarios').select('id_usuario').limit(1).execute()
            self.is_connected = True
            logging.info("[OK] Conexión exitosa a Supabase")
            
        except Exception as e:
            logging.error(f"[ERROR] Error conectando a Supabase: {e}")
            self.is_connected = False
            raise
    
    def close(self):
        """Cerrar conexión (Supabase no requiere cerrar explícitamente)"""
        self.is_connected = False
        # Don't log during cleanup to avoid shutdown race conditions
    
    def close_connection(self):
        """Alias para compatibilidad"""
        self.close()
    
    def __del__(self):
        """Destructor para cerrar conexión"""
        try:
            self.close()
        except Exception:
            # Ignore errors during cleanup, logging might be closed
            pass
    
    def initialize_database(self):
        """Verificar que la base de datos esté disponible en Supabase"""
        try:
            if not self.is_connected:
                self.connect()
            
            # Probar acceso a tabla usuarios
            response = self.client.table('usuarios').select('id_usuario').limit(1).execute()
            logging.info("[OK] Base de datos Supabase verificada correctamente")
            return True
            
        except Exception as e:
            logging.error(f"[ERROR] Error verificando base de datos: {e}")
            return False
    
    # ========== AUTENTICACIÓN ==========
    
    def authenticate_user(self, username: str, password: str) -> Optional[Dict]:
        """
        Autenticar un usuario por nombre de usuario y contraseña.
        
        Args:
            username: Nombre de usuario
            password: Contraseña en texto plano
            
        Returns:
            dict con información del usuario si la autenticación es exitosa, None si falla
        """
        try:
            if not self.is_connected:
                self.connect()
            
            # Consultar usuario por nombre de usuario
            response = self.client.table('usuarios').select('*').eq('nombre_usuario', username).eq('activo', True).execute()
            
            if not response.data:
                logging.warning(f"Usuario no encontrado o inactivo: {username}")
                return None
            
            user = response.data[0]
            stored_password = user['contrasenia']
            
            # Verificar la contraseña usando bcrypt
            if bcrypt.checkpw(password.encode('utf-8'), stored_password.encode('utf-8')):
                logging.info(f"[OK] Autenticación exitosa para usuario: {username}")
                
                # Actualizar último acceso
                self.client.table('usuarios').update({'ultimo_acceso': datetime.now().isoformat()}).eq('id_usuario', user['id_usuario']).execute()
                
                return {
                    "id_usuario": user['id_usuario'],
                    "username": user['nombre_usuario'],
                    "nombre_completo": user['nombre_completo'],
                    "rol": user['rol']
                }
            else:
                logging.warning(f"Contraseña incorrecta para usuario: {username}")
                return None
                
        except Exception as e:
            logging.error(f"Error durante la autenticación: {e}")
            return None
    
    def create_user(self, username: str, password: str, nombre_completo: str, rol: str = "recepcionista") -> Optional[int]:
        """
        Crear un nuevo usuario en Supabase.
        
        Args:
            username: Nombre de usuario (mínimo 3 caracteres)
            password: Contraseña en texto plano
            nombre_completo: Nombre completo del usuario
            rol: Rol del usuario (administrador, recepcionista, sistemas)
            
        Returns:
            ID del usuario creado, o None si hay error
        """
        try:
            if not self.is_connected:
                self.connect()
            
            # Validar longitud del nombre de usuario
            if len(username) < 3:
                logging.error("El nombre de usuario debe tener al menos 3 caracteres")
                return None
            
            # Verificar si el usuario ya existe
            response = self.client.table('usuarios').select('id_usuario').eq('nombre_usuario', username).execute()
            
            if response.data:
                logging.warning(f"El usuario '{username}' ya existe")
                return None
            
            # Hashear la contraseña
            salt = bcrypt.gensalt()
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
            
            # Insertar nuevo usuario
            user_data = {
                'nombre_usuario': username,
                'contrasenia': hashed_password,
                'nombre_completo': nombre_completo,
                'rol': rol,
                'activo': True
            }
            
            response = self.client.table('usuarios').insert(user_data).execute()
            
            if response.data:
                user_id = response.data[0]['id_usuario']
                logging.info(f"[OK] Usuario '{username}' creado exitosamente con ID: {user_id}")
                return user_id
            else:
                logging.error(f"No se pudo crear el usuario '{username}'")
                return None
                
        except Exception as e:
            logging.error(f"Error al crear usuario: {e}")
            return None
    
    def update_user_password(self, username: str, new_password: str) -> bool:
        """
        Actualizar la contraseña de un usuario existente.
        
        Args:
            username: Nombre de usuario
            new_password: Nueva contraseña en texto plano
            
        Returns:
            True si se actualizó exitosamente, False en caso contrario
        """
        try:
            if not self.is_connected:
                self.connect()
            
            # Obtener usuario
            response = self.client.table('usuarios').select('id_usuario').eq('nombre_usuario', username).execute()
            
            if not response.data:
                logging.warning(f"Usuario no encontrado: {username}")
                return False
            
            user_id = response.data[0]['id_usuario']
            
            # Hashear la nueva contraseña
            salt = bcrypt.gensalt()
            hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), salt).decode('utf-8')
            
            # Actualizar contraseña
            update_response = self.client.table('usuarios').update({'contrasenia': hashed_password}).eq('id_usuario', user_id).execute()
            
            if update_response.data:
                logging.info(f"[OK] Contraseña actualizada para usuario: {username}")
                return True
            else:
                logging.error(f"No se pudo actualizar la contraseña para {username}")
                return False
                    
        except Exception as e:
            logging.error(f"Error al actualizar contraseña: {e}")
            return False
    
    # ========== PRODUCTOS ==========
    
    def get_all_products(self) -> List[Dict]:
        """Obtener todos los productos activos con stock"""
        try:
            if not self.is_connected:
                self.connect()
            
            productos_resultado = []
            
            # Obtener productos varios
            response_varios = self.client.table('ca_productos_varios').select(
                'id_producto, codigo_interno, nombre, precio_venta, categoria, codigo_barras'
            ).eq('activo', True).execute()
            
            # Obtener suplementos
            response_suplementos = self.client.table('ca_suplementos').select(
                'id_suplemento, codigo_interno, nombre, precio_venta, tipo, codigo_barras'
            ).eq('activo', True).execute()
            
            # Procesar productos varios
            for prod_varios in (response_varios.data or []):
                codigo_interno = prod_varios.get('codigo_interno')
                
                # Obtener stock del inventario
                inv_response = self.client.table('inventario').select(
                    'stock_actual, stock_minimo, id_ubicacion'
                ).eq('codigo_interno', codigo_interno).eq('tipo_producto', 'varios').execute()
                
                stock_actual = 0
                stock_minimo = 0
                id_ubicacion = None
                if inv_response.data:
                    inv = inv_response.data[0]
                    stock_actual = inv.get('stock_actual', 0)
                    stock_minimo = inv.get('stock_minimo', 0)
                    id_ubicacion = inv.get('id_ubicacion')
                
                productos_resultado.append({
                    'id_producto': prod_varios.get('id_producto'),
                    'codigo_interno': codigo_interno,
                    'nombre': prod_varios.get('nombre'),
                    'precio_venta': float(prod_varios.get('precio_venta', 0.0)),
                    'categoria': prod_varios.get('categoria', 'General'),
                    'codigo_barras': prod_varios.get('codigo_barras'),
                    'stock_actual': stock_actual,
                    'stock_minimo': stock_minimo,
                    'tipo_producto': 'varios',
                    'id_ubicacion': id_ubicacion
                })
            
            # Procesar suplementos
            for prod_suplemento in (response_suplementos.data or []):
                codigo_interno = prod_suplemento.get('codigo_interno')
                
                # Obtener stock del inventario
                inv_response = self.client.table('inventario').select(
                    'stock_actual, stock_minimo, id_ubicacion'
                ).eq('codigo_interno', codigo_interno).eq('tipo_producto', 'suplemento').execute()
                
                stock_actual = 0
                stock_minimo = 0
                id_ubicacion = None
                if inv_response.data:
                    inv = inv_response.data[0]
                    stock_actual = inv.get('stock_actual', 0)
                    stock_minimo = inv.get('stock_minimo', 0)
                    id_ubicacion = inv.get('id_ubicacion')
                
                productos_resultado.append({
                    'id_producto': prod_suplemento.get('id_suplemento'),  # Usar id_suplemento como id_producto
                    'codigo_interno': codigo_interno,
                    'nombre': prod_suplemento.get('nombre'),
                    'precio_venta': float(prod_suplemento.get('precio_venta', 0.0)),
                    'categoria': prod_suplemento.get('tipo', 'Suplemento'),
                    'codigo_barras': prod_suplemento.get('codigo_barras'),
                    'stock_actual': stock_actual,
                    'stock_minimo': stock_minimo,
                    'tipo_producto': 'suplemento',
                    'id_ubicacion': id_ubicacion
                })
            
            logging.info(f"Obtenidos {len(productos_resultado)} productos activos (con stock)")
            return productos_resultado
        
        except Exception as e:
            logging.error(f"Error obteniendo productos: {e}")
            return []
    
    def search_products(self, search_text: str) -> List[Dict]:
        """Buscar productos por código o nombre (CON STOCK INCLUIDO)"""
        try:
            if not self.is_connected:
                self.connect()
            
            search_pattern = f"%{search_text}%"
            productos_resultado = []
            
            # Buscar en productos varios
            response_varios = self.client.table('ca_productos_varios').select(
                'id_producto, codigo_interno, nombre, precio_venta, categoria, codigo_barras'
            ).or_(
                f"nombre.ilike.{search_pattern},codigo_barras.ilike.{search_pattern},codigo_interno.ilike.{search_pattern}"
            ).eq('activo', True).execute()
            
            # Buscar en suplementos
            response_suplementos = self.client.table('ca_suplementos').select(
                'id_suplemento, codigo_interno, nombre, precio_venta, tipo, codigo_barras'
            ).or_(
                f"nombre.ilike.{search_pattern},codigo_barras.ilike.{search_pattern},codigo_interno.ilike.{search_pattern}"
            ).eq('activo', True).execute()
            
            # Procesar productos varios
            for prod_varios in (response_varios.data or []):
                codigo_interno = prod_varios.get('codigo_interno')
                
                # Obtener stock del inventario
                inv_response = self.client.table('inventario').select(
                    'stock_actual, stock_minimo, id_ubicacion'
                ).eq('codigo_interno', codigo_interno).eq('tipo_producto', 'varios').execute()
                
                stock_actual = 0
                stock_minimo = 0
                id_ubicacion = None
                if inv_response.data:
                    inv = inv_response.data[0]
                    stock_actual = inv.get('stock_actual', 0)
                    stock_minimo = inv.get('stock_minimo', 0)
                    id_ubicacion = inv.get('id_ubicacion')
                
                productos_resultado.append({
                    'id_producto': prod_varios.get('id_producto'),
                    'codigo_interno': codigo_interno,
                    'nombre': prod_varios.get('nombre'),
                    'precio_venta': float(prod_varios.get('precio_venta', 0.0)),
                    'categoria': prod_varios.get('categoria', 'General'),
                    'codigo_barras': prod_varios.get('codigo_barras'),
                    'stock_actual': stock_actual,
                    'stock_minimo': stock_minimo,
                    'tipo_producto': 'varios',
                    'id_ubicacion': id_ubicacion
                })
            
            # Procesar suplementos
            for prod_suplemento in (response_suplementos.data or []):
                codigo_interno = prod_suplemento.get('codigo_interno')
                
                # Obtener stock del inventario
                inv_response = self.client.table('inventario').select(
                    'stock_actual, stock_minimo, id_ubicacion'
                ).eq('codigo_interno', codigo_interno).eq('tipo_producto', 'suplemento').execute()
                
                stock_actual = 0
                stock_minimo = 0
                id_ubicacion = None
                if inv_response.data:
                    inv = inv_response.data[0]
                    stock_actual = inv.get('stock_actual', 0)
                    stock_minimo = inv.get('stock_minimo', 0)
                    id_ubicacion = inv.get('id_ubicacion')
                
                productos_resultado.append({
                    'id_producto': prod_suplemento.get('id_suplemento'),  # Usar id_suplemento como id_producto
                    'codigo_interno': codigo_interno,
                    'nombre': prod_suplemento.get('nombre'),
                    'precio_venta': float(prod_suplemento.get('precio_venta', 0.0)),
                    'categoria': prod_suplemento.get('tipo', 'Suplemento'),
                    'codigo_barras': prod_suplemento.get('codigo_barras'),
                    'stock_actual': stock_actual,
                    'stock_minimo': stock_minimo,
                    'tipo_producto': 'suplemento',
                    'id_ubicacion': id_ubicacion
                })
            
            logging.info(f"Encontrados {len(productos_resultado)} productos para '{search_text}'")
            return productos_resultado
            
        except Exception as e:
            logging.error(f"Error buscando productos: {e}")
            return []
    
    def get_product_by_barcode(self, barcode: str) -> Optional[Dict]:
        """Buscar producto por código de barras (RÁPIDO - búsqueda exacta con stock incluido)"""
        import time
        tiempo_inicio = time.perf_counter()
        
        try:
            if not self.is_connected:
                self.connect()
            
            # Buscar en productos varios
            tiempo_varios = time.perf_counter()
            response_varios = self.client.table('ca_productos_varios').select(
                'id_producto, codigo_interno, nombre, precio_venta, categoria, codigo_barras'
            ).eq('codigo_barras', barcode).eq('activo', True).execute()
            tiempo_varios_ms = (time.perf_counter() - tiempo_varios) * 1000
            
            if response_varios.data:
                prod_varios = response_varios.data[0]
                codigo_interno = prod_varios.get('codigo_interno')
                
                # Obtener stock del inventario
                tiempo_stock = time.perf_counter()
                inv_response = self.client.table('inventario').select(
                    'stock_actual, stock_minimo, id_ubicacion'
                ).eq('codigo_interno', codigo_interno).eq('tipo_producto', 'varios').execute()
                tiempo_stock_ms = (time.perf_counter() - tiempo_stock) * 1000
                
                stock_actual = 0
                stock_minimo = 0
                id_ubicacion = None
                if inv_response.data:
                    inv = inv_response.data[0]
                    stock_actual = inv.get('stock_actual', 0)
                    stock_minimo = inv.get('stock_minimo', 0)
                    id_ubicacion = inv.get('id_ubicacion')
                
                tiempo_total_ms = (time.perf_counter() - tiempo_inicio) * 1000
                logging.info(f"✓ Encontrado en ca_productos_varios: {tiempo_varios_ms:.1f}ms + stock: {tiempo_stock_ms:.1f}ms = {tiempo_total_ms:.1f}ms total")
                
                return {
                    'id_producto': prod_varios.get('id_producto'),
                    'codigo_interno': codigo_interno,
                    'nombre': prod_varios.get('nombre'),
                    'precio_venta': float(prod_varios.get('precio_venta', 0.0)),
                    'categoria': prod_varios.get('categoria', 'General'),
                    'codigo_barras': prod_varios.get('codigo_barras'),
                    'stock_actual': stock_actual,
                    'stock_minimo': stock_minimo,
                    'tipo_producto': 'varios',
                    'id_ubicacion': id_ubicacion
                }
            
            # Buscar en suplementos
            tiempo_suplementos = time.perf_counter()
            response_suplementos = self.client.table('ca_suplementos').select(
                'id_suplemento, codigo_interno, nombre, precio_venta, tipo, codigo_barras'
            ).eq('codigo_barras', barcode).eq('activo', True).execute()
            tiempo_suplementos_ms = (time.perf_counter() - tiempo_suplementos) * 1000
            
            if response_suplementos.data:
                prod_suplemento = response_suplementos.data[0]
                codigo_interno = prod_suplemento.get('codigo_interno')
                
                # Obtener stock del inventario
                tiempo_stock = time.perf_counter()
                inv_response = self.client.table('inventario').select(
                    'stock_actual, stock_minimo, id_ubicacion'
                ).eq('codigo_interno', codigo_interno).eq('tipo_producto', 'suplemento').execute()
                tiempo_stock_ms = (time.perf_counter() - tiempo_stock) * 1000
                
                stock_actual = 0
                stock_minimo = 0
                id_ubicacion = None
                if inv_response.data:
                    inv = inv_response.data[0]
                    stock_actual = inv.get('stock_actual', 0)
                    stock_minimo = inv.get('stock_minimo', 0)
                    id_ubicacion = inv.get('id_ubicacion')
                
                tiempo_total_ms = (time.perf_counter() - tiempo_inicio) * 1000
                logging.info(f"✓ Encontrado en ca_suplementos: {tiempo_varios_ms:.1f}ms + {tiempo_suplementos_ms:.1f}ms + stock: {tiempo_stock_ms:.1f}ms = {tiempo_total_ms:.1f}ms total")
                
                return {
                    'id_producto': prod_suplemento.get('id_suplemento'),
                    'codigo_interno': codigo_interno,
                    'nombre': prod_suplemento.get('nombre'),
                    'precio_venta': float(prod_suplemento.get('precio_venta', 0.0)),
                    'categoria': prod_suplemento.get('tipo', 'Suplemento'),
                    'codigo_barras': prod_suplemento.get('codigo_barras'),
                    'stock_actual': stock_actual,
                    'stock_minimo': stock_minimo,
                    'tipo_producto': 'suplemento',
                    'id_ubicacion': id_ubicacion
                }
            
            tiempo_total_ms = (time.perf_counter() - tiempo_inicio) * 1000
            logging.warning(f"✗ Código de barras {barcode} no encontrado: {tiempo_varios_ms:.1f}ms + {tiempo_suplementos_ms:.1f}ms = {tiempo_total_ms:.1f}ms")
            return None
        
        except Exception as e:
            tiempo_total_ms = (time.perf_counter() - tiempo_inicio) * 1000
            logging.error(f"Error buscando producto por código de barras ({tiempo_total_ms:.1f}ms): {e}")
            return None
    
    def get_product_by_code(self, code: str) -> Optional[Dict]:
        """Buscar producto por código interno"""
        try:
            if not self.is_connected:
                self.connect()
            
            # Buscar en productos varios
            response_varios = self.client.table('ca_productos_varios').select('*').eq('codigo_interno', code).eq('activo', True).execute()
            
            if response_varios.data:
                return response_varios.data[0]
            
            # Buscar en suplementos
            response_suplementos = self.client.table('ca_suplementos').select('*').eq('codigo_interno', code).eq('activo', True).execute()
            
            if response_suplementos.data:
                return response_suplementos.data[0]
            
            logging.warning(f"Producto con código interno {code} no encontrado")
            return None
        
        except Exception as e:
            logging.error(f"Error buscando producto por código interno: {e}")
            return None
    
    def get_product_with_stock(self, codigo_interno: str) -> Optional[Dict]:
        """Obtener producto completo con stock actual desde inventario
        
        Busca el producto en ca_productos_varios o ca_suplementos y agrega el stock
        desde la tabla inventario.
        
        Returns:
            Dict con campos: nombre, precio_venta, stock_actual, tipo_producto, etc.
            O None si no encuentra el producto
        """
        try:
            if not self.is_connected:
                self.connect()
            
            # Buscar en productos varios
            response_varios = self.client.table('ca_productos_varios').select(
                'codigo_interno, nombre, precio_venta, categoria, codigo_barras'
            ).eq('codigo_interno', codigo_interno).eq('activo', True).execute()
            
            if response_varios.data:
                producto = response_varios.data[0]
                tipo_producto = 'varios'
            else:
                # Buscar en suplementos
                response_suplementos = self.client.table('ca_suplementos').select(
                    'codigo_interno, nombre, precio_venta, tipo, codigo_barras'
                ).eq('codigo_interno', codigo_interno).eq('activo', True).execute()
                
                if response_suplementos.data:
                    producto = response_suplementos.data[0]
                    tipo_producto = 'suplemento'
                else:
                    logging.warning(f"Producto con código interno {codigo_interno} no encontrado")
                    return None
            
            # Obtener stock del inventario
            response_inventario = self.client.table('inventario').select(
                'stock_actual, stock_minimo, id_ubicacion'
            ).eq('codigo_interno', codigo_interno).eq('tipo_producto', tipo_producto).execute()
            
            stock_actual = 0
            stock_minimo = 0
            id_ubicacion = None
            
            if response_inventario.data:
                inv = response_inventario.data[0]
                stock_actual = inv.get('stock_actual', 0)
                stock_minimo = inv.get('stock_minimo', 0)
                id_ubicacion = inv.get('id_ubicacion')
            
            # Combinar datos
            resultado = {
                'codigo_interno': producto.get('codigo_interno'),
                'nombre': producto.get('nombre'),
                'precio_venta': float(producto.get('precio_venta', 0.0)),
                'codigo_barras': producto.get('codigo_barras'),
                'stock_actual': stock_actual,
                'stock_minimo': stock_minimo,
                'tipo_producto': tipo_producto,
                'id_ubicacion': id_ubicacion
            }
            
            # Agregar campo de categoría según tipo
            if tipo_producto == 'varios':
                resultado['categoria'] = producto.get('categoria', 'General')
            else:
                resultado['categoria'] = producto.get('tipo', 'Suplemento')
            
            return resultado
            
        except Exception as e:
            logging.error(f"Error obteniendo producto con stock: {e}")
            return None
    
    # ========== VENTAS ==========
    
    def create_sale(self, venta_data: Dict) -> Optional[int]:
        """Crear nueva venta"""
        try:
            if not self.is_connected:
                self.connect()
            
            # Calcular totales
            subtotal = venta_data['total']
            descuento = venta_data.get('descuento', 0)
            impuestos = venta_data.get('impuestos', 0)
            
            # Preparar datos de venta
            venta_insert = {
                'id_usuario': venta_data['id_usuario'],
                'id_miembro': venta_data.get('id_miembro'),
                'id_turno': venta_data.get('id_turno'),  # Agregar ID del turno
                'fecha': venta_data.get('fecha', datetime.now().isoformat()),
                'subtotal': float(subtotal),
                'descuento': float(descuento),
                'impuestos': float(impuestos),
                'total': float(venta_data['total']),
                'metodo_pago': venta_data.get('metodo_pago', 'efectivo'),
                'tipo_venta': venta_data.get('tipo_venta', 'producto'),
                'estado': 'completada'
            }
            
            # Insertar venta
            response = self.client.table('ventas').insert(venta_insert).execute()
            
            if not response.data:
                logging.error("Error insertando venta")
                return None
            
            venta_id = response.data[0]['id_venta']
            
            # Insertar detalles y actualizar stock
            for item in venta_data.get('productos', []):
                # Obtener información del producto
                producto_response = self.client.table('ca_productos_varios').select('codigo_interno, nombre, descripcion').eq('id_producto', item['id_producto']).execute()
                
                if not producto_response.data:
                    logging.error(f"Producto {item['id_producto']} no encontrado")
                    continue
                
                producto_info = producto_response.data[0]
                codigo_interno = producto_info['codigo_interno']
                
                # Verificar stock
                stock_response = self.client.table('inventario').select('stock_actual').eq('codigo_interno', codigo_interno).eq('tipo_producto', 'varios').execute()
                
                if not stock_response.data or stock_response.data[0]['stock_actual'] < item['cantidad']:
                    logging.error(f"Stock insuficiente para {producto_info['nombre']}")
                    continue
                
                # Insertar detalle
                detalle_data = {
                    'id_venta': venta_id,
                    'codigo_interno': codigo_interno,
                    'tipo_producto': 'varios',
                    'cantidad': item['cantidad'],
                    'precio_unitario': float(item['precio']),
                    'subtotal_linea': float(item['subtotal']),
                    'nombre_producto': producto_info['nombre'],
                    'descripcion_producto': producto_info.get('descripcion')
                }
                
                self.client.table('detalles_venta').insert(detalle_data).execute()
                
                # Actualizar stock
                stock_anterior = stock_response.data[0]['stock_actual']
                stock_nuevo = stock_anterior - item['cantidad']
                
                self.client.table('inventario').update({'stock_actual': stock_nuevo}).eq('codigo_interno', codigo_interno).eq('tipo_producto', 'varios').execute()
                
                # Registrar movimiento
                movimiento_data = {
                    'codigo_interno': codigo_interno,
                    'tipo_producto': 'varios',
                    'tipo_movimiento': 'venta',
                    'cantidad': -item['cantidad'],
                    'stock_anterior': stock_anterior,
                    'stock_nuevo': stock_nuevo,
                    'id_usuario': venta_data['id_usuario'],
                    'id_venta': venta_id
                }
                
                self.client.table('movimientos_inventario').insert(movimiento_data).execute()
            
            logging.info(f"✅ Venta creada: ID {venta_id}, Total: ${venta_data['total']:.2f}")
            return venta_id
            
        except Exception as e:
            logging.error(f"Error creando venta: {e}")
            raise

    def get_turno_abierto_id(self, id_usuario: int) -> Optional[int]:
        """Obtener el ID del turno abierto del usuario (si existe)."""
        try:
            if not self.is_connected:
                self.connect()

            response = (
                self.client.table('turnos_caja')
                .select('id_turno')
                .eq('id_usuario', id_usuario)
                .eq('cerrado', False)
                .order('fecha_apertura', desc=True)
                .limit(1)
                .execute()
            )

            if response.data and len(response.data) > 0:
                return response.data[0].get('id_turno')
            return None
        except Exception as e:
            logging.error(f"Error obteniendo turno abierto para usuario {id_usuario}: {e}")
            return None

    def get_ventas_digitales_pendientes_efectivo_hoy(self, id_venta_digital: int) -> List[int]:
        """Obtener IDs de ventas_digitales pendientes (efectivo) del mismo miembro creadas hoy.

        Replica la lógica de la Edge Function `confirm-cash-payment` para saber qué se activará,
        y usarlo para contabilizar en el POS sin duplicar.
        """
        try:
            if not self.is_connected:
                self.connect()

            venta_resp = (
                self.client.table('ventas_digitales')
                .select('id_miembro, estado, metodo_pago, fecha_compra')
                .eq('id_venta_digital', id_venta_digital)
                .limit(1)
                .execute()
            )

            if not venta_resp.data:
                return []

            venta = venta_resp.data[0]
            member_id = venta.get('id_miembro')
            if not member_id:
                return []

            hoy_str = date.today().isoformat()
            response = (
                self.client.table('ventas_digitales')
                .select('id_venta_digital')
                .eq('id_miembro', member_id)
                .eq('estado', 'pendiente_pago')
                .eq('metodo_pago', 'efectivo')
                .gte('fecha_compra', f"{hoy_str}T00:00:00")
                .lt('fecha_compra', f"{hoy_str}T23:59:59")
                .execute()
            )

            ids = [row.get('id_venta_digital') for row in (response.data or []) if row.get('id_venta_digital')]
            return ids
        except Exception as e:
            logging.error(f"Error obteniendo ventas digitales pendientes del día: {e}")
            return []

    def contabilizar_pago_efectivo_digital_en_pos(
        self,
        ids_ventas_digitales: List[int],
        id_usuario: int,
        id_turno: int,
    ) -> Optional[int]:
        """Registrar una venta contable en `ventas` + `detalles_venta` por confirmación de efectivo.

        Es idempotente usando `ventas.referencia_pago` con un valor determinístico basado en
        los IDs de `ventas_digitales` confirmados.
        """
        try:
            if not self.is_connected:
                self.connect()

            ids = sorted({int(v) for v in (ids_ventas_digitales or []) if v})
            if not ids:
                return None

            referencia_pago = f"CASHCONF:{','.join(map(str, ids))}"

            # Idempotencia: si ya existe la venta contable, no duplicar
            existing = (
                self.client.table('ventas')
                .select('id_venta')
                .eq('referencia_pago', referencia_pago)
                .limit(1)
                .execute()
            )
            if existing.data:
                return existing.data[0].get('id_venta')

            ventas_resp = (
                self.client.table('ventas_digitales')
                .select('id_venta_digital, id_miembro, id_producto_digital, monto')
                .in_('id_venta_digital', ids)
                .execute()
            )
            ventas_digitales = ventas_resp.data or []
            if not ventas_digitales:
                return None

            member_ids = {v.get('id_miembro') for v in ventas_digitales if v.get('id_miembro')}
            if len(member_ids) != 1:
                logging.error(f"No se puede contabilizar: múltiples miembros en ventas_digitales {ids}")
                return None

            id_miembro = next(iter(member_ids))
            total = sum(float(v.get('monto') or 0) for v in ventas_digitales)

            venta_insert = {
                'id_usuario': id_usuario,
                'id_miembro': id_miembro,
                'id_turno': id_turno,
                'fecha': datetime.now().isoformat(),
                'subtotal': float(total),
                'descuento': 0.0,
                'impuestos': 0.0,
                'total': float(total),
                'metodo_pago': 'efectivo',
                'tipo_venta': 'membresia',
                'estado': 'completada',
                'referencia_pago': referencia_pago,
                'notas': f"Pago en efectivo confirmado (app). Ventas digitales: {referencia_pago}",
            }

            venta_response = self.client.table('ventas').insert(venta_insert).execute()
            if not venta_response.data:
                logging.error("No se pudo insertar la venta contable")
                return None

            id_venta = venta_response.data[0].get('id_venta')
            if not id_venta:
                return None

            producto_ids = sorted({v.get('id_producto_digital') for v in ventas_digitales if v.get('id_producto_digital')})
            productos_map: Dict[int, Dict[str, Any]] = {}
            if producto_ids:
                productos_resp = (
                    self.client.table('ca_productos_digitales')
                    .select('id_producto_digital, codigo_interno, nombre, descripcion')
                    .in_('id_producto_digital', producto_ids)
                    .execute()
                )
                for p in (productos_resp.data or []):
                    if p.get('id_producto_digital') is not None:
                        productos_map[int(p['id_producto_digital'])] = p

            for v in ventas_digitales:
                pid = v.get('id_producto_digital')
                producto = productos_map.get(int(pid)) if pid is not None else None
                monto = float(v.get('monto') or 0)

                detalle = {
                    'id_venta': id_venta,
                    'codigo_interno': (producto or {}).get('codigo_interno') or f"DIGITAL-{pid}",
                    'tipo_producto': 'digital',
                    'cantidad': 1,
                    'precio_unitario': monto,
                    'subtotal_linea': monto,
                    'descuento_linea': 0,
                    'nombre_producto': (producto or {}).get('nombre') or 'Producto digital',
                    'descripcion_producto': (producto or {}).get('descripcion'),
                }

                self.client.table('detalles_venta').insert(detalle).execute()

            logging.info(f"✅ Pago efectivo contabilizado en POS. Venta={id_venta}, Ref={referencia_pago}")
            return id_venta
        except Exception as e:
            logging.error(f"Error contabilizando pago efectivo digital en POS: {e}")
            return None

    def contabilizar_pago_efectivo_notificacion_en_pos(
        self,
        id_notificacion: int,
        id_usuario: int,
        id_turno: int,
    ) -> Optional[int]:
        """Registrar una venta contable en `ventas` + `detalles_venta` usando `notificaciones_pos`.

        Motivación: la app que genera la notificación puede no tener desglose ni ventas_digitales
        consistentes. Para el corte diario, se toma `monto_pendiente` como total y se crea un
        único detalle genérico.

        Es idempotente por `ventas.referencia_pago = CASHNOTIF:<id_notificacion>`.
        """
        try:
            if not self.is_connected:
                self.connect()

            if not id_notificacion:
                return None

            referencia_pago = f"CASHNOTIF:{int(id_notificacion)}"

            existing = (
                self.client.table('ventas')
                .select('id_venta')
                .eq('referencia_pago', referencia_pago)
                .limit(1)
                .execute()
            )
            if existing.data:
                return existing.data[0].get('id_venta')

            notif_resp = (
                self.client.table('notificaciones_pos')
                .select('id_notificacion, id_miembro, id_venta_digital, monto_pendiente, codigo_pago_generado, tipo_notificacion, asunto')
                .eq('id_notificacion', int(id_notificacion))
                .limit(1)
                .execute()
            )

            if not notif_resp.data:
                logging.error(f"No se encontró notificación {id_notificacion} para contabilizar")
                return None

            notif = notif_resp.data[0]
            id_miembro = notif.get('id_miembro')
            monto = float(notif.get('monto_pendiente') or 0)

            if not id_miembro:
                logging.error(f"Notificación {id_notificacion} sin id_miembro; no se puede contabilizar")
                return None
            if monto <= 0:
                logging.error(f"Notificación {id_notificacion} con monto_pendiente inválido: {notif.get('monto_pendiente')}")
                return None

            now_iso = datetime.now().isoformat()
            codigo = (notif.get('codigo_pago_generado') or '').strip() or None
            id_venta_digital = notif.get('id_venta_digital')

            venta_insert = {
                'id_usuario': id_usuario,
                'id_miembro': id_miembro,
                'id_turno': id_turno,
                'fecha': now_iso,
                'subtotal': float(monto),
                'descuento': 0.0,
                'impuestos': 0.0,
                'total': float(monto),
                'metodo_pago': 'efectivo',
                # Mantener un valor genérico ya usado por el POS
                'tipo_venta': 'producto',
                'estado': 'completada',
                'referencia_pago': referencia_pago,
                'notas': (
                    f"Pago en efectivo confirmado (app). Notificación={id_notificacion}"
                    + (f", VentaDigital={id_venta_digital}" if id_venta_digital else "")
                    + (f", Código={codigo}" if codigo else "")
                ),
            }

            venta_response = self.client.table('ventas').insert(venta_insert).execute()
            if not venta_response.data:
                logging.error("No se pudo insertar la venta contable (notificación)")
                return None

            id_venta = venta_response.data[0].get('id_venta')
            if not id_venta:
                return None

            detalle = {
                'id_venta': id_venta,
                'codigo_interno': 'PAGO-EFECTIVO-APP',
                'tipo_producto': 'digital',
                'cantidad': 1,
                'precio_unitario': float(monto),
                'subtotal_linea': float(monto),
                'descuento_linea': 0,
                'nombre_producto': 'Pago en efectivo (app)',
                'descripcion_producto': (
                    'Registro contable sin desglose; total tomado de notificaciones_pos.monto_pendiente.'
                ),
            }

            self.client.table('detalles_venta').insert(detalle).execute()
            logging.info(f"✅ Pago efectivo contabilizado desde notificación. Venta={id_venta}, Ref={referencia_pago}")
            return id_venta
        except Exception as e:
            logging.error(f"Error contabilizando pago efectivo desde notificación en POS: {e}")
            return None
    
    # ========== MIEMBROS Y ACCESO ==========
    
    def obtener_miembro_por_codigo_qr(self, codigo_qr: str) -> Optional[Dict]:
        """Obtener miembro por código QR"""
        try:
            if not self.is_connected:
                self.connect()
            
            response = self.client.table('miembros').select('*').eq('codigo_qr', codigo_qr).execute()
            
            if response.data:
                return response.data[0]
            
            logging.warning(f"Miembro con código QR {codigo_qr} no encontrado")
            return None
                
        except Exception as e:
            logging.error(f"Error obteniendo miembro: {e}")
            return None
    
    def get_total_members(self) -> int:
        """Obtener total de miembros activos"""
        try:
            if not self.is_connected:
                self.connect()
            
            response = self.client.table('miembros').select('id_miembro', count='exact').eq('activo', True).execute()
            return response.count or 0
        except Exception as e:
            logging.error(f"Error obteniendo total de miembros: {e}")
            return 0
    
    # ========== GESTIÓN DE PRODUCTOS E INVENTARIO ==========
    
    def producto_existe(self, codigo_interno: str) -> bool:
        """Verificar si un código interno ya existe"""
        try:
            if not self.is_connected:
                self.connect()
            
            # Buscar en productos varios
            response_varios = self.client.table('ca_productos_varios').select('id_producto').eq('codigo_interno', codigo_interno).limit(1).execute()
            
            if response_varios.data:
                return True
            
            # Buscar en suplementos
            response_suplementos = self.client.table('ca_suplementos').select('id_suplemento').eq('codigo_interno', codigo_interno).limit(1).execute()
            
            if response_suplementos.data:
                return True
            
            return False
                
        except Exception as e:
            logging.error(f"Error verificando existencia de producto: {e}")
            return False
    
    def insertar_producto_varios(self, producto_data: Dict) -> bool:
        """Insertar un nuevo producto normal (varios) en Supabase"""
        try:
            if not self.is_connected:
                self.connect()
            
            producto_insert = {
                'codigo_interno': producto_data['codigo_interno'],
                'codigo_barras': producto_data.get('codigo_barras'),
                'nombre': producto_data['nombre'],
                'descripcion': producto_data.get('descripcion'),
                'precio_venta': float(producto_data['precio_venta']),
                'categoria': producto_data.get('categoria', 'General'),
                'requiere_refrigeracion': bool(producto_data.get('requiere_refrigeracion', False)),
                'cantidad_medida': float(producto_data['cantidad_medida']) if producto_data.get('cantidad_medida') else None,
                'unidad_medida': producto_data.get('unidad_medida'),
                'activo': bool(producto_data.get('activo', True))
            }
            
            response = self.client.table('ca_productos_varios').insert(producto_insert).execute()
            
            if response.data:
                id_producto = response.data[0]['id_producto']
                logging.info(f"✅ Producto varios '{producto_data['nombre']}' insertado con ID: {id_producto}")
                return True
            else:
                logging.error(f"No se pudo insertar el producto '{producto_data['nombre']}'")
                return False
                
        except Exception as e:
            logging.error(f"Error insertando producto varios: {e}")
            return False
    
    def insertar_suplemento(self, suplemento_data: Dict) -> bool:
        """Insertar un nuevo suplemento en Supabase"""
        try:
            if not self.is_connected:
                self.connect()
            
            suplemento_insert = {
                'codigo_interno': suplemento_data['codigo_interno'],
                'codigo_barras': suplemento_data.get('codigo_barras'),
                'nombre': suplemento_data['nombre'],
                'descripcion': suplemento_data.get('descripcion'),
                'marca': suplemento_data['marca'],
                'tipo': suplemento_data['tipo'],
                'cantidad_medida': float(suplemento_data['cantidad_medida']) if suplemento_data.get('cantidad_medida') else None,
                'unidad_medida': suplemento_data.get('unidad_medida'),
                'precio_venta': float(suplemento_data['precio_venta']),
                'activo': bool(suplemento_data.get('activo', True)),
                'fecha_vencimiento': suplemento_data.get('fecha_vencimiento')
            }
            
            response = self.client.table('ca_suplementos').insert(suplemento_insert).execute()
            
            if response.data:
                id_suplemento = response.data[0]['id_suplemento']
                logging.info(f"✅ Suplemento '{suplemento_data['nombre']}' insertado con ID: {id_suplemento}")
                return True
            else:
                logging.error(f"No se pudo insertar el suplemento '{suplemento_data['nombre']}'")
                return False
                
        except Exception as e:
            logging.error(f"Error insertando suplemento: {e}")
            return False
    
    def crear_inventario(self, inventario_data: Dict) -> bool:
        """Crear un registro de inventario para un producto físico"""
        try:
            if not self.is_connected:
                self.connect()
            
            inventario_insert = {
                'codigo_interno': inventario_data['codigo_interno'],
                'tipo_producto': inventario_data['tipo_producto'],
                'stock_actual': int(inventario_data.get('stock_actual', 0)),
                'stock_minimo': int(inventario_data.get('stock_minimo', 5)),
                'id_ubicacion': int(inventario_data.get('id_ubicacion', 1)),
                'activo': bool(inventario_data.get('activo', True))
            }
            
            response = self.client.table('inventario').insert(inventario_insert).execute()
            
            if response.data:
                id_inventario = response.data[0]['id_inventario']
                logging.info(f"✅ Inventario creado para '{inventario_data['codigo_interno']}' con ID: {id_inventario}")
                return True
            else:
                logging.error(f"No se pudo crear inventario para '{inventario_data['codigo_interno']}'")
                return False
                
        except Exception as e:
            logging.error(f"Error creando inventario: {e}")
            return False
    
    def obtener_inventario_completo(self) -> List[Dict]:
        """Obtener inventario completo con datos de productos (JOIN con ca_productos_varios, ca_suplementos y ca_ubicaciones)"""
        try:
            if not self.is_connected:
                self.connect()
            
            # Obtener inventario con productos varios
            response_varios = self.client.table('inventario').select(
                'id_inventario, codigo_interno, tipo_producto, stock_actual, stock_minimo, id_ubicacion, seccion, activo'
            ).eq('tipo_producto', 'varios').eq('activo', True).execute()
            
            productos_varios = response_varios.data or []
            
            # Obtener inventario con suplementos
            response_suplementos = self.client.table('inventario').select(
                'id_inventario, codigo_interno, tipo_producto, stock_actual, stock_minimo, id_ubicacion, seccion, activo'
            ).eq('tipo_producto', 'suplemento').eq('activo', True).execute()
            
            productos_suplementos = response_suplementos.data or []
            
            # Obtener todas las ubicaciones para mapeo
            ubicaciones_map = {}
            try:
                response_ubicaciones = self.client.table('ca_ubicaciones').select(
                    'id_ubicacion, nombre'
                ).execute()
                ubicaciones_map = {
                    u['id_ubicacion']: u['nombre'] 
                    for u in (response_ubicaciones.data or [])
                }
            except Exception as e:
                logging.warning(f"No se pudieron obtener ubicaciones: {e}")
            
            # Obtener detalles de productos varios
            productos_varios_data = {}
            if productos_varios:
                codigos_varios = [p['codigo_interno'] for p in productos_varios]
                response = self.client.table('ca_productos_varios').select(
                    'codigo_interno, nombre, precio_venta, categoria, codigo_barras'
                ).in_('codigo_interno', codigos_varios).execute()
                
                productos_varios_data = {p['codigo_interno']: p for p in (response.data or [])}
            
            # Obtener detalles de suplementos
            productos_suplementos_data = {}
            if productos_suplementos:
                codigos_suplementos = [p['codigo_interno'] for p in productos_suplementos]
                response = self.client.table('ca_suplementos').select(
                    'codigo_interno, nombre, precio_venta, tipo, codigo_barras'
                ).in_('codigo_interno', codigos_suplementos).execute()
                
                productos_suplementos_data = {p['codigo_interno']: p for p in (response.data or [])}
            
            # Combinar datos
            inventario_completo = []
            
            # Agregar productos varios
            for inv in productos_varios:
                codigo = inv['codigo_interno']
                producto = productos_varios_data.get(codigo, {})
                id_ubicacion = inv.get('id_ubicacion')
                ubicacion_nombre = ubicaciones_map.get(id_ubicacion, 'N/A')
                
                inventario_completo.append({
                    'id_inventario': inv['id_inventario'],
                    'codigo_interno': codigo,
                    'nombre': producto.get('nombre', 'N/A'),
                    'precio': float(producto.get('precio_venta', 0.0)),
                    'categoria': producto.get('categoria', 'General'),
                    'codigo_barras': producto.get('codigo_barras'),
                    'seccion': inv.get('seccion', 'N/A'),
                    'tipo_producto': inv['tipo_producto'],
                    'stock_actual': inv['stock_actual'],
                    'stock_minimo': inv['stock_minimo'],
                    'id_ubicacion': id_ubicacion,
                    'ubicacion': ubicacion_nombre,
                    'activo': inv['activo']
                })
            
            # Agregar suplementos
            for inv in productos_suplementos:
                codigo = inv['codigo_interno']
                producto = productos_suplementos_data.get(codigo, {})
                id_ubicacion = inv.get('id_ubicacion')
                ubicacion_nombre = ubicaciones_map.get(id_ubicacion, 'N/A')
                
                inventario_completo.append({
                    'id_inventario': inv['id_inventario'],
                    'codigo_interno': codigo,
                    'nombre': producto.get('nombre', 'N/A'),
                    'precio': float(producto.get('precio_venta', 0.0)),
                    'categoria': producto.get('tipo', 'Suplemento'),  # Para suplementos usamos 'tipo' como categoría
                    'codigo_barras': producto.get('codigo_barras'),
                    'seccion': inv.get('seccion', 'N/A'),
                    'tipo_producto': inv['tipo_producto'],
                    'stock_actual': inv['stock_actual'],
                    'stock_minimo': inv['stock_minimo'],
                    'id_ubicacion': id_ubicacion,
                    'ubicacion': ubicacion_nombre,
                    'activo': inv['activo']
                })
            
            logging.info(f"✅ Inventario completo cargado: {len(inventario_completo)} productos")
            return inventario_completo
            
        except Exception as e:
            logging.error(f"Error obteniendo inventario completo: {e}")
            return []
    
    def actualizar_stock(self, codigo_interno: str, tipo_producto: str, nuevo_stock: int, 
                        fecha_entrada: str = None, fecha_salida: str = None) -> bool:
        """Actualizar stock en la tabla inventario
        
        Args:
            codigo_interno: Código del producto
            tipo_producto: 'varios' o 'suplemento'
            nuevo_stock: Nuevo valor de stock
            fecha_entrada: Timestamp de entrada (opcional)
            fecha_salida: Timestamp de salida (opcional)
        
        Returns:
            True si la actualización fue exitosa, False en caso contrario
        """
        try:
            if not self.is_connected:
                self.connect()
            
            update_data = {'stock_actual': nuevo_stock}
            
            if fecha_entrada:
                update_data['fecha_ultima_entrada'] = fecha_entrada
            
            if fecha_salida:
                update_data['fecha_ultima_salida'] = fecha_salida
            
            response = self.client.table('inventario').update(update_data).eq(
                'codigo_interno', codigo_interno
            ).eq('tipo_producto', tipo_producto).execute()
            
            logging.info(f"✅ Stock actualizado: {codigo_interno} → {nuevo_stock} unidades")
            return True
            
        except Exception as e:
            logging.error(f"Error actualizando stock: {e}")
            return False
    
    def registrar_movimiento_inventario(self, movimiento_data: Dict) -> bool:
        """Registrar un movimiento en la tabla movimientos_inventario
        
        Args:
            movimiento_data: Dict con campos:
                - codigo_interno (str)
                - tipo_producto (str): 'varios' o 'suplemento'
                - tipo_movimiento (str): 'entrada', 'salida', 'venta', 'merma', 'ajuste'
                - cantidad (int): cantidad del movimiento (positivo para entrada, negativo para salida)
                - stock_anterior (int)
                - stock_nuevo (int)
                - motivo (str, opcional)
                - id_usuario (int, opcional)
                - id_venta (int, opcional)
        
        Returns:
            True si el registro fue exitoso, False en caso contrario
        """
        try:
            if not self.is_connected:
                self.connect()
            
            # Asegurar que tenemos los campos requeridos
            movimiento_insert = {
                'codigo_interno': movimiento_data.get('codigo_interno'),
                'tipo_producto': movimiento_data.get('tipo_producto'),
                'tipo_movimiento': movimiento_data.get('tipo_movimiento'),
                'cantidad': int(movimiento_data.get('cantidad', 0)),
                'stock_anterior': int(movimiento_data.get('stock_anterior', 0)),
                'stock_nuevo': int(movimiento_data.get('stock_nuevo', 0))
            }
            
            # Campos opcionales
            if movimiento_data.get('motivo'):
                movimiento_insert['motivo'] = movimiento_data['motivo']
            
            if movimiento_data.get('id_usuario'):
                movimiento_insert['id_usuario'] = movimiento_data['id_usuario']
            
            if movimiento_data.get('id_venta'):
                movimiento_insert['id_venta'] = movimiento_data['id_venta']
            
            response = self.client.table('movimientos_inventario').insert(movimiento_insert).execute()
            
            logging.info(f"✅ Movimiento registrado: {movimiento_data.get('tipo_movimiento')} de {movimiento_data.get('codigo_interno')}")
            return True
            
        except Exception as e:
            logging.error(f"Error registrando movimiento de inventario: {e}")
            return False
    
    def obtener_movimientos_completos(self, limite: int = 1000) -> List[Dict]:
        """Obtener movimientos de inventario con nombres de productos y usuarios
        
        Optimizado: Usa batch queries en lugar de N+1 queries individuales
        
        Args:
            limite: Número máximo de movimientos a retornar (default 1000)
        
        Returns:
            Lista de diccionarios con movimientos completos incluyendo:
            - nombre_producto (del JOIN con ca_productos_varios o ca_suplementos)
            - nombre_usuario (del JOIN con usuarios si existe id_usuario)
        """
        try:
            if not self.is_connected:
                self.connect()
            
            # 1. Obtener movimientos básicos (UNA sola query)
            logging.info("📊 Obteniendo movimientos de base de datos...")
            response = self.client.table('movimientos_inventario').select(
                'id_movimiento, fecha, tipo_movimiento, codigo_interno, tipo_producto, '
                'cantidad, stock_anterior, stock_nuevo, motivo, id_usuario, id_venta'
            ).neq('tipo_movimiento', 'venta').order('fecha', desc=True).limit(limite).execute()
            
            movimientos = response.data or []
            if not movimientos:
                logging.info("✅ No hay movimientos para retornar")
                return []
            
            logging.info(f"📦 Procesando {len(movimientos)} movimientos...")
            
            # 2. Extraer códigos únicos de productos (para batch query)
            codigos_varios = set()
            codigos_suplementos = set()
            ids_usuarios = set()
            
            for mov in movimientos:
                tipo = mov.get('tipo_producto', 'varios')
                codigo = mov.get('codigo_interno')
                
                if tipo == 'varios' and codigo:
                    codigos_varios.add(codigo)
                elif tipo == 'suplemento' and codigo:
                    codigos_suplementos.add(codigo)
                
                id_usuario = mov.get('id_usuario')
                if id_usuario:
                    ids_usuarios.add(id_usuario)
            
            # 3. Obtener datos de productos en BATCH (máximo 2 queries en lugar de N)
            productos_varios_map = {}
            productos_suplementos_map = {}
            usuarios_map = {}
            
            # Query 1: Todos los productos "varios" de una sola vez
            if codigos_varios:
                try:
                    logging.info(f"📥 Obteniendo {len(codigos_varios)} productos varios...")
                    response_varios = self.client.table('ca_productos_varios').select(
                        'codigo_interno, nombre'
                    ).in_('codigo_interno', list(codigos_varios)).execute()
                    
                    for prod in (response_varios.data or []):
                        productos_varios_map[prod['codigo_interno']] = prod['nombre']
                    logging.info(f"✅ Obtenidos {len(productos_varios_map)} productos varios")
                except Exception as e:
                    logging.warning(f"⚠️ Error obteniendo productos varios: {e}")
            
            # Query 2: Todos los suplementos de una sola vez
            if codigos_suplementos:
                try:
                    logging.info(f"📥 Obteniendo {len(codigos_suplementos)} suplementos...")
                    response_suplementos = self.client.table('ca_suplementos').select(
                        'codigo_interno, nombre'
                    ).in_('codigo_interno', list(codigos_suplementos)).execute()
                    
                    for prod in (response_suplementos.data or []):
                        productos_suplementos_map[prod['codigo_interno']] = prod['nombre']
                    logging.info(f"✅ Obtenidos {len(productos_suplementos_map)} suplementos")
                except Exception as e:
                    logging.warning(f"⚠️ Error obteniendo suplementos: {e}")
            
            # Query 3: Todos los usuarios de una sola vez
            if ids_usuarios:
                try:
                    logging.info(f"📥 Obteniendo {len(ids_usuarios)} usuarios...")
                    response_usuarios = self.client.table('usuarios').select(
                        'id_usuario, nombre_completo'
                    ).in_('id_usuario', list(ids_usuarios)).execute()
                    
                    for usuario in (response_usuarios.data or []):
                        usuarios_map[usuario['id_usuario']] = usuario['nombre_completo']
                    logging.info(f"✅ Obtenidos {len(usuarios_map)} usuarios")
                except Exception as e:
                    logging.warning(f"⚠️ Error obteniendo usuarios: {e}")
            
            # 4. Construir resultado con lookups (sin más queries)
            logging.info("🔄 Combinando datos...")
            movimientos_completos = []
            
            for mov in movimientos:
                codigo_interno = mov.get('codigo_interno')
                tipo_producto = mov.get('tipo_producto', 'varios')
                id_usuario = mov.get('id_usuario')
                
                # Lookup del nombre del producto (O(1) en lugar de query)
                if tipo_producto == 'varios':
                    nombre_producto = productos_varios_map.get(codigo_interno, 'Producto desconocido')
                else:
                    nombre_producto = productos_suplementos_map.get(codigo_interno, 'Producto desconocido')
                
                # Lookup del nombre del usuario (O(1) en lugar de query)
                nombre_usuario = usuarios_map.get(id_usuario, 'Usuario desconocido') if id_usuario else 'Sin usuario'
                
                movimientos_completos.append({
                    'id_movimiento': mov.get('id_movimiento'),
                    'fecha': mov.get('fecha'),
                    'tipo_movimiento': mov.get('tipo_movimiento'),
                    'codigo_interno': codigo_interno,
                    'tipo_producto': tipo_producto,
                    'cantidad': mov.get('cantidad'),
                    'stock_anterior': mov.get('stock_anterior'),
                    'stock_nuevo': mov.get('stock_nuevo'),
                    'motivo': mov.get('motivo') or '',
                    'id_usuario': id_usuario,
                    'id_venta': mov.get('id_venta'),
                    'nombre_producto': nombre_producto,
                    'nombre_usuario': nombre_usuario
                })
            
            logging.info(f"✅ Obtuvieron {len(movimientos_completos)} movimientos completos (optimizado: 3-4 queries en lugar de {len(movimientos)*2})")
            return movimientos_completos
            
        except Exception as e:
            logging.error(f"Error obteniendo movimientos completos: {e}")
            return []
    
    # ========== UBICACIONES ==========
    
    def get_ubicaciones(self) -> List[Dict]:
        """Obtener todas las ubicaciones activas"""
        try:
            if not self.is_connected:
                self.connect()
            
            response = self.client.table('ca_ubicaciones').select('*').eq('activa', True).order('nombre').execute()
            return response.data or []
        except Exception as e:
            logging.error(f"Error obteniendo ubicaciones: {e}")
            return []
    
    def get_ubicacion_by_id(self, id_ubicacion: int) -> Optional[Dict]:
        """Obtener una ubicación por ID"""
        try:
            if not self.is_connected:
                self.connect()
            
            response = self.client.table('ca_ubicaciones').select('*').eq('id_ubicacion', id_ubicacion).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logging.error(f"Error obteniendo ubicación: {e}")
            return None
    
    # ========== PRODUCTOS DIGITALES ==========
    
    def get_productos_digitales(self) -> List[Dict]:
        """Obtener todos los productos digitales activos"""
        try:
            if not self.is_connected:
                self.connect()
            
            response = self.client.table('ca_productos_digitales').select('*').eq('activo', True).order('nombre').execute()
            return response.data or []
        except Exception as e:
            logging.error(f"Error obteniendo productos digitales: {e}")
            return []
    
    def get_producto_digital_by_id(self, id_producto_digital: int) -> Optional[Dict]:
        """Obtener producto digital por ID"""
        try:
            if not self.is_connected:
                self.connect()
            
            response = self.client.table('ca_productos_digitales').select('*').eq('id_producto_digital', id_producto_digital).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logging.error(f"Error obteniendo producto digital: {e}")
            return None
    
    def get_producto_digital_by_name(self, nombre: str) -> Optional[Dict]:
        """Obtener producto digital por nombre"""
        try:
            if not self.is_connected:
                self.connect()
            
            response = self.client.table('ca_productos_digitales').select('*').eq('nombre', nombre).eq('activo', True).execute()
            
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            logging.error(f"Error obteniendo producto digital por nombre: {e}")
            return None
    
    def insertar_producto_digital(self, producto_data: Dict) -> Optional[int]:
        """Insertar un nuevo producto digital"""
        try:
            if not self.is_connected:
                self.connect()
            
            producto_insert = {
                'codigo_interno': producto_data['codigo_interno'],
                'nombre': producto_data['nombre'],
                'descripcion': producto_data.get('descripcion'),
                'tipo': producto_data['tipo'],
                'precio_venta': float(producto_data.get('precio_venta', 0)),
                'duracion_dias': int(producto_data.get('duracion_dias', 0)) if producto_data.get('duracion_dias') else None,
                'aplica_domingo': bool(producto_data.get('aplica_domingo', False)),
                'aplica_festivo': bool(producto_data.get('aplica_festivo', False)),
                'es_unico': bool(producto_data.get('es_unico', False)),
                'requiere_asignacion': bool(producto_data.get('requiere_asignacion', False)),
                'activo': True
            }
            
            response = self.client.table('ca_productos_digitales').insert(producto_insert).execute()
            
            if response.data:
                id_producto = response.data[0]['id_producto_digital']
                logging.info(f"✅ Producto digital '{producto_data['nombre']}' creado con ID: {id_producto}")
                return id_producto
            else:
                logging.error(f"No se pudo crear el producto digital '{producto_data['nombre']}'")
                return None
        except Exception as e:
            logging.error(f"Error insertando producto digital: {e}")
            return None
    
    # ========== LOCKERS ==========
    
    def get_lockers(self) -> List[Dict]:
        """Obtener todos los lockers activos"""
        try:
            if not self.is_connected:
                self.connect()
            
            response = self.client.table('lockers').select('*').eq('activo', True).order('numero').execute()
            return response.data or []
        except Exception as e:
            logging.error(f"Error obteniendo lockers: {e}")
            return []
    
    def get_locker_by_id(self, id_locker: int) -> Optional[Dict]:
        """Obtener locker por ID"""
        try:
            if not self.is_connected:
                self.connect()
            
            response = self.client.table('lockers').select('*').eq('id_locker', id_locker).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logging.error(f"Error obteniendo locker: {e}")
            return None
    
    def insertar_locker(self, locker_data: Dict) -> Optional[int]:
        """Insertar un nuevo locker"""
        try:
            if not self.is_connected:
                self.connect()
            
            locker_insert = {
                'numero': locker_data['numero'],
                'ubicacion': locker_data.get('ubicacion', 'Zona Lockers'),
                'tipo': locker_data.get('tipo', 'estándar'),
                'requiere_llave': bool(locker_data.get('requiere_llave', True)),
                'activo': True
            }
            
            response = self.client.table('lockers').insert(locker_insert).execute()
            
            if response.data:
                id_locker = response.data[0]['id_locker']
                logging.info(f"✅ Locker '{locker_data['numero']}' creado con ID: {id_locker}")
                return id_locker
            else:
                logging.error(f"No se pudo crear el locker '{locker_data['numero']}'")
                return None
        except Exception as e:
            logging.error(f"Error insertando locker: {e}")
            return None
    
    # ========== ASIGNACIONES ACTIVAS ==========
    
    def crear_asignacion_activa(self, asignacion_data: Dict) -> Optional[int]:
        """Crear una asignación activa (membresía o locker)"""
        try:
            if not self.is_connected:
                self.connect()
            
            asignacion_insert = {
                'id_miembro': asignacion_data['id_miembro'],
                'id_producto_digital': asignacion_data['id_producto_digital'],
                'id_venta': asignacion_data.get('id_venta'),
                'id_locker': asignacion_data.get('id_locker'),
                'activa': True,
                'cancelada': False,
                'fecha_inicio': asignacion_data['fecha_inicio'],
                'fecha_fin': asignacion_data['fecha_fin'],
                'estado': asignacion_data.get('estado', 'activa')
            }
            
            response = self.client.table('asignaciones_activas').insert(asignacion_insert).execute()
            
            if response.data:
                id_asignacion = response.data[0]['id_asignacion']
                logging.info(f"✅ Asignación activa creada con ID: {id_asignacion}")
                return id_asignacion
            else:
                logging.error("No se pudo crear la asignación activa")
                return None
        except Exception as e:
            logging.error(f"Error creando asignación activa: {e}")
            return None
    
    def get_asignaciones_activas_por_miembro(self, id_miembro: int) -> List[Dict]:
        """Obtener asignaciones activas de un miembro"""
        try:
            if not self.is_connected:
                self.connect()
            
            response = self.client.table('asignaciones_activas').select('*').eq('id_miembro', id_miembro).eq('activa', True).order('fecha_inicio', desc=True).execute()
            return response.data or []
        except Exception as e:
            logging.error(f"Error obteniendo asignaciones activas: {e}")
            return []
    
    def cancelar_asignacion(self, id_asignacion: int) -> bool:
        """Cancelar una asignación activa"""
        try:
            if not self.is_connected:
                self.connect()
            
            response = self.client.table('asignaciones_activas').update({
                'activa': False,
                'cancelada': True,
                'estado': 'cancelada',
                'fecha_cancelacion': datetime.now().isoformat()
            }).eq('id_asignacion', id_asignacion).execute()
            
            if response.data:
                logging.info(f"✅ Asignación {id_asignacion} cancelada")
                return True
            else:
                logging.error(f"No se pudo cancelar la asignación {id_asignacion}")
                return False
        except Exception as e:
            logging.error(f"Error cancelando asignación: {e}")
            return False
    
    # ========== REGISTRO DE ENTRADAS ==========
    
    def registrar_entrada(self, entrada_data: Dict) -> Optional[int]:
        """Registrar una entrada al gimnasio"""
        try:
            if not self.is_connected:
                self.connect()
            
            entrada_insert = {
                'id_miembro': entrada_data.get('id_miembro'),
                'id_personal': entrada_data.get('id_personal'),
                'nombre_visitante': entrada_data.get('nombre_visitante'),
                'tipo_acceso': entrada_data['tipo_acceso'],
                'area_accedida': entrada_data.get('area_accedida', 'General'),
                'dispositivo_registro': entrada_data.get('dispositivo_registro'),
                'notas': entrada_data.get('notas'),
                'autorizado_por': entrada_data.get('autorizado_por'),
                'id_venta_acceso': entrada_data.get('id_venta_acceso'),
                'fecha_entrada': datetime.now().isoformat()
            }
            
            response = self.client.table('registro_entradas').insert(entrada_insert).execute()
            
            if response.data:
                id_entrada = response.data[0]['id_entrada']
                logging.info(f"✅ Entrada registrada con ID: {id_entrada}")
                return id_entrada
            else:
                logging.error("No se pudo registrar la entrada")
                return None
        except Exception as e:
            logging.error(f"Error registrando entrada: {e}")
            return None
    
    def registrar_salida(self, id_entrada: int) -> bool:
        """Registrar la salida de una persona"""
        try:
            if not self.is_connected:
                self.connect()
            
            response = self.client.table('registro_entradas').update({'fecha_salida': datetime.now().isoformat()}).eq('id_entrada', id_entrada).execute()
            
            if response.data:
                logging.info(f"✅ Salida registrada para entrada {id_entrada}")
                return True
            else:
                logging.error(f"No se pudo registrar la salida para entrada {id_entrada}")
                return False
        except Exception as e:
            logging.error(f"Error registrando salida: {e}")
            return False
    
    def get_historial_entradas(self, id_miembro: int, limite: int = 50) -> List[Dict]:
        """Obtener historial de entradas de un miembro"""
        try:
            if not self.is_connected:
                self.connect()
            
            response = self.client.table('registro_entradas').select('*').eq('id_miembro', id_miembro).order('fecha_entrada', desc=True).limit(limite).execute()
            return response.data or []
        except Exception as e:
            logging.error(f"Error obteniendo historial de entradas: {e}")
            return []
    
    # ========== VENTAS DIGITALES (APP) ==========
    
    def crear_venta_digital(self, venta_data: Dict) -> Optional[int]:
        """Crear una venta digital desde la app"""
        try:
            if not self.is_connected:
                self.connect()
            
            venta_insert = {
                'id_miembro': venta_data['id_miembro'],
                'id_producto_digital': venta_data['id_producto_digital'],
                'id_locker': venta_data.get('id_locker'),
                'id_usuario': venta_data.get('id_usuario'),
                'fecha_compra': datetime.now().isoformat(),
                'monto': float(venta_data['monto']),
                'metodo_pago': venta_data.get('metodo_pago', 'efectivo'),
                'referencia_pago': venta_data.get('referencia_pago'),
                'estado': venta_data.get('estado', 'pendiente_pago'),
                'fecha_inicio': venta_data['fecha_inicio'],
                'fecha_fin': venta_data['fecha_fin']
            }
            
            response = self.client.table('ventas_digitales').insert(venta_insert).execute()
            
            if response.data:
                id_venta = response.data[0]['id_venta_digital']
                logging.info(f"✅ Venta digital creada con ID: {id_venta}")
                return id_venta
            else:
                logging.error("No se pudo crear la venta digital")
                return None
        except Exception as e:
            logging.error(f"Error creando venta digital: {e}")
            return None
    
    def get_ventas_digitales_por_miembro(self, id_miembro: int) -> List[Dict]:
        """Obtener ventas digitales de un miembro"""
        try:
            if not self.is_connected:
                self.connect()
            
            response = self.client.table('ventas_digitales').select('*').eq('id_miembro', id_miembro).order('fecha_compra', desc=True).execute()
            return response.data or []
        except Exception as e:
            logging.error(f"Error obteniendo ventas digitales: {e}")
            return []
    
    def actualizar_estado_venta_digital(self, id_venta_digital: int, nuevo_estado: str) -> bool:
        """Actualizar el estado de una venta digital"""
        try:
            if not self.is_connected:
                self.connect()
            
            response = self.client.table('ventas_digitales').update({'estado': nuevo_estado}).eq('id_venta_digital', id_venta_digital).execute()
            
            if response.data:
                logging.info(f"✅ Venta digital {id_venta_digital} actualizada a estado: {nuevo_estado}")
                return True
            else:
                logging.error(f"No se pudo actualizar venta digital {id_venta_digital}")
                return False
        except Exception as e:
            logging.error(f"Error actualizando venta digital: {e}")
            return False
    
    # ========== NOTIFICACIONES DE PAGO ==========
    
    def crear_notificacion_pago(self, notif_data: Dict) -> Optional[int]:
        """Crear una notificación de pago"""
        try:
            if not self.is_connected:
                self.connect()
            
            notif_insert = {
                'id_miembro': notif_data['id_miembro'],
                'id_venta_digital': notif_data.get('id_venta_digital'),
                'tipo_notificacion': notif_data['tipo_notificacion'],
                'asunto': notif_data['asunto'],
                'descripcion': notif_data.get('descripcion'),
                'monto_pendiente': float(notif_data.get('monto_pendiente', 0)) if notif_data.get('monto_pendiente') else None,
                'fecha_vencimiento': notif_data.get('fecha_vencimiento'),
                'para_miembro': bool(notif_data.get('para_miembro', True)),
                'para_recepcion': bool(notif_data.get('para_recepcion', True)),
                'codigo_pago_generado': notif_data.get('codigo_pago_generado'),
                'leida': False,
                'respondida': False
            }
            
            response = self.client.table('notificaciones_pos').insert(notif_insert).execute()
            
            if response.data:
                id_notif = response.data[0]['id_notificacion']
                logging.info(f"✅ Notificación de pago creada con ID: {id_notif}")
                return id_notif
            else:
                logging.error("No se pudo crear la notificación de pago")
                return None
        except Exception as e:
            logging.error(f"Error creando notificación de pago: {e}")
            return None
    
    def get_notificaciones_pendientes(self, para_recepcion: bool = True) -> List[Dict]:
        """Obtener notificaciones de pago pendientes"""
        try:
            if not self.is_connected:
                self.connect()
            
            query = self.client.table('notificaciones_pos').select('*').eq('leida', False).eq('respondida', False)
            
            if para_recepcion:
                query = query.eq('para_recepcion', True)
            
            response = query.order('creada_en', desc=True).execute()
            return response.data or []
        except Exception as e:
            logging.error(f"Error obteniendo notificaciones pendientes: {e}")
            return []
    
    def marcar_notificacion_como_leida(self, id_notificacion: int) -> bool:
        """Marcar una notificación como leída"""
        try:
            if not self.is_connected:
                self.connect()
            
            response = self.client.table('notificaciones_pos').update({'leida': True}).eq('id_notificacion', id_notificacion).execute()
            
            if response.data:
                logging.info(f"✅ Notificación {id_notificacion} marcada como leída")
                return True
            else:
                logging.error(f"No se pudo marcar la notificación {id_notificacion} como leída")
                return False
        except Exception as e:
            logging.error(f"Error marcando notificación como leída: {e}")
            return False
    
    # ========== TURNOS DE CAJA ==========
    
    def abrir_turno_caja(self, id_usuario: int, monto_inicial: Decimal = 0) -> Optional[int]:
        """Abrir un nuevo turno de caja"""
        try:
            if not self.is_connected:
                self.connect()
            
            turno_insert = {
                'id_usuario': id_usuario,
                'monto_inicial': float(monto_inicial),
                'cerrado': False
            }
            
            response = self.client.table('turnos_caja').insert(turno_insert).execute()
            
            if response.data:
                id_turno = response.data[0]['id_turno']
                logging.info(f"✅ Turno de caja abierto con ID: {id_turno} para usuario {id_usuario}")
                return id_turno
            else:
                logging.error(f"No se pudo abrir turno de caja para usuario {id_usuario}")
                return None
        except Exception as e:
            logging.error(f"Error abriendo turno de caja: {e}")
            return None
    
    def get_turno_activo(self, id_usuario: int) -> Optional[Dict]:
        """Obtener el turno activo de un usuario"""
        try:
            if not self.is_connected:
                self.connect()
            
            response = self.client.table('turnos_caja').select('*').eq('id_usuario', id_usuario).eq('cerrado', False).order('fecha_apertura', desc=True).limit(1).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logging.error(f"Error obteniendo turno activo: {e}")
            return None
    
    def cerrar_turno_caja(self, id_turno: int, monto_real_cierre: Decimal) -> bool:
        """Cerrar un turno de caja"""
        try:
            if not self.is_connected:
                self.connect()
            
            # Obtener datos del turno
            response = self.client.table('turnos_caja').select('*').eq('id_turno', id_turno).eq('cerrado', False).execute()
            
            if not response.data:
                logging.warning(f"Turno {id_turno} no encontrado o ya cerrado")
                return False
            
            turno = response.data[0]
            diferencia = monto_real_cierre - (turno.get('monto_esperado') or 0)
            
            update_data = {
                'fecha_cierre': datetime.now().isoformat(),
                'monto_real_cierre': float(monto_real_cierre),
                'diferencia': float(diferencia),
                'cerrado': True,
                'actualizado_en': datetime.now().isoformat()
            }
            
            update_response = self.client.table('turnos_caja').update(update_data).eq('id_turno', id_turno).execute()
            
            if update_response.data:
                logging.info(f"✅ Turno {id_turno} cerrado. Diferencia: ${diferencia:.2f}")
                return True
            else:
                logging.error(f"No se pudo cerrar el turno {id_turno}")
                return False
        except Exception as e:
            logging.error(f"Error cerrando turno de caja: {e}")
            return False
    
    # ========== MÉTODOS PARA PAGOS EN EFECTIVO ==========
    
    def buscar_notificacion_por_codigo_pago(self, codigo_pago: str) -> Optional[Dict]:
        """Buscar una notificación de pago pendiente por código generado"""
        try:
            if not self.is_connected:
                self.connect()
            
            response = self.client.table('notificaciones_pos').select('*, miembros(*)').eq('codigo_pago_generado', codigo_pago).eq('respondida', False).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logging.error(f"Error buscando notificación por código: {e}")
            return None
    
    def obtener_detalle_notificacion(self, id_notificacion: int) -> Optional[Dict]:
        """Obtener detalles completos de una notificación de pago"""
        try:
            if not self.is_connected:
                self.connect()
            
            response = self.client.table('notificaciones_pos').select('*, miembros(*), ventas_digitales(*, ca_productos_digitales(*))').eq('id_notificacion', id_notificacion).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logging.error(f"Error obteniendo detalles de notificación: {e}")
            return None
    
    def obtener_notificaciones_pendientes(self) -> List[Dict]:
        """Obtener todas las notificaciones de pago pendientes para recepción"""
        try:
            if not self.is_connected:
                self.connect()
            
            response = self.client.table('notificaciones_pos').select('*, miembros(*)').eq('para_recepcion', True).eq('respondida', False).in_('tipo_notificacion', ['membresia_pendiente', 'visita_pendiente', 'pago_pendiente']).order('creada_en', desc=True).execute()
            return response.data or []
        except Exception as e:
            logging.error(f"Error obteniendo notificaciones pendientes: {e}")
            return []
    
    def sincronizar_notificacion_supabase(self, id_notificacion: int, datos_supabase: Dict) -> bool:
        """Sincronizar una notificación que viene de Supabase"""
        try:
            if not self.is_connected:
                self.connect()
            
            logging.info(f"✅ Notificación {id_notificacion} sincronizada desde Supabase (ya está en la base de datos)")
            return True
                
        except Exception as e:
            logging.error(f"Error sincronizando notificación: {e}")
            return False
    
    def confirmar_pago_efectivo(self, id_notificacion: int, observaciones: str = None) -> bool:
        """Confirmar pago en efectivo y activar asignación correspondiente"""
        try:
            if not self.is_connected:
                self.connect()
            
            # Obtener datos de la venta digital
            notif_response = self.client.table('notificaciones_pos').select('*, ventas_digitales(*)').eq('id_notificacion', id_notificacion).execute()
            
            if not notif_response.data:
                logging.error(f"Notificación {id_notificacion} no encontrada")
                return False
            
            notif = notif_response.data[0]
            id_venta_digital = notif.get('id_venta_digital')
            
            if not id_venta_digital:
                logging.error(f"Venta digital no encontrada para notificación {id_notificacion}")
                return False
            
            venta_response = self.client.table('ventas_digitales').select('*').eq('id_venta_digital', id_venta_digital).execute()
            
            if not venta_response.data:
                logging.error(f"Venta digital {id_venta_digital} no encontrada")
                return False
            
            venta = venta_response.data[0]
            timestamp_actual = datetime.now().isoformat()
            referencia_pago = f"EFECTIVO_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            # Actualizar venta_digital a 'activa'
            self.client.table('ventas_digitales').update({
                'estado': 'activa',
                'fecha_compra': timestamp_actual,
                'referencia_pago': referencia_pago
            }).eq('id_venta_digital', id_venta_digital).execute()
            
            # Actualizar notificación como resuelta
            self.client.table('notificaciones_pos').update({
                'leida': True,
                'respondida': True,
                'resuelve_en': timestamp_actual
            }).eq('id_notificacion', id_notificacion).execute()
            
            # Crear asignación activa
            self.client.table('asignaciones_activas').insert({
                'id_miembro': venta['id_miembro'],
                'id_producto_digital': venta['id_producto_digital'],
                'id_venta': None,
                'id_locker': venta.get('id_locker'),
                'activa': True,
                'cancelada': False,
                'fecha_inicio': venta['fecha_inicio'],
                'fecha_fin': venta['fecha_fin']
            }).execute()
            
            # Registrar entrada
            obs_completa = f"Pago efectivo confirmado. Ref: {referencia_pago}. {observaciones or ''}"
            self.client.table('registro_entradas').insert({
                'id_miembro': venta['id_miembro'],
                'tipo_acceso': 'miembro',
                'fecha_entrada': timestamp_actual,
                'area_accedida': 'Recepción',
                'dispositivo_registro': 'POS',
                'notas': obs_completa
            }).execute()
            
            # Crear notificación de confirmación
            self.client.table('notificaciones_pos').insert({
                'id_miembro': venta['id_miembro'],
                'id_venta_digital': id_venta_digital,
                'tipo_notificacion': 'pago_completado',
                'asunto': 'Pago Confirmado',
                'descripcion': 'Tu pago en efectivo ha sido confirmado. Tu membresía/visita está activa.',
                'leida': False,
                'respondida': True,
                'para_miembro': True,
                'para_recepcion': False
            }).execute()
            
            logging.info(f"✅ Pago efectivo confirmado: {referencia_pago}")
            return True
                
        except Exception as e:
            logging.error(f"Error confirmando pago: {e}")
            return False

    def registrar_recargo_cobrado(self, recargo_data: Dict) -> Optional[int]:
        """Registrar un recargo cobrado en la tabla recargos_cobrados"""
        try:
            if not self.is_connected:
                self.connect()
            
            recargo_insert = {
                'id_miembro': recargo_data['id_miembro'],
                'id_producto_digital': recargo_data['id_producto_digital'],
                'id_venta': recargo_data.get('id_venta'),
                'id_detalle_venta': recargo_data.get('id_detalle_venta'),
                'fecha_aplica': recargo_data['fecha_aplica'],
                'id_locker': recargo_data.get('id_locker'),
                'monto': float(recargo_data['monto']),
                'procesado': recargo_data.get('procesado', True),
                'pagado': recargo_data.get('pagado', False)
            }
            
            response = self.client.table('recargos_cobrados').insert(recargo_insert).execute()
            
            if response.data:
                id_recargo = response.data[0]['id_recargo']
                logging.info(f"✅ Recargo cobrado registrado con ID: {id_recargo}")
                return id_recargo
            else:
                logging.error("No se pudo registrar el recargo cobrado")
                return None
        except Exception as e:
            logging.error(f"Error registrando recargo cobrado: {e}")
            return None

    def actualizar_pago_recargo(self, id_recargo: int, id_venta: int, id_detalle_venta: int) -> bool:
        """Actualizar el estado de pago de un recargo cobrado cuando se genera la venta digital"""
        try:
            if not self.is_connected:
                self.connect()
            
            update_data = {
                'pagado': True,
                'id_venta': id_venta,
                'id_detalle_venta': id_detalle_venta
            }
            
            response = self.client.table('recargos_cobrados').update(update_data).eq('id_recargo', id_recargo).execute()
            
            if response.data:
                logging.info(f"✅ Recargo {id_recargo} marcado como pagado - Venta ID: {id_venta}")
                return True
            else:
                logging.error(f"No se pudo actualizar el pago del recargo {id_recargo}")
                return False
        except Exception as e:
            logging.error(f"Error actualizando pago del recargo {id_recargo}: {e}")
            return False


# Ejemplo de uso
if __name__ == "__main__":
    # Configuración de conexión (solo necesita URL y KEY de Supabase)
    config = {
        'url': os.getenv('SUPABASE_URL', 'https://xxxx.supabase.co'),
        'key': os.getenv('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIs...')
    }
    
    try:
        # Crear instancia del gestor
        db = PostgresManager(config)
        
        # Ejemplo: Autenticar usuario
        user = db.authenticate_user('admin', 'admin123')
        if user:
            print(f"✅ Usuario autenticado: {user['nombre_completo']}")
            print(f"   Rol: {user['rol']}")
        else:
            print("❌ Autenticación fallida")
        
        # Ejemplo: Actualizar pago de recargo cuando se genera venta digital
        # recargo_id = 123  # ID del recargo obtenido al registrar la multa
        # venta_id = 456    # ID de la venta generada
        # detalle_venta_id = 789  # ID del detalle de venta
        # exito = db.actualizar_pago_recargo(recargo_id, venta_id, detalle_venta_id)
        # if exito:
        #     print("✅ Recargo marcado como pagado")
        
        # Cerrar conexión
        db.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
