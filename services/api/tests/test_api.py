BOCA_MALDITA = {"lat": -25.4322, "lng": -49.2743}
JARDIM_BOTANICO = {"lat": -25.4418, "lng": -49.2387}
PATIO_BATEL = {"lat": -25.4430, "lng": -49.2909}
LONGE = {"lat": -25.4500, "lng": -49.2500}            # PUCPR, a ~3 km do Centro
PERTO_DA_T05 = {"lat": -25.4311, "lng": -49.2770}      # na R. Cruz Machado (trecho t-05)
PERTO_DA_EST01 = {"lat": -25.4306, "lng": -49.2706}


def test_saude(cliente):
    resposta = cliente.get("/saude").json()
    assert resposta["status"] == "ok" and resposta["distancia_maxima_m"] == 300


def test_busca_de_destino_ignora_acentos(cliente):
    nomes = [d["nome"] for d in cliente.get("/destinos", params={"q": "guaira"}).json()]
    assert nomes == ["Teatro Guaíra"]


# --- Recomendação -------------------------------------------------------------------------------


def test_trabalho_de_3h_em_horario_comercial_so_recomenda_privados(cliente):
    r = cliente.get("/recomendacoes", params={**BOCA_MALDITA, "contexto": "trabalho", "duracao_min": 180}).json()
    assert r["candidatos"], "deveria haver estacionamentos privados"
    assert all(c["tipo"] == "estacionamento" for c in r["candidatos"])
    assert any("EstaR permite no máximo" in d["motivo"] for d in r["descartados"])


def test_lazer_de_1h_inclui_rua_e_ordena_pela_nota(cliente):
    r = cliente.get("/recomendacoes", params={**BOCA_MALDITA, "contexto": "lazer", "duracao_min": 60}).json()
    assert {c["tipo"] for c in r["candidatos"]} == {"rua", "estacionamento"}
    notas = [c["nota"] for c in r["candidatos"]]
    assert notas == sorted(notas, reverse=True)


def test_vagas_exclusivas_exigem_credencial(cliente):
    params = {"lat": -25.4318, "lng": -49.2705, "duracao_min": 60}
    sem = cliente.get("/recomendacoes", params=params).json()
    com = cliente.get("/recomendacoes", params={**params, "credencial": "idoso"}).json()
    assert "t-06" not in [c["id"] for c in sem["candidatos"]]
    assert "t-06" in [c["id"] for c in com["candidatos"]]


def test_destino_fora_do_piloto_explica_a_falta_de_cobertura(cliente):
    r = cliente.get("/recomendacoes", params=JARDIM_BOTANICO).json()
    assert r["candidatos"] == []
    assert "Batel" in r["mensagem"]


def test_origem_informada_calcula_tempo_de_carro_e_chegada(cliente):
    r = cliente.get("/recomendacoes", params={**BOCA_MALDITA, "origem_lat": -25.4500, "origem_lng": -49.2500}).json()
    assert all(c["tempo_carro_min"] is not None for c in r["candidatos"])
    assert r["chegada_prevista"] > "2026-10-20T10:30"


# --- Batel (dados reais do OSM) -----------------------------------------------------------------


def test_batel_mostra_quadras_reais_com_regime_e_tracejado(cliente):
    vagas = cliente.get("/vagas", params={**PATIO_BATEL, "raio_m": 800}).json()
    ruas = [v for v in vagas if v["tipo"] == "rua" and v["id"].startswith("osm-")]
    assert len(ruas) > 20
    a_confirmar = [v for v in ruas if v["regime"] == "a_confirmar"]
    oficiais = [v for v in ruas if v["situacao"] == "fonte_oficial"]
    assert a_confirmar and all(v["tracejado"] for v in a_confirmar)
    assert a_confirmar[0]["rotulo_regime"] == "Pode ser EstaR — confira a placa"
    assert oficiais and not any(v["tracejado"] for v in oficiais)
    assert all(v["capacidade_estimada"] and v["estimativa"]["comprimento_m"] > 0 for v in ruas)


def test_batel_estacionamentos_reais_sem_preco_nao_prometem_valor(cliente):
    vagas = cliente.get("/vagas", params={**PATIO_BATEL, "raio_m": 2000}).json()
    reais = [v for v in vagas if v["tipo"] == "estacionamento" and v["id"].startswith("osm-")]
    assert reais and all(v["preco_hora"] is None and v["fonte"] == "OpenStreetMap" for v in reais)
    assert all("preço não informado" in v["rotulo_regime"] for v in reais)


def test_batel_trecho_a_confirmar_segue_regras_do_estar_por_cautela(cliente):
    r = cliente.get("/recomendacoes", params={**PATIO_BATEL, "contexto": "trabalho", "duracao_min": 180}).json()
    assert not [c for c in r["candidatos"] if c["regime"] == "a_confirmar"]  # 3 h > limite do EstaR
    lazer = cliente.get("/recomendacoes", params={**PATIO_BATEL, "duracao_min": 60}).json()
    rua = [c for c in lazer["candidatos"] if c["regime"] == "a_confirmar"]
    assert rua and "Pode ser EstaR: o preço considera o pior caso" in rua[0]["motivos"]


# --- Reservas ------------------------------------------------------------------------------------


def test_fluxo_de_reserva(cliente, relogio):
    r = cliente.post("/reservas", json={"estacionamento_id": "est-01"})
    assert r.status_code == 201
    reserva = r.json()
    assert reserva["codigo"].startswith("VC-")

    assert cliente.post("/reservas", json={"estacionamento_id": "est-02"}).status_code == 409  # já tem uma

    relogio.avancar(11)
    assert cliente.get(f"/reservas/{reserva['id']}").json()["status"] == "expirada"


def test_reserva_entrada_pela_cancela(cliente):
    reserva = cliente.post("/reservas", json={"estacionamento_id": "est-02"}).json()
    r = cliente.post(f"/reservas/{reserva['id']}/entrada")
    assert r.json()["status"] == "utilizada"


def test_cota_de_reservas_e_respeitada(cliente):
    for i in range(5):  # est-01 tem cota de 5
        r = cliente.post("/reservas", json={"estacionamento_id": "est-01"}, headers={"X-Usuario-Id": f"u{i}"})
        assert r.status_code == 201
    r = cliente.post("/reservas", json={"estacionamento_id": "est-01"}, headers={"X-Usuario-Id": "u-extra"})
    assert r.status_code == 409


def test_vaga_de_rua_nao_pode_ser_reservada(cliente):
    r = cliente.post("/reservas", json={"estacionamento_id": "t-01"})
    assert r.status_code == 422
    assert "não podem ser reservadas" in r.json()["detail"]


# --- Reportes e sessões (exigem estar perto) ------------------------------------------------------


def test_reporte_exige_proximidade_e_respeita_intervalo(cliente):
    longe = cliente.post("/reportes", json={"alvo_id": "t-05", "livre": True, **LONGE})
    assert longe.status_code == 422 and "300 m" in longe.json()["detail"]
    assert cliente.post("/reportes", json={"alvo_id": "t-05", "livre": True, **PERTO_DA_T05}).status_code == 204
    assert cliente.post("/reportes", json={"alvo_id": "t-05", "livre": False, **PERTO_DA_T05}).status_code == 429


def test_sessao_so_inicia_perto_da_vaga(cliente):
    r = cliente.post("/sessoes", json={"alvo_id": "t-05", "placa": "ABC1D23", "duracao_min": 60, **LONGE})
    assert r.status_code == 422
    assert "até 300 m" in r.json()["detail"] and "você está a" in r.json()["detail"]


def test_raio_de_proximidade_e_configuravel(relogio):
    from fastapi.testclient import TestClient

    from app.main import criar_app

    cliente = TestClient(criar_app(relogio=relogio, distancia_maxima_m=10_000))
    r = cliente.post("/sessoes", json={"alvo_id": "t-05", "placa": "ABC1D23", "duracao_min": 60, **LONGE})
    assert r.status_code == 201


def test_sessao_de_rua_respeita_limite_e_libera_a_vaga_ao_encerrar(cliente, estado):
    r = cliente.post("/sessoes", json={"alvo_id": "t-05", "placa": "abc1d23", "duracao_min": 60, **PERTO_DA_T05})
    assert r.status_code == 201
    sessao = r.json()
    assert sessao["valor_pago"] == 4.0 and sessao["placa"] == "ABC1D23"

    assert cliente.post(f"/sessoes/{sessao['id']}/estender", json={"minutos": 90}).status_code == 422  # passaria de 2 h
    assert cliente.post(f"/sessoes/{sessao['id']}/estender", json={"minutos": 60}).json()["valor_pago"] == 8.0

    cliente.post(f"/sessoes/{sessao['id']}/encerrar")
    assert estado.disponibilidade.estado("t-05", estado.relogio()).fonte == "saida"


def test_placa_invalida(cliente):
    r = cliente.post("/sessoes", json={"alvo_id": "est-01", "placa": "123", "duracao_min": 60, **PERTO_DA_EST01})
    assert r.status_code == 422


def test_taxa_de_acerto(cliente):
    cliente.post("/chegadas", json={"alvo_id": "t-01", "encontrou": True})
    cliente.post("/chegadas", json={"alvo_id": "t-02", "encontrou": False})
    assert cliente.get("/metricas").json()["taxa_acerto"] == 0.5


def test_painel_do_parceiro_atualiza_ocupacao(cliente):
    painel = cliente.get("/parceiros/parc-01/estacionamentos").json()
    assert {p["estacionamento"]["id"] for p in painel} == {"est-01", "est-02"}

    r = cliente.put("/parceiros/parc-01/estacionamentos/est-02/ocupacao", json={"vagas_livres": 7})
    assert r.json()["estado"]["rotulo"] == "7 vagas · atendente · há menos de 1 min"

    outro = cliente.put("/parceiros/parc-01/estacionamentos/est-03/ocupacao", json={"vagas_livres": 1})
    assert outro.status_code == 404
