# horizons_reader.py
import re
import math
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict

from config import config
from models import Observacion
from utils import BarraProgreso

barra = BarraProgreso()

_PATRON_COORDS = re.compile(r'Center geodetic\s*:\s*([-\d\.]+),\s*([-\d\.]+)')
_PATRON_STEP = re.compile(r'Step-size\s*:\s*([\d]+)\s*minutes')
_PATRON_FECHALN = re.compile(r'^\s*(\d{4}-[A-Za-z]{3}-\d{2})\s+(\d{2}:\d{2})')

_MESES = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
    'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
    'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
}

def _parse_fecha(date_str: str, time_str: str) -> Optional[datetime]:
    try:
        year = int(date_str[0:4])
        mes = _MESES.get(date_str[5:8], 0)
        day = int(date_str[9:11])
        hour = int(time_str[0:2])
        minute = int(time_str[3:5])
        if mes == 0:
            return None
        return datetime(year, mes, day, hour, minute)
    except Exception:
        return None

class HorizonsReader:
    def __init__(self, objeto: str, lat_usuario: float, lon_usuario: float,
                 fecha: datetime, data_folder: str = "datos"):
        self.objeto = objeto.lower()
        self.lat_usuario = lat_usuario
        self.lon_usuario = lon_usuario
        self.fecha = fecha
        self.data_folder = Path(data_folder)
        self.ruta_archivo = None
        self.paso_minutos = config.paso_recomendado.get(self.objeto, 60)
        self._encontrar_archivo_correcto()

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2):
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) *
             math.cos(math.radians(lat2)) * math.sin(dlon/2)**2)
        return R * 2 * math.asin(math.sqrt(max(0.0, a)))

    def _leer_cabecera(self, ruta: Path):
        coords = None
        step = None
        try:
            with open(ruta, 'r', encoding='utf-8') as f:
                for _ in range(60):
                    linea = f.readline()
                    if not linea: break
                    if coords is None:
                        mc = _PATRON_COORDS.search(linea)
                        if mc:
                            lon = float(mc.group(1))
                            lat = float(mc.group(2))
                            if lon > 180: lon -= 360
                            coords = (lat, lon)
                    if step is None:
                        ms = _PATRON_STEP.search(linea)
                        if ms:
                            step = int(ms.group(1))
                    if coords and step: break
        except Exception:
            pass
        return coords, step

    def _extraer_rango_fechas(self, ruta: Path):
        primera = None
        ultima = None
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
                                if primera is None: primera = dt
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
            barra.mostrar(i+1, total, 35, "     Leyendo cabeceras")
            coords, step = self._leer_cabecera(arch)
            if coords:
                datos.append((arch, coords, step or 60))
        barra.finalizar()
        if not datos:
            raise FileNotFoundError("No se pudieron leer coordenadas de ningún archivo")

        observadores = {}
        for arch, coords, step in datos:
            clave = (round(coords[0],2), round(coords[1],2))
            observadores.setdefault(clave, []).append((arch, step))

        mejor_clave = min(observadores.keys(),
                          key=lambda c: self._haversine(self.lat_usuario, self.lon_usuario, c[0], c[1]))
        dist = self._haversine(self.lat_usuario, self.lon_usuario, mejor_clave[0], mejor_clave[1])
        archivos_obs = observadores[mejor_clave]

        print(f"  📍 Observador más cercano: {mejor_clave[0]:.2f}°, {mejor_clave[1]:.2f}°")
        print(f"  📏 Distancia: {dist:.1f} km")

        archivo_elegido = None
        step_elegido = 60
        for arch, step in sorted(archivos_obs, key=lambda x: x[0].name):
            rango = self._extraer_rango_fechas(arch)
            if rango is None: continue
            fecha_ini, fecha_fin = rango
            if fecha_ini.date() <= self.fecha.date() <= fecha_fin.date():
                archivo_elegido = arch
                step_elegido = step
                break

        if archivo_elegido is None:
            def dist_temporal(item):
                arch, step = item
                rango = self._extraer_rango_fechas(arch)
                if rango is None: return timedelta(days=9999)
                return abs(rango[0].date() - self.fecha.date())
            archivo_elegido, step_elegido = min(archivos_obs, key=dist_temporal)
            rango = self._extraer_rango_fechas(archivo_elegido)
            print(f"  ⚠️  Fecha {self.fecha.strftime('%d/%m/%Y')} fuera de rango exacto.")
            if rango:
                print(f"       Archivo más cercano cubre: {rango[0].strftime('%d/%m/%Y')} – {rango[1].strftime('%d/%m/%Y')}")
            print(f"       Usando: {archivo_elegido.name}")
        else:
            print(f"  📁 Archivo seleccionado: {archivo_elegido.name}")

        self.ruta_archivo = archivo_elegido
        self.paso_minutos = step_elegido
        print(f"  ⏱️  Paso de datos detectado: {self.paso_minutos} minutos")

    def _obtener_posiciones_columnas(self, contenido: str, idx_soe: int) -> Dict[str, int]:
        lineas_antes = contenido[:idx_soe].splitlines()
        linea_header = ""
        for linea in reversed(lineas_antes):
            if 'Azi' in linea and 'Elev' in linea:
                linea_header = linea
                break
        if not linea_header:
            print("  ⚠️  No se encontró línea de encabezado con 'Azi' y 'Elev'")
            return {}

        print(f"  📋 Encabezado detectado (primeros 150 chars):\n     {linea_header[:150]}")
        posiciones = {}
        idx_azi = linea_header.find('Azi')
        if idx_azi != -1:
            posiciones['AZ_EL_start'] = idx_azi
        idx_apmag = linea_header.find('APmag')
        if idx_apmag != -1:
            posiciones['APmag_start'] = idx_apmag
        idx_sbrt = linea_header.find('S-brt')
        if idx_sbrt != -1:
            posiciones['S-brt_start'] = idx_sbrt
        
        # ── CORRECCIÓN: Buscar Illu% exactamente ──────────────────────
        idx_illu = linea_header.find('Illu%')
        if idx_illu == -1:
            # Fallback: buscar con espacio
            idx_illu = linea_header.find(' Illu% ')
            if idx_illu == -1:
                # Último recurso: buscar Illu (pero NO Def_illu)
                idx_illu = linea_header.find(' Illu ')
        if idx_illu != -1:
            posiciones['Illu_start'] = idx_illu
            
        idx_ang = linea_header.find('Ang-diam')
        if idx_ang != -1:
            posiciones['Ang-diam_start'] = idx_ang
        idx_delta = linea_header.find(' delta ')
        if idx_delta != -1:
            posiciones['delta_start'] = idx_delta
        
        idx_solar = linea_header.find('Solar')
        if idx_solar == -1:
            idx_solar = linea_header.find('sun')
        if idx_solar != -1:
            posiciones['solar_start'] = idx_solar
            
        return posiciones

    def _extraer_numero_desde_posicion(self, linea: str, inicio: int) -> Optional[float]:
        if inicio >= len(linea):
            return None
        sub = linea[inicio:]
        patron = re.compile(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?')
        match = patron.search(sub)
        if match:
            try:
                return float(match.group())
            except ValueError:
                return None
        return None

    def _extraer_dos_numeros_consecutivos(self, linea: str, inicio: int) -> Tuple[Optional[float], Optional[float]]:
        primero = self._extraer_numero_desde_posicion(linea, inicio)
        if primero is None:
            return None, None
        sub = linea[inicio:]
        patron_num = re.compile(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?')
        match = patron_num.search(sub)
        if not match:
            return primero, None
        next_start = inicio + match.end()
        segundo = self._extraer_numero_desde_posicion(linea, next_start)
        return primero, segundo

    def _validar_magnitud(self, val: float, objeto: str) -> bool:
        mag_min, mag_max = config.rangos_magnitud.get(objeto, (-30, 30))
        return mag_min <= val <= mag_max

    def _buscar_magnitud_corregida(self, linea: str, pos_inicio: int, objeto: str) -> Optional[float]:
        val = self._extraer_numero_desde_posicion(linea, pos_inicio)
        if val is not None and self._validar_magnitud(val, objeto):
            return val
        patron = re.compile(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?')
        for match in patron.finditer(linea):
            try:
                num = float(match.group())
                if self._validar_magnitud(num, objeto):
                    return num
            except:
                continue
        return val

    def cargar_observaciones(self, debug_filas: int = 0) -> List[Observacion]:
        print(f"\n  📖 Cargando observaciones desde: {self.ruta_archivo.name}")
        with open(self.ruta_archivo, 'r', encoding='utf-8') as f:
            contenido = f.read()

        idx_soe = contenido.find('$$SOE')
        idx_eoe = contenido.find('$$EOE')
        if idx_soe == -1 or idx_eoe == -1:
            print("  ⚠️  No se encontraron marcadores $$SOE/$$EOE")
            return []

        posiciones = self._obtener_posiciones_columnas(contenido, idx_soe)
        if not posiciones:
            print("  ⚠️  No se pudieron determinar posiciones de columnas, se aborta carga.")
            return []

        bloque_datos = contenido[idx_soe+5:idx_eoe]
        lineas = bloque_datos.splitlines()
        total = len(lineas)
        print(f"  📊 Líneas en bloque de datos: {total}")

        if self.paso_minutos > 60:
            margen = timedelta(days=max(4, self.paso_minutos // (60*12)))
            fecha_ini = self.fecha - margen
            fecha_fin = self.fecha + margen
            print(f"  🗓️  Ventana amplia: {fecha_ini.strftime('%d/%m/%Y')} – {fecha_fin.strftime('%d/%m/%Y')}")
        else:
            fecha_ini = datetime(self.fecha.year, self.fecha.month, self.fecha.day, 0, 0)
            fecha_fin = fecha_ini + timedelta(days=1) - timedelta(seconds=1)
            print(f"  🗓️  Filtrando día UTC: {self.fecha.strftime('%d/%m/%Y')}")

        observaciones = []
        n_debug = 0

        for i, linea in enumerate(lineas):
            if i % 200 == 0:
                barra.mostrar(i, total, 35, "     Procesando")
            if not linea.strip():
                continue
            if not _PATRON_FECHALN.match(linea):
                continue

            partes_fecha = linea.split()[:2]
            if len(partes_fecha) < 2:
                continue
            fecha_obs = _parse_fecha(partes_fecha[0], partes_fecha[1])
            if fecha_obs is None:
                continue
            if not (fecha_ini <= fecha_obs <= fecha_fin):
                continue

            try:
                az_el_start = posiciones.get('AZ_EL_start')
                if az_el_start is None:
                    continue
                az, el = self._extraer_dos_numeros_consecutivos(linea, az_el_start)
                if az is None or el is None:
                    continue
                az = az % 360.0
                if el < -90.0 or el > 90.0:
                    if debug_filas:
                        print(f"  ⚠️  Elevación fuera de rango: {el:.2f}° en línea {i}")
                    continue

                apmag_start = posiciones.get('APmag_start')
                if apmag_start is None:
                    continue
                apmag = self._buscar_magnitud_corregida(linea, apmag_start, self.objeto)
                if apmag is None:
                    continue

                sbrt = 0.0
                if 'S-brt_start' in posiciones:
                    val = self._extraer_numero_desde_posicion(linea, posiciones['S-brt_start'])
                    if val is not None and 0 <= val <= 15:
                        sbrt = val
                
                # ── CORRECCIÓN: Leer Illu% correctamente ──────────────
                illu = 0.0
                if 'Illu_start' in posiciones:
                    val = self._extraer_numero_desde_posicion(linea, posiciones['Illu_start'])
                    if val is not None and 0 <= val <= 100:
                        illu = val
                    else:
                        # Intentar buscar específicamente Illu% en la línea
                        import re
                        match = re.search(r'Illu%\s+(\d+\.\d+)', linea)
                        if match:
                            try:
                                illu = float(match.group(1))
                            except:
                                pass
                
                angdiam = 0.0
                if 'Ang-diam_start' in posiciones:
                    val = self._extraer_numero_desde_posicion(linea, posiciones['Ang-diam_start'])
                    if val is not None and val > 0:
                        angdiam = val
                delta = 0.0
                if 'delta_start' in posiciones:
                    val = self._extraer_numero_desde_posicion(linea, posiciones['delta_start'])
                    if val is not None and 0 < val < 50:
                        delta = abs(val)

                elev_solar = -90.0
                if 'solar_start' in posiciones:
                    sol_val = self._extraer_numero_desde_posicion(linea, posiciones['solar_start'])
                    if sol_val is not None and -90 <= sol_val <= 90:
                        elev_solar = sol_val

                obs = Observacion(
                    timestamp=fecha_obs,
                    azimut=az,
                    elevacion=el,
                    magnitud=apmag,
                    brillo_superficial=sbrt,
                    iluminacion=illu,
                    angulo_diametro=angdiam,
                    distancia_au=delta,
                    elevacion_solar=elev_solar
                )
                observaciones.append(obs)

                if debug_filas and n_debug < debug_filas:
                    print(f"\n  🔎 DEBUG #{n_debug+1}:")
                    print(f"       UTC : {fecha_obs}")
                    print(f"       AZ  : {az:.4f}° | EL: {el:.4f}°")
                    print(f"       APmag: {apmag:.3f} | Illu%: {illu:.2f}%")
                    print(f"       Delta: {delta:.6f} UA")
                    print(f"       Sol : {elev_solar:.1f}°")
                    n_debug += 1

            except Exception as e:
                if debug_filas:
                    print(f"  ⚠️  Error línea {i}: {e}")
                continue

        barra.finalizar()
        print(f"  ✅ Observaciones cargadas: {len(observaciones)}")
        if observaciones:
            visibles = [o for o in observaciones if o.visible]
            print(f"  🌞 Sobre horizonte (EL>0): {len(visibles)}/{len(observaciones)}")
            if visibles:
                mejor = max(visibles, key=lambda o: o.elevacion)
                print(f"  ⭐ Máx elevación: {mejor.elevacion:.1f}° a las {mejor.timestamp.strftime('%H:%M')} UTC")
            else:
                print("  ⚠️  No hay observaciones con elevación positiva en el rango seleccionado.")
        return observaciones