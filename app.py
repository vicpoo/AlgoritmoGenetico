# app.py
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session
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
        latitud = float(data['latitud'])
        longitud = float(data['longitud'])
        offset_utc = int(data.get('offset_utc', -6))
        fecha_str = data['fecha']
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d')
        objeto = data['objeto'].lower()
        if objeto not in config.objetos_soportados:
            return jsonify({'error': f'Objeto no soportado: {objeto}'}), 400
        tipo_tel = data.get('tipo_telescopio', 'reflector')
        apertura = float(data['apertura_mm'])
        aumentos = [int(x.strip()) for x in data['aumentos'].split(',')]
        estado_cielo = data.get('estado_cielo', 'despejado')
        luna_llena = data.get('luna_llena') == 'true'
        seeing = data.get('seeing', 'bueno')

        telescopio = Telescopio(tipo_tel, apertura, aumentos)
        condiciones = CondicionesAmbientales(estado_cielo, luna_llena, seeing)
        core = AstroOptiCore()
        resultados_raw = core.optimizar(latitud, longitud, fecha, objeto,
                                        telescopio, condiciones, offset_utc=offset_utc,
                                        debug_filas=0)
        resultados_json = []
        for r in resultados_raw:
            v = r['ventana']
            mo = r['momento_optimo']
            # Convertir a hora local
            def localize(dt):
                return dt + timedelta(hours=offset_utc)
            res = {
                'numero': r['numero'],
                'calidad_pct': round(r['calidad_pct'], 1),
                'categoria': r['categoria'],
                'inicio': localize(v.inicio).isoformat(),
                'fin': localize(v.fin).isoformat(),
                'duracion_min': round(v.duracion_minutos, 1),
                'aumento': r['aumento'],
                'offset_utc': offset_utc
            }
            if mo:
                res['optimo'] = {
                    'hora': localize(mo.timestamp).isoformat(),
                    'altitud': round(mo.elevacion, 1),
                    'azimut': round(mo.azimut, 1),
                    'magnitud': round(mo.magnitud, 2),
                    'iluminacion': round(mo.iluminacion, 1),
                    'diametro': round(mo.angulo_diametro, 2),
                    'distancia': round(mo.distancia_au, 6)
                }
            resultados_json.append(res)
        convergencia = {
            'mejor': core.algoritmo.historial_convergencia,
            'promedio': core.algoritmo.historial_promedio
        }
        return jsonify({'success': True, 'resultados': resultados_json, 'convergencia': convergencia})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)