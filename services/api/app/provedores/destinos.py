"""Busca de destinos (endereços e pontos de interesse).

Hoje: `DestinosMock`, que procura numa lista fixa de lugares de Curitiba.
Depois: um `DestinosGooglePlaces` com a mesma interface, chamando o Places API (New)
com session token pelo servidor — assim a chave do Google não fica no app.
"""

import json
import unicodedata
from typing import Optional, Protocol

from app.catalogo import PASTA_MOCK
from app.modelos import Destino


class ProvedorDestinos(Protocol):
    def buscar(self, texto: str, limite: int = 5) -> list[Destino]: ...
    def obter(self, destino_id: str) -> Optional[Destino]: ...


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower().strip()


class DestinosMock:
    def __init__(self) -> None:
        dados = json.loads((PASTA_MOCK / "destinos.json").read_text(encoding="utf-8"))
        self._destinos = [Destino(**d) for d in dados]

    def buscar(self, texto: str, limite: int = 5) -> list[Destino]:
        termo = _normalizar(texto)
        if not termo:
            return self._destinos[:limite]
        achados = [d for d in self._destinos if termo in _normalizar(f"{d.nome} {d.endereco}")]
        return achados[:limite]

    def obter(self, destino_id: str) -> Optional[Destino]:
        return next((d for d in self._destinos if d.id == destino_id), None)
