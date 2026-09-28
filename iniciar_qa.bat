@echo off
REM ===========================================================================
REM  Arranca el POS contra la base de QA local (Supabase en Docker).
REM
REM  NO toca el archivo .env: define las variables en el entorno del proceso,
REM  y load_dotenv() no pisa lo que ya viene definido. Al cerrar esta ventana
REM  no queda nada cambiado.
REM
REM  Requisitos: Docker corriendo y `supabase start` ya ejecutado.
REM  Comprobar con:  supabase status
REM ===========================================================================

title POS HTF - BASE DE QA (NO es produccion)

echo.
echo  ===========================================================
echo    POS HTF  --  CONECTADO A LA BASE DE QA
echo    Los cambios que hagas aqui NO afectan al gimnasio.
echo  ===========================================================
echo.

REM --- Apuntar a la API REST del Supabase local ---
set "SUPABASE_URL=http://127.0.0.1:54321"

REM Llave service_role del stack local de Supabase. Es una llave de desarrollo
REM publica y fija, identica en cualquier instalacion: no es un secreto.
set "SUPABASE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"
set "SUPABASE_KEY=%SUPABASE_ROLE_KEY%"

REM --- Servidor del torniquete: solo local, sin exponer a la red ---
set "TORNIQUETE_API_TOKEN=token-de-pruebas-qa"
set "TORNIQUETE_LISTEN_HOST=127.0.0.1"

cd /d "%~dp0"
python main.py

echo.
echo  El POS se cerro. Pulsa una tecla para salir.
pause >nul
