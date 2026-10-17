"""Catálogo de vagas (setores EstaR, trechos de rua, estacionamentos, parceiros).

Fontes carregadas:
- app/dados_mock/  — Centro e parceiros fictícios (MVP);
- app/dados_osm/   — Batel com dados reais (gerados por scripts/gerar_batel_osm.py).

A API depende só da interface `Catalogo`. O mapeamento colaborativo altera o catálogo em
memória (regime de um trecho, preço ou fechamento de um estacionamento, novos
estacionamentos). Depois, uma implementação sobre o PostGIS mantém a mesma interface.
"""

import json
import threading
from pathlib import Path
from typing import Any, Optional, Protocol

from app.geo import distancia_ate_linha_m, distancia_m
from app.modelos import Estacionamento, Parceiro, Setor, Trecho

PASTA_MOCK = Path(__file__).parent / "dados_mock"
PASTA_OSM = Path(__file__).parent / "dados_osm"


class Catalogo(Protocol):
    def setores(self) -> list[Setor]: ...
    def setor(self, setor_id: str) -> Optional[Setor]: ...
    def trechos(self) -> list[Trecho]: ...
    def trecho(self, trecho_id: str) -> Optional[Trecho]: ...
    def estacionamentos(self) -> list[Estacionamento]: ...
    def estacionamento(self, estacionamento_id: str) -> Optional[Estacionamento]: ...
    def parceiros(self) -> list[Parceiro]: ...
    def atualizar_trecho(self, trecho_id: str, **campos: Any) -> Trecho: ...
    def atualizar_estacionamento(self, estacionamento_id: str, **campos: Any) -> Estacionamento: ...
    def adicionar_estacionamento(self, estacionamento: Estacionamento) -> None: ...
    def distancia_ate(self, alvo_id: str, lat: float, lng: float) -> Optional[float]: ...


def _carregar(pasta: Path, nome: str) -> list[dict]:
    arquivo = pasta / nome
    return json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else []


class CatalogoArquivos:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._setores = {s["id"]: Setor(**s) for s in _carregar(PASTA_MOCK, "setores.json")}
        self._trechos = {
            t["id"]: Trecho(**t)
            for t in _carregar(PASTA_MOCK, "trechos.json") + _carregar(PASTA_OSM, "batel_trechos.json")
        }
        self._estacionamentos = {
            e["id"]: Estacionamento(**e)
            for e in _carregar(PASTA_MOCK, "estacionamentos.json") + _carregar(PASTA_OSM, "batel_estacionamentos.json")
        }
        self._parceiros = {p["id"]: Parceiro(**p) for p in _carregar(PASTA_MOCK, "parceiros.json")}

    def setores(self) -> list[Setor]:
        return list(self._setores.values())

    def setor(self, setor_id: str) -> Optional[Setor]:
        return self._setores.get(setor_id)

    def trechos(self) -> list[Trecho]:
        with self._lock:
            return list(self._trechos.values())

    def trecho(self, trecho_id: str) -> Optional[Trecho]:
        return self._trechos.get(trecho_id)

    def estacionamentos(self) -> list[Estacionamento]:
        with self._lock:
            return list(self._estacionamentos.values())

    def estacionamento(self, estacionamento_id: str) -> Optional[Estacionamento]:
        return self._estacionamentos.get(estacionamento_id)

    def parceiros(self) -> list[Parceiro]:
        return list(self._parceiros.values())

    def atualizar_trecho(self, trecho_id: str, **campos: Any) -> Trecho:
        with self._lock:
            novo = self._trechos[trecho_id].model_copy(update=campos)
            self._trechos[trecho_id] = novo
            return novo

    def atualizar_estacionamento(self, estacionamento_id: str, **campos: Any) -> Estacionamento:
        with self._lock:
            novo = self._estacionamentos[estacionamento_id].model_copy(update=campos)
            self._estacionamentos[estacionamento_id] = novo
            return novo

    def adicionar_estacionamento(self, estacionamento: Estacionamento) -> None:
        with self._lock:
            self._estacionamentos[estacionamento.id] = estacionamento

    def distancia_ate(self, alvo_id: str, lat: float, lng: float) -> Optional[float]:
        """Distância (m) do ponto até a vaga: até a linha do trecho ou o ponto do estacionamento."""
        trecho = self.trecho(alvo_id)
        if trecho:
            return distancia_ate_linha_m(lat, lng, trecho.coordenadas)
        est = self.estacionamento(alvo_id)
        if est:
            return distancia_m(lat, lng, est.lat, est.lng)
        return None
