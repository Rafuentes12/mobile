"""Regra de proximidade: algumas ações só valem para quem está perto da vaga."""

from app.catalogo import Catalogo
from app.erros import ErroNegocio


def formatar_distancia(metros: float) -> str:
    return f"{metros / 1000:.1f} km".replace(".", ",") if metros >= 1000 else f"{round(metros)} m"


def exigir_proximidade(catalogo: Catalogo, alvo_id: str, lat: float, lng: float,
                       distancia_maxima_m: float, acao: str) -> float:
    distancia = catalogo.distancia_ate(alvo_id, lat, lng)
    if distancia is None:
        raise ErroNegocio("Vaga não encontrada", 404)
    if distancia > distancia_maxima_m:
        raise ErroNegocio(
            f"Para {acao}, você precisa estar a até {formatar_distancia(distancia_maxima_m)} da vaga "
            f"(você está a {formatar_distancia(distancia)}).", 422)
    return distancia
