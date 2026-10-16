"""Disponibilidade: junta sinais de várias fontes num estado por vaga.

Cada sinal tem uma confiança inicial que cai pela metade a cada "meia-vida"
(um reporte de usuário vale minutos; uma contagem de cancela, um pouco mais).
O histórico (perfil de ocupação por hora, o "modelo v0") preenche as lacunas.
O app mostra a fonte e a idade da informação para ser honesto sobre a incerteza.
"""

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.catalogo import Catalogo
from app.erros import ErroNegocio
from app.modelos import EstadoVaga, FonteSinal
from app.servicos.regras import tipo_de_dia


@dataclass(frozen=True)
class ConfigFonte:
    confianca: float
    meia_vida_min: float
    rotulo: str


FONTES: dict[str, ConfigFonte] = {
    "cancela": ConfigFonte(0.95, 10, "cancela"),
    "atendente": ConfigFonte(0.85, 20, "atendente"),
    "saida": ConfigFonte(0.70, 4, "vaga liberada por usuário"),
    "usuario": ConfigFonte(0.60, 3, "reporte de usuário"),
}
PESO_HISTORICO = 0.30
PESO_MINIMO = 0.05  # abaixo disso o sinal é considerado vencido


@dataclass
class Sinal:
    alvo_id: str
    fonte: FonteSinal
    criado_em: datetime
    vagas_livres: Optional[int] = None  # estacionamentos (cancela/atendente)
    livre: Optional[bool] = None        # trechos de rua (usuários)
    usuario_id: Optional[str] = None


def _prob_por_vagas(vagas: int) -> float:
    if vagas <= 0:
        return 0.05
    return {1: 0.6, 2: 0.8}.get(vagas, 0.95)


def _idade_min(desde: datetime, ate: datetime) -> float:
    return max(0.0, (ate - desde).total_seconds() / 60)


def _texto_idade(minutos: float) -> str:
    return "há menos de 1 min" if minutos < 1 else f"há {int(minutos)} min"


class ServicoDisponibilidade:
    def __init__(self, catalogo: Catalogo) -> None:
        self._catalogo = catalogo
        self._sinais: dict[str, list[Sinal]] = {}
        self._lock = threading.Lock()

    def registrar(self, sinal: Sinal) -> None:
        if not self._capacidade_e_setor(sinal.alvo_id):
            raise ErroNegocio(f"Vaga '{sinal.alvo_id}' não existe", 404)
        with self._lock:
            self._sinais.setdefault(sinal.alvo_id, []).append(sinal)

    def sinais(self, alvo_id: str) -> list[Sinal]:
        with self._lock:
            return list(self._sinais.get(alvo_id, []))

    def _capacidade_e_setor(self, alvo_id: str) -> Optional[tuple[int, str]]:
        trecho = self._catalogo.trecho(alvo_id)
        if trecho:
            return trecho.capacidade, trecho.setor_id
        est = self._catalogo.estacionamento(alvo_id)
        if est:
            return est.capacidade, est.setor_referencia
        return None

    def estado(self, alvo_id: str, agora: datetime, momento: Optional[datetime] = None) -> EstadoVaga:
        """Estado da vaga previsto para `momento` (ex.: horário de chegada), visto em `agora`."""
        momento = momento or agora
        dados = self._capacidade_e_setor(alvo_id)
        if dados is None:
            raise ErroNegocio(f"Vaga '{alvo_id}' não existe", 404)
        capacidade, setor_id = dados

        # Modelo v0: perfil histórico de ocupação do setor na hora prevista.
        setor = self._catalogo.setor(setor_id)
        ocupacao = setor.perfil_ocupacao[tipo_de_dia(momento)][momento.hour] if setor else 0.8
        # Aproximação: vagas vizinhas não são independentes, por isso capacidade/3.
        p_historico = 1 - ocupacao ** max(1.0, capacidade / 3)
        livres_historico = round(capacidade * (1 - ocupacao))

        melhor: Optional[tuple[float, Sinal]] = None
        for sinal in self.sinais(alvo_id):
            if sinal.criado_em > agora:
                continue
            cfg = FONTES[sinal.fonte]
            peso = cfg.confianca * 0.5 ** (_idade_min(sinal.criado_em, momento) / cfg.meia_vida_min)
            if peso >= PESO_MINIMO and (melhor is None or peso > melhor[0]):
                melhor = (peso, sinal)

        if melhor is None or melhor[0] < PESO_HISTORICO:
            p = p_historico
            if melhor is not None:  # sinal fraco ainda puxa um pouco a estimativa
                p = (melhor[0] * self._prob_sinal(melhor[1]) + PESO_HISTORICO * p_historico) / (melhor[0] + PESO_HISTORICO)
            return EstadoVaga(
                prob_livre=round(p, 2),
                vagas_livres_estimadas=livres_historico,
                confianca=PESO_HISTORICO,
                fonte="historico",
                atualizado_ha_min=None,
                rotulo=f"Provável {round(p * 100)}% · histórico",
            )

        peso, sinal = melhor
        p_sinal = self._prob_sinal(sinal)
        p = (peso * p_sinal + PESO_HISTORICO * p_historico) / (peso + PESO_HISTORICO)
        idade_agora = _idade_min(sinal.criado_em, agora)
        rotulo_fonte = FONTES[sinal.fonte].rotulo
        livres = sinal.vagas_livres if sinal.vagas_livres is not None else livres_historico

        if sinal.vagas_livres is not None:
            texto = f"{livres} vagas" if livres != 1 else "1 vaga"
            if livres == 0:
                texto = "Lotado"
        elif p >= 0.5:
            texto = "Livre agora"
        else:
            texto = "Provavelmente ocupada"

        return EstadoVaga(
            prob_livre=round(p, 2),
            vagas_livres_estimadas=livres,
            confianca=round(peso, 2),
            fonte=sinal.fonte,
            atualizado_ha_min=int(idade_agora),
            rotulo=f"{texto} · {rotulo_fonte} · {_texto_idade(idade_agora)}",
        )

    @staticmethod
    def _prob_sinal(sinal: Sinal) -> float:
        if sinal.vagas_livres is not None:
            return _prob_por_vagas(sinal.vagas_livres)
        return 0.9 if sinal.livre else 0.1
