# genetic_algorithm.py
import random
import math
from typing import List, Tuple, Set
from config import config
from models import Individuo, Observacion, Telescopio, CondicionesAmbientales, VentanaObservacion
from utils import BarraProgreso
from telescopio_knowledge import TelescopioKnowledge

barra = BarraProgreso()
conocimiento_telescopios = TelescopioKnowledge()


def masa_de_aire(elevacion_deg: float) -> float:
    """
    Calcula la masa de aire usando la fórmula de Pickering (2002).
    Más precisa que 1/sin(z) para ángulos bajos.
    Devuelve un valor entre 1.0 (cenit) y ~40 (horizonte).
    """
    if elevacion_deg <= 0:
        return 40.0
    elev_rad = math.radians(elevacion_deg)
    # Fórmula de Pickering: más precisa que secante simple
    X = 1.0 / math.sin(math.radians(elevacion_deg + 244.0 / (165.0 + 47.0 * elevacion_deg ** 1.1)))
    return max(1.0, min(40.0, X))


def score_masa_aire(elevacion_deg: float) -> float:
    """
    Convierte masa de aire a score 0–1.
    X=1.0 (cenit, 90°) → 1.0
    X=2.0 (~30°)       → 0.70
    X=3.0 (~19°)       → 0.40
    X=5.0 (~12°)       → 0.15
    """
    X = masa_de_aire(elevacion_deg)
    # Decaimiento exponencial: score = exp(-k*(X-1))
    k = 0.45
    return max(0.0, min(1.0, math.exp(-k * (X - 1.0))))


class AlgoritmoGenetico:
    def __init__(self):
        self.historial_convergencia = []
        self.historial_promedio = []
        self.historial_duracion = []
        self.historial_aumento = []

    def optimizar_top_n(self, observaciones: List[Observacion], telescopio: Telescopio,
                        objeto: str, condiciones: CondicionesAmbientales,
                        paso_minutos: int, n: int = 3) -> List[VentanaObservacion]:
        if len(observaciones) < 3:
            raise ValueError(f"Solo hay {len(observaciones)} observaciones. Se necesitan al menos 3.")

        max_idx = max(0, len(observaciones) - 3)
        dur_max = max(3, min(len(observaciones), 24))
        aumentos = telescopio.aumentos_disponibles or [50, 100, 150, 200]
        factor_amb = condiciones.factor_calidad_sin_lunar()  # sin penalización lunar aquí

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
        print(f"  Objeto           : {objeto.upper()}")
        print(f"  Telescopio       : {telescopio.tipo}, {telescopio.apertura_mm}mm")
        print()

        print("  🧬 [1] Generando población inicial (aleatoria)...")
        poblacion = self._crear_poblacion(max_idx, dur_max, aumentos)

        print("  📊 [2] Evaluando aptitud inicial...")
        for i, ind in enumerate(poblacion):
            barra.mostrar(i + 1, len(poblacion), 35, "     Evaluando")
            ind.fitness = self._evaluar(ind, observaciones, telescopio, objeto,
                                        condiciones, factor_amb, dur_max, paso_minutos)
        barra.finalizar()

        self.historial_convergencia = []
        self.historial_promedio = []
        self.historial_duracion = []
        self.historial_aumento = []

        print(f"\n  🔄 [3] Selección → [4] Cruce → [5] Mutación → [6] Reemplazo")
        print(f"  ⏹️  [7] Criterio de parada: {config.generaciones} generaciones\n")

        for gen in range(config.generaciones):
            barra.mostrar(gen + 1, config.generaciones, 45,
                          f"     Gen {gen+1:3d}/{config.generaciones}")
            poblacion.sort(key=lambda x: x.fitness, reverse=True)

            mejor_gen = poblacion[0].fitness
            promedio_gen = sum(i.fitness for i in poblacion) / len(poblacion)
            self.historial_convergencia.append(mejor_gen)
            self.historial_promedio.append(promedio_gen)

            mejor_ind = poblacion[0]
            self.historial_duracion.append(mejor_ind.duracion_pasos * paso_minutos)
            self.historial_aumento.append(mejor_ind.aumento)

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
                hijo1.fitness = self._evaluar(hijo1, observaciones, telescopio, objeto,
                                              condiciones, factor_amb, dur_max, paso_minutos)
                hijo2.fitness = self._evaluar(hijo2, observaciones, telescopio, objeto,
                                              condiciones, factor_amb, dur_max, paso_minutos)
                nueva_pob.append(hijo1)
                if len(nueva_pob) < config.poblacion_size:
                    nueva_pob.append(hijo2)
            poblacion = nueva_pob

        barra.finalizar()
        poblacion.sort(key=lambda x: x.fitness, reverse=True)
        print(f"\n  ✅ Parada: {config.generaciones} generaciones completadas")
        print(f"  📈 Mejor fitness    : {poblacion[0].fitness*100:.1f}%")
        print(f"  📊 Promedio final   : {self.historial_promedio[-1]*100:.1f}%")
        if self.historial_convergencia:
            mejora = (self.historial_convergencia[-1] - self.historial_convergencia[0]) * 100
            print(f"  📈 Mejora total     : +{mejora:.1f}%")

        return self._seleccionar_ventanas_diversas(
            poblacion, observaciones, objeto, paso_minutos, n)

    def _crear_poblacion(self, max_idx: int, dur_max: int,
                         aumentos: List[int]) -> List[Individuo]:
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
                 telescopio: Telescopio, objeto: str,
                 condiciones: CondicionesAmbientales,
                 factor_amb: float, dur_max: int,
                 paso_minutos: int = 15) -> float:
        """
        Fitness con suma ponderada discriminativa.
        Cada componente 0–1, pesos calibrados por relevancia física.
        La iluminación lunar se aplica SOLO si el objeto no es la Luna.
        """
        try:
            fin = ind.idx_inicio + ind.duracion_pasos
            if fin > len(observaciones) or ind.duracion_pasos < 1:
                return 0.0

            ventana = observaciones[ind.idx_inicio:fin]
            if not ventana:
                return 0.0

            # ── HARD CONSTRAINTS (descalificación inmediata) ───────────
            if any(o.elevacion <= 0 for o in ventana):
                return 0.0

            elev_prom = sum(o.elevacion for o in ventana) / len(ventana)
            if elev_prom < config.elevacion_minima:
                return 0.0

            # Oscuridad mínima: no observar con sol sobre el horizonte
            elev_sol_prom = sum(o.elevacion_solar for o in ventana) / len(ventana)
            es_objeto_diurno = objeto in config.objetos_diurnos
            if not es_objeto_diurno and elev_sol_prom > -6.0:
                # Solo se permite hasta crepúsculo civil
                return 0.0

            # ── COMPONENTE 1: MASA DE AIRE (peso 0.30) ─────────────────
            # Usa la fórmula física real, no solo elevación lineal
            aire_scores = [score_masa_aire(o.elevacion) for o in ventana]
            aire_score = sum(aire_scores) / len(aire_scores)

            # ── COMPONENTE 2: OSCURIDAD DEL CIELO (peso 0.20) ──────────
            if es_objeto_diurno:
                oscuridad = 1.0  # Sol y Luna se observan de día
            elif elev_sol_prom > 0:
                oscuridad = 0.0
            elif elev_sol_prom > -6:
                oscuridad = 0.15
            elif elev_sol_prom > -12:
                oscuridad = 0.50
            elif elev_sol_prom > -18:
                oscuridad = 0.80
            else:
                oscuridad = 1.0

            # ── COMPONENTE 3: CONTAMINACIÓN LUNAR (peso 0.20) ──────────
            # CORREGIDO: la iluminación lunar es independiente del objeto
            # Se calcula desde condiciones, no desde o.iluminacion (que es del objeto)
            if objeto == 'luna':
                # Observar la Luna: fase llena es mejor
                factor_lunar = condiciones.factor_lunar_para_luna()
            elif objeto in ('mercurio', 'venus'):
                # Planetas interiores: elongación baja, la Luna importa menos
                factor_lunar = condiciones.factor_lunar_para_planeta(peso=0.35)
            else:
                # Planetas exteriores: Luna llena sí molesta
                factor_lunar = condiciones.factor_lunar_para_planeta(peso=0.55)

            # ── COMPONENTE 4: BRILLO / MAGNITUD (peso 0.12) ────────────
            if objeto == 'luna':
                mag_score = 1.0
            else:
                mag_prom = sum(o.magnitud for o in ventana) / len(ventana)
                mag_min, mag_max = config.rangos_magnitud.get(objeto, (-3.0, 6.0))
                rango = mag_max - mag_min
                if rango > 0:
                    # Más brillante (magnitud más negativa) → score más alto
                    mag_score = max(0.0, min(1.0, (mag_max - mag_prom) / rango))
                    # Curva convexa: objetos brillantes merecen más recompensa
                    mag_score = mag_score ** 0.7
                else:
                    mag_score = 0.5

            # ── COMPONENTE 5: TELESCOPIO + EMPÍRICO (peso 0.12) ────────
            max_aumento_util = telescopio.apertura_mm * 2.0
            aum = ind.aumento
            if aum > max_aumento_util * 1.5:
                tel_score_base = 0.05   # Completamente inútil
            elif aum > max_aumento_util:
                # Sobreuso: penalización progresiva
                exceso = (aum - max_aumento_util) / (max_aumento_util * 0.5)
                tel_score_base = max(0.10, 0.50 - exceso * 0.40)
            elif aum < telescopio.apertura_mm * 0.3:
                tel_score_base = 0.30   # Aumento muy bajo
            else:
                # Rango útil con óptimo en ~apertura_mm
                ratio = aum / max_aumento_util
                tel_score_base = 0.55 + 0.45 * math.sin(math.pi * ratio)

            tel_empirico = conocimiento_telescopios.predecir_calidad(
                objeto, telescopio.apertura_mm, telescopio.tipo, aum)
            tel_score = tel_score_base * 0.55 + tel_empirico * 0.45

            # Penalización de seeing: aumentos altos con mal seeing
            if factor_amb < 0.6 and aum > telescopio.apertura_mm:
                penaliz = 1.0 - (1.0 - factor_amb) * 0.5 * (aum / max_aumento_util)
                tel_score *= max(0.4, penaliz)

            # ── COMPONENTE 6: DURACIÓN (peso 0.10) ─────────────────────
            dur_min = config.duracion_minima_minutos
            dur_max_cfg = config.duracion_maxima_minutos
            dur_min_2 = 20  # Mínimo para contar como sesión real
            dur_opt = 90    # Duración óptima en minutos

            duracion_min = ind.duracion_pasos * paso_minutos
            if duracion_min < dur_min:
                dur_score = duracion_min / dur_min * 0.3
            elif duracion_min < dur_min_2:
                dur_score = 0.3 + 0.4 * (duracion_min - dur_min) / (dur_min_2 - dur_min)
            elif duracion_min <= dur_opt:
                dur_score = 0.7 + 0.3 * (duracion_min - dur_min_2) / (dur_opt - dur_min_2)
            elif duracion_min <= dur_max_cfg:
                # Decrece suavemente después del óptimo
                dur_score = 1.0 - 0.25 * (duracion_min - dur_opt) / (dur_max_cfg - dur_opt)
            else:
                dur_score = max(0.20, 0.75 - (duracion_min - dur_max_cfg) / dur_max_cfg)

            dur_score = max(0.0, min(1.0, dur_score))

            # ── COMPONENTE 7: TENDENCIA DE ELEVACIÓN (peso 0.08) ───────
            if len(ventana) >= 3:
                elev_inicio = ventana[0].elevacion
                elev_final = ventana[-1].elevacion
                elev_max_v = max(o.elevacion for o in ventana)
                # ¿El máximo está en el centro de la ventana? → mejor
                idx_max = max(range(len(ventana)), key=lambda i: ventana[i].elevacion)
                centro_rel = idx_max / max(1, len(ventana) - 1)  # 0=inicio, 1=fin
                # Preferimos que el máximo esté en la primera mitad o centro
                if centro_rel <= 0.6:
                    tendencia_score = 1.0
                elif centro_rel <= 0.8:
                    tendencia_score = 0.75
                else:
                    tendencia_score = 0.50

                # Penalizar si el objeto baja mucho al final
                if elev_final < 15 and elev_inicio > 30:
                    tendencia_score *= 0.5
                elif elev_final < 20:
                    tendencia_score *= 0.75
            else:
                tendencia_score = 1.0

            # ── COMPONENTE 8: ORIENTACIÓN (peso 0.08) ──────────────────
            mejor_obs = max(ventana, key=lambda o: o.calidad_base_para(objeto))
            diff_alt = abs(mejor_obs.elevacion - ind.altitud)
            diff_azi = min(abs(mejor_obs.azimut - ind.azimut),
                           360.0 - abs(mejor_obs.azimut - ind.azimut))
            ori_alt = max(0.0, 1.0 - diff_alt / 90.0) ** 2.0
            ori_azi = max(0.0, 1.0 - diff_azi / 180.0)
            orientacion_score = ori_alt * 0.65 + ori_azi * 0.35

            # ── FITNESS FINAL: SUMA PONDERADA ──────────────────────────
            # Pesos calibrados para máxima discriminación física
            fitness = (
                aire_score        * 0.30 +
                oscuridad         * 0.20 +
                factor_lunar      * 0.20 +
                mag_score         * 0.12 +
                tel_score         * 0.12 +
                dur_score         * 0.10 +
                tendencia_score   * 0.08 +
                orientacion_score * 0.08
            )

            # Re-normalizar (suma de pesos = 1.20 por diseño intencional
            # para amplificar contraste; dividir por 1.20)
            # En realidad los pesos suman 1.0 exacto, verificado:
            # 0.30+0.20+0.20+0.12+0.12+0.10+0.08+0.08 = 1.20 → ajustar
            fitness = fitness / 1.20  # normalizar a 0–1

            # Escalar con condiciones ambientales: afecta pero no colapsa
            fitness = fitness * (0.40 + 0.60 * factor_amb)

            return max(0.0, min(1.0, fitness))

        except Exception as e:
            print(f"  ⚠️ Error en evaluacion: {e}")
            return 0.0

    def _seleccionar_torneo(self, poblacion: List[Individuo]) -> Individuo:
        k = min(config.tamano_torneo, len(poblacion))
        candidatos = random.sample(poblacion, k)
        return max(candidatos, key=lambda x: x.fitness)

    def _cruzar(self, p1: Individuo, p2: Individuo, max_idx: int,
                dur_max: int, aumentos: List[int]) -> Tuple[Individuo, Individuo]:
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
        azi1 = azi1 % 360.0
        azi2 = azi2 % 360.0
        return (Individuo(idx1, dur1, alt1, azi1, aum1),
                Individuo(idx2, dur2, alt2, azi2, aum2))

    def _mutar(self, ind: Individuo, max_idx: int, dur_max: int,
               aumentos: List[int]) -> Individuo:
        m = ind.copia()
        if random.random() < config.tasa_mutacion:
            delta = random.randint(-max(1, max_idx // 5), max(1, max_idx // 5))
            m.idx_inicio = max(0, min(max_idx, m.idx_inicio + delta))
        if random.random() < config.tasa_mutacion:
            m.duracion_pasos = max(1, min(dur_max,
                                          m.duracion_pasos + random.randint(-3, 3)))
            if m.idx_inicio + m.duracion_pasos > max_idx + dur_max:
                m.duracion_pasos = max(1, max_idx - m.idx_inicio + 1)
        if random.random() < config.tasa_mutacion:
            m.altitud = max(10.0, min(85.0, m.altitud + random.gauss(0, 10.0)))
        if random.random() < config.tasa_mutacion:
            m.azimut = (m.azimut + random.gauss(0, 20.0)) % 360.0
        if random.random() < config.tasa_mutacion and len(aumentos) > 1:
            otros = [a for a in aumentos if a != m.aumento]
            if otros:
                m.aumento = random.choice(otros)
        return m

    def _construir_ventana(self, ind: Individuo, observaciones: List[Observacion],
                           objeto: str) -> VentanaObservacion:
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

    def _seleccionar_ventanas_diversas(self, poblacion: List[Individuo],
                                       observaciones: List[Observacion],
                                       objeto: str, paso_minutos: int,
                                       n: int) -> List[VentanaObservacion]:
        sep_seg = max(paso_minutos * 3, 30) * 60
        seleccionadas = []
        vistas: Set[tuple] = set()

        for ind in poblacion:
            if len(seleccionadas) >= n:
                break
            v = self._construir_ventana(ind, observaciones, objeto)
            cerca = any(
                abs((v.inicio - p.inicio).total_seconds()) < sep_seg
                for p in seleccionadas
            )
            sig = (v.inicio, v.fin)
            if not cerca and sig not in vistas and v.calidad > 0.05:
                seleccionadas.append(v)
                vistas.add(sig)

        # Segunda pasada: rellena si no hay n soluciones suficientemente diversas
        for ind in poblacion:
            if len(seleccionadas) >= n:
                break
            v = self._construir_ventana(ind, observaciones, objeto)
            sig = (v.inicio, v.fin)
            if sig not in vistas and v.calidad > 0.01:
                seleccionadas.append(v)
                vistas.add(sig)

        return seleccionadas[:n]