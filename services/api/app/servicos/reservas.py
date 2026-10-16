"""Reservas de 10 minutos — só em estacionamentos parceiros.

Vaga de rua (EstaR) é espaço público e não pode ser reservada (limitação 2 do
planejamento). Cada parceiro reserva uma cota de vagas para o VagaCerta; a reserva
desconta dessa cota de forma atômica. Em produção, o contador vai para o Postgres
(SELECT ... FOR UPDATE) ou para o Redis com TTL.
"""

import secrets
import threading
from datetime import datetime, timedelta

from app.catalogo import Catalogo
from app.erros import ErroNegocio
from app.modelos import Reserva

DURACAO_RESERVA = timedelta(minutes=10)


class ServicoReservas:
    def __init__(self, catalogo: Catalogo) -> None:
        self._catalogo = catalogo
        self._reservas: dict[str, Reserva] = {}
        self._lock = threading.Lock()

    def _atualizar_expiradas(self, agora: datetime) -> None:
        for r in self._reservas.values():
            if r.status == "ativa" and r.expira_em <= agora:
                r.status = "expirada"

    def _ativas(self, agora: datetime) -> list[Reserva]:
        self._atualizar_expiradas(agora)
        return [r for r in self._reservas.values() if r.status == "ativa"]

    def ativas_do_estacionamento(self, estacionamento_id: str, agora: datetime) -> list[Reserva]:
        with self._lock:
            return [r for r in self._ativas(agora) if r.estacionamento_id == estacionamento_id]

    def cota_disponivel(self, estacionamento_id: str, agora: datetime) -> int:
        est = self._catalogo.estacionamento(estacionamento_id)
        if est is None or not est.aceita_reserva:
            return 0
        return max(0, est.cota_reserva - len(self.ativas_do_estacionamento(estacionamento_id, agora)))

    def criar(self, estacionamento_id: str, usuario_id: str, agora: datetime) -> Reserva:
        if self._catalogo.trecho(estacionamento_id):
            raise ErroNegocio("Vagas de rua (EstaR) não podem ser reservadas", 422)
        est = self._catalogo.estacionamento(estacionamento_id)
        if est is None:
            raise ErroNegocio("Estacionamento não encontrado", 404)
        if not est.aceita_reserva:
            raise ErroNegocio("Este estacionamento não aceita reservas", 422)

        with self._lock:
            ativas = self._ativas(agora)
            if any(r.usuario_id == usuario_id for r in ativas):
                raise ErroNegocio("Você já tem uma reserva ativa", 409)
            if sum(r.estacionamento_id == est.id for r in ativas) >= est.cota_reserva:
                raise ErroNegocio("Cota de reservas deste estacionamento esgotada", 409)
            reserva = Reserva(
                id=f"res-{secrets.token_hex(4)}",
                estacionamento_id=est.id,
                usuario_id=usuario_id,
                codigo=f"VC-{secrets.token_hex(3).upper()}",
                criada_em=agora,
                expira_em=agora + DURACAO_RESERVA,
                status="ativa",
            )
            self._reservas[reserva.id] = reserva
            return reserva

    def obter(self, reserva_id: str, agora: datetime) -> Reserva:
        with self._lock:
            self._atualizar_expiradas(agora)
            reserva = self._reservas.get(reserva_id)
            if reserva is None:
                raise ErroNegocio("Reserva não encontrada", 404)
            return reserva

    def _mudar_status(self, reserva_id: str, usuario_id: str, novo: str, agora: datetime) -> Reserva:
        reserva = self.obter(reserva_id, agora)
        if reserva.usuario_id != usuario_id:
            raise ErroNegocio("Reserva de outro usuário", 403)
        if reserva.status != "ativa":
            raise ErroNegocio(f"Reserva já está {reserva.status}", 409)
        reserva.status = novo
        return reserva

    def cancelar(self, reserva_id: str, usuario_id: str, agora: datetime) -> Reserva:
        return self._mudar_status(reserva_id, usuario_id, "cancelada", agora)

    def registrar_entrada(self, reserva_id: str, usuario_id: str, agora: datetime) -> Reserva:
        """Simula a cancela lendo o código/placa na entrada."""
        return self._mudar_status(reserva_id, usuario_id, "utilizada", agora)
