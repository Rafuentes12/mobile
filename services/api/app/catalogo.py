"""Catálogo de vagas (setores EstaR, trechos de rua, estacionamentos, parceiros).

A API depende só da interface `Catalogo`. Hoje a implementação lê os JSONs mockados
de `app/dados_mock/`; depois, uma `CatalogoPostgres` lerá as mesmas entidades do
PostGIS sem mudar os serviços.
"""

import json
from pathlib import Path
from typing import Optional, Protocol

from app.modelos import Estacionamento, Parceiro, Setor, Trecho

PASTA_MOCK = Path(__file__).parent / "dados_mock"


class Catalogo(Protocol):
    def setores(self) -> list[Setor]: ...
    def setor(self, setor_id: str) -> Optional[Setor]: ...
    def trechos(self) -> list[Trecho]: ...
    def trecho(self, trecho_id: str) -> Optional[Trecho]: ...
    def estacionamentos(self) -> list[Estacionamento]: ...
    def estacionamento(self, estacionamento_id: str) -> Optional[Estacionamento]: ...
    def parceiros(self) -> list[Parceiro]: ...


def _carregar(nome: str) -> list[dict]:
    return json.loads((PASTA_MOCK / nome).read_text(encoding="utf-8"))


class CatalogoMock:
    def __init__(self) -> None:
        self._setores = {s["id"]: Setor(**s) for s in _carregar("setores.json")}
        self._trechos = {t["id"]: Trecho(**t) for t in _carregar("trechos.json")}
        self._estacionamentos = {e["id"]: Estacionamento(**e) for e in _carregar("estacionamentos.json")}
        self._parceiros = {p["id"]: Parceiro(**p) for p in _carregar("parceiros.json")}

    def setores(self) -> list[Setor]:
        return list(self._setores.values())

    def setor(self, setor_id: str) -> Optional[Setor]:
        return self._setores.get(setor_id)

    def trechos(self) -> list[Trecho]:
        return list(self._trechos.values())

    def trecho(self, trecho_id: str) -> Optional[Trecho]:
        return self._trechos.get(trecho_id)

    def estacionamentos(self) -> list[Estacionamento]:
        return list(self._estacionamentos.values())

    def estacionamento(self, estacionamento_id: str) -> Optional[Estacionamento]:
        return self._estacionamentos.get(estacionamento_id)

    def parceiros(self) -> list[Parceiro]:
        return list(self._parceiros.values())
