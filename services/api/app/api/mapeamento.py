"""Mapeamento colaborativo: motoristas confirmam EstaR, proibições, preços e estacionamentos."""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.estado import Estado, obter_estado, obter_usuario
from app.modelos import (
    ResultadoMapeamento,
    ResultadoSugestao,
    SugestaoEstacionamento,
    TipoReporteEstacionamento,
    TipoReporteTrecho,
)

router = APIRouter(prefix="/mapeamento", tags=["mapeamento colaborativo"])


class Posicao(BaseModel):
    lat: float  # posição atual do usuário: precisa estar perto do local
    lng: float


class ReporteTrecho(Posicao):
    tipo: TipoReporteTrecho


class ReporteEstacionamento(Posicao):
    tipo: TipoReporteEstacionamento
    preco_hora: Optional[float] = None


class NovaSugestao(Posicao):
    nome: str = Field(min_length=3, max_length=80)
    preco_hora: Optional[float] = None


@router.post("/trechos/{trecho_id}", response_model=ResultadoMapeamento)
def reportar_trecho(trecho_id: str, dados: ReporteTrecho, usuario: str = Depends(obter_usuario),
                    estado: Estado = Depends(obter_estado)):
    """"Tem EstaR", "sem EstaR" ou "proibido". Muda o mapa com 2 confirmações de usuários diferentes."""
    return estado.mapeamento.reportar_trecho(trecho_id, usuario, dados.tipo, dados.lat, dados.lng, estado.relogio())


@router.post("/estacionamentos/{estacionamento_id}", response_model=ResultadoMapeamento)
def reportar_estacionamento(estacionamento_id: str, dados: ReporteEstacionamento,
                            usuario: str = Depends(obter_usuario), estado: Estado = Depends(obter_estado)):
    """"Fechou" (sai do mapa com 2 confirmações) ou "preço" (vale a mediana dos informados)."""
    return estado.mapeamento.reportar_estacionamento(
        estacionamento_id, usuario, dados.tipo, dados.lat, dados.lng, estado.relogio(), dados.preco_hora)


@router.post("/sugestoes", response_model=ResultadoSugestao)
def sugerir_estacionamento(dados: NovaSugestao, usuario: str = Depends(obter_usuario),
                           estado: Estado = Depends(obter_estado)):
    """Estacionamento que falta no mapa, sugerido no local. Aparece com 2 usuários diferentes."""
    return estado.mapeamento.sugerir_estacionamento(
        usuario, dados.nome, dados.lat, dados.lng, estado.relogio(), dados.preco_hora)


@router.get("/sugestoes", response_model=list[SugestaoEstacionamento])
def sugestoes_pendentes(estado: Estado = Depends(obter_estado)):
    return estado.mapeamento.sugestoes_pendentes()
