"""Como apresentar cada vaga: regime, confiabilidade do dado e fonte (seção 1 do planejamento:
ser honesto sobre a incerteza). O app desenha tracejado o que é só estimativa."""

from app.modelos import Descricao, Estacionamento, Trecho

ROTULOS_REGIME = {
    "estar": "EstaR",
    "a_confirmar": "Pode ser EstaR — confira a placa",
    "livre": "Rua sem EstaR (grátis)",
    "proibido": "Proibido estacionar",
}


def descrever_trecho(trecho: Trecho) -> Descricao:
    rotulo = ROTULOS_REGIME[trecho.regime]
    if trecho.regime == "estar" and trecho.situacao == "estimado":
        rotulo = "EstaR previsto — confira a placa"
    if trecho.situacao == "confirmado_usuarios":
        rotulo += " · confirmado por usuários"
    return Descricao(
        regime=trecho.regime,
        situacao=trecho.situacao,
        tracejado=trecho.situacao == "estimado",
        rotulo_regime=rotulo,
        fonte=trecho.fonte,
        capacidade=trecho.capacidade,
        capacidade_estimada=trecho.estimativa is not None,
        estimativa=trecho.estimativa,
    )


def descrever_estacionamento(est: Estacionamento) -> Descricao:
    partes = ["Estacionamento"]
    if est.parceiro_id:
        partes.append("parceiro VagaCerta")
    if est.acesso == "clientes":
        partes.append("provavelmente só para clientes")
    if est.preco_hora is None:
        partes.append("preço não informado")
    elif est.preco_hora == 0:
        partes.append("gratuito")
    return Descricao(
        situacao=est.situacao,
        tracejado=est.situacao == "estimado",
        rotulo_regime=" · ".join(partes),
        fonte=est.fonte + (f" · preço: {est.fonte_preco}" if est.fonte_preco else ""),
        capacidade=est.capacidade,
        capacidade_estimada=est.capacidade_estimada,
        preco_hora=est.preco_hora,
        acesso=est.acesso,
        parceiro=est.parceiro_id is not None,
    )
