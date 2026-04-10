#astroopti.py
#!/usr/bin/env python3
"""
AstroOpti - Sistema Inteligente para Optimizar la Observación Astronómica
Basado en Algoritmo Genético

CORRECCIONES v3 (parser definitivo):
  - Los índices de columnas en Horizons son FIJOS independientemente del flag:
      [0]  fecha       [1]  hora       [2]  flag (*m / m / * / etc.)
      [17] azimut      [18] elevacion
      [19] APmag       [20] S-brt      [21] Illu%
      [22] Ang-diam    [25] delta (AU)
  - El flag siempre ocupa [2] — nunca se aplica offset adicional.
  - La lógica de offset del v1/v2 era INCORRECTA y causaba lecturas erróneas.
  - Zona horaria UTC documentada y convertida a hora local en la salida.

USO:
    python astroopti.py
"""

import re
import math
import random
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pathlib import Path


# ============================================================================
# CONFIGURACIÓN
# ============================================================================

@dataclass
class Config:
    # ── Parámetros del AG ──────────────────────────────────────────────────
    poblacion_size: int   = 50
    generaciones: int     = 100
    tasa_mutacion: float  = 0.15
    tasa_cruce: float     = 0.8
    elitismo: int         = 2
    tamano_torneo: int    = 3

    # ── Restricciones de observación ──────────────────────────────────────
    elevacion_minima: float      = 10.0
    duracion_minima_minutos: int = 10
    duracion_maxima_minutos: int = 240

    # ── Umbrales de calidad ────────────────────────────────────────────────
    umbral_excelente: float = 0.8
    umbral_buena: float     = 0.6
    umbral_aceptable: float = 0.4

    objetos_soportados: List[str] = field(default_factory=lambda: [
        'mercurio', 'venus', 'marte', 'jupiter',
        'saturno', 'urano', 'neptuno', 'luna'
    ])

    carpeta_objeto: Dict[str, str] = field(default_factory=lambda: {
        'mercurio': 'Mercurio', 'venus': 'Venus', 'marte': 'Marte',
        'jupiter':  'Jupiter',  'saturno': 'Saturno', 'urano': 'Urano',
        'neptuno':  'Neptuno',  'luna': 'Luna'
    })

    rangos_aumento: Dict[str, Tuple[int, int]] = field(default_factory=lambda: {
        'mercurio': (50, 150),  'venus':   (50, 150),
        'marte':    (150, 300), 'jupiter': (100, 250),
        'saturno':  (100, 250), 'urano':   (150, 300),
        'neptuno':  (200, 400), 'luna':    (50, 200)
    })

    # Rango real de magnitud (más brillante, más tenue)
    rangos_magnitud: Dict[str, Tuple[float, float]] = field(default_factory=lambda: {
        'mercurio': (-2.0, 5.5),
        'venus':    (-4.9, -3.0),
        'marte':    (-2.9,  1.6),
        'jupiter':  (-2.9, -1.6),
        'saturno':  (-0.5,  1.3),
        'urano':    ( 5.4,  6.1),
        'neptuno':  ( 7.8,  8.0),
        'luna':     (-12.9, -2.5),
    })

    # Paso de datos por defecto si no se detecta del archivo
    paso_recomendado: Dict[str, int] = field(default_factory=lambda: {
        'mercurio': 10,  'venus':   10,  'marte':   30,
        'jupiter':  60,  'saturno': 60,  'urano':   60,
        'neptuno':  60,  'luna':    10
    })


config = Config()


# ============================================================================
# BARRA DE PROGRESO
# ============================================================================

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


barra = BarraProgreso()


# ============================================================================
# ESCALA BORTLE
# ============================================================================

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
                    'nombre':       item.get('nombre', ''),
                    'latitud':      item.get('latitud', 0),
                    'longitud':     item.get('longitud', 0),
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
        print(f"  📍 Ciudad más cercana: {ciudad} (a {dist:.1f} km, Bortle {bortle})")
        return max(0.0, min(1.0, calidad))


# ============================================================================
# ENTIDADES
# ============================================================================

@dataclass
class Observacion:
    timestamp: datetime        # siempre UTC
    azimut: float
    elevacion: float
    magnitud: float
    brillo_superficial: float
    iluminacion: float
    angulo_diametro: float
    distancia_au: float
    fase: Optional[float] = None

    @property
    def visible(self) -> bool:
        return self.elevacion > 0

    def calidad_base_para(self, objeto: str) -> float:
        elev_norm = min(1.0, self.elevacion / 90.0)
        mag_min, mag_max = config.rangos_magnitud.get(objeto.lower(), (-3.0, 6.0))
        rango = mag_max - mag_min
        brillo_norm = max(0.0, min(1.0, (mag_max - self.magnitud) / rango)) if rango > 0 else 0.5
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
        return (self.fin - self.inicio).total_seconds() / 60.0

    @property
    def momento_optimo(self) -> Optional[Observacion]:
        if not self.observaciones:
            return None
        return max(self.observaciones,
                   key=lambda x: x.calidad_base_para(self.objeto) if self.objeto else 0.0)


# ============================================================================
# PARSER HORIZONS — ÍNDICES FIJOS CONFIRMADOS
#
# Formato verificado con múltiples filas reales del archivo:
#
#   [0]  fecha     "2026-Jan-01"
#   [1]  hora      "00:00"
#   [2]  flag      "*m" | "m" | "*" | "Am" | "Cm" | ...  (SIEMPRE 1 token)
#   [3..5]  RA ICRF (h m s)
#   [6..8]  DEC ICRF (±d m s)
#   [9..11] RA aparente
#   [12..14] DEC aparente
#   [15] dRA*cosD   [16] d(DEC)/dt
#   [17] Azimut     ← FIJO, sin offset
#   [18] Elevación  ← FIJO, sin offset
#   [19] APmag
#   [20] S-brt
#   [21] Illu%
#   [22] Ang-diam
#   [23] ObsSub-LON [24] ObsSub-LAT
#   [25] delta (AU) ← FIJO, sin offset
#   [26] deldot  ...
#
# El flag en [2] es SIEMPRE un único token; los índices posteriores
# no cambian. NO se necesita ni se aplica ningún offset.
# ============================================================================

_MESES = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
    'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
    'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
}

_PATRON_COORDS  = re.compile(r'Center geodetic\s*:\s*([-\d\.]+),\s*([-\d\.]+)')
_PATRON_STEP    = re.compile(r'Step-size\s*:\s*([\d]+)\s*minutes')
_PATRON_FECHALN = re.compile(r'^\s*(\d{4}-[A-Za-z]{3}-\d{2})\s+(\d{2}:\d{2})')


def _parse_fecha(date_str: str, time_str: str) -> Optional[datetime]:
    """Parsea '2026-Apr-09' + '20:22' → datetime UTC."""
    try:
        year = int(date_str[0:4])
        mes  = _MESES.get(date_str[5:8], 0)
        day  = int(date_str[9:11])
        hour = int(time_str[0:2])
        minu = int(time_str[3:5])
        if mes == 0:
            return None
        return datetime(year, mes, day, hour, minu)
    except Exception:
        return None


def _safe_float(val: str) -> Optional[float]:
    """Convierte a float; devuelve None para 'n.a.' y similares."""
    v = val.strip()
    if v in ('n.a.', 'N/A', '', 'n/a', '*'):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _parsear_linea_horizons(linea: str) -> Optional[dict]:
    """
    Parsea una línea de datos Horizons con ÍNDICES FIJOS.

    Índices clave (verificados y siempre constantes):
        [17] azimut     [18] elevacion
        [19] APmag      [20] S-brt     [21] Illu%
        [22] Ang-diam   [25] delta (AU)

    Retorna dict o None si la línea no es válida.
    """
    if not _PATRON_FECHALN.match(linea):
        return None

    partes = linea.split()

    # Necesitamos al menos hasta el índice [25]
    if len(partes) < 26:
        return None

    fecha_str = partes[0]
    hora_str  = partes[1]
    # partes[2] es el flag de visibilidad — se ignora, no afecta índices

    try:
        azimut    = _safe_float(partes[17])
        elevacion = _safe_float(partes[18])
        magnitud  = _safe_float(partes[19])
        sbrt      = _safe_float(partes[20])
        illu      = _safe_float(partes[21])
        angdiam   = _safe_float(partes[22])
        delta     = _safe_float(partes[25])
    except IndexError:
        return None

    # Campos obligatorios
    if any(v is None for v in [azimut, elevacion, magnitud, illu, angdiam, delta]):
        return None

    return {
        'fecha_str': fecha_str,
        'hora_str':  hora_str,
        'azimut':    azimut,
        'elevacion': elevacion,
        'magnitud':  magnitud,
        'sbrt':      sbrt if sbrt is not None else 0.0,
        'illu':      illu,
        'angdiam':   angdiam,
        'delta_au':  abs(delta),
    }


# ============================================================================
# LECTOR DE DATOS HORIZONS
# ============================================================================

class HorizonsReader:
    def __init__(self, objeto: str, lat_usuario: float, lon_usuario: float,
                 fecha: datetime, data_folder: str = "datos"):
        self.objeto       = objeto.lower()
        self.lat_usuario  = lat_usuario
        self.lon_usuario  = lon_usuario
        self.fecha        = fecha
        self.data_folder  = Path(data_folder)
        self.ruta_archivo = None
        self.paso_minutos = config.paso_recomendado.get(self.objeto, 60)
        self._encontrar_archivo_correcto()

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2) -> float:
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        return R * 2 * math.asin(math.sqrt(max(0.0, a)))

    def _leer_cabecera(self, ruta: Path) -> Tuple[Optional[Tuple[float, float]], Optional[int]]:
        coords = None
        step   = None
        try:
            with open(ruta, 'r', encoding='utf-8') as f:
                for _ in range(60):
                    linea = f.readline()
                    if not linea:
                        break
                    if coords is None:
                        mc = _PATRON_COORDS.search(linea)
                        if mc:
                            lon = float(mc.group(1))
                            lat = float(mc.group(2))
                            if lon > 180:
                                lon -= 360
                            coords = (lat, lon)
                    if step is None:
                        ms = _PATRON_STEP.search(linea)
                        if ms:
                            step = int(ms.group(1))
                    if coords and step:
                        break
        except Exception:
            pass
        return coords, step

    def _extraer_rango_fechas(self, ruta: Path) -> Optional[Tuple[datetime, datetime]]:
        primera = ultima = None
        try:
            with open(ruta, 'r', encoding='utf-8') as f:
                dentro = False
                for linea in f:
                    if '$$SOE' in linea:
                        dentro = True
                        continue
                    if '$$EOE' in linea:
                        break
                    if dentro:
                        mn = _PATRON_FECHALN.match(linea)
                        if mn:
                            dt = _parse_fecha(mn.group(1), mn.group(2))
                            if dt:
                                if primera is None:
                                    primera = dt
                                ultima = dt
        except Exception:
            pass
        return (primera, ultima) if primera and ultima else None

    def _encontrar_archivo_correcto(self):
        carpeta_nombre = config.carpeta_objeto.get(self.objeto)
        if not carpeta_nombre:
            raise ValueError(f"Objeto no reconocido: {self.objeto}")

        carpeta = self.data_folder / carpeta_nombre
        if not carpeta.exists():
            raise FileNotFoundError(f"Carpeta no encontrada: {carpeta}")

        archivos = sorted(carpeta.glob("horizons_results*.txt"))
        if not archivos:
            raise FileNotFoundError(f"No se encontraron archivos TXT en {carpeta}")

        print(f"\n  🔍 Buscando archivo para {self.fecha.strftime('%d/%m/%Y')}...")
        print(f"  📍 Cerca de ({self.lat_usuario:.4f}°, {self.lon_usuario:.4f}°)")

        datos = []
        total = len(archivos)
        for i, arch in enumerate(archivos):
            barra.mostrar(i + 1, total, 35, "     Leyendo cabeceras")
            coords, step = self._leer_cabecera(arch)
            if coords:
                datos.append((arch, coords, step or 60))
        barra.finalizar()

        if not datos:
            raise FileNotFoundError("No se pudieron leer coordenadas de ningún archivo")

        observadores: Dict[Tuple, List] = {}
        for arch, coords, step in datos:
            clave = (round(coords[0], 2), round(coords[1], 2))
            observadores.setdefault(clave, []).append((arch, step))

        mejor_clave = min(
            observadores.keys(),
            key=lambda c: self._haversine(self.lat_usuario, self.lon_usuario, c[0], c[1])
        )
        dist = self._haversine(self.lat_usuario, self.lon_usuario,
                               mejor_clave[0], mejor_clave[1])
        archivos_obs = observadores[mejor_clave]

        print(f"  📍 Observador más cercano: {mejor_clave[0]:.2f}°, {mejor_clave[1]:.2f}°")
        print(f"  📏 Distancia: {dist:.1f} km")

        archivo_elegido = None
        step_elegido    = 60

        for arch, step in sorted(archivos_obs, key=lambda x: x[0].name):
            rango = self._extraer_rango_fechas(arch)
            if rango is None:
                continue
            fecha_ini, fecha_fin = rango
            if fecha_ini.date() <= self.fecha.date() <= fecha_fin.date():
                archivo_elegido = arch
                step_elegido    = step
                break

        if archivo_elegido is None:
            def dist_temporal(item):
                arch, step = item
                rango = self._extraer_rango_fechas(arch)
                if rango is None:
                    return timedelta(days=9999)
                return abs(rango[0].date() - self.fecha.date())

            archivo_elegido, step_elegido = min(archivos_obs, key=dist_temporal)
            rango = self._extraer_rango_fechas(archivo_elegido)
            print(f"  ⚠️  Fecha {self.fecha.strftime('%d/%m/%Y')} fuera de rango exacto.")
            if rango:
                print(f"       Archivo más cercano cubre: "
                      f"{rango[0].strftime('%d/%m/%Y')} – {rango[1].strftime('%d/%m/%Y')}")
            print(f"       Usando: {archivo_elegido.name}")
        else:
            print(f"  📁 Archivo seleccionado: {archivo_elegido.name}")

        self.ruta_archivo = archivo_elegido
        self.paso_minutos = step_elegido
        print(f"  ⏱️  Paso de datos detectado: {self.paso_minutos} minutos")

    def cargar_observaciones(self, debug_filas: int = 0) -> List[Observacion]:
        """
        Carga observaciones del bloque $$SOE..$$EOE.
        Usa índices FIJOS verificados: azi=[17], elev=[18], delta=[25].

        debug_filas > 0 → muestra las primeras N filas con sus valores
        parseados para verificación manual contra efemérides.
        """
        print(f"\n  📖 Cargando observaciones...")
        print(f"  ℹ️  Timestamps en UTC. Hora local = UTC{'+' if 0 >= 0 else ''} offset.")

        with open(self.ruta_archivo, 'r', encoding='utf-8') as f:
            contenido = f.read()

        idx_soe = contenido.find('$$SOE')
        idx_eoe = contenido.find('$$EOE')
        if idx_soe == -1 or idx_eoe == -1:
            print("  ⚠️  No se encontraron marcadores $$SOE/$$EOE")
            return []

        bloque = contenido[idx_soe + 5: idx_eoe]
        lineas = bloque.splitlines()
        total  = len(lineas)
        print(f"  📊 Líneas en bloque de datos: {total}")

        # Ventana de fechas
        if self.paso_minutos > 60:
            margen    = timedelta(days=max(4, self.paso_minutos // (60 * 12)))
            fecha_ini = self.fecha - margen
            fecha_fin = self.fecha + margen
            print(f"  🗓️  Paso grande ({self.paso_minutos} min): "
                  f"ventana {fecha_ini.strftime('%d/%m/%Y')} – {fecha_fin.strftime('%d/%m/%Y')}")
        else:
            fecha_ini = datetime(self.fecha.year, self.fecha.month, self.fecha.day, 0, 0)
            fecha_fin = fecha_ini + timedelta(days=1) - timedelta(seconds=1)
            print(f"  🗓️  Filtrando día (UTC): {self.fecha.strftime('%d/%m/%Y')}")

        observaciones = []
        n_debug = 0

        for i, linea in enumerate(lineas):
            if i % 200 == 0:
                barra.mostrar(i, total, 35, "     Procesando")
            if not linea.strip():
                continue

            datos = _parsear_linea_horizons(linea)
            if datos is None:
                continue

            fecha_obs = _parse_fecha(datos['fecha_str'], datos['hora_str'])
            if fecha_obs is None:
                continue

            if not (fecha_ini <= fecha_obs <= fecha_fin):
                continue

            obs = Observacion(
                timestamp=fecha_obs,
                azimut=datos['azimut'],
                elevacion=datos['elevacion'],
                magnitud=datos['magnitud'],
                brillo_superficial=datos['sbrt'],
                iluminacion=datos['illu'],
                angulo_diametro=datos['angdiam'],
                distancia_au=datos['delta_au'],
            )
            observaciones.append(obs)

            # Diagnóstico opcional
            if debug_filas > 0 and n_debug < debug_filas:
                print(f"\n  🔎 DEBUG fila {n_debug+1}:")
                print(f"       Raw     : {linea.rstrip()}")
                print(f"       UTC     : {fecha_obs.strftime('%d/%m/%Y %H:%M')}")
                print(f"       Azimut  : {obs.azimut:.4f}°")
                print(f"       Elev    : {obs.elevacion:.4f}°")
                print(f"       APmag   : {obs.magnitud:.3f}")
                print(f"       Illu%   : {obs.iluminacion:.4f}")
                print(f"       Ang-diam: {obs.angulo_diametro:.4f}\"")
                print(f"       Delta   : {obs.distancia_au:.6f} UA")
                n_debug += 1

        barra.mostrar(total, total, 35, "     Procesando")
        barra.finalizar()
        print(f"  ✅ Observaciones cargadas: {len(observaciones)}")

        if len(observaciones) == 0:
            rango = self._extraer_rango_fechas(self.ruta_archivo)
            if rango:
                print(f"  ℹ️  El archivo cubre (UTC): "
                      f"{rango[0].strftime('%d/%m/%Y %H:%M')} – "
                      f"{rango[1].strftime('%d/%m/%Y %H:%M')}")
        else:
            visibles = [o for o in observaciones if o.visible]
            print(f"  🌙 Sobre el horizonte: {len(visibles)}/{len(observaciones)}")
            if visibles:
                mejor = max(visibles, key=lambda o: o.elevacion)
                print(f"  ⭐ Mayor elevación: {mejor.elevacion:.1f}° "
                      f"a las {mejor.timestamp.strftime('%H:%M')} UTC  "
                      f"(Azimut {mejor.azimut:.1f}°)")

        return observaciones


# ============================================================================
# INDIVIDUO (CROMOSOMA)
# ============================================================================

@dataclass
class Individuo:
    idx_inicio:     int
    duracion_pasos: int
    altitud:        float
    azimut:         float
    aumento:        int
    fitness:        float = 0.0

    def copia(self) -> 'Individuo':
        return Individuo(self.idx_inicio, self.duracion_pasos,
                         self.altitud, self.azimut, self.aumento, self.fitness)


# ============================================================================
# ALGORITMO GENÉTICO
# ============================================================================

class AlgoritmoGenetico:

    def __init__(self):
        self.historial_convergencia: List[float] = []
        self.historial_promedio:     List[float] = []

    def optimizar_top_n(self, observaciones: List[Observacion],
                        telescopio: Telescopio, objeto: str,
                        condiciones: CondicionesAmbientales,
                        paso_minutos: int, n: int = 3) -> List[VentanaObservacion]:

        if len(observaciones) < 3:
            raise ValueError(
                f"Solo hay {len(observaciones)} observaciones. Se necesitan al menos 3."
            )

        max_idx    = max(0, len(observaciones) - 3)
        dur_max    = max(3, min(len(observaciones), 24))
        aumentos   = telescopio.aumentos_disponibles or [50, 100, 150, 200]
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
            barra.mostrar(i + 1, len(poblacion), 35, "     Evaluando")
            ind.fitness = self._evaluar(ind, observaciones, telescopio,
                                        objeto, factor_amb, dur_max)
        barra.finalizar()

        self.historial_convergencia = []
        self.historial_promedio     = []

        print(f"\n  🔄 [3] Selección → [4] Cruce → [5] Mutación → [6] Reemplazo")
        print(f"  ⏹️  [7] Criterio de parada: {config.generaciones} generaciones\n")

        for gen in range(config.generaciones):
            barra.mostrar(gen + 1, config.generaciones, 45,
                          f"     Gen {gen+1:3d}/{config.generaciones}")

            poblacion.sort(key=lambda x: x.fitness, reverse=True)
            mejor_gen    = poblacion[0].fitness
            promedio_gen = sum(i.fitness for i in poblacion) / len(poblacion)
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

                hijo1.fitness = self._evaluar(hijo1, observaciones, telescopio,
                                              objeto, factor_amb, dur_max)
                hijo2.fitness = self._evaluar(hijo2, observaciones, telescopio,
                                              objeto, factor_amb, dur_max)

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
        mejora = (self.historial_convergencia[-1] - self.historial_convergencia[0]) * 100
        print(f"  📈 Mejora total     : +{mejora:.1f}%")

        return self._seleccionar_ventanas_diversas(
            poblacion, observaciones, objeto, paso_minutos, n
        )

    def _crear_poblacion(self, max_idx: int, dur_max: int,
                         aumentos: List[int]) -> List[Individuo]:
        poblacion = []
        for _ in range(config.poblacion_size):
            idx = random.randint(0, max_idx)
            dur = random.randint(1, dur_max)
            if idx + dur > max_idx + dur_max:
                dur = max(1, max_idx - idx + 1)
            altitud = random.uniform(10.0, 85.0)
            azimut  = random.uniform(0.0, 360.0)
            aumento = random.choice(aumentos)
            poblacion.append(Individuo(idx, dur, altitud, azimut, aumento))
        return poblacion

    def _evaluar(self, ind: Individuo, observaciones: List[Observacion],
                 telescopio: Telescopio, objeto: str,
                 factor_ambiental: float, dur_max: int) -> float:
        """
        Fitness multiobjetivo ponderado:
          0.30 × elevacion_norm
          0.20 × brillo_norm
          0.15 × duracion_norm
          0.20 × calidad_telescopio
          0.15 × orientacion_score
        """
        fin = ind.idx_inicio + ind.duracion_pasos
        if fin > len(observaciones) or ind.duracion_pasos < 1:
            return 0.0

        ventana = observaciones[ind.idx_inicio:fin]
        if not ventana:
            return 0.0

        if not all(o.visible for o in ventana):
            return 0.0

        elev_prom = sum(o.elevacion for o in ventana) / len(ventana)
        if elev_prom < config.elevacion_minima:
            return 0.0

        # [a] Elevación (30%)
        elev_norm = min(1.0, elev_prom / 90.0)

        # [b] Brillo (20%)
        mag_min, mag_max = config.rangos_magnitud.get(objeto.lower(), (-3.0, 6.0))
        rango_mag = mag_max - mag_min
        mag_prom  = sum(o.magnitud for o in ventana) / len(ventana)
        brillo_norm = (max(0.0, min(1.0, (mag_max - mag_prom) / rango_mag))
                       if rango_mag > 0 else 0.5)

        # [c] Duración (15%)
        duracion_norm = min(1.0, ind.duracion_pasos / dur_max)

        # [d] Telescopio (20%)
        tel_quality = telescopio.calidad_para_aumento(ind.aumento, objeto)

        # [e] Orientación (15%)
        optimo   = max(ventana, key=lambda o: o.calidad_base_para(objeto))
        diff_alt = abs(optimo.elevacion - ind.altitud)
        diff_azi = min(abs(optimo.azimut - ind.azimut),
                       360 - abs(optimo.azimut - ind.azimut))
        ori_alt  = max(0.0, 1.0 - diff_alt / 90.0)
        ori_azi  = max(0.0, 1.0 - diff_azi / 180.0)
        orientacion = (ori_alt + ori_azi) / 2.0

        fitness = (0.30 * elev_norm +
                   0.20 * brillo_norm +
                   0.15 * duracion_norm +
                   0.20 * tel_quality +
                   0.15 * orientacion)

        fitness *= factor_ambiental

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

    def _cruzar(self, p1: Individuo, p2: Individuo,
                max_idx: int, dur_max: int,
                aumentos: List[int]) -> Tuple[Individuo, Individuo]:
        alpha = random.random()
        beta  = 1.0 - alpha

        idx1 = int(round(alpha * p1.idx_inicio     + beta  * p2.idx_inicio))
        idx2 = int(round(beta  * p1.idx_inicio     + alpha * p2.idx_inicio))
        dur1 = int(round(alpha * p1.duracion_pasos + beta  * p2.duracion_pasos))
        dur2 = int(round(beta  * p1.duracion_pasos + alpha * p2.duracion_pasos))

        alt1 = alpha * p1.altitud + beta  * p2.altitud
        alt2 = beta  * p1.altitud + alpha * p2.altitud
        azi1 = alpha * p1.azimut  + beta  * p2.azimut
        azi2 = beta  * p1.azimut  + alpha * p2.azimut

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

    def _mutar(self, ind: Individuo, max_idx: int,
               dur_max: int, aumentos: List[int]) -> Individuo:
        m = ind.copia()

        if random.random() < config.tasa_mutacion:
            delta = random.randint(-max(1, max_idx // 5), max(1, max_idx // 5))
            m.idx_inicio = max(0, min(max_idx, m.idx_inicio + delta))

        if random.random() < config.tasa_mutacion:
            m.duracion_pasos = max(1, min(dur_max, m.duracion_pasos + random.randint(-3, 3)))
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

    def _construir_ventana(self, ind: Individuo,
                           observaciones: List[Observacion],
                           objeto: str) -> VentanaObservacion:
        fin = min(ind.idx_inicio + ind.duracion_pasos, len(observaciones))
        obs = observaciones[ind.idx_inicio:fin] or [observaciones[0]]
        return VentanaObservacion(
            inicio=obs[0].timestamp, fin=obs[-1].timestamp,
            observaciones=obs, calidad=ind.fitness,
            aumento_recomendado=ind.aumento, objeto=objeto
        )

    def _seleccionar_ventanas_diversas(self, poblacion: List[Individuo],
                                       observaciones: List[Observacion],
                                       objeto: str, paso_minutos: int,
                                       n: int) -> List[VentanaObservacion]:
        sep_seg = max(paso_minutos * 3, 30) * 60
        seleccionadas: List[VentanaObservacion] = []
        vistas: set = set()

        for ind in poblacion:
            if len(seleccionadas) >= n:
                break
            v = self._construir_ventana(ind, observaciones, objeto)
            cerca = any(
                abs((v.inicio - p.inicio).total_seconds()) < sep_seg
                for p in seleccionadas
            )
            sig = (v.inicio, v.fin)
            if not cerca and sig not in vistas:
                seleccionadas.append(v)
                vistas.add(sig)

        for ind in poblacion:
            if len(seleccionadas) >= n:
                break
            v   = self._construir_ventana(ind, observaciones, objeto)
            sig = (v.inicio, v.fin)
            if sig not in vistas:
                seleccionadas.append(v)
                vistas.add(sig)

        return seleccionadas[:n]


# ============================================================================
# SERVICIO PRINCIPAL
# ============================================================================

class AstroOpti:
    def __init__(self):
        self.algoritmo = AlgoritmoGenetico()
        self.bortle    = EscalaBortle()

    def optimizar(self, latitud: float, longitud: float, fecha: datetime,
                  objeto: str, telescopio: Telescopio,
                  condiciones: CondicionesAmbientales,
                  offset_utc: int = -6,
                  debug_filas: int = 0) -> List[dict]:

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


# ============================================================================
# PRESENTACIÓN
# ============================================================================

def _dir_cardinal(az: float) -> str:
    dirs = ['N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO']
    return dirs[int((az + 22.5) / 45) % 8]


def _hora_local(dt: datetime, offset: int) -> str:
    return (dt + timedelta(hours=offset)).strftime('%d/%m/%Y %H:%M')


def mostrar_resultado(r: dict):
    pct    = r['calidad_pct']
    emoji  = "🌟" if pct >= 80 else ("⭐" if pct >= 60 else ("✨" if pct >= 40 else "💫"))
    offset = r.get('offset_utc', -6)

    print(f"\n{'='*60}")
    print(f"📋 ESCENARIO #{r['numero']} — {emoji} {pct:.1f}%  ({r['categoria']})")
    print(f"{'='*60}")

    v  = r['ventana']
    mo = r['momento_optimo']

    print(f"\n  📅 VENTANA DE OBSERVACIÓN (hora local UTC{offset:+d}):")
    print(f"     Inicio   : {_hora_local(v.inicio, offset)}")
    print(f"     Fin      : {_hora_local(v.fin, offset)}")
    print(f"     Duración : {v.duracion_minutos:.0f} min  ({v.duracion_minutos/60:.1f} h)")
    print(f"     (UTC)    : {v.inicio.strftime('%H:%M')} – {v.fin.strftime('%H:%M')}")

    if mo:
        print(f"\n  ⭐ MOMENTO DE MÁXIMA VISIBILIDAD:")
        print(f"     Hora local : {_hora_local(mo.timestamp, offset)}")
        print(f"     (UTC)      : {mo.timestamp.strftime('%H:%M')}")
        print(f"     Altitud    : {mo.elevacion:.1f}°")
        print(f"     Azimut     : {mo.azimut:.1f}°  ({_dir_cardinal(mo.azimut)})")
        print(f"     Magnitud   : {mo.magnitud:.2f}")

        print(f"\n  🔭 CONFIGURACIÓN RECOMENDADA:")
        print(f"     Aumento    : {r['aumento']}x")

        print(f"\n  📊 INFORMACIÓN COMPLEMENTARIA:")
        if r['objeto'].lower() == 'luna':
            print(f"     Fase lunar        : {mo.iluminacion:.1f}%")
        print(f"     Iluminación       : {mo.iluminacion:.1f}%")
        print(f"     Diámetro aparente : {mo.angulo_diametro:.2f}\"")
        print(f"     Distancia         : {mo.distancia_au:.6f} UA")


def mostrar_convergencia(historial_mejor: List[float], historial_prom: List[float]):
    if not historial_mejor:
        return

    print(f"\n  📈 CONVERGENCIA DEL ALGORITMO GENÉTICO")
    print(f"  {'─'*54}")

    alto    = 8
    ancho_g = min(52, len(historial_mejor))
    paso_g  = max(1, len(historial_mejor) // ancho_g)
    pts_m   = [historial_mejor[i] for i in range(0, len(historial_mejor), paso_g)][:ancho_g]
    pts_p   = [historial_prom[i]  for i in range(0, len(historial_prom),  paso_g)][:ancho_g]

    max_f = max(pts_m)
    min_f = min(pts_p)
    rango = max_f - min_f if max_f != min_f else 1.0

    for fila in range(alto, -1, -1):
        umbral = min_f + (fila / alto) * rango
        linea  = f"  {umbral*100:5.1f}% │"
        for j in range(len(pts_m)):
            m = pts_m[j] >= umbral
            p = pts_p[j] >= umbral if j < len(pts_p) else False
            linea += "█" if (m and p) else ("▓" if m else ("░" if p else " "))
        print(linea)

    print(f"         └{'─'*ancho_g}")
    print(f"          Gen 1{' '*(ancho_g-11)}Gen {len(historial_mejor)}")
    print(f"  ▓ mejor fitness  │  ░ promedio  │  █ ambos")
    print(f"  Fitness: {historial_mejor[0]*100:.1f}% → {historial_mejor[-1]*100:.1f}%   "
          f"Promedio: {historial_prom[0]*100:.1f}% → {historial_prom[-1]*100:.1f}%")


# ============================================================================
# MAIN
# ============================================================================

def main():
    print()
    print("╔" + "=" * 60 + "╗")
    print("║" + " " * 14 + "🚀 ASTROOPTI v3 🚀" + " " * 20 + "║")
    print("║" + " " * 8 + "Optimizador Inteligente de Observación" + " " * 14 + "║")
    print("╚" + "=" * 60 + "╝")
    print()
    print("  ℹ️  Archivos Horizons en UTC.")
    print("  ℹ️  Tuxtla Gutiérrez: UTC-6 (CST) / UTC-5 (CDT verano)")
    print()

    try:
        print("📍 UBICACIÓN DEL OBSERVADOR")
        print("-" * 40)
        print("  Ejemplo: Tuxtla Gutiérrez → lat 16.7821, lon -93.0900")
        latitud  = float(input("  Latitud  (negativo para sur):   "))
        longitud = float(input("  Longitud (negativo para oeste): "))
        print()

        print("🕐 ZONA HORARIA")
        print("-" * 40)
        print("  Offset respecto a UTC (ej: -6 para CST, -5 para CDT)")
        offset_str = input("  Offset UTC [por defecto -6]: ").strip()
        offset_utc = int(offset_str) if offset_str else -6
        print()

        print("📅 FECHA DE OBSERVACIÓN")
        print("-" * 40)
        fecha_str = input("  Fecha (dd/mm/aaaa): ")
        dia, mes, año = map(int, fecha_str.split('/'))
        fecha = datetime(año, mes, dia)
        print()

        print("🔭 OBJETO CELESTE")
        print("-" * 40)
        print("  Opciones:", ', '.join(config.objetos_soportados))
        objeto = input("  Objeto: ").strip().lower()
        if objeto not in config.objetos_soportados:
            print(f"  ⚠️  No reconocido. Usando 'jupiter'")
            objeto = "jupiter"
        print()

        print("🔭 TELESCOPIO")
        print("-" * 40)
        tipo = input("  Tipo (reflector/refractor/catadioptrico): ").strip().lower()
        if tipo not in ['reflector', 'refractor', 'catadioptrico']:
            tipo = "reflector"
        apertura     = float(input("  Apertura en mm (ej: 200): "))
        aumentos_str = input("  Aumentos disponibles (ej: 50,100,200): ")
        aumentos     = [int(x.strip()) for x in aumentos_str.split(',') if x.strip()]
        print()

        print("🌤️  CONDICIONES AMBIENTALES")
        print("-" * 40)
        print("  Cielo: 1-Despejado  2-Parcialmente nublado  3-Nublado")
        cielo        = input("  Elige (1-3): ").strip()
        estado_cielo = {'1': 'despejado', '2': 'parcialmente_nublado'}.get(cielo, 'nublado')

        print("\n  Luna: 1-Nueva/creciente (bueno)  2-Llena (malo)")
        luna_llena = input("  Elige (1-2): ").strip() == "2"

        print("\n  Seeing: 1-Bueno  2-Regular  3-Malo")
        seeing = {'1': 'bueno', '2': 'regular'}.get(
            input("  Elige (1-3): ").strip(), 'malo')

        print("\n  🔎 Diagnóstico: ¿cuántas filas raw mostrar para verificar?")
        debug_str  = input("  Filas debug [0=ninguna]: ").strip()
        debug_rows = int(debug_str) if debug_str.isdigit() else 0
        print()

        telescopio  = Telescopio(tipo, apertura, aumentos)
        condiciones = CondicionesAmbientales(estado_cielo, luna_llena, seeing)

        astroopti  = AstroOpti()
        resultados = astroopti.optimizar(
            latitud, longitud, fecha, objeto,
            telescopio, condiciones,
            offset_utc=offset_utc,
            debug_filas=debug_rows,
        )

        print(f"\n🏆 TOP 3 ESCENARIOS PARA {objeto.upper()}")
        for r in resultados:
            mostrar_resultado(r)

        mostrar_convergencia(
            astroopti.algoritmo.historial_convergencia,
            astroopti.algoritmo.historial_promedio
        )

        print("\n" + "=" * 60)
        print("💡 RECOMENDACIÓN: El escenario #1 es el óptimo")
        print(f"   Horas en UTC{offset_utc:+d} (hora local)")
        print("=" * 60)

    except FileNotFoundError as e:
        print(f"\n❌ ERROR: {e}")
        print("   Verifica: datos/[Objeto]/horizons_results*.txt")
    except ValueError as e:
        print(f"\n❌ ERROR: {e}")
    except KeyboardInterrupt:
        print("\n\n👋 ¡Hasta luego!")
    except Exception as e:
        print(f"\n❌ ERROR inesperado: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()