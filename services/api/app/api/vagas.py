from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.estado import Estado, obter_estado
from app.geo import distancia_m
from app.modelos import (
    Contexto,
    Coordenada,
    Credencial,
    Destino,
    RespostaRecomendacao,
    Setor,
    VagaNoMapa,
)
from app.servicos.descricao import descrever_estacionamento, descrever_trecho
from app.servicos.recomendacao import RAIO_PADRAO_M, recomendar

router = APIRouter(tags=["vagas"])


@router.get("/destinos", response_model=list[Destino])
def buscar_destinos(q: str = "", estado: Estado = Depends(obter_estado)):
    """Busca de destino. Mock hoje; Google Places (via servidor) depois."""
    return estado.destinos.buscar(q)


@router.get("/setores", response_model=list[Setor])
def listar_setores(estado: Estado = Depends(obter_estado)):
    return estado.catalogo.setores()


@router.get("/vagas", response_model=list[VagaNoMapa])
def vagas_no_mapa(
    lat: float,
    lng: float,
    raio_m: int = Query(1500, ge=100, le=5000),
    estado: Estado = Depends(obter_estado),
):
    """Todas as vagas (rua e estacionamentos) perto de um ponto, com o estado atual e a
    descrição do dado (regime, fonte e se é só estimativa → linha tracejada no app)."""
    agora = estado.relogio()
    resultado: list[VagaNoMapa] = []
    for t in estado.catalogo.trechos():
        if distancia_m(lat, lng, t.lat, t.lng) <= raio_m:
            resultado.append(VagaNoMapa(
                **descrever_trecho(t).model_dump(),
                id=t.id, tipo="rua", nome=t.nome, lat=t.lat, lng=t.lng, tipo_vaga=t.tipo,
                coordenadas=t.coordenadas, estado=estado.disponibilidade.estado(t.id, agora),
            ))
    for e in estado.catalogo.estacionamentos():
        if e.ativo and distancia_m(lat, lng, e.lat, e.lng) <= raio_m:
            resultado.append(VagaNoMapa(
                **descrever_estacionamento(e).model_dump(),
                id=e.id, tipo="estacionamento", nome=e.nome, lat=e.lat, lng=e.lng,
                estado=estado.disponibilidade.estado(e.id, agora),
            ))
    return resultado


@router.get("/recomendacoes", response_model=RespostaRecomendacao)
def recomendacoes(
    lat: float,
    lng: float,
    contexto: Contexto = "lazer",
    duracao_min: int = Query(60, ge=15, le=24 * 60),
    origem_lat: Optional[float] = None,
    origem_lng: Optional[float] = None,
    credencial: Credencial = "nenhuma",
    raio_m: int = Query(RAIO_PADRAO_M, ge=100, le=2000),
    estado: Estado = Depends(obter_estado),
):
    origem = Coordenada(lat=origem_lat, lng=origem_lng) if origem_lat is not None and origem_lng is not None else None
    return recomendar(
        catalogo=estado.catalogo,
        disponibilidade=estado.disponibilidade,
        reservas=estado.reservas,
        rotas=estado.rotas,
        destino=Coordenada(lat=lat, lng=lng),
        contexto=contexto,
        duracao_min=duracao_min,
        agora=estado.relogio(),
        origem=origem,
        credencial=credencial,
        raio_m=raio_m,
    )
