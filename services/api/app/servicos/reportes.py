"""Crowdsourcing ("vaga livre/ocupada") e a métrica de acerto ("encontrou a vaga?")."""

import threading
from datetime import datetime, timedelta
from typing import Optional

from app.catalogo import Catalogo
from app.erros import ErroNegocio
from app.geo import distancia_m
from app.modelos import FeedbackChegada
from app.servicos.disponibilidade import ServicoDisponibilidade, Sinal

INTERVALO_MINIMO = timedelta(minutes=2)  # por usuário e por vaga
DISTANCIA_MAXIMA_M = 300                 # antifraude simples: precisa estar perto da vaga


class ServicoReportes:
    def __init__(self, catalogo: Catalogo, disponibilidade: ServicoDisponibilidade) -> None:
        self._catalogo = catalogo
        self._disponibilidade = disponibilidade
        self._feedbacks: list[FeedbackChegada] = []
        self._lock = threading.Lock()

    def reportar(self, alvo_id: str, usuario_id: str, livre: bool, agora: datetime,
                 lat: Optional[float] = None, lng: Optional[float] = None) -> None:
        trecho = self._catalogo.trecho(alvo_id)
        if trecho is None:
            raise ErroNegocio("Reportes valem só para vagas de rua", 422)
        if lat is not None and lng is not None and distancia_m(lat, lng, trecho.lat, trecho.lng) > DISTANCIA_MAXIMA_M:
            raise ErroNegocio("Você precisa estar perto da vaga para reportar", 422)
        recentes = [s for s in self._disponibilidade.sinais(alvo_id)
                    if s.usuario_id == usuario_id and s.fonte == "usuario" and agora - s.criado_em < INTERVALO_MINIMO]
        if recentes:
            raise ErroNegocio("Aguarde um pouco antes de reportar esta vaga de novo", 429)
        self._disponibilidade.registrar(
            Sinal(alvo_id=alvo_id, fonte="usuario", criado_em=agora, livre=livre, usuario_id=usuario_id)
        )

    def registrar_chegada(self, alvo_id: str, usuario_id: str, encontrou: bool, agora: datetime) -> FeedbackChegada:
        if not (self._catalogo.trecho(alvo_id) or self._catalogo.estacionamento(alvo_id)):
            raise ErroNegocio("Vaga não encontrada", 404)
        feedback = FeedbackChegada(alvo_id=alvo_id, usuario_id=usuario_id, encontrou=encontrou, registrado_em=agora)
        with self._lock:
            self._feedbacks.append(feedback)
        return feedback

    def metricas(self) -> dict:
        with self._lock:
            total = len(self._feedbacks)
            acertos = sum(f.encontrou for f in self._feedbacks)
        return {
            "chegadas_avaliadas": total,
            "acertos": acertos,
            "taxa_acerto": round(acertos / total, 3) if total else None,
        }
