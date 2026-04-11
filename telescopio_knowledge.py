# telescopio_knowledge.py
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

class TelescopioKnowledge:
    def __init__(self, archivo_json: str = "telescopio_knowledge.json"):
        self.datos: Dict[str, List[dict]] = {}
        self._cargar(archivo_json)

    def _cargar(self, archivo: str):
        try:
            ruta = Path(archivo)
            if not ruta.exists():
                print(f"  ⚠️ Archivo {archivo} no encontrado, usando valores por defecto")
                return
            with open(ruta, 'r', encoding='utf-8') as f:
                self.datos = json.load(f)
            print(f"  📚 Cargada base de conocimiento de telescopios: {len(self.datos)} objetos")
        except Exception as e:
            print(f"  ⚠️ Error cargando {archivo}: {e}")

    def predecir_calidad(self, objeto: str, apertura_mm: float, tipo: str, aumento: int) -> float:
        """Predice la calidad esperada basada en datos empíricos"""
        objeto = objeto.lower()
        if objeto not in self.datos:
            return 0.5  # Valor neutral si no hay datos
        
        registros = self.datos[objeto]
        mejor_match = None
        mejor_puntaje = 0.0
        
        for reg in registros:
            # Calcular similitud
            diff_apertura = abs(reg['apertura_mm'] - apertura_mm) / max(apertura_mm, reg['apertura_mm'])
            mismo_tipo = 1.0 if reg['tipo'] == tipo else 0.5
            
            # Verificar si el aumento está en rango
            aumento_ok = (reg['aumentos_min'] <= aumento <= reg['aumentos_max']) if aumento else True
            if not aumento_ok:
                continue
                
            # Puntaje de similitud
            puntaje = (1.0 - min(0.5, diff_apertura)) * mismo_tipo * reg.get('peso', 0.5)
            
            if puntaje > mejor_puntaje:
                mejor_puntaje = puntaje
                mejor_match = reg
        
        if mejor_match:
            resultado = mejor_match['resultado']
            mapa = {'muy_bien': 0.9, 'bien': 0.7, 'regular': 0.5, 'mal': 0.3}
            return mapa.get(resultado, 0.5)
        
        return 0.5