# utils.py
import math
import re
from datetime import datetime

_MESES = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
    'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
    'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
}

class BarraProgreso:
    def __init__(self):
        self.ultimo_ancho = 0

    def mostrar(self, actual: int, total: int, ancho: int = 40,
                prefijo: str = "  Progreso", sufijo: str = ""):
        if total == 0:
            return
        porcentaje = actual / total
        barra_len = int(ancho * porcentaje)
        barra = '█' * barra_len + '░' * (ancho - barra_len)
        texto = f"\r{prefijo}: [{barra}] {porcentaje*100:.1f}% ({actual}/{total}){sufijo}"
        if len(texto) < self.ultimo_ancho:
            texto += ' ' * (self.ultimo_ancho - len(texto))
        self.ultimo_ancho = len(texto)
        print(texto, end='', flush=True)

    def finalizar(self):
        print()

def haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(max(0.0, a)))

def parse_fecha_horizons(date_str: str, time_str: str) -> datetime:
    """Parsea '2026-Apr-09' + '20:22' → datetime UTC."""
    year = int(date_str[0:4])
    mes  = _MESES.get(date_str[5:8], 0)
    day  = int(date_str[9:11])
    hour = int(time_str[0:2])
    minu = int(time_str[3:5])
    if mes == 0:
        raise ValueError(f"Mes no reconocido en {date_str}")
    return datetime(year, mes, day, hour, minu)

def safe_float(val: str) -> float:
    """Convierte a float; devuelve 0.0 para 'n.a.' y similares."""
    v = val.strip()
    if v in ('n.a.', 'N/A', '', 'n/a', '*'):
        return 0.0
    try:
        return float(v)
    except ValueError:
        return 0.0