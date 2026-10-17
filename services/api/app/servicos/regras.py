"""Regras de horário, permanência e preço.

As regras vêm dos dados (setores/estacionamentos), não do código, porque mudam:
preço, horário de cobrança e tempo máximo do EstaR são definidos pela Prefeitura.
Os valores nos JSONs mockados são ilustrativos — conferir as regras vigentes na URBS.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from app.modelos import Estacionamento, Horario, Regime, Setor


def tipo_de_dia(momento: datetime) -> str:
    dia = momento.weekday()
    if dia < 5:
        return "seg_sex"
    return "sab" if dia == 5 else "dom"


def _janela(horario: Horario, momento: datetime) -> Optional[tuple[datetime, datetime]]:
    faixa = horario.get(tipo_de_dia(momento))
    if not faixa:
        return None
    base = momento.replace(hour=0, minute=0, second=0, microsecond=0)
    return base + timedelta(hours=faixa[0]), base + timedelta(hours=faixa[1])


def minutos_em_cobranca(setor: Setor, inicio: datetime, duracao_min: int) -> int:
    """Quantos minutos da permanência caem dentro do horário de cobrança do EstaR.

    Simplificação do MVP: considera só a janela do dia da chegada.
    """
    janela = _janela(setor.horario_cobranca, inicio)
    if janela is None:
        return 0
    fim = inicio + timedelta(minutes=duracao_min)
    sobreposicao = min(fim, janela[1]) - max(inicio, janela[0])
    return max(0, math.ceil(sobreposicao.total_seconds() / 60))


@dataclass
class AvaliacaoRua:
    permitido: bool
    preco: float
    minutos_cobrados: int
    motivo: Optional[str] = None


def avaliar_rua(setor: Setor, chegada: datetime, duracao_min: int, regime: Regime = "estar") -> AvaliacaoRua:
    """Regras de uma vaga de rua. "a_confirmar" usa as regras do EstaR por cautela:
    se o trecho for EstaR, o motorista não leva multa por ter seguido o app."""
    if regime == "livre":
        return AvaliacaoRua(True, 0.0, 0)
    if regime == "proibido":
        return AvaliacaoRua(False, 0.0, 0, "Proibido estacionar neste trecho")
    cobrados = minutos_em_cobranca(setor, chegada, duracao_min)
    if cobrados > setor.tempo_max_min:
        horas = setor.tempo_max_min / 60
        limite = f"{horas:g} h" if horas >= 1 else f"{setor.tempo_max_min} min"
        return AvaliacaoRua(False, 0.0, cobrados, f"EstaR permite no máximo {limite} neste setor")
    fracoes = math.ceil(cobrados / 15)
    return AvaliacaoRua(True, round(fracoes * setor.preco_fracao_15min, 2), cobrados)


def estacionamento_aberto(est: Estacionamento, momento: datetime) -> bool:
    """Horário desconhecido conta como aberto (o app avisa que não foi informado)."""
    if est.horario is None:
        return True
    janela = _janela(est.horario, momento)
    return janela is not None and janela[0] <= momento < janela[1]


def fecha_antes_de(est: Estacionamento, chegada: datetime, duracao_min: int) -> bool:
    if est.horario is None:
        return False
    janela = _janela(est.horario, chegada)
    return janela is not None and chegada + timedelta(minutes=duracao_min) > janela[1]


def preco_estacionamento(est: Estacionamento, duracao_min: int) -> Optional[float]:
    """None quando o preço não é conhecido."""
    if est.preco_hora is None:
        return None
    total = max(1, math.ceil(duracao_min / 60)) * est.preco_hora
    if est.preco_diaria is not None:
        total = min(total, est.preco_diaria)
    return round(total, 2)
