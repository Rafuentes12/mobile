"""Cálculos geográficos simples.

No MVP mockado a busca por raio é feita em memória com Haversine. Com o banco real,
ela vira uma consulta PostGIS (ST_DWithin) — ver infra/db/schema.sql.
"""

import math

RAIO_TERRA_M = 6_371_000
FATOR_CAMINHADA = 1.3  # caminhada real ≈ linha reta × 1,3 (aproximação do planejamento)
VELOCIDADE_CAMINHADA_M_MIN = 80


def distancia_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RAIO_TERRA_M * math.asin(math.sqrt(a))


def caminhada(lat1: float, lng1: float, lat2: float, lng2: float) -> tuple[float, float]:
    """Retorna (metros, minutos) estimados de caminhada."""
    metros = distancia_m(lat1, lng1, lat2, lng2) * FATOR_CAMINHADA
    return metros, metros / VELOCIDADE_CAMINHADA_M_MIN
