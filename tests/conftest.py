"""Configuración común para la suite de tests.

Añade la raíz del repo a `sys.path` para poder importar los módulos del
proyecto (`summarizer`, `lyric_aligner`, ...) sin instalarlo como paquete.
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
