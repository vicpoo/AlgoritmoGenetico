# models.py
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from config import config

@dataclass
class Observacion:
    timestamp: datetime
    azimut: float
    elevacion: float
    magnitud: float
    brillo_superficial: float = 0.0
    iluminacion: float = 0.0
    angulo_diametro: float = 0.0
    distancia_au: float = 0.0

    @property
    def visible(self) -> bool:
        return self.elevacion > 0

    def es_valida(self, objeto: str) -> bool:
        """Verifica que los valores estén dentro de rangos físicos aceptables."""
        if not (-90.0 <= self.elevacion <= 90.0):
            return False
        if not (0.0 <= self.azimut < 360.0):
            return False
        mag_min, mag_max = config.rangos_magnitud.get(objeto, (-30, 30))
        if not (mag_min <= self.magnitud <= mag_max):
            return False
        if self.iluminacion < 0 or self.iluminacion > 100:
            return False
        if self.distancia_au < 0:
            return False
        return True

    def calidad_base_para(self, objeto: str) -> float:
        """
        Calidad instantánea sin considerar ventana completa.
        Para la Luna se usa un criterio especial (importa más la fase que la magnitud).
        """
        if objeto == 'luna':
            # La Luna es siempre muy brillante, pero interesa la fase:
            # 0% = nueva (invisible), 100% = llena (muy brillante)
            fase_norm = self.iluminacion / 100.0
            elev_norm = min(1.0, self.elevacion / 90.0)
            return elev_norm * 0.7 + fase_norm * 0.3
        else:
            elev_norm = min(1.0, self.elevacion / 90.0)
            mag_min, mag_max = config.rangos_magnitud.get(objeto, (-3.0, 6.0))
            rango = mag_max - mag_min
            if rango <= 0:
                brillo_norm = 0.5
            else:
                brillo_norm = max(0.0, min(1.0, (mag_max - self.magnitud) / rango))
            return elev_norm * 0.6 + brillo_norm * 0.4

@dataclass
class Telescopio:
    tipo: str
    apertura_mm: float
    aumentos_disponibles: List[int]

    def calidad_para_aumento(self, aumento: int, objeto: str) -> float:
        min_a, max_a = config.rangos_aumento.get(objeto.lower(), (50, 200))
        if min_a <= aumento <= max_a:
            return 1.0
        elif aumento < min_a:
            return 0.5 * (aumento / min_a)
        else:
            return 0.5 * (max_a / aumento)

@dataclass
class CondicionesAmbientales:
    estado_cielo: str
    luna_llena: bool
    seeing: str
    calidad_cielo_bortle: float = 0.7

    def factor_calidad(self) -> float:
        factor = {'despejado': 1.0, 'parcialmente_nublado': 0.6}.get(self.estado_cielo, 0.2)
        if self.luna_llena:
            factor *= 0.5
        factor *= {'bueno': 1.0, 'regular': 0.7}.get(self.seeing, 0.4)
        factor *= self.calidad_cielo_bortle
        return max(0.05, min(1.0, factor))

@dataclass
class VentanaObservacion:
    inicio: datetime
    fin: datetime
    observaciones: List[Observacion]
    calidad: float
    aumento_recomendado: int
    objeto: str = ""

    @property
    def duracion_minutos(self) -> float:
        if not self.observaciones:
            return 0.0
        return (self.fin - self.inicio).total_seconds() / 60.0

    @property
    def momento_optimo(self) -> Optional[Observacion]:
        if not self.observaciones:
            return None
        return max(self.observaciones,
                   key=lambda x: x.calidad_base_para(self.objeto) if self.objeto else 0.0)

@dataclass
class Individuo:
    idx_inicio: int
    duracion_pasos: int
    altitud: float
    azimut: float
    aumento: int
    fitness: float = 0.0

    def copia(self) -> 'Individuo':
        return Individuo(self.idx_inicio, self.duracion_pasos,
                         self.altitud, self.azimut, self.aumento, self.fitness)