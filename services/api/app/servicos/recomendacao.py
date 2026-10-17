"""Recomendação de vagas por contexto de uso.

nota = a·P(livre) + b·(1−preço) + c·(1−caminhada) + d·(1−tempo de carro) + e·confiança
com tudo normalizado entre 0 e 1 e pesos que mudam conforme o contexto
(ajuste 2 das entrevistas). Os pesos começam fixos; depois são calibrados com dados de uso.
"""

from dataclasses import dataclass
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
    Descricao,
    EstadoVaga,
    RespostaRecomendacao,
)
from app.provedores.rotas import ProvedorRotas
from app.servicos import regras
from app.servicos.descricao import descrever_estacionamento, descrever_trecho
from app.servicos.disponibilidade import ServicoDisponibilidade
from app.servicos.reservas import ServicoReservas

RAIO_PADRAO_M = 600
MAX_CANDIDATOS = 8

PESOS: dict[str, dict[str, float]] = {
    "urgencia": {"prob_livre": 0.45, "preco": 0.05, "caminhada": 0.15, "tempo_carro": 0.25, "confianca": 0.10},
    "trabalho": {"prob_livre": 0.30, "preco": 0.35, "caminhada": 0.15, "tempo_carro": 0.05, "confianca": 0.15},
    "lazer":    {"prob_livre": 0.30, "preco": 0.25, "caminhada": 0.25, "tempo_carro": 0.05, "confianca": 0.15},
}


@dataclass
class _Bruto:
    """Candidato antes da normalização e da nota."""

    id: str
    tipo: str
    nome: str
    lat: float
    lng: float
    coordenadas: Optional[list]
    caminhada_m: float
    caminhada_min: float
    tempo_carro: Optional[float]
    preco: Optional[float]
    estado: EstadoVaga
    descricao: Descricao
    pode_reservar: bool
    motivos: list[str]
    avisos: list[str]


def _motivos_rua(regime: str, avaliacao: regras.AvaliacaoRua, duracao_min: int) -> list[str]:
    if regime == "livre":
        return ["Rua sem EstaR: grátis e sem limite de tempo"]
    motivos = []
    if regime == "a_confirmar":
        motivos.append("Pode ser EstaR: o preço considera o pior caso")
    if avaliacao.minutos_cobrados == 0:
        motivos.append("Grátis: fora do horário de cobrança do EstaR")
    elif avaliacao.minutos_cobrados < duracao_min:
        motivos.append(f"Só {avaliacao.minutos_cobrados} min caem no horário de cobrança")
    return motivos


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
        avaliacao = regras.avaliar_rua(setor, chegada, duracao_min, trecho.regime)
        if not avaliacao.permitido:
            descartados.append(Descartado(id=trecho.id, nome=trecho.nome, motivo=avaliacao.motivo))
            continue

        carro = tempo_carro(trecho.lat, trecho.lng)
        momento = agora + timedelta(minutes=carro) if carro is not None else chegada
        metros, minutos = caminhada(trecho.lat, trecho.lng, destino.lat, destino.lng)
        descricao = descrever_trecho(trecho)
        motivos = _motivos_rua(trecho.regime, avaliacao, duracao_min)
        if trecho.tipo in ("idoso", "pcd"):
            motivos.append(f"Vaga {trecho.tipo.upper()} (credencial informada)")
        avisos = ["Vaga de rua não pode ser reservada"]
        if descricao.tracejado:
            avisos.append("Trecho e capacidade estimados a partir do mapa")
        brutos.append(_Bruto(
            trecho.id, "rua", trecho.nome, trecho.lat, trecho.lng, trecho.coordenadas, metros, minutos, carro,
            avaliacao.preco, disponibilidade.estado(trecho.id, agora, momento), descricao, False, motivos, avisos,
        ))

    for est in catalogo.estacionamentos():
        if not est.ativo or distancia_m(destino.lat, destino.lng, est.lat, est.lng) > raio_m:
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
        if est.acesso == "clientes":
            avisos.append("Provavelmente só para clientes")
        if est.preco_hora is None:
            avisos.append("Preço não informado")
        if est.horario is None:
            avisos.append("Horário não informado")
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
            est.id, "estacionamento", est.nome, est.lat, est.lng, None, metros, minutos, carro,
            regras.preco_estacionamento(est, duracao_min), disponibilidade.estado(est.id, agora, momento),
            descrever_estacionamento(est), pode_reservar, motivos, avisos,
        ))

    candidatos = _pontuar(brutos, PESOS[contexto], raio_m)
    mensagem = None
    if not candidatos:
        mensagem = ("Ainda não temos vagas cadastradas perto deste destino. "
                    "O piloto cobre o Centro (dados de demonstração) e o Batel (dados reais).")
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
    precos = [b.preco for b in brutos if b.preco is not None]
    maior_preco = max(precos, default=0.0) or 1.0
    tempos = [b.tempo_carro for b in brutos if b.tempo_carro is not None]
    maior_tempo = max(tempos) if tempos else 1.0
    maior_caminhada = raio_m * FATOR_CAMINHADA

    candidatos = []
    for b in brutos:
        componentes = {
            "prob_livre": b.estado.prob_livre,
            # Preço desconhecido conta como o mais caro: o app não promete economia que não sabe.
            "preco": 1 - (b.preco if b.preco is not None else maior_preco) / maior_preco,
            "caminhada": max(0.0, 1 - b.caminhada_m / maior_caminhada),
            "tempo_carro": 1 - (b.tempo_carro / maior_tempo) if b.tempo_carro is not None else 1.0,
            "confianca": b.estado.confianca,
        }
        nota = sum(pesos[k] * v for k, v in componentes.items())
        candidatos.append(Candidato(
            **b.descricao.model_dump(),
            id=b.id, tipo=b.tipo, nome=b.nome, lat=b.lat, lng=b.lng, coordenadas=b.coordenadas,
            caminhada_m=round(b.caminhada_m), caminhada_min=max(1, round(b.caminhada_min)),
            tempo_carro_min=round(b.tempo_carro) if b.tempo_carro is not None else None,
            preco_estimado=b.preco, estado=b.estado, pode_reservar=b.pode_reservar,
            nota=round(nota, 3), componentes={k: round(v, 3) for k, v in componentes.items()},
            motivos=b.motivos, avisos=b.avisos,
        ))
    return sorted(candidatos, key=lambda c: c.nota, reverse=True)
