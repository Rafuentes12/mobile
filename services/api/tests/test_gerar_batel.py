"""Gerador das vagas reais do Batel: regras com um mapa sintético e sanidade dos dados gerados."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from gerar_batel_osm import (  # noqa: E402
    FATOR_GARAGENS_NAO_MAPEADAS,
    SAIDA,
    ElementosBatel,
    dividir,
    estimar_quadra,
    quadras_da_rua,
    regime_da_quadra,
)
from osm_comum import dist, ponto_no_meio, ponto_no_poligono  # noqa: E402

LAT = -25.44
PASSO = 0.0025  # ~250 m de longitude


def _via(id_, nome, highway, pontos, **tags):
    nos = [p[0] for p in pontos]
    geometria = [{"lat": p[1], "lon": p[2]} for p in pontos]
    tags = {"highway": highway, **({"name": nome} if nome else {}), **tags}
    return {"type": "way", "id": id_, "tags": tags, "nodes": nos, "geometry": geometria}


def mapa(tags_principal=None, extras=()):
    """Rua Principal com duas quadras de ~250 m, cortada pelas ruas A, B e C."""
    p = [(1, LAT, -49.29), (2, LAT, -49.29 - PASSO), (3, LAT, -49.29 - 2 * PASSO)]
    transversal = lambda base, no: [(base, LAT + 0.001, no[2]), no, (base + 1, LAT - 0.001, no[2])]
    return {"elements": [
        _via(100, "Rua Principal", "residential", p, **(tags_principal or {})),
        _via(101, "Rua A", "residential", transversal(10, p[0])),
        _via(102, "Rua B", "residential", transversal(20, p[1])),
        _via(103, "Rua C", "residential", transversal(30, p[2])),
        *extras,
    ]}


def quadra(dados, indice=0):
    el = ElementosBatel(dados)
    caminhos = sorted(quadras_da_rua(el.ruas, "Rua Principal"))
    return el, caminhos[indice]


def test_rua_e_dividida_nas_esquinas():
    el = ElementosBatel(mapa())
    assert sorted(quadras_da_rua(el.ruas, "Rua Principal")) == [[1, 2], [2, 3]]


def test_mao_dupla_tem_dois_lados_e_mao_unica_um():
    el, caminho = quadra(mapa())
    dupla, _ = estimar_quadra(el, "Rua Principal", caminho)
    el, caminho = quadra(mapa({"oneway": "yes"}))
    unica, _ = estimar_quadra(el, "Rua Principal", caminho)
    assert dupla["lados"] == 2 and unica["lados"] == 1
    assert dupla["capacidade"] == pytest.approx(2 * unica["capacidade"], abs=1)
    comprimento_util = dist((LAT, -49.29), (LAT, -49.29 - PASSO)) - 10
    assert unica["capacidade"] == int(comprimento_util * FATOR_GARAGENS_NAO_MAPEADAS // 5.5)
    assert unica["nome"] == "R. Principal, entre R. A e R. B"


def test_faixa_de_onibus_e_proibicao_tiram_lados():
    el, caminho = quadra(mapa({"busway:right": "lane"}))
    assert estimar_quadra(el, "Rua Principal", caminho)[0]["lados"] == 1
    el, caminho = quadra(mapa({"oneway": "yes", "parking:both": "no"}))
    resultado, motivo = estimar_quadra(el, "Rua Principal", caminho)
    assert resultado is None and "sem lado livre" in motivo


def test_rotatoria_e_ponte_sao_excluidas():
    el, caminho = quadra(mapa({"junction": "roundabout"}))
    assert estimar_quadra(el, "Rua Principal", caminho) == (None, "rotatória")
    el, caminho = quadra(mapa({"bridge": "yes"}))
    assert estimar_quadra(el, "Rua Principal", caminho)[1] == "ponte, viaduto ou túnel"


def test_garagem_e_ponto_de_onibus_descontam_vagas():
    sem, caminho = quadra(mapa())
    base = estimar_quadra(sem, "Rua Principal", caminho)[0]["capacidade"]
    meio = (LAT, -49.29 - PASSO / 2)
    garagem = _via(200, None, "service", [(50, LAT - 0.0003, meio[1]), (2, LAT, -49.29 - PASSO)])
    ponto = {"type": "node", "id": 60, "lat": meio[0] + 0.0001, "lon": meio[1], "tags": {"highway": "bus_stop"}}
    # A garagem chega num nó interno: precisa de um nó no meio da quadra.
    dados = mapa(extras=[ponto])
    dados["elements"][0]["nodes"].insert(1, 5)
    dados["elements"][0]["geometry"].insert(1, {"lat": meio[0], "lon": meio[1]})
    garagem["nodes"][-1] = 5
    dados["elements"].append(garagem)
    el, caminho = quadra(dados)
    resultado = estimar_quadra(el, "Rua Principal", caminho)[0]
    assert resultado["estimativa"]["descontos_m"] == {"garagens mapeadas": 4, "pontos de ônibus": 15}
    assert resultado["capacidade"] < base


def test_quadra_longa_e_dividida_em_partes():
    el, caminho = quadra(mapa())
    inteira = estimar_quadra(el, "Rua Principal", caminho)[0]
    partes = dividir(inteira)
    assert len(partes) == 2
    assert sum(p["capacidade"] for p in partes) == inteira["capacidade"]
    assert partes[0]["nome"].endswith("(parte 1 de 2)")


def test_regime_vem_da_lista_da_setran():
    fonte = {"fonte": {"publicado_em": "2019-11-01"}}
    caminho = [1, 2, 3]
    marcadas = {("Rua X", (1, 2)): "implantado", ("Rua X", (2, 3)): "implantado"}
    assert regime_da_quadra("Rua X", caminho, marcadas, fonte)[:2] == ("estar", "fonte_oficial")
    marcadas = {("Rua X", (1, 2)): "previsto", ("Rua X", (2, 3)): "previsto"}
    assert regime_da_quadra("Rua X", caminho, marcadas, fonte)[:2] == ("estar", "estimado")
    assert regime_da_quadra("Rua X", caminho, {}, fonte)[:2] == ("a_confirmar", "estimado")


@pytest.mark.skipif(not (SAIDA / "batel_trechos.json").exists(), reason="dados do Batel não gerados")
def test_dados_reais_gerados_sao_coerentes():
    trechos = json.loads((SAIDA / "batel_trechos.json").read_text(encoding="utf-8"))
    limite = [tuple(p) for p in json.loads((SAIDA / "batel_limite.json").read_text())]
    assert len(trechos) > 100
    assert len({t["id"] for t in trechos}) == len(trechos)
    for t in trechos:
        assert t["capacidade"] >= 1 and len(t["coordenadas"]) >= 2
        assert t["regime"] in ("estar", "a_confirmar")
        # Partes de quadras na borda podem passar um pouco do limite; o meio da quadra original está dentro.
        meio = ponto_no_meio([tuple(c) for c in t["coordenadas"]])
        assert ponto_no_poligono(meio, limite) or "parte" in t["nome"]
    assert any(t["situacao"] == "fonte_oficial" for t in trechos)
