# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['..\\main.py'],
    pathex=[],
    binaries=[],
    datas=[('c:\\Users\\ferch\\Desktop\\HTF_gimnasio\\POS_HTF\\database', 'database'), ('c:\\Users\\ferch\\Desktop\\HTF_gimnasio\\POS_HTF\\ui', 'ui'), ('c:\\Users\\ferch\\Desktop\\HTF_gimnasio\\POS_HTF\\services', 'services'), ('c:\\Users\\ferch\\Desktop\\HTF_gimnasio\\POS_HTF\\utils', 'utils'), ('c:\\Users\\ferch\\Desktop\\HTF_gimnasio\\POS_HTF\\.env', '.')],
    hiddenimports=['sqlite3', 'PySide6', 'dotenv', 'supabase', 'psycopg2', 'services.printing.escpos_printer', 'services.printing.windows_printer_manager', 'utils.fastapi_server_entradas', 'fastapi', 'uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.loops.asyncio', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.http.h11_impl', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'pydantic', 'pydantic.types', 'pydantic.fields', 'pydantic_core', 'starlette', 'starlette.applications', 'starlette.routing', 'starlette.responses', 'starlette.middleware', 'starlette.middleware.cors', 'anyio', 'anyio._backends', 'anyio._backends._asyncio', 'h11', 'httptools', 'click'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='HTF_Gimnasio_POS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
