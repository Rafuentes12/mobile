BOCA_MALDITA = {"lat": -25.4322, "lng": -49.2743}
JARDIM_BOTANICO = {"lat": -25.4418, "lng": -49.2387}


def test_saude(cliente):
    assert cliente.get("/saude").json()["status"] == "ok"


def test_busca_de_destino_ignora_acentos(cliente):
    nomes = [d["nome"] for d in cliente.get("/destinos", params={"q": "guaira"}).json()]
    assert nomes == ["Teatro Guaíra"]


def test_trabalho_de_3h_em_horario_comercial_so_recomenda_privados(cliente):
    r = cliente.get("/recomendacoes", params={**BOCA_MALDITA, "contexto": "trabalho", "duracao_min": 180}).json()
    assert r["candidatos"], "deveria haver estacionamentos privados"
    assert all(c["tipo"] == "estacionamento" for c in r["candidatos"])
    assert any("EstaR permite no máximo" in d["motivo"] for d in r["descartados"])


def test_lazer_de_1h_inclui_rua_e_ordena_pela_nota(cliente):
    r = cliente.get("/recomendacoes", params={**BOCA_MALDITA, "contexto": "lazer", "duracao_min": 60}).json()
    tipos = {c["tipo"] for c in r["candidatos"]}
    assert tipos == {"rua", "estacionamento"}
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
    assert "Centro e Batel" in r["mensagem"]


def test_origem_informada_calcula_tempo_de_carro_e_chegada(cliente):
    r = cliente.get("/recomendacoes", params={**BOCA_MALDITA, "origem_lat": -25.4500, "origem_lng": -49.2500}).json()
    assert all(c["tempo_carro_min"] is not None for c in r["candidatos"])
    assert r["chegada_prevista"] > "2026-10-20T10:30"


def test_fluxo_de_reserva(cliente, relogio):
    r = cliente.post("/reservas", json={"estacionamento_id": "est-01"})
    assert r.status_code == 201
    reserva = r.json()
    assert reserva["codigo"].startswith("VC-")

    assert cliente.post("/reservas", json={"estacionamento_id": "est-04"}).status_code == 409  # já tem uma

    relogio.avancar(11)
    assert cliente.get(f"/reservas/{reserva['id']}").json()["status"] == "expirada"


def test_reserva_entrada_pela_cancela(cliente):
    reserva = cliente.post("/reservas", json={"estacionamento_id": "est-04"}).json()
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


def test_reporte_exige_proximidade_e_respeita_intervalo(cliente):
    longe = cliente.post("/reportes", json={"alvo_id": "t-05", "livre": True, "lat": -25.45, "lng": -49.29})
    assert longe.status_code == 422
    assert cliente.post("/reportes", json={"alvo_id": "t-05", "livre": True}).status_code == 204
    assert cliente.post("/reportes", json={"alvo_id": "t-05", "livre": False}).status_code == 429


def test_sessao_de_rua_respeita_limite_e_libera_a_vaga_ao_encerrar(cliente, estado):
    r = cliente.post("/sessoes", json={"alvo_id": "t-05", "placa": "abc1d23", "duracao_min": 60})
    assert r.status_code == 201
    sessao = r.json()
    assert sessao["valor_pago"] == 4.0 and sessao["placa"] == "ABC1D23"

    assert cliente.post(f"/sessoes/{sessao['id']}/estender", json={"minutos": 90}).status_code == 422  # passaria de 2 h
    assert cliente.post(f"/sessoes/{sessao['id']}/estender", json={"minutos": 60}).json()["valor_pago"] == 8.0

    cliente.post(f"/sessoes/{sessao['id']}/encerrar")
    assert estado.disponibilidade.estado("t-05", estado.relogio()).fonte == "saida"


def test_placa_invalida(cliente):
    r = cliente.post("/sessoes", json={"alvo_id": "est-01", "placa": "123", "duracao_min": 60})
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

    outro = cliente.put("/parceiros/parc-01/estacionamentos/est-04/ocupacao", json={"vagas_livres": 1})
    assert outro.status_code == 404
