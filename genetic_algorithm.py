# genetic_algorithm.py
import random
import math
from typing import List, Tuple, Set
from config import config
from models import Individuo, Observacion, Telescopio, CondicionesAmbientales, VentanaObservacion
from utils import BarraProgreso

barra = BarraProgreso()

class AlgoritmoGenetico:
    def __init__(self):
        self.historial_convergencia = []
        self.historial_promedio = []

    def optimizar_top_n(self, observaciones: List[Observacion], telescopio: Telescopio,
                        objeto: str, condiciones: CondicionesAmbientales,
                        paso_minutos: int, n: int = 3) -> List[VentanaObservacion]:
        if len(observaciones) < 3:
            raise ValueError(f"Solo hay {len(observaciones)} observaciones. Se necesitan al menos 3.")
        max_idx = max(0, len(observaciones) - 3)
        dur_max = max(3, min(len(observaciones), 24))
        aumentos = telescopio.aumentos_disponibles or [50,100,150,200]
        factor_amb = condiciones.factor_calidad()

        print(f"\n  ═══════════════════════════════════════════════════════")
        print(f"  ALGORITMO GENÉTICO — Parámetros")
        print(f"  ═══════════════════════════════════════════════════════")
        print(f"  Generaciones     : {config.generaciones}")
        print(f"  Población        : {config.poblacion_size} individuos")
        print(f"  Tasa de cruce    : {config.tasa_cruce*100:.0f}%")
        print(f"  Tasa de mutación : {config.tasa_mutacion*100:.0f}%")
        print(f"  Elitismo         : {config.elitismo} individuos")
        print(f"  Selección        : torneo (k={config.tamano_torneo})")
        print(f"  Observaciones    : {len(observaciones)} (paso {paso_minutos} min)")
        print(f"  Factor ambiental : {factor_amb:.3f}")
        print()

        print("  🧬 [1] Generando población inicial (aleatoria)...")
        poblacion = self._crear_poblacion(max_idx, dur_max, aumentos)

        print("  📊 [2] Evaluando aptitud inicial...")
        for i, ind in enumerate(poblacion):
            barra.mostrar(i+1, len(poblacion), 35, "     Evaluando")
            ind.fitness = self._evaluar(ind, observaciones, telescopio, objeto, factor_amb, dur_max)
        barra.finalizar()

        self.historial_convergencia = []
        self.historial_promedio = []

        print(f"\n  🔄 [3] Selección → [4] Cruce → [5] Mutación → [6] Reemplazo")
        print(f"  ⏹️  [7] Criterio de parada: {config.generaciones} generaciones\n")

        for gen in range(config.generaciones):
            barra.mostrar(gen+1, config.generaciones, 45, f"     Gen {gen+1:3d}/{config.generaciones}")
            poblacion.sort(key=lambda x: x.fitness, reverse=True)
            mejor_gen = poblacion[0].fitness
            promedio_gen = sum(i.fitness for i in poblacion)/len(poblacion)
            self.historial_convergencia.append(mejor_gen)
            self.historial_promedio.append(promedio_gen)

            nueva_pob = [ind.copia() for ind in poblacion[:config.elitismo]]
            while len(nueva_pob) < config.poblacion_size:
                padre1 = self._seleccionar_torneo(poblacion)
                padre2 = self._seleccionar_torneo(poblacion)
                if random.random() < config.tasa_cruce:
                    hijo1, hijo2 = self._cruzar(padre1, padre2, max_idx, dur_max, aumentos)
                else:
                    hijo1, hijo2 = padre1.copia(), padre2.copia()
                    hijo1.fitness = hijo2.fitness = 0.0
                hijo1 = self._mutar(hijo1, max_idx, dur_max, aumentos)
                hijo2 = self._mutar(hijo2, max_idx, dur_max, aumentos)
                hijo1.fitness = self._evaluar(hijo1, observaciones, telescopio, objeto, factor_amb, dur_max)
                hijo2.fitness = self._evaluar(hijo2, observaciones, telescopio, objeto, factor_amb, dur_max)
                nueva_pob.append(hijo1)
                if len(nueva_pob) < config.poblacion_size:
                    nueva_pob.append(hijo2)
            poblacion = nueva_pob

        barra.finalizar()
        poblacion.sort(key=lambda x: x.fitness, reverse=True)
        print(f"\n  ✅ Parada: {config.generaciones} generaciones completadas")
        print(f"  📈 Mejor fitness    : {poblacion[0].fitness*100:.1f}%")
        print(f"  📊 Promedio final   : {self.historial_promedio[-1]*100:.1f}%")
        print(f"  📉 Fitness inicial  : {self.historial_convergencia[0]*100:.1f}%")
        mejora = (self.historial_convergencia[-1] - self.historial_convergencia[0])*100
        print(f"  📈 Mejora total     : +{mejora:.1f}%")

        return self._seleccionar_ventanas_diversas(poblacion, observaciones, objeto, paso_minutos, n)

    def _crear_poblacion(self, max_idx: int, dur_max: int, aumentos: List[int]) -> List[Individuo]:
        poblacion = []
        for _ in range(config.poblacion_size):
            idx = random.randint(0, max_idx)
            dur = random.randint(1, dur_max)
            if idx + dur > max_idx + dur_max:
                dur = max(1, max_idx - idx + 1)
            altitud = random.uniform(10.0, 85.0)
            azimut = random.uniform(0.0, 360.0)
            aumento = random.choice(aumentos)
            poblacion.append(Individuo(idx, dur, altitud, azimut, aumento))
        return poblacion

    def _evaluar(self, ind: Individuo, observaciones: List[Observacion],
                 telescopio: Telescopio, objeto: str, factor_amb: float, dur_max: int) -> float:
        fin = ind.idx_inicio + ind.duracion_pasos
        if fin > len(observaciones) or ind.duracion_pasos < 1:
            return 0.0
        ventana = observaciones[ind.idx_inicio:fin]
        if not ventana:
            return 0.0

        # 1. Penalización inmediata si alguna observación tiene elevación <= 0
        if any(o.elevacion <= 0 for o in ventana):
            return 0.0

        # 2. Elevación promedio
        elev_prom = sum(o.elevacion for o in ventana) / len(ventana)
        if elev_prom < config.elevacion_minima:
            return 0.0
        elev_norm = min(1.0, elev_prom / 90.0)

        # 3. Brillo (diferente para Luna)
        if objeto == 'luna':
            # Para la Luna, el brillo es siempre muy alto, pero penalizamos si la fase es muy baja (iluminación < 20%)
            ilum_prom = sum(o.iluminacion for o in ventana) / len(ventana)
            brillo_norm = max(0.0, min(1.0, ilum_prom / 100.0))
        else:
            # Planetas: usamos magnitud
            mag_min, mag_max = config.rangos_magnitud.get(objeto, (-3.0, 6.0))
            rango = mag_max - mag_min
            if rango <= 0:
                brillo_norm = 0.5
            else:
                mag_prom = sum(o.magnitud for o in ventana) / len(ventana)
                # Si la magnitud está fuera de rango, penalizar fuertemente
                if mag_prom < mag_min or mag_prom > mag_max:
                    brillo_norm = 0.1
                else:
                    brillo_norm = max(0.0, min(1.0, (mag_max - mag_prom) / rango))

        # 4. Duración
        duracion_norm = min(1.0, ind.duracion_pasos / dur_max)

        # 5. Telescopio
        tel_quality = telescopio.calidad_para_aumento(ind.aumento, objeto)

        # 6. Orientación (respecto al momento de máxima calidad)
        optimo = max(ventana, key=lambda o: o.calidad_base_para(objeto))
        diff_alt = abs(optimo.elevacion - ind.altitud)
        diff_azi = min(abs(optimo.azimut - ind.azimut), 360 - abs(optimo.azimut - ind.azimut))
        ori_alt = max(0.0, 1.0 - diff_alt / 90.0)
        ori_azi = max(0.0, 1.0 - diff_azi / 180.0)
        orientacion = (ori_alt + ori_azi) / 2.0

        # 7. Tendencia de elevación (evitar que el objeto se esté ocultando)
        if len(ventana) >= 3:
            elev_inicio = ventana[0].elevacion
            elev_final = ventana[-1].elevacion
            tendencia = (elev_final - elev_inicio) / max(1.0, abs(elev_inicio))
            # Penalizar si la tendencia es negativa y la elevación final es baja
            penal_tend = 1.0
            if tendencia < -0.1 and elev_final < 30:
                penal_tend = max(0.2, 1.0 + tendencia)  # tendencia -0.5 -> 0.5
            else:
                penal_tend = 1.0
        else:
            penal_tend = 1.0

        # Pesos adaptados según objeto
        if objeto == 'luna':
            w_elev = 0.40
            w_brillo = 0.10
            w_duracion = 0.10
            w_telescopio = 0.20
            w_orientacion = 0.10
            w_tendencia = 0.10
        else:
            w_elev = 0.35
            w_brillo = 0.15
            w_duracion = 0.10
            w_telescopio = 0.20
            w_orientacion = 0.10
            w_tendencia = 0.10

        fitness = (w_elev * elev_norm +
                   w_brillo * brillo_norm +
                   w_duracion * duracion_norm +
                   w_telescopio * tel_quality +
                   w_orientacion * orientacion) * penal_tend

        fitness *= factor_amb
        # Penalización extra si la elevación máxima es baja
        elev_max = max(o.elevacion for o in ventana)
        if elev_max < 20:
            fitness *= 0.5
        elif elev_max < 30:
            fitness *= 0.75

        return max(0.0, min(1.0, fitness))

    def _seleccionar_torneo(self, poblacion: List[Individuo]) -> Individuo:
        k = min(config.tamano_torneo, len(poblacion))
        candidatos = random.sample(poblacion, k)
        return max(candidatos, key=lambda x: x.fitness)

    def _cruzar(self, p1: Individuo, p2: Individuo, max_idx: int, dur_max: int, aumentos: List[int]) -> Tuple[Individuo, Individuo]:
        alpha = random.random()
        beta = 1.0 - alpha
        idx1 = int(round(alpha * p1.idx_inicio + beta * p2.idx_inicio))
        idx2 = int(round(beta * p1.idx_inicio + alpha * p2.idx_inicio))
        dur1 = int(round(alpha * p1.duracion_pasos + beta * p2.duracion_pasos))
        dur2 = int(round(beta * p1.duracion_pasos + alpha * p2.duracion_pasos))
        alt1 = alpha * p1.altitud + beta * p2.altitud
        alt2 = beta * p1.altitud + alpha * p2.altitud
        azi1 = alpha * p1.azimut + beta * p2.azimut
        azi2 = beta * p1.azimut + alpha * p2.azimut
        aum1 = p2.aumento
        aum2 = p1.aumento

        def clamp(idx, dur):
            idx = max(0, min(max_idx, idx))
            dur = max(1, min(dur_max, dur))
            if idx + dur > max_idx + dur_max:
                dur = max(1, max_idx - idx + 1)
            return idx, dur

        idx1, dur1 = clamp(idx1, dur1)
        idx2, dur2 = clamp(idx2, dur2)
        alt1 = max(10.0, min(85.0, alt1))
        alt2 = max(10.0, min(85.0, alt2))
        azi1 = azi1 % 360
        azi2 = azi2 % 360
        return (Individuo(idx1, dur1, alt1, azi1, aum1),
                Individuo(idx2, dur2, alt2, azi2, aum2))

    def _mutar(self, ind: Individuo, max_idx: int, dur_max: int, aumentos: List[int]) -> Individuo:
        m = ind.copia()
        if random.random() < config.tasa_mutacion:
            delta = random.randint(-max(1, max_idx//5), max(1, max_idx//5))
            m.idx_inicio = max(0, min(max_idx, m.idx_inicio + delta))
        if random.random() < config.tasa_mutacion:
            m.duracion_pasos = max(1, min(dur_max, m.duracion_pasos + random.randint(-3,3)))
            if m.idx_inicio + m.duracion_pasos > max_idx + dur_max:
                m.duracion_pasos = max(1, max_idx - m.idx_inicio + 1)
        if random.random() < config.tasa_mutacion:
            m.altitud = max(10.0, min(85.0, m.altitud + random.gauss(0, 10.0)))
        if random.random() < config.tasa_mutacion:
            m.azimut = (m.azimut + random.gauss(0, 20.0)) % 360
        if random.random() < config.tasa_mutacion and len(aumentos) > 1:
            otros = [a for a in aumentos if a != m.aumento]
            if otros:
                m.aumento = random.choice(otros)
        return m

    def _construir_ventana(self, ind: Individuo, observaciones: List[Observacion], objeto: str) -> VentanaObservacion:
        fin = min(ind.idx_inicio + ind.duracion_pasos, len(observaciones))
        obs = observaciones[ind.idx_inicio:fin] or [observaciones[0]]
        return VentanaObservacion(
            inicio=obs[0].timestamp,
            fin=obs[-1].timestamp,
            observaciones=obs,
            calidad=ind.fitness,
            aumento_recomendado=ind.aumento,
            objeto=objeto
        )

    def _seleccionar_ventanas_diversas(self, poblacion: List[Individuo], observaciones: List[Observacion],
                                       objeto: str, paso_minutos: int, n: int) -> List[VentanaObservacion]:
        sep_seg = max(paso_minutos * 3, 30) * 60
        seleccionadas = []
        vistas = set()
        for ind in poblacion:
            if len(seleccionadas) >= n: break
            v = self._construir_ventana(ind, observaciones, objeto)
            cerca = any(abs((v.inicio - p.inicio).total_seconds()) < sep_seg for p in seleccionadas)
            sig = (v.inicio, v.fin)
            if not cerca and sig not in vistas:
                seleccionadas.append(v)
                vistas.add(sig)
        for ind in poblacion:
            if len(seleccionadas) >= n: break
            v = self._construir_ventana(ind, observaciones, objeto)
            sig = (v.inicio, v.fin)
            if sig not in vistas:
                seleccionadas.append(v)
                vistas.add(sig)
        return seleccionadas[:n]