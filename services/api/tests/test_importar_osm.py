"""Testes do importador de trechos do OSM com um mapa sintético (sem rede)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from importar_trechos_osm import Ruas, comprimento, dist, gerar_trecho  # noqa: E402

# Rua Principal (leste–oeste) cruzada por Rua A, Rua B e Rua C a cada ~100 m.
# Entre A e B há também um calçadão (Rua Pedestre) — ele delimita a quadra.
LAT = -25.43
PASSO = 0.001  # ~100 m de longitude nesta latitude


def _no(id_, lng, lat=LAT):
    return id_, {"lat": lat, "lon": lng}


def _via(nome, highway, nos):
    return {"type": "way", "tags": {"name": nome, "highway": highway},
            "nodes": [n for n, _ in nos], "geometry": [g for _, g in nos]}


def mapa_sintetico():
    principal = [_no(1, -49.270), _no(2, -49.270 - PASSO), _no(3, -49.270 - 2 * PASSO), _no(4, -49.270 - 3 * PASSO)]
    transversal = lambda id_base, lng: [_no(id_base, lng, LAT + 0.0005), _no(id_base + 1, lng), _no(id_base + 2, lng, LAT - 0.0005)]
    rua_a = transversal(10, -49.270)
    rua_b = transversal(20, -49.270 - PASSO)
    rua_c = transversal(30, -49.270 - 3 * PASSO)
    # As transversais compartilham o nó da Rua Principal.
    rua_a[1], rua_b[1], rua_c[1] = principal[0], principal[1], principal[3]
    pedestre = [_no(40, -49.270 - 2 * PASSO, LAT + 0.0005), principal[2]]
    return {"elements": [
        _via("Rua Principal", "residential", principal),
        _via("Rua A", "residential", rua_a),
        _via("Rua B", "residential", rua_b),
        _via("Rua C", "residential", rua_c),
        _via("Rua Pedestre", "pedestrian", pedestre),
    ]}


@pytest.fixture
def ruas():
    return Ruas(mapa_sintetico())


def ref(**extra):
    base = {"id": "t-x", "setor_id": "centro", "rua_osm": "Rua Principal", "entre": ["Rua A", "Rua B"],
            "tipo": "comum", "capacidade": 5}
    return {**base, **extra}


def test_quadra_comum_tira_5_m_de_cada_esquina(ruas):
    trecho = gerar_trecho(ruas, ref())
    linha = [tuple(c) for c in trecho["coordenadas"]]
    quadra = dist((LAT, -49.270), (LAT, -49.271))
    assert comprimento(linha) == pytest.approx(quadra - 10, abs=0.5)
    assert trecho["nome"] == "R. Principal, entre R. A e R. B"


def test_recusa_trecho_com_mais_de_uma_quadra(ruas):
    with pytest.raises(ValueError, match="outras esquinas"):
        gerar_trecho(ruas, ref(entre=["Rua B", "Rua C"]))  # o calçadão corta a quadra no meio


def test_recusa_rua_que_nao_cruza(ruas):
    with pytest.raises(ValueError, match="não cruza"):
        gerar_trecho(ruas, ref(entre=["Rua A", "Rua Inexistente"]))


def test_vaga_especial_fica_junto_a_esquina_indicada(ruas):
    trecho = gerar_trecho(ruas, ref(tipo="pcd", capacidade=2, junto_a="Rua B"))
    linha = [tuple(c) for c in trecho["coordenadas"]]
    assert comprimento(linha) == pytest.approx(11, abs=0.5)  # 2 vagas × 5,5 m
    assert dist(linha[-1], (LAT, -49.271)) == pytest.approx(5, abs=0.5)  # termina a 5 m da Rua B
