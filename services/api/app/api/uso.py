"""Ações do motorista: reservar, iniciar/estender/encerrar sessão, reportar, avaliar a chegada."""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.estado import Estado, obter_estado, obter_usuario
from app.modelos import FeedbackChegada, Reserva, Sessao

router = APIRouter(tags=["motorista"])


class NovaReserva(BaseModel):
    estacionamento_id: str


class NovaSessao(BaseModel):
    alvo_id: str
    placa: str
    duracao_min: int = Field(ge=15, le=24 * 60)
    lat: float  # posição atual do usuário: precisa estar perto da vaga
    lng: float


class Extensao(BaseModel):
    minutos: int = Field(ge=15, le=240)


class NovoReporte(BaseModel):
    alvo_id: str
    livre: bool
    lat: float
    lng: float


class NovaChegada(BaseModel):
    alvo_id: str
    encontrou: bool


@router.post("/reservas", response_model=Reserva, status_code=201)
def criar_reserva(dados: NovaReserva, usuario: str = Depends(obter_usuario), estado: Estado = Depends(obter_estado)):
    return estado.reservas.criar(dados.estacionamento_id, usuario, estado.relogio())


@router.get("/reservas/{reserva_id}", response_model=Reserva)
def obter_reserva(reserva_id: str, estado: Estado = Depends(obter_estado)):
    return estado.reservas.obter(reserva_id, estado.relogio())


@router.post("/reservas/{reserva_id}/cancelar", response_model=Reserva)
def cancelar_reserva(reserva_id: str, usuario: str = Depends(obter_usuario), estado: Estado = Depends(obter_estado)):
    return estado.reservas.cancelar(reserva_id, usuario, estado.relogio())


@router.post("/reservas/{reserva_id}/entrada", response_model=Reserva)
def registrar_entrada(reserva_id: str, usuario: str = Depends(obter_usuario), estado: Estado = Depends(obter_estado)):
    """Simula a cancela do parceiro lendo o código da reserva."""
    return estado.reservas.registrar_entrada(reserva_id, usuario, estado.relogio())


@router.post("/sessoes", response_model=Sessao, status_code=201)
def iniciar_sessao(dados: NovaSessao, usuario: str = Depends(obter_usuario), estado: Estado = Depends(obter_estado)):
    """Inicia uma sessão com pagamento SIMULADO. Exige estar a até 300 m da vaga (configurável)."""
    return estado.sessoes.iniciar(dados.alvo_id, usuario, dados.placa, dados.duracao_min, estado.relogio(),
                                  dados.lat, dados.lng)


@router.get("/sessoes/ativa", response_model=Optional[Sessao])
def sessao_ativa(usuario: str = Depends(obter_usuario), estado: Estado = Depends(obter_estado)):
    return estado.sessoes.ativa_do_usuario(usuario)


@router.post("/sessoes/{sessao_id}/estender", response_model=Sessao)
def estender_sessao(sessao_id: str, dados: Extensao, usuario: str = Depends(obter_usuario),
                    estado: Estado = Depends(obter_estado)):
    return estado.sessoes.estender(sessao_id, usuario, dados.minutos, estado.relogio())


@router.post("/sessoes/{sessao_id}/encerrar", response_model=Sessao)
def encerrar_sessao(sessao_id: str, usuario: str = Depends(obter_usuario), estado: Estado = Depends(obter_estado)):
    return estado.sessoes.encerrar(sessao_id, usuario, estado.relogio())


@router.post("/reportes", status_code=204)
def reportar(dados: NovoReporte, usuario: str = Depends(obter_usuario), estado: Estado = Depends(obter_estado)):
    estado.reportes.reportar(dados.alvo_id, usuario, dados.livre, estado.relogio(), dados.lat, dados.lng)


@router.post("/chegadas", response_model=FeedbackChegada, status_code=201)
def avaliar_chegada(dados: NovaChegada, usuario: str = Depends(obter_usuario), estado: Estado = Depends(obter_estado)):
    """Resposta ao "Encontrou a vaga?" — alimenta a taxa de acerto."""
    return estado.reportes.registrar_chegada(dados.alvo_id, usuario, dados.encontrou, estado.relogio())


@router.get("/metricas")
def metricas(estado: Estado = Depends(obter_estado)):
    return estado.reportes.metricas()
