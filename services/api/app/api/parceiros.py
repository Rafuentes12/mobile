"""Painel do parceiro: o atendente informa as vagas livres ("Mágico de Oz" do MVP)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.erros import ErroNegocio
from app.estado import Estado, obter_estado
from app.modelos import Estacionamento, EstadoVaga, Parceiro, Reserva
from app.servicos.disponibilidade import Sinal

router = APIRouter(prefix="/parceiros", tags=["parceiros"])


class EstacionamentoNoPainel(BaseModel):
    estacionamento: Estacionamento
    estado: EstadoVaga
    reservas_ativas: list[Reserva]
    cota_reserva_disponivel: int


class AtualizacaoOcupacao(BaseModel):
    vagas_livres: int = Field(ge=0)


@router.get("", response_model=list[Parceiro])
def listar_parceiros(estado: Estado = Depends(obter_estado)):
    return estado.catalogo.parceiros()


def _painel(estado: Estado, est: Estacionamento) -> EstacionamentoNoPainel:
    agora = estado.relogio()
    return EstacionamentoNoPainel(
        estacionamento=est,
        estado=estado.disponibilidade.estado(est.id, agora),
        reservas_ativas=estado.reservas.ativas_do_estacionamento(est.id, agora),
        cota_reserva_disponivel=estado.reservas.cota_disponivel(est.id, agora),
    )


def _do_parceiro(estado: Estado, parceiro_id: str, estacionamento_id: str) -> Estacionamento:
    est = estado.catalogo.estacionamento(estacionamento_id)
    if est is None or est.parceiro_id != parceiro_id:
        raise ErroNegocio("Estacionamento não pertence a este parceiro", 404)
    return est


@router.get("/{parceiro_id}/estacionamentos", response_model=list[EstacionamentoNoPainel])
def estacionamentos_do_parceiro(parceiro_id: str, estado: Estado = Depends(obter_estado)):
    if not any(p.id == parceiro_id for p in estado.catalogo.parceiros()):
        raise ErroNegocio("Parceiro não encontrado", 404)
    return [_painel(estado, e) for e in estado.catalogo.estacionamentos() if e.parceiro_id == parceiro_id]


@router.put("/{parceiro_id}/estacionamentos/{estacionamento_id}/ocupacao", response_model=EstacionamentoNoPainel)
def atualizar_ocupacao(parceiro_id: str, estacionamento_id: str, dados: AtualizacaoOcupacao,
                       estado: Estado = Depends(obter_estado)):
    est = _do_parceiro(estado, parceiro_id, estacionamento_id)
    if dados.vagas_livres > est.capacidade:
        raise ErroNegocio(f"Máximo de {est.capacidade} vagas", 422)
    estado.disponibilidade.registrar(
        Sinal(alvo_id=est.id, fonte="atendente", criado_em=estado.relogio(), vagas_livres=dados.vagas_livres)
    )
    return _painel(estado, est)
