# config.py
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

@dataclass
class Config:
    poblacion_size: int = 50
    generaciones: int = 100
    tasa_mutacion: float = 0.15
    tasa_cruce: float = 0.8
    elitismo: int = 2
    tamano_torneo: int = 3

    elevacion_minima: float = 10.0
    duracion_minima_minutos: int = 10
    duracion_maxima_minutos: int = 240

    umbral_excelente: float = 0.8
    umbral_buena: float = 0.6
    umbral_aceptable: float = 0.4

    objetos_soportados: List[str] = field(default_factory=lambda: [
        'mercurio', 'venus', 'marte', 'jupiter',
        'saturno', 'urano', 'neptuno', 'luna'
    ])

    carpeta_objeto: Dict[str, str] = field(default_factory=lambda: {
        'mercurio': 'Mercurio', 'venus': 'Venus', 'marte': 'Marte',
        'jupiter': 'Jupiter', 'saturno': 'Saturno', 'urano': 'Urano',
        'neptuno': 'Neptuno', 'luna': 'Luna'
    })

    rangos_aumento: Dict[str, Tuple[int, int]] = field(default_factory=lambda: {
        'mercurio': (50, 150), 'venus': (50, 150),
        'marte': (150, 300), 'jupiter': (100, 250),
        'saturno': (100, 250), 'urano': (150, 300),
        'neptuno': (200, 400), 'luna': (50, 200)
    })

    rangos_magnitud: Dict[str, Tuple[float, float]] = field(default_factory=lambda: {
        'mercurio': (-2.0, 5.5), 'venus': (-4.9, -3.0),
        'marte': (-2.9, 1.6), 'jupiter': (-2.9, -1.6),
        'saturno': (-0.5, 1.3), 'urano': (5.4, 6.1),
        'neptuno': (7.8, 8.0), 'luna': (-14.0, -2.0),
    })

    paso_recomendado: Dict[str, int] = field(default_factory=lambda: {
        'mercurio': 10, 'venus': 10, 'marte': 30,
        'jupiter': 60, 'saturno': 60, 'urano': 60,
        'neptuno': 60, 'luna': 10
    })


config = Config()