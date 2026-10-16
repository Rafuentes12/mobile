"""Recomendação de vagas por contexto de uso.

nota = a·P(livre) + b·(1−preço) + c·(1−caminhada) + d·(1−tempo de carro) + e·confiança
com tudo normalizado entre 0 e 1 e pesos que mudam conforme o contexto
(ajuste 2 das entrevistas). Os pesos começam fixos; depois são calibrados com dados de uso.
"""

from datetime import datetime, timedelta
from typing import Optional

from app.catalogo import Catalogo
from app.geo import FATOR_CAMINHADA, caminhada, distancia_m
from app.modelos import (
    Candidato,
    Contexto,
    Coordenada,
    Credencial,
    Descartado,
    EstadoVaga,
    RespostaRecomendacao,
)
from app.provedores.rotas import ProvedorRotas
from app.servicos import regras
from app.servicos.disponibilidade import ServicoDisponibilidade
from app.servicos.reservas import ServicoReservas

RAIO_PADRAO_M = 600
MAX_CANDIDATOS = 8

PESOS: dict[str, dict[str, float]] = {
    "urgencia": {"prob_livre": 0.45, "preco": 0.05, "caminhada": 0.15, "tempo_carro": 0.25, "confianca": 0.10},
    "trabalho": {"prob_livre": 0.30, "preco": 0.35, "caminhada": 0.15, "tempo_carro": 0.05, "confianca": 0.15},
    "lazer":    {"prob_livre": 0.30, "preco": 0.25, "caminhada": 0.25, "tempo_carro": 0.05, "confianca": 0.15},
}


class _Bruto:
    """Candidato antes da normalização e da nota."""

    def __init__(self, id, tipo, nome, lat, lng, caminhada_m, caminhada_min, tempo_carro,
                 preco, estado: EstadoVaga, pode_reservar, motivos, avisos):
        self.id, self.tipo, self.nome, self.lat, self.lng = id, tipo, nome, lat, lng
        self.caminhada_m, self.caminhada_min, self.tempo_carro = caminhada_m, caminhada_min, tempo_carro
        self.preco, self.estado, self.pode_reservar = preco, estado, pode_reservar
        self.motivos, self.avisos = motivos, avisos


def recomendar(
    *,
    catalogo: Catalogo,
    disponibilidade: ServicoDisponibilidade,
    reservas: ServicoReservas,
    rotas: ProvedorRotas,
    destino: Coordenada,
    contexto: Contexto,
    duracao_min: int,
    agora: datetime,
    origem: Optional[Coordenada] = None,
    credencial: Credencial = "nenhuma",
    raio_m: int = RAIO_PADRAO_M,
) -> RespostaRecomendacao:
    tempo_ate_destino = rotas.tempo_carro_min(origem, destino) if origem else 0.0
    chegada = agora + timedelta(minutes=tempo_ate_destino)

    brutos: list[_Bruto] = []
    descartados: list[Descartado] = []

    def tempo_carro(lat: float, lng: float) -> Optional[float]:
        return rotas.tempo_carro_min(origem, Coordenada(lat=lat, lng=lng)) if origem else None

    for trecho in catalogo.trechos():
        if distancia_m(destino.lat, destino.lng, trecho.lat, trecho.lng) > raio_m:
            continue
        if trecho.tipo == "carga_descarga":
            descartados.append(Descartado(id=trecho.id, nome=trecho.nome, motivo="Vaga de carga e descarga"))
            continue
        if trecho.tipo in ("idoso", "pcd") and credencial != trecho.tipo:
            descartados.append(Descartado(id=trecho.id, nome=trecho.nome,
                                          motivo=f"Vaga exclusiva ({trecho.tipo.upper()}) — exige credencial"))
            continue
        setor = catalogo.setor(trecho.setor_id)
        avaliacao = regras.avaliar_rua(setor, chegada, duracao_min)
        if not avaliacao.permitido:
            descartados.append(Descartado(id=trecho.id, nome=trecho.nome, motivo=avaliacao.motivo))
            continue

        carro = tempo_carro(trecho.lat, trecho.lng)
        momento = agora + timedelta(minutes=carro) if carro is not None else chegada
        metros, minutos = caminhada(trecho.lat, trecho.lng, destino.lat, destino.lng)
        motivos = ["Rua (EstaR)"]
        if avaliacao.minutos_cobrados == 0:
            motivos.append("Grátis: fora do horário de cobrança do EstaR")
        elif avaliacao.minutos_cobrados < duracao_min:
            motivos.append(f"Só {avaliacao.minutos_cobrados} min caem no horário de cobrança")
        if trecho.tipo in ("idoso", "pcd"):
            motivos.append(f"Vaga {trecho.tipo.upper()} (credencial informada)")
        brutos.append(_Bruto(
            trecho.id, "rua", trecho.nome, trecho.lat, trecho.lng, metros, minutos, carro,
            avaliacao.preco, disponibilidade.estado(trecho.id, agora, momento),
            False, motivos, ["Vaga de rua não pode ser reservada"],
        ))

    for est in catalogo.estacionamentos():
        if distancia_m(destino.lat, destino.lng, est.lat, est.lng) > raio_m:
            continue
        if not regras.estacionamento_aberto(est, chegada):
            descartados.append(Descartado(id=est.id, nome=est.nome, motivo="Fechado no horário de chegada"))
            continue

        carro = tempo_carro(est.lat, est.lng)
        momento = agora + timedelta(minutes=carro) if carro is not None else chegada
        metros, minutos = caminhada(est.lat, est.lng, destino.lat, destino.lng)
        motivos, avisos = [], []
        if est.parceiro_id is None:
            avisos.append("Não parceiro: sem dados ao vivo, só estimativa")
        pode_reservar = est.aceita_reserva and reservas.cota_disponivel(est.id, agora) > 0
        if pode_reservar:
            motivos.append("Reserva por 10 min disponível")
        if est.atributos.coberto:
            motivos.append("Coberto")
        if est.atributos.recarga_ev:
            motivos.append("Recarga para elétricos")
        if regras.fecha_antes_de(est, chegada, duracao_min):
            avisos.append("Fecha antes do fim da sua permanência")
        brutos.append(_Bruto(
            est.id, "estacionamento", est.nome, est.lat, est.lng, metros, minutos, carro,
            regras.preco_estacionamento(est, duracao_min), disponibilidade.estado(est.id, agora, momento),
            pode_reservar, motivos, avisos,
        ))

    candidatos = _pontuar(brutos, PESOS[contexto], raio_m)
    mensagem = None
    if not candidatos:
        mensagem = ("Ainda não temos vagas cadastradas perto deste destino. "
                    "O piloto cobre apenas Centro e Batel.")
    return RespostaRecomendacao(
        destino=destino,
        contexto=contexto,
        duracao_min=duracao_min,
        chegada_prevista=chegada,
        candidatos=candidatos[:MAX_CANDIDATOS],
        descartados=descartados,
        mensagem=mensagem,
    )


def _pontuar(brutos: list[_Bruto], pesos: dict[str, float], raio_m: int) -> list[Candidato]:
    if not brutos:
        return []
    maior_preco = max(b.preco for b in brutos) or 1.0
    tempos = [b.tempo_carro for b in brutos if b.tempo_carro is not None]
    maior_tempo = max(tempos) if tempos else 1.0
    maior_caminhada = raio_m * FATOR_CAMINHADA

    candidatos = []
    for b in brutos:
        componentes = {
            "prob_livre": b.estado.prob_livre,
            "preco": 1 - b.preco / maior_preco,
            "caminhada": max(0.0, 1 - b.caminhada_m / maior_caminhada),
            "tempo_carro": 1 - (b.tempo_carro / maior_tempo) if b.tempo_carro is not None else 1.0,
            "confianca": b.estado.confianca,
        }
        nota = sum(pesos[k] * v for k, v in componentes.items())
        candidatos.append(Candidato(
            id=b.id, tipo=b.tipo, nome=b.nome, lat=b.lat, lng=b.lng,
            caminhada_m=round(b.caminhada_m), caminhada_min=max(1, round(b.caminhada_min)),
            tempo_carro_min=round(b.tempo_carro) if b.tempo_carro is not None else None,
            preco_estimado=b.preco, estado=b.estado, pode_reservar=b.pode_reservar,
            nota=round(nota, 3), componentes={k: round(v, 3) for k, v in componentes.items()},
            motivos=b.motivos, avisos=b.avisos,
        ))
    return sorted(candidatos, key=lambda c: c.nota, reverse=True)
