"""Mapeamento colaborativo: reportes de EstaR, proibições, preços e estacionamentos novos."""

import pytest

from app.geo import distancia_m

LONGE = {"lat": -25.4500, "lng": -49.2500}


def usuario(nome):
    return {"X-Usuario-Id": nome}


@pytest.fixture
def trecho_batel(estado):
    """Uma quadra real do Batel ainda "a confirmar", e um ponto em cima dela."""
    trecho = next(t for t in estado.catalogo.trechos() if t.regime == "a_confirmar")
    lat, lng = trecho.coordenadas[0]
    return trecho, {"lat": lat, "lng": lng}


@pytest.fixture
def estacionamento_osm(estado):
    est = next(e for e in estado.catalogo.estacionamentos() if e.id.startswith("osm-"))
    return est, {"lat": est.lat, "lng": est.lng}


def reportar_trecho(cliente, trecho_id, tipo, posicao, quem):
    return cliente.post(f"/mapeamento/trechos/{trecho_id}", json={"tipo": tipo, **posicao}, headers=usuario(quem))


def vaga_no_mapa(cliente, vaga_id, perto):
    vagas = cliente.get("/vagas", params={**perto, "raio_m": 500}).json()
    return next((v for v in vagas if v["id"] == vaga_id), None)


def test_estar_confirmado_por_dois_usuarios_vira_linha_cheia(cliente, trecho_batel):
    trecho, perto = trecho_batel
    primeiro = reportar_trecho(cliente, trecho.id, "tem_estar", perto, "ana").json()
    assert not primeiro["aplicado"] and primeiro["faltam"] == 1
    assert vaga_no_mapa(cliente, trecho.id, perto)["tracejado"] is True

    segundo = reportar_trecho(cliente, trecho.id, "tem_estar", perto, "bia").json()
    assert segundo["aplicado"] and segundo["contagem"] == {"tem_estar": 2}
    vaga = vaga_no_mapa(cliente, trecho.id, perto)
    assert vaga["regime"] == "estar" and vaga["situacao"] == "confirmado_usuarios"
    assert vaga["tracejado"] is False and "confirmado por usuários" in vaga["rotulo_regime"]


def test_mesmo_usuario_conta_uma_vez(cliente, trecho_batel):
    trecho, perto = trecho_batel
    reportar_trecho(cliente, trecho.id, "tem_estar", perto, "ana")
    assert reportar_trecho(cliente, trecho.id, "tem_estar", perto, "ana").status_code == 429
    mudou_de_ideia = reportar_trecho(cliente, trecho.id, "sem_estar", perto, "ana").json()
    assert mudou_de_ideia["contagem"] == {"sem_estar": 1} and not mudou_de_ideia["aplicado"]


def test_empate_nao_muda_o_mapa(cliente, trecho_batel):
    trecho, perto = trecho_batel
    for quem, tipo in (("ana", "tem_estar"), ("bia", "tem_estar"), ("caio", "sem_estar"), ("davi", "sem_estar")):
        reportar_trecho(cliente, trecho.id, tipo, perto, quem)
    vaga = vaga_no_mapa(cliente, trecho.id, perto)
    assert vaga["regime"] == "estar"  # a maioria (2 a 0) já tinha decidido antes do empate


def test_mapear_exige_estar_perto(cliente, trecho_batel):
    trecho, _ = trecho_batel
    r = reportar_trecho(cliente, trecho.id, "tem_estar", LONGE, "ana")
    assert r.status_code == 422 and "até 300 m" in r.json()["detail"]


def test_rua_sem_estar_confirmada_fica_gratis_e_sem_limite(cliente, trecho_batel):
    trecho, perto = trecho_batel
    for quem in ("ana", "bia"):
        reportar_trecho(cliente, trecho.id, "sem_estar", perto, quem)
    r = cliente.get("/recomendacoes", params={"lat": trecho.lat, "lng": trecho.lng, "contexto": "trabalho",
                                              "duracao_min": 480, "raio_m": 150}).json()
    candidato = next(c for c in r["candidatos"] if c["id"] == trecho.id)
    assert candidato["preco_estimado"] == 0 and candidato["regime"] == "livre"
    assert "Rua sem EstaR: grátis e sem limite de tempo" in candidato["motivos"]


def test_proibido_confirmado_sai_da_recomendacao(cliente, trecho_batel):
    trecho, perto = trecho_batel
    for quem in ("ana", "bia"):
        reportar_trecho(cliente, trecho.id, "proibido", perto, quem)
    r = cliente.get("/recomendacoes", params={"lat": trecho.lat, "lng": trecho.lng, "raio_m": 150}).json()
    assert trecho.id not in [c["id"] for c in r["candidatos"]]
    assert any(d["id"] == trecho.id and "Proibido" in d["motivo"] for d in r["descartados"])


def test_preco_informado_pelos_usuarios_usa_a_mediana(cliente, estacionamento_osm):
    est, perto = estacionamento_osm
    url = f"/mapeamento/estacionamentos/{est.id}"
    cliente.post(url, json={"tipo": "preco", "preco_hora": 12, **perto}, headers=usuario("ana"))
    r = cliente.post(url, json={"tipo": "preco", "preco_hora": 14, **perto}, headers=usuario("bia")).json()
    assert "13,00" in r["mensagem"]
    vaga = vaga_no_mapa(cliente, est.id, perto)
    assert vaga["preco_hora"] == 13 and "informado por 2 usuários" in vaga["fonte"]


def test_preco_invalido(cliente, estacionamento_osm):
    est, perto = estacionamento_osm
    r = cliente.post(f"/mapeamento/estacionamentos/{est.id}", json={"tipo": "preco", "preco_hora": 500, **perto})
    assert r.status_code == 422


def test_estacionamento_fechado_sai_do_mapa_com_duas_confirmacoes(cliente, estacionamento_osm):
    est, perto = estacionamento_osm
    url = f"/mapeamento/estacionamentos/{est.id}"
    assert cliente.post(url, json={"tipo": "fechado", **perto}, headers=usuario("ana")).json()["faltam"] == 1
    assert vaga_no_mapa(cliente, est.id, perto) is not None
    assert cliente.post(url, json={"tipo": "fechado", **perto}, headers=usuario("bia")).json()["aplicado"]
    assert vaga_no_mapa(cliente, est.id, perto) is None


def test_parceiro_nao_recebe_reporte_de_usuario(cliente):
    r = cliente.post("/mapeamento/estacionamentos/est-01", json={"tipo": "preco", "preco_hora": 5,
                                                                 "lat": -25.4305, "lng": -49.2705})
    assert r.status_code == 422


def test_sugestao_de_estacionamento_aparece_com_dois_usuarios(cliente, estado):
    # Um ponto do Batel longe de qualquer estacionamento já cadastrado.
    local = {"lat": -25.4460, "lng": -49.2930}
    assert all(distancia_m(local["lat"], local["lng"], e.lat, e.lng) > 40 for e in estado.catalogo.estacionamentos())

    r1 = cliente.post("/mapeamento/sugestoes", json={"nome": "Estacionamento Teste", "preco_hora": 10, **local},
                      headers=usuario("ana")).json()
    assert r1["status"] == "pendente" and r1["faltam"] == 1
    assert len(cliente.get("/mapeamento/sugestoes").json()) == 1
    repetida = cliente.post("/mapeamento/sugestoes", json={"nome": "Estacionamento Teste", **local},
                            headers=usuario("ana"))
    assert repetida.status_code == 409

    perto = {"lat": local["lat"] + 0.0002, "lng": local["lng"]}  # ~22 m de distância
    r2 = cliente.post("/mapeamento/sugestoes", json={"nome": "Estacionamento Teste", "preco_hora": 12, **perto},
                      headers=usuario("bia")).json()
    assert r2["status"] == "confirmada" and r2["estacionamento"]["preco_hora"] == 11
    vaga = vaga_no_mapa(cliente, r2["estacionamento"]["id"], local)
    assert vaga is not None and vaga["fonte"].startswith("Sugerido por 2 usuários")


def test_sugestao_em_cima_de_estacionamento_existente(cliente, estacionamento_osm):
    est, perto = estacionamento_osm
    r = cliente.post("/mapeamento/sugestoes", json={"nome": "Outro nome", **perto})
    assert r.status_code == 409 and est.nome in r.json()["detail"]
