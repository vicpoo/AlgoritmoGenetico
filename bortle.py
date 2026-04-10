# bortle.py
import json
import math
from pathlib import Path
from typing import Tuple


class EscalaBortle:
    def __init__(self, archivo_json: str = "bortle_locations.json"):
        self.ubicaciones = []
        self._cargar(archivo_json)

    def _cargar(self, archivo: str):
        try:
            ruta = Path(archivo)
            if not ruta.exists():
                return
            with open(ruta, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for item in data.get('bortle_locations', []):
                self.ubicaciones.append({
                    'nombre': item.get('nombre', ''),
                    'latitud': item.get('latitud', 0),
                    'longitud': item.get('longitud', 0),
                    'bortle_class': item.get('bortle_class', 4)
                })
        except Exception:
            pass

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2) -> float:
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        return R * 2 * math.asin(math.sqrt(max(0.0, a)))

    def get_ciudad_cercana(self, lat: float, lon: float) -> Tuple[str, float, float]:
        if not self.ubicaciones:
            return ("Desconocido", 0.0, 4)
        mejor = min(self.ubicaciones,
                    key=lambda u: self._haversine(lat, lon, u['latitud'], u['longitud']))
        dist = self._haversine(lat, lon, mejor['latitud'], mejor['longitud'])
        return (mejor['nombre'], dist, mejor['bortle_class'])

    def get_calidad_cielo(self, lat: float, lon: float) -> float:
        ciudad, dist, bortle = self.get_ciudad_cercana(lat, lon)
        calidad = 1.0 - ((bortle - 1) / 8.0)
        print(
            f"  📍 Ciudad más cercana: {ciudad} (a {dist:.1f} km, Bortle {bortle})")
        return max(0.0, min(1.0, calidad))
