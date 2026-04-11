# config.py
from dataclasses import dataclass, field
from typing import List, Dict, Tuple


@dataclass
class Config:
    # ── Parámetros del algoritmo genético ─────────────────────────────
    poblacion_size:   int   = 50
    generaciones:     int   = 100
    tasa_mutacion:    float = 0.15
    tasa_cruce:       float = 0.80
    elitismo:         int   = 2
    tamano_torneo:    int   = 3

    # ── Restricciones físicas ──────────────────────────────────────────
    elevacion_minima:          float = 10.0
    duracion_minima_minutos:   int   = 10
    duracion_maxima_minutos:   int   = 240

    # Ángulo solar mínimo para cielo astronómico oscuro (grados bajo horizonte)
    angulo_solar_oscuro: float = -18.0

    # ── Umbrales de calidad ────────────────────────────────────────────
    umbral_excelente: float = 0.72
    umbral_buena:     float = 0.52
    umbral_aceptable: float = 0.32

    # ── Objetos ───────────────────────────────────────────────────────
    objetos_soportados: List[str] = field(default_factory=lambda: [
        'mercurio', 'venus', 'marte', 'jupiter',
        'saturno', 'urano', 'neptuno', 'luna'
    ])

    # Objetos que pueden (o deben) observarse de día
    objetos_diurnos: List[str] = field(default_factory=lambda: [
        'mercurio', 'venus'   # elongación máxima puede estar cerca del crepúsculo
        # 'sol' si se agrega en el futuro
    ])

    carpeta_objeto: Dict[str, str] = field(default_factory=lambda: {
        'mercurio': 'Mercurio', 'venus':   'Venus',
        'marte':    'Marte',    'jupiter': 'Jupiter',
        'saturno':  'Saturno',  'urano':   'Urano',
        'neptuno':  'Neptuno',  'luna':    'Luna',
    })

    # ── Rangos de aumento recomendado por objeto ───────────────────────
    rangos_aumento: Dict[str, Tuple[int, int]] = field(default_factory=lambda: {
        'mercurio': (50,  150), 'venus':   (50,  150),
        'marte':    (150, 300), 'jupiter': (100, 250),
        'saturno':  (100, 250), 'urano':   (150, 300),
        'neptuno':  (200, 400), 'luna':    (50,  200),
    })

    # ── Rangos de magnitud aparente (más negativo = más brillante) ─────
    rangos_magnitud: Dict[str, Tuple[float, float]] = field(default_factory=lambda: {
        'mercurio': (-2.0,  5.5),
        'venus':    (-4.9, -3.0),
        'marte':    (-2.9,  1.6),
        'jupiter':  (-2.9, -1.6),
        'saturno':  (-0.5,  1.3),
        'urano':    ( 5.4,  6.1),
        'neptuno':  ( 7.8,  8.0),
        'luna':     (-14.0, -2.0),
    })

    # ── Paso temporal recomendado por objeto (minutos) ─────────────────
    paso_recomendado: Dict[str, int] = field(default_factory=lambda: {
        'mercurio': 10, 'venus':   10, 'marte':  30,
        'jupiter':  60, 'saturno': 60, 'urano':  60,
        'neptuno':  60, 'luna':    10,
    })

    # ── Pesos para la función de fitness (referencia documental) ──────
    # Los pesos reales están en genetic_algorithm.py
    fitness_weights: Dict[str, Dict[str, float]] = field(default_factory=lambda: {
        'luna': {
            'masa_aire':    0.30,
            'oscuridad':    0.15,
            'fase_luna':    0.25,   # Fase más pesada para la Luna
            'magnitud':     0.08,
            'telescopio':   0.10,
            'duracion':     0.07,
            'tendencia':    0.05,
            'orientacion':  0.00,
        },
        'default': {
            'masa_aire':    0.30,
            'oscuridad':    0.20,
            'lunar':        0.20,
            'magnitud':     0.12,
            'telescopio':   0.12,
            'duracion':     0.10,
            'tendencia':    0.08,
            'orientacion':  0.08,
        },
    })


config = Config()