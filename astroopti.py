# astroopti_core.py
import time
from datetime import datetime
from typing import List, Dict

from config import config
from models import Telescopio, CondicionesAmbientales, FaseLunar
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

        # Fase lunar del cielo (de las condiciones del usuario, no del objeto)
        fase_lunar_cielo_str = condiciones.descripcion_fase_lunar()

        resultados = []
        for i, v in enumerate(ventanas):
            pct = v.calidad * 100

            if pct >= config.umbral_excelente * 100:
                cat = "EXCELENTE"
            elif pct >= config.umbral_buena * 100:
                cat = "BUENA"
            elif pct >= config.umbral_aceptable * 100:
                cat = "ACEPTABLE"
            else:
                cat = "MALA"

            mo = v.momento_optimo
            momento_data = None
            if mo:
                # distancia_tierra_au: primero intenta el campo dedicado,
                # luego fallback a distancia_au si el reader no lo separa aún
                dist_tierra = mo.distancia_tierra_au
                if dist_tierra == 0.0:
                    dist_tierra = mo.distancia_au  # fallback

                # Fase del OBJETO (fracción iluminada del disco): solo planetas/luna
                # Esto NO es la fase lunar del cielo
                fase_objeto_pct = round(mo.iluminacion, 1)  # % del disco iluminado

                momento_data = {
                    'timestamp':        mo.timestamp,
                    'elevacion':        mo.elevacion,
                    'azimut':           mo.azimut,
                    'magnitud':         mo.magnitud,
                    # Fase del objeto (disco iluminado), no iluminación lunar
                    'fase_objeto_pct':  fase_objeto_pct,
                    'angulo_diametro':  mo.angulo_diametro,
                    'distancia_sol_au': mo.distancia_au,
                    'distancia_tierra_au': dist_tierra,
                    # Fase lunar del CIELO (condición ambiental, independiente del objeto)
                    'fase_lunar_cielo': fase_lunar_cielo_str,
                }

            resultados.append({
                'numero':         i + 1,
                'calidad_pct':    pct,
                'categoria':      cat,
                'ventana':        v,
                'momento_optimo': momento_data,
                'aumento':        v.aumento_recomendado,
                'objeto':         objeto,
                'paso_minutos':   paso_real,
                'offset_utc':     offset_utc,
                # Condición lunar del cielo para mostrar en UI
                'fase_lunar_cielo': fase_lunar_cielo_str,
            })

        return resultados