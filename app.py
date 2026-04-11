# app.py
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
import traceback

from astroopti_core import AstroOptiCore
from models import Telescopio, CondicionesAmbientales
from config import config

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui'


@app.route('/')
def index():
    return render_template('index.html', objetos=config.objetos_soportados)


@app.route('/optimizar', methods=['POST'])
def optimizar():
    try:
        data = request.get_json()

        # ── Leer y validar entradas ────────────────────────────────────
        latitud    = float(data['latitud'])
        longitud   = float(data['longitud'])
        offset_utc = int(data.get('offset_utc', -6))
        fecha_str  = data['fecha']
        fecha      = datetime.strptime(fecha_str, '%Y-%m-%d')
        objeto     = data['objeto'].lower()

        if objeto not in config.objetos_soportados:
            return jsonify({'error': f'Objeto no soportado: {objeto}'}), 400

        tipo_tel     = data.get('tipo_telescopio', 'reflector')
        apertura     = float(data['apertura_mm'])
        aumentos_raw = data.get('aumentos', '50,100,150,200,250,300')
        aumentos     = [int(x.strip()) for x in aumentos_raw.split(',') if x.strip()]
        estado_cielo = data.get('estado_cielo', 'despejado')
        fase_lunar   = data.get('fase_lunar', 'nueva')
        seeing       = data.get('seeing', 'bueno')

        telescopio  = Telescopio(tipo_tel, apertura, aumentos)
        condiciones = CondicionesAmbientales(estado_cielo, fase_lunar, seeing)
        core        = AstroOptiCore()

        resultados_raw = core.optimizar(
            latitud, longitud, fecha, objeto,
            telescopio, condiciones,
            offset_utc=offset_utc,
            debug_filas=0
        )

        # ── Serializar resultados ──────────────────────────────────────
        def localize(dt: datetime) -> str:
            return (dt + timedelta(hours=offset_utc)).isoformat()

        resultados_json = []
        for r in resultados_raw:
            v  = r['ventana']
            mo = r['momento_optimo']

            res = {
                'numero':       r['numero'],
                'calidad_pct':  round(r['calidad_pct'], 1),
                'categoria':    r['categoria'],
                'inicio':       localize(v.inicio),
                'fin':          localize(v.fin),
                'duracion_min': round(v.duracion_minutos, 1),
                'aumento':      r['aumento'],
                'offset_utc':   offset_utc,
                'objeto':       objeto,
                'fase_lunar_cielo': r.get('fase_lunar_cielo', ''),
                'optimo': None,
            }

            if mo:
                res['optimo'] = {
                    'hora':         localize(mo['timestamp']),
                    'altitud':      round(mo['elevacion'], 1),
                    'azimut':       round(mo['azimut'], 1),
                    'magnitud':     round(mo['magnitud'], 2),
                    'fase_objeto_pct': round(mo.get('fase_objeto_pct', mo.get('iluminacion', 0)), 1),
                    'diametro':     round(mo['angulo_diametro'], 2),
                    'distancia_sol_au':    round(mo.get('distancia_sol_au', mo.get('distancia_au', 0)), 4),
                    'distancia_tierra_au': round(mo.get('distancia_tierra_au', 0), 4),
                    'fase_lunar_cielo': mo.get('fase_lunar_cielo', ''),
                }

            resultados_json.append(res)

        # ── Datos de convergencia del GA ───────────────────────────────
        convergencia = {
            'mejor':    core.algoritmo.historial_convergencia or [0.5] * 100,
            'promedio': core.algoritmo.historial_promedio     or [0.3] * 100,
            'duracion': core.algoritmo.historial_duracion     or [],
            'aumento':  core.algoritmo.historial_aumento      or [],
        }

        return jsonify({
            'success':     True,
            'resultados':  resultados_json,
            'convergencia': convergencia,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)