"""
Monitor de Entradas - Detecta nuevos registros usando Supabase Realtime
Emite señal cuando se detecta una nueva entrada en tiempo real
"""

from PySide6.QtCore import QObject, QTimer, Signal, QThread
import logging
from datetime import datetime
import json
import asyncio
import threading


class SupabaseRealtimeThread(QThread):
    """Hilo separado para escuchar cambios en tiempo real de Supabase"""

    entrada_insertada = Signal(dict)  # Emite los datos de la nueva entrada

    def __init__(self, supabase_service):
        super().__init__()
        self.supabase_service = supabase_service
        self.running = False
        self.channel = None
        self.loop = None
        self.thread = None
        self.procesados = set()  # Track de IDs de entrada ya procesados

    def run(self):
        """Conectar y escuchar cambios en tiempo real"""
        try:
            if not self.supabase_service or not self.supabase_service.is_connected:
                logging.error("[ERROR] Supabase no disponible para realtime")
                return

            logging.info("[OK] Iniciando Supabase Realtime para registro_entradas")

            # Crear un nuevo loop de eventos para este hilo
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            # Ejecutar la función async en el loop
            self.loop.run_until_complete(self._run_async())

        except Exception as e:
            if self.running:  # Solo loggear si no fue un apagado intencional
                logging.error(f"[ERROR] Error en Supabase Realtime thread: {e}")
        finally:
            if self.loop:
                try:
                    # Cancelar y esperar cualquier tarea pendiente antes de cerrar el loop
                    try:
                        pending = [t for t in asyncio.all_tasks(self.loop) if not t.done()]
                        if pending:
                            logging.info(f"[SHUTDOWN] Cancelando {len(pending)} tareas pendientes antes de cerrar el loop")
                            for t in pending:
                                try:
                                    t.cancel()
                                except Exception:
                                    pass
                            self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    except Exception:
                        pass

                    # Forzar recolección de objetos y verificar si hay coroutines pendientes
                    try:
                        import gc, types
                        coros = [o for o in gc.get_objects() if isinstance(o, types.CoroutineType)]
                        if coros:
                            logging.info(f"[SHUTDOWN] {len(coros)} coroutine objects in GC; running gc.collect() to finalize them")
                            gc.collect()
                    except Exception:
                        pass
                finally:
                    try:
                        if not self.loop.is_closed():
                            self.loop.close()
                    except Exception:
                        pass

    async def _run_async(self):
        """Función async para manejar el realtime"""
        try:
            # Configurar exception handler personalizado para evitar logging después del cierre
            def custom_exception_handler(loop, context):
                # Ignorar excepciones relacionadas con el cierre del loop
                exception = context.get('exception')
                if isinstance(exception, RuntimeError) and 'Event loop is closed' in str(exception):
                    return  # Silenciar esta excepción común durante el cierre
                
                # Solo intentar loggear si el hilo sigue activo y el logger está disponible
                if self.running:
                    try:
                        import logging
                        logger = logging.getLogger()
                        if logger and logger.hasHandlers() and hasattr(logger, 'error'):
                            # Verificar que el logger no esté cerrado
                            try:
                                # Intentar hacer un log de prueba para ver si funciona
                                logger.debug("test")
                                loop.default_exception_handler(context)
                            except (ValueError, AttributeError):
                                # Logger cerrado, no hacer nada
                                pass
                    except:
                        pass  # Silenciar cualquier error de logging
            
            self.loop.set_exception_handler(custom_exception_handler)
            
            # Crear cliente async
            from supabase import acreate_client
            client = await acreate_client(self.supabase_service.url, self.supabase_service.key)
            # Guardar referencia al cliente async para poder cerrarlo durante el apagado
            self.client = client

            # Crear canal de realtime
            self.channel = client.channel('registro_entradas_changes')

            # Suscribirse a eventos INSERT en la tabla registro_entradas
            self.channel.on_postgres_changes(
                event='INSERT',
                schema='public',
                table='registro_entradas',
                callback=self._on_entrada_insertada
            )

            # Suscribirse al canal
            await self.channel.subscribe()

            self.running = True

            try:
                # Mantener el hilo vivo mientras esté corriendo
                while self.running:
                    await asyncio.sleep(0.1)  # Pequeña pausa para no consumir CPU
            except asyncio.CancelledError:
                # Capturar CancelledError para asegurar limpieza
                self.running = False
                if self.running:  # Solo loggear si sigue corriendo
                    logging.info("[SHUTDOWN] Hilo cancelado, ejecutando shutdown...")
                raise  # Re-lanzar para que el loop sepa que fue cancelado

        except asyncio.CancelledError:
            # El hilo fue cancelado, asegurar limpieza
            self.running = False
            if self.running:  # Solo loggear si sigue corriendo
                logging.info("[SHUTDOWN] CancelledError capturado en _run_async")
        except Exception as e:
            if self.running:  # Solo loggear si fue un error intencional
                logging.error(f"[ERROR] Error en Supabase Realtime async: {e}")
        finally:
            # Ejecutar limpieza centralizada
            try:
                await self._shutdown_async()
            except Exception:
                pass

    def _on_entrada_insertada(self, payload):
        """Manejar cuando se inserta una nueva entrada"""
        try:
            # Verificar que sea un evento INSERT
            data = payload.get('data', {})
            event_type = data.get('type')
            
            if event_type != 'INSERT':
                # Ignorar otros tipos de eventos (DELETE, UPDATE)
                return
            
            if not self.running:
                # No procesar eventos si el hilo se está deteniendo
                return
            
            logging.debug(f"[REALTIME] Nueva entrada INSERT detectada")

            # El payload tiene la estructura: {'data': {'record': {...}}}
            new_record = data.get('record', {})

            if new_record:
                # Verificar si es 'efectivo_pendiente' - si es así, no emitir alerta
                tipo_acceso = new_record.get('tipo_acceso')
                if tipo_acceso == 'efectivo_pendiente':
                    if self.running:  # Solo loggear si el hilo sigue activo
                        entrada_id = new_record.get('id_entrada')
                        logging.info(f"[ENTRADA] Entrada ignorada por tipo 'efectivo_pendiente': ID {entrada_id}")
                    return
                
                # Verificar si ya procesamos este evento
                entrada_id = new_record.get('id_entrada')
                if entrada_id in self.procesados:
                    if self.running:  # Solo loggear si el hilo sigue activo
                        logging.debug(f"[REALTIME] Evento ya procesado, ignorando: {entrada_id}")
                    return
                
                # Marcar como procesado
                self.procesados.add(entrada_id)
                
                # Procesar la entrada en el hilo principal usando una señal segura
                id_miembro = new_record.get('id_miembro')

                if self.running:  # Solo loggear si el hilo sigue activo
                    logging.info(f"[ENTRADA] Procesando entrada ID: {entrada_id}, Miembro: {id_miembro}")

                # Emitir señal con los datos básicos
                self.entrada_insertada.emit(new_record)
            else:
                if self.running:  # Solo loggear si el hilo sigue activo
                    logging.warning(f"[REALTIME] No se encontraron datos de registro en el payload: {payload}")

        except Exception as e:
            logging.error(f"[ERROR] Error procesando entrada realtime: {e}")
            import traceback
            traceback.print_exc()

    async def _shutdown_async(self):
        """Rutina centralizada que se ejecuta para limpiar recursos.
        Se llama tanto desde _run_async() como desde stop()."""
        # Marcar que no estamos corriendo
        self.running = False

        # Intentar desconectar canal
        if self.channel:
            try:
                await self.channel.unsubscribe()
            except Exception:
                pass
            finally:
                self.channel = None

        # Intentar cerrar cliente async si existe
        await self._close_client()

        # Cancelar tareas pendientes (excluyendo esta)
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
        if pending:
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    async def _close_client(self):
        """Cerrar el cliente async de manera segura (reutilizable)"""
        if getattr(self, 'client', None):
            try:
                aclose = getattr(self.client, 'aclose', None)
                if aclose and callable(aclose):
                    res = aclose()
                    if asyncio.iscoroutine(res):
                        await res
                else:
                    close = getattr(self.client, 'close', None)
                    if close and callable(close):
                        res = close()
                        if asyncio.iscoroutine(res):
                            await res
            except Exception:
                pass
            finally:
                self.client = None

    def stop(self):
        """Detener el listener de manera segura"""
        self.running = False

        # Esperar un poco para que el _run_async termine naturalmente
        import time
        time.sleep(0.2)

        if self.loop and not self.loop.is_closed():
            try:
                # Ejecutar la rutina de apagado dentro del event loop del hilo de forma segura
                import asyncio
                
                # Si el loop está corriendo, usar run_coroutine_threadsafe
                if self.loop.is_running():
                    try:
                        future = asyncio.run_coroutine_threadsafe(self._shutdown_async(), self.loop)
                        try:
                            future.result(timeout=2.0)
                        except Exception:
                            # Ignorar timeouts/cancelaciones durante el cierre
                            pass
                    except Exception:
                        # Si no podemos ejecutar coroutine, intentar parar el loop directamente
                        try:
                            self.loop.call_soon_threadsafe(self.loop.stop)
                        except Exception:
                            pass
                    
                    # Dar tiempo para que el loop se detenga
                    time.sleep(0.1)
                else:
                    # Si el loop no está corriendo, simplemente cerrar
                    try:
                        if not self.loop.is_closed():
                            self.loop.close()
                    except Exception:
                        pass
            except Exception as e:
                logging.error(f"Error durante shutdown del loop: {e}")

        # Esperar a que el hilo termine (máximo 2 segundos)
        try:
            self.wait(timeout=2000)
        except Exception:
            pass

    def __del__(self):
        """Destructor para asegurar limpieza de recursos"""
        try:
            if self.isRunning():
                self.stop()
        except:
            pass


class MonitorEntradas(QObject):
    """
    Monitorea nuevas entradas usando Supabase Realtime.
    Emite una señal cuando se detecta una nueva entrada.
    """

    nueva_entrada_detectada = Signal(dict)  # Emite los datos de la entrada y del miembro

    def __init__(self, postgres_manager, supabase_service=None):
        """
        Args:
            postgres_manager: Instancia de PostgresManager para manejar la base de datos
            supabase_service: Instancia de SupabaseService para realtime
        """
        super().__init__()
        self.postgres_manager = postgres_manager
        self.supabase_service = supabase_service

        # Hilo de realtime
        self.realtime_thread = None

        # Estado del monitor
        self.activo = False

        logging.info("Monitor de entradas inicializado (Supabase Realtime)")
    
    @staticmethod
    def _build_entrada_data(entrada, include_foto=False):
        """Construir diccionario con datos de entrada y miembro.
        
        Args:
            entrada: Diccionario con datos de entrada y miembros relacionados
            include_foto: Si incluir campos de foto (foto, foto_url)
            
        Returns:
            Diccionario con estructura esperada para notificaciones
        """
        miembro = entrada.get('miembros', {})
        
        entrada_data = {
            'id_entrada': entrada.get('id_entrada'),
            'id_miembro': entrada.get('id_miembro'),
            'tipo_acceso': entrada.get('tipo_acceso'),
            'fecha_entrada': entrada.get('fecha_entrada'),
            'area_accedida': entrada.get('area_accedida'),
            'dispositivo_registro': entrada.get('dispositivo_registro'),
            'notas': entrada.get('notas'),
            'nombres': miembro.get('nombres', ''),
            'apellido_paterno': miembro.get('apellido_paterno', ''),
            'apellido_materno': miembro.get('apellido_materno', ''),
            'telefono': miembro.get('telefono', ''),
            'email': miembro.get('email', ''),
            'codigo_qr': miembro.get('codigo_qr', ''),
            'activo': miembro.get('activo', True),
            'fecha_registro': miembro.get('fecha_registro', ''),
            'fecha_nacimiento': miembro.get('fecha_nacimiento', '')
        }
        
        # Incluir foto solo si se solicita explícitamente
        if include_foto:
            entrada_data.update({
                'foto': miembro.get('foto', None),
                'foto_url': miembro.get('foto_url', None)
            })
        
        return entrada_data
    
    def iniciar(self):
        """Iniciar el monitoreo en tiempo real"""
        if self.activo:
            logging.warning("Monitor ya está activo")
            return

        if not self.supabase_service or not self.supabase_service.is_connected:
            logging.error("[ERROR] Supabase no disponible para iniciar monitor")
            return

        try:
            # Crear y configurar hilo de realtime
            self.realtime_thread = SupabaseRealtimeThread(self.supabase_service)

            # Conectar señal
            self.realtime_thread.entrada_insertada.connect(self.procesar_nueva_entrada)

            # Iniciar hilo
            self.realtime_thread.start()

            self.activo = True

            logging.info("[OK] Monitor de entradas iniciado (Supabase Realtime)")

        except Exception as e:
            logging.error(f"[ERROR] Error iniciando monitor de entradas: {e}")
    
    def detener(self):
        """Detener el monitoreo"""
        if not self.activo:
            return

        logging.info("Deteniendo monitor de entradas...")

        if self.realtime_thread:
            try:
                # Detener el hilo de manera segura
                self.realtime_thread.stop()
                # Esperar a que termine con timeout más largo
                if not self.realtime_thread.wait(5000):  # 5 segundos timeout
                    logging.warning("Thread de realtime no terminó en tiempo esperado, forzando terminación")
                    self.realtime_thread.terminate()  # Forzar terminación si es necesario
                    self.realtime_thread.wait(2000)  # Esperar 2 segundos más después de terminate
            except Exception as e:
                logging.error(f"Error deteniendo thread de realtime: {e}")
            finally:
                self.realtime_thread = None

        self.activo = False

        logging.info("Monitor de entradas detenido")
    
    def procesar_nueva_entrada(self, entrada_data):
        """Procesar nueva entrada detectada por realtime"""
        try:
            if not self.activo:
                # No procesar si el monitor ya se detuvo
                return
                
            entrada_id = entrada_data.get('id_entrada')
            id_miembro = entrada_data.get('id_miembro')

            logging.info(f"[ENTRADA] Procesando entrada ID: {entrada_id}, Miembro: {id_miembro}")

            # Consultar datos completos desde Supabase (entrada + datos del miembro)
            if self.supabase_service and self.supabase_service.is_connected:
                try:
                    # Consultar entrada con datos del miembro
                    response = self.supabase_service.client.table('registro_entradas')\
                        .select('*, miembros(*)')\
                        .eq('id_entrada', entrada_id)\
                        .single()\
                        .execute()

                    if response.data:
                        entrada = response.data
                        
                        # Construir datos completos usando método centralizado
                        entrada_completa = self._build_entrada_data(entrada, include_foto=True)

                        # Emitir señal con los datos completos
                        nombre_completo = f"{entrada_completa['nombres']} {entrada_completa['apellido_paterno']}"
                        logging.info(f"✅ Nueva entrada procesada - ID: {entrada_id}, Miembro: {nombre_completo}")
                        self.nueva_entrada_detectada.emit(entrada_completa)
                    else:
                        logging.warning(f"No se encontraron datos para entrada ID: {entrada_id}")

                except Exception as e:
                    logging.error(f"Error consultando datos completos desde Supabase: {e}")
                    # Si falla la consulta, emitir los datos básicos que tenemos
                    self.nueva_entrada_detectada.emit(entrada_data)
            else:
                # Si no hay Supabase, emitir los datos básicos
                logging.warning("Supabase no disponible, emitiendo datos básicos de entrada")
                self.nueva_entrada_detectada.emit(entrada_data)

        except Exception as e:
            logging.error(f"[ERROR] Error procesando nueva entrada: {e}")
    
    def reiniciar(self):
        """Reiniciar el monitor"""
        was_active = self.activo

        if was_active:
            self.detener()
            # Pequeña pausa para asegurar cierre limpio
            QThread.msleep(500)
            self.iniciar()

        logging.info("Monitor de entradas reiniciado")
