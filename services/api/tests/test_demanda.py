"""Modelo de disponibilidade sem dados ao vivo: Erlang B, dias e demanda dos estabelecimentos."""

from collections import Counter
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.config import FUSO
from app.main import criar_app
from app.modelos import Trecho
from app.servicos import demanda as dm
from app.servicos.demanda import ModeloDemanda, dia_e_hora, erlang_b, nivel

TERCA_10H = datetime(2026, 10, 20, 10, tzinfo=FUSO)
SEXTA_22H = datetime(2026, 10, 23, 22, tzinfo=FUSO)
SABADO_1H = datetime(2026, 10, 24, 1, tzinfo=FUSO)
DOMINGO_7H = datetime(2026, 10, 25, 7, tzinfo=FUSO)

# Duas quadras de 20 vagas: uma colada a 5 bares, outra a ~350 m deles.
PERTO = (-25.4400, -49.2900)
LONGE = (-25.4400, -49.2865)


class CatalogoDeTeste:
    def __init__(self):
        self._trechos = [
            Trecho(id=nome, setor_id="batel", nome=nome, tipo="comum", capacidade=20,
                   coordenadas=[(lat, lng - 0.0004), (lat, lng + 0.0004)])
            for nome, (lat, lng) in (("perto", PERTO), ("longe", LONGE))
        ]

    def trechos(self):
        return self._trechos

    def estacionamentos(self):
        return []


@pytest.fixture
def modelo():
    bares = [{"categoria": "bar", "lat": PERTO[0] + 0.0003, "lng": PERTO[1], "nome": f"Bar {i}"} for i in range(5)]
    return ModeloDemanda(CatalogoDeTeste(), pois=bares)


def test_erlang_b_valores_conhecidos():
    assert erlang_b(1, 2.0) == pytest.approx(2 / 3)       # B(1, A) = A / (1 + A)
    assert erlang_b(20, 20.0) == pytest.approx(0.1588, abs=1e-3)
    assert erlang_b(10, 0) == 0
    assert erlang_b(10, 5) < erlang_b(10, 10) < erlang_b(10, 20)


def test_madrugada_conta_como_a_noite_anterior():
    assert dia_e_hora(SABADO_1H) == ("sex", 25.0, "Sexta")
    assert dia_e_hora(TERCA_10H)[0] == "seg_qui"
    assert dia_e_hora(DOMINGO_7H)[0] == "dom"


def test_demanda_de_cada_estabelecimento_se_conserva(modelo):
    parcelas = modelo._parcelas
    total = sum(carros for alvo in parcelas.values() for _, carros in alvo)
    assert total == pytest.approx(5 * dm.CATEGORIAS["bar"].carros_no_pico * dm.FATOR_COBERTURA_OSM)
    assert sum(c for _, c in parcelas["perto"]) > sum(c for _, c in parcelas["longe"])


def test_perto_dos_bares_e_mais_dificil_na_sexta_a_noite(modelo):
    perto = modelo.estimar("perto", 20, SEXTA_22H)
    longe = modelo.estimar("longe", 20, SEXTA_22H)
    assert perto.prob_livre < longe.prob_livre
    assert nivel(perto.prob_livre) == "dificil"
    assert perto.explicacao == "Sexta, 22h · perto de 5 bares"
    assert modelo.estimar("perto", 20, DOMINGO_7H).prob_livre > perto.prob_livre


def test_bar_fechado_nao_entra_na_explicacao(modelo):
    assert modelo.estimar("perto", 20, TERCA_10H).explicacao == "Terça, 10h · pouco movimento previsto por perto"


def test_niveis():
    assert [nivel(p) for p in (0.95, 0.85, 0.6, 0.5, 0.3)] == ["facil", "facil", "moderado", "moderado", "dificil"]


def test_batel_real_sexta_a_noite_e_mais_dificil_que_domingo_cedo():
    niveis = {}
    for nome, momento in (("sexta", SEXTA_22H), ("domingo", DOMINGO_7H)):
        cliente = TestClient(criar_app(relogio=lambda m=momento: m))
        vagas = cliente.get("/vagas", params={"lat": -25.4430, "lng": -49.2909, "raio_m": 1500}).json()
        niveis[nome] = Counter(v["estado"]["nivel"] for v in vagas if v["id"].startswith("osm-q"))
    assert niveis["sexta"]["facil"] < niveis["domingo"]["facil"]
    assert niveis["sexta"]["dificil"] > niveis["domingo"]["dificil"]
