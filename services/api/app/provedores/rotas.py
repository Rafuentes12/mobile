"""Tempo de carro entre dois pontos.

Hoje: `RotasEstimadas`, uma estimativa por distância (sem chamadas externas).
Depois: um `RotasOSRM` com a mesma interface, consultando um OSRM próprio com dados
do OpenStreetMap (ver infra/README.md). O planejamento evita o Route Matrix do Google
aqui por causa do custo por elemento.
"""

from typing import Protocol

from app.geo import distancia_m
from app.modelos import Coordenada

FATOR_SINUOSIDADE = 1.4      # ruas não são linha reta
VELOCIDADE_MEDIA_KMH = 22    # trânsito urbano no centro
TEMPO_FIXO_MIN = 1.0         # sair da vaga, semáforos etc.


class ProvedorRotas(Protocol):
    def tempo_carro_min(self, origem: Coordenada, destino: Coordenada) -> float: ...


class RotasEstimadas:
    def tempo_carro_min(self, origem: Coordenada, destino: Coordenada) -> float:
        metros = distancia_m(origem.lat, origem.lng, destino.lat, destino.lng) * FATOR_SINUOSIDADE
        return TEMPO_FIXO_MIN + metros / (VELOCIDADE_MEDIA_KMH * 1000 / 60)
