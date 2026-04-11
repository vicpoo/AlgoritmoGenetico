# models.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from enum import Enum
from config import config


class FaseLunar(Enum):
    NUEVA              = ("🌑", "Luna nueva",          0.00, 0.00)
    CRECIENTE_INICIAL  = ("🌒", "Creciente inicial",   0.20, 0.15)
    CUARTO_CRECIENTE   = ("🌓", "Cuarto creciente",    0.50, 0.50)
    GIBOSA_CRECIENTE   = ("🌔", "Gibosa creciente",    0.80, 0.80)
    LLENA              = ("🌕", "Luna llena",           1.00, 1.00)
    GIBOSA_MENGUANTE   = ("🌖", "Gibosa menguante",    0.80, 0.80)
    CUARTO_MENGUANTE   = ("🌗", "Cuarto menguante",    0.50, 0.50)
    MENGUANTE_INICIAL  = ("🌘", "Menguante inicial",   0.20, 0.15)

    def __init__(self, emoji: str, nombre: str,
                 factor_luz: float, iluminacion_aprox: float):
        self.emoji = emoji
        self.nombre = nombre
        self.factor_luz = factor_luz
        self.iluminacion_aprox = iluminacion_aprox

    @staticmethod
    def desde_iluminacion(iluminacion: float) -> 'FaseLunar':
        if iluminacion < 5:
            return FaseLunar.NUEVA
        elif iluminacion < 25:
            return FaseLunar.CRECIENTE_INICIAL
        elif iluminacion < 45:
            return FaseLunar.CUARTO_CRECIENTE
        elif iluminacion < 75:
            return FaseLunar.GIBOSA_CRECIENTE
        else:
            return FaseLunar.LLENA

    @staticmethod
    def desde_nombre(nombre: str) -> 'FaseLunar':
        mapa = {
            'nueva':              FaseLunar.NUEVA,
            'creciente_inicial':  FaseLunar.CRECIENTE_INICIAL,
            'cuarto_creciente':   FaseLunar.CUARTO_CRECIENTE,
            'gibosa_creciente':   FaseLunar.GIBOSA_CRECIENTE,
            'llena':              FaseLunar.LLENA,
            'gibosa_menguante':   FaseLunar.GIBOSA_MENGUANTE,
            'cuarto_menguante':   FaseLunar.CUARTO_MENGUANTE,
            'menguante_inicial':  FaseLunar.MENGUANTE_INICIAL,
        }
        return mapa.get(nombre, FaseLunar.NUEVA)

    @property
    def impacto_lunar(self) -> float:
        return self.factor_luz

    def __str__(self) -> str:
        return f"{self.emoji} {self.nombre}"


@dataclass
class Observacion:
    timestamp:        datetime
    azimut:           float
    elevacion:        float
    magnitud:         float
    brillo_superficial: float = 0.0
    # iluminacion: para planetas/luna = fracción iluminada del disco (0–100%)
    # NO es la iluminación de la Luna en el cielo
    iluminacion:      float = 0.0
    angulo_diametro:  float = 0.0
    # distancia_au: distancia al Sol (AU)
    distancia_au:     float = 0.0
    # distancia_tierra_au: distancia a la Tierra (AU) — campo separado
    distancia_tierra_au: float = 0.0
    elevacion_solar:  float = 0.0

    @property
    def visible(self) -> bool:
        return self.elevacion > 0

    @property
    def fase_objeto(self) -> float:
        """Fracción iluminada del disco del objeto (0–1). NO es la fase lunar del cielo."""
        return self.iluminacion / 100.0

    def calidad_base_para(self, objeto: str) -> float:
        """
        Calidad base de esta observación para encontrar el momento óptimo.
        Usa masa de aire real y no mezcla iluminación lunar con fase del objeto.
        """
        try:
            import math

            if objeto == 'luna':
                # Para la Luna: maximizar elevación y fase iluminada
                elev_ratio = max(0.0, min(1.0, self.elevacion / 90.0))
                elev_norm = elev_ratio ** 1.5
                fase_norm = 0.3 + (self.iluminacion / 100.0) * 0.7
                return elev_norm * 0.6 + fase_norm * 0.4
            else:
                # Para planetas: maximizar elevación (masa de aire) y brillo
                elev_ratio = max(0.0, min(1.0, self.elevacion / 90.0))
                elev_norm = elev_ratio ** 1.5

                mag_min, mag_max = config.rangos_magnitud.get(objeto, (-3.0, 6.0))
                rango = mag_max - mag_min
                if rango > 0:
                    brillo_norm = max(0.0, min(1.0, (mag_max - self.magnitud) / rango))
                    brillo_norm = brillo_norm ** 0.8
                else:
                    brillo_norm = 0.5

                return elev_norm * 0.70 + brillo_norm * 0.30

        except Exception:
            return 0.0


@dataclass
class Telescopio:
    tipo:               str
    apertura_mm:        float
    aumentos_disponibles: List[int]

    def calidad_para_aumento(self, aumento: int, objeto: str) -> float:
        aumento_max_util = self.apertura_mm * 2
        if aumento > aumento_max_util * 1.5:
            return 0.1
        elif aumento > aumento_max_util:
            return 0.4
        elif aumento < self.apertura_mm * 0.5:
            return 0.5
        else:
            return 1.0


@dataclass
class CondicionesAmbientales:
    estado_cielo:       str
    fase_lunar_nombre:  str
    seeing:             str
    calidad_cielo_bortle: float = 0.7

    @property
    def fase_lunar(self) -> FaseLunar:
        return FaseLunar.desde_nombre(self.fase_lunar_nombre)

    # ── Métodos separados para evitar mezcla de contexto ───────────────

    def factor_calidad_sin_lunar(self) -> float:
        """
        Factor ambiental SIN penalización lunar.
        Usado en el GA para que la Luna se aplique solo donde corresponde.
        """
        factor = {'despejado': 1.0, 'parcialmente_nublado': 0.6}.get(
            self.estado_cielo, 0.2)
        seeing_map = {'bueno': 1.0, 'regular': 0.7, 'malo': 0.4}
        factor *= seeing_map.get(self.seeing, 0.5)
        factor *= self.calidad_cielo_bortle
        return max(0.05, min(1.0, factor))

    def factor_lunar_para_planeta(self, peso: float = 0.55) -> float:
        """
        Factor de contaminación lunar al observar un PLANETA.
        Luna llena (factor_luz=1.0) → penalización máxima.
        Luna nueva (factor_luz=0.0) → sin penalización.
        """
        fase = self.fase_lunar
        return max(0.20, 1.0 - fase.factor_luz * peso)

    def factor_lunar_para_luna(self) -> float:
        """
        Factor para observar LA LUNA.
        Luna llena → mejor (factor = 1.0).
        Luna nueva → peor (factor = 0.30).
        """
        fase = self.fase_lunar
        return max(0.30, 0.30 + fase.factor_luz * 0.70)

    def factor_calidad(self) -> float:
        """
        Factor global legacy (cielo + seeing + bortle + lunar).
        Mantenido por compatibilidad, pero el GA ahora usa factor_calidad_sin_lunar().
        """
        factor = self.factor_calidad_sin_lunar()
        penal_lunar = self.factor_lunar_para_planeta(0.5)
        factor *= penal_lunar
        return max(0.05, min(1.0, factor))

    def descripcion_fase_lunar(self) -> str:
        """Descripción legible de la fase lunar con emoji."""
        return str(self.fase_lunar)


@dataclass
class VentanaObservacion:
    inicio:              datetime
    fin:                 datetime
    observaciones:       List[Observacion]
    calidad:             float
    aumento_recomendado: int
    objeto:              str = ""

    @property
    def duracion_minutos(self) -> float:
        if not self.observaciones:
            return 0.0
        return (self.fin - self.inicio).total_seconds() / 60.0

    @property
    def momento_optimo(self) -> Optional[Observacion]:
        if not self.observaciones:
            return None
        mejor = None
        mejor_calidad = -1.0
        for obs in self.observaciones:
            cal = obs.calidad_base_para(self.objeto) if self.objeto else 0.0
            if cal > mejor_calidad:
                mejor_calidad = cal
                mejor = obs
        return mejor


@dataclass
class Individuo:
    idx_inicio:      int
    duracion_pasos:  int
    altitud:         float
    azimut:          float
    aumento:         int
    fitness:         float = 0.0

    def copia(self) -> 'Individuo':
        return Individuo(
            self.idx_inicio, self.duracion_pasos,
            self.altitud, self.azimut,
            self.aumento, self.fitness
        )