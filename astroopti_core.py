# astroopti_core.py
import time
from datetime import datetime
from typing import List, Dict

from config import config
from models import Telescopio, CondicionesAmbientales
from horizons_reader import HorizonsReader
from genetic_algorithm import AlgoritmoGenetico
from bortle import EscalaBortle

class AstroOptiCore:
    def __init__(self):
        self.algoritmo = AlgoritmoGenetico()
        self.bortle    = EscalaBortle()

    def optimizar(self, latitud: float, longitud: float, fecha: datetime,
                  objeto: str, telescopio: Telescopio,
                  condiciones: CondicionesAmbientales,
                  offset_utc: int = -6,
                  debug_filas: int = 0) -> List[Dict]:

        print("\n" + "=" * 60)
        print("🚀 OPTIMIZANDO...")
        print("=" * 60)
        print(f"\n  🕐 Zona horaria: UTC{offset_utc:+d}")

        condiciones.calidad_cielo_bortle = self.bortle.get_calidad_cielo(latitud, longitud)

        print(f"\n📡 Cargando datos de {objeto.upper()} "
              f"para {fecha.strftime('%d/%m/%Y')} (UTC)...")
        t0 = time.time()
        reader        = HorizonsReader(objeto, latitud, longitud, fecha)
        observaciones = reader.cargar_observaciones(debug_filas=debug_filas)
        paso_real     = reader.paso_minutos
        print(f"  ⏱️  Carga en {time.time()-t0:.1f}s")

        if not observaciones:
            raise ValueError(
                f"No se encontraron observaciones para {objeto} "
                f"en o cerca de {fecha.strftime('%d/%m/%Y')}."
            )

        t1 = time.time()
        ventanas = self.algoritmo.optimizar_top_n(
            observaciones, telescopio, objeto, condiciones, paso_real, n=3
        )
        print(f"  ⏱️  Optimización en {time.time()-t1:.1f}s")

        resultados = []
        for i, v in enumerate(ventanas):
            pct = v.calidad * 100
            if   pct >= config.umbral_excelente * 100: cat = "EXCELENTE"
            elif pct >= config.umbral_buena     * 100: cat = "BUENA"
            elif pct >= config.umbral_aceptable * 100: cat = "ACEPTABLE"
            else:                                       cat = "MALA"

            resultados.append({
                'numero': i + 1, 'calidad_pct': pct, 'categoria': cat,
                'ventana': v, 'momento_optimo': v.momento_optimo,
                'aumento': v.aumento_recomendado,
                'objeto': objeto, 'paso_minutos': paso_real,
                'offset_utc': offset_utc,
            })
        return resultados