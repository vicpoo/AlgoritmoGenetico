# app.py
"""
API REST de AstroOpti.

IMPORTANTE: este archivo NO modifica el algoritmo genético ni su lógica.
Solo cambia la capa de transporte: antes servía HTML (render_template),
ahora es una API JSON pura para ser consumida desde la app Flutter.

Cambios respecto a la versión web:
  - Se elimina render_template / la ruta que servía index.html.
  - Se agrega flask-cors para permitir peticiones desde la app móvil.
  - Se agregan validaciones de entrada más estrictas (400 en vez de 500
    cuando falta un campo, porque un cliente Flutter necesita errores
    predecibles para mostrar mensajes al usuario).
  - Se agregan endpoints auxiliares: /health y /objetos (para que la app
    pueda poblar el dropdown de objetos sin hardcodear la lista).
  - debug=True se quita del app.run(); en producción se usa Gunicorn
    (ver Procfile / wsgi.py).
"""
import traceback
from datetime import datetime, timedelta

from flask import Flask, request, jsonify
from flask_cors import CORS

from astroopti_core import AstroOptiCore
from models import Telescopio, CondicionesAmbientales
from config import config

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui'

# CORS abierto por ahora; en producción puedes restringirlo a tu dominio
# o simplemente dejarlo así si solo la app Flutter (no un navegador) consume la API.
CORS(app)


# ──────────────────────────────────────────────────────────────────────────
# Helpers de validación (nuevos — no existían en la versión web porque el
# HTML con required="" en los <input> ya evitaba mandar campos vacíos)
# ──────────────────────────────────────────────────────────────────────────

class ErrorValidacion(Exception):
    """Error de validación de entrada -> se traduce a HTTP 400."""
    pass


def _requerido(data: dict, campo: str):
    if campo not in data or data[campo] in (None, ''):
        raise ErrorValidacion(f"Falta el campo requerido: '{campo}'")
    return data[campo]


def _validar_payload(data: dict):
    """Valida y normaliza el payload de /optimizar. Lanza ErrorValidacion con
    mensajes claros para que la app Flutter pueda mostrarlos directamente."""

    try:
        latitud = float(_requerido(data, 'latitud'))
    except (ValueError, TypeError):
        raise ErrorValidacion("'latitud' debe ser un número")
    if not (-90.0 <= latitud <= 90.0):
        raise ErrorValidacion("'latitud' debe estar entre -90 y 90")

    try:
        longitud = float(_requerido(data, 'longitud'))
    except (ValueError, TypeError):
        raise ErrorValidacion("'longitud' debe ser un número")
    if not (-180.0 <= longitud <= 180.0):
        raise ErrorValidacion("'longitud' debe estar entre -180 y 180")

    try:
        offset_utc = int(data.get('offset_utc', -6))
    except (ValueError, TypeError):
        raise ErrorValidacion("'offset_utc' debe ser un entero")

    fecha_str = _requerido(data, 'fecha')
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d')
    except ValueError:
        raise ErrorValidacion("'fecha' debe tener formato YYYY-MM-DD")

    objeto = str(_requerido(data, 'objeto')).lower()
    if objeto not in config.objetos_soportados:
        raise ErrorValidacion(
            f"Objeto no soportado: '{objeto}'. "
            f"Soportados: {', '.join(config.objetos_soportados)}"
        )

    tipo_tel = data.get('tipo_telescopio', 'reflector')
    if tipo_tel not in ('reflector', 'refractor', 'catadioptrico'):
        raise ErrorValidacion(
            "'tipo_telescopio' debe ser 'reflector', 'refractor' o 'catadioptrico'"
        )

    try:
        apertura = float(_requerido(data, 'apertura_mm'))
    except (ValueError, TypeError):
        raise ErrorValidacion("'apertura_mm' debe ser un número")
    if apertura <= 0:
        raise ErrorValidacion("'apertura_mm' debe ser mayor a 0")

    aumentos_raw = data.get('aumentos', '50,100,150,200,250,300')
    try:
        if isinstance(aumentos_raw, list):
            aumentos = [int(x) for x in aumentos_raw]
        else:
            aumentos = [int(x.strip()) for x in str(aumentos_raw).split(',') if x.strip()]
    except ValueError:
        raise ErrorValidacion(
            "'aumentos' debe ser una lista de enteros o string separado por comas, ej: '50,100,150'"
        )
    if not aumentos:
        raise ErrorValidacion("'aumentos' no puede estar vacío")

    estado_cielo = data.get('estado_cielo', 'despejado')
    if estado_cielo not in ('despejado', 'parcialmente_nublado', 'nublado'):
        raise ErrorValidacion(
            "'estado_cielo' debe ser 'despejado', 'parcialmente_nublado' o 'nublado'"
        )

    fase_lunar = data.get('fase_lunar', 'nueva')
    fases_validas = (
        'nueva', 'creciente_inicial', 'cuarto_creciente', 'gibosa_creciente',
        'llena', 'gibosa_menguante', 'cuarto_menguante', 'menguante_inicial'
    )
    if fase_lunar not in fases_validas:
        raise ErrorValidacion(f"'fase_lunar' debe ser una de: {', '.join(fases_validas)}")

    seeing = data.get('seeing', 'bueno')
    if seeing not in ('bueno', 'regular', 'malo'):
        raise ErrorValidacion("'seeing' debe ser 'bueno', 'regular' o 'malo'")

    return {
        'latitud': latitud,
        'longitud': longitud,
        'offset_utc': offset_utc,
        'fecha': fecha,
        'objeto': objeto,
        'tipo_telescopio': tipo_tel,
        'apertura_mm': apertura,
        'aumentos': aumentos,
        'estado_cielo': estado_cielo,
        'fase_lunar': fase_lunar,
        'seeing': seeing,
    }


# ──────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    """Endpoint simple para que AWS (ALB/Elastic Beanstalk) y la app
    verifiquen que el servicio está vivo."""
    return jsonify({'status': 'ok'})


@app.route('/objetos', methods=['GET'])
def objetos():
    """Devuelve la lista de objetos soportados, para poblar el selector
    en Flutter sin hardcodearla en el cliente."""
    return jsonify({'objetos': config.objetos_soportados})


@app.route('/optimizar', methods=['POST'])
def optimizar():
    try:
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({'error': 'El cuerpo de la petición debe ser JSON válido'}), 400

        try:
            v = _validar_payload(data)
        except ErrorValidacion as e:
            return jsonify({'error': str(e)}), 400

        telescopio  = Telescopio(v['tipo_telescopio'], v['apertura_mm'], v['aumentos'])
        condiciones = CondicionesAmbientales(v['estado_cielo'], v['fase_lunar'], v['seeing'])
        core        = AstroOptiCore()

        # ── Llamada al algoritmo genético: SIN CAMBIOS ──────────────────
        resultados_raw = core.optimizar(
            v['latitud'], v['longitud'], v['fecha'], v['objeto'],
            telescopio, condiciones,
            offset_utc=v['offset_utc'],
            debug_filas=0
        )

        # ── Serializar resultados (idéntico a la versión web) ───────────
        def localize(dt: datetime) -> str:
            return (dt + timedelta(hours=v['offset_utc'])).isoformat()

        resultados_json = []
        for r in resultados_raw:
            ventana = r['ventana']
            mo = r['momento_optimo']

            res = {
                'numero':       r['numero'],
                'calidad_pct':  round(r['calidad_pct'], 1),
                'categoria':    r['categoria'],
                'inicio':       localize(ventana.inicio),
                'fin':          localize(ventana.fin),
                'duracion_min': round(ventana.duracion_minutos, 1),
                'aumento':      r['aumento'],
                'offset_utc':   v['offset_utc'],
                'objeto':       v['objeto'],
                'fase_lunar_cielo': r.get('fase_lunar_cielo', ''),
                'optimo': None,
            }

            if mo:
                ts_utc = mo['timestamp']
                ts_loc = ts_utc + timedelta(hours=v['offset_utc'])

                res['optimo'] = {
                    'hora_utc': ts_utc.isoformat(),
                    'hora_loc': ts_loc.isoformat(),
                    'altitud': round(mo['elevacion'], 1),
                    'azimut': round(mo['azimut'], 1),
                    'magnitud': round(mo['magnitud'], 2),
                    'fase_objeto_pct': round(mo.get('fase_objeto_pct', mo.get('iluminacion', 0)), 1),
                    'diametro': round(mo['angulo_diametro'], 2),
                    'distancia_sol_au': round(mo.get('distancia_sol_au', mo.get('distancia_au', 0)), 4),
                    'distancia_tierra_au': round(mo.get('distancia_tierra_au', 0), 4),
                    'fase_lunar_cielo': mo.get('fase_lunar_cielo', ''),
                }

            resultados_json.append(res)

        return jsonify({
            'success': True,
            'resultados': resultados_json,
        })

    except ValueError as e:
        # Errores esperados del core (ej: sin observaciones para esa fecha/objeto)
        traceback.print_exc()
        return jsonify({'error': str(e)}), 400

    except Exception as e:
        # Cualquier otro error inesperado -> 500, pero sin filtrar traceback al cliente
        traceback.print_exc()
        return jsonify({'error': 'Error interno del servidor. Intenta de nuevo más tarde.'}), 500


@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint no encontrado'}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({'error': 'Método no permitido en este endpoint'}), 405


if __name__ == '__main__':
    # Solo para desarrollo local. En AWS se usa Gunicorn (ver wsgi.py / Procfile).
    app.run(host='0.0.0.0', port=5000, debug=False)