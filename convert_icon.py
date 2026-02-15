"""
Convertir PNG a ICO para el icono de la aplicación
"""
from PIL import Image
import os

# Rutas - usando directorio del script
script_dir = os.path.dirname(os.path.abspath(__file__))
png_path = os.path.join(script_dir, 'assets', 'pos_icono.png')
ico_path = os.path.join(script_dir, 'assets', 'pos_icono.ico')

try:
    # Abrir imagen PNG
    img = Image.open(png_path)
    
    # Convertir a ICO con múltiples tamaños
    img.save(ico_path, format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    
    print(f"✓ Icono convertido exitosamente: {ico_path}")
    
except Exception as e:
    print(f"✗ Error convirtiendo icono: {e}")
