"""Monta os serviços da aplicação (injeção de dependências simples).

Tudo fica em memória: reiniciar a API volta aos dados iniciais (mock do Centro + Batel do OSM)
e descarta reportes, sessões e mudanças feitas pelo mapeamento colaborativo.
"""

import json
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Header, Request

from app.catalogo import PASTA_MOCK, Catalogo, CatalogoArquivos
from app.config import DISTANCIA_MAXIMA_M, Relogio, criar_relogio
from app.provedores.destinos import DestinosMock, ProvedorDestinos
from app.provedores.rotas import ProvedorRotas, RotasEstimadas
from app.servicos.disponibilidade import ServicoDisponibilidade, Sinal
from app.servicos.mapeamento import ServicoMapeamento
from app.servicos.reportes import ServicoReportes
from app.servicos.reservas import ServicoReservas
from app.servicos.sessoes import ServicoSessoes


@dataclass
class Estado:
    relogio: Relogio
    catalogo: Catalogo
    destinos: ProvedorDestinos
    rotas: ProvedorRotas
    disponibilidade: ServicoDisponibilidade
    reservas: ServicoReservas
    sessoes: ServicoSessoes
    reportes: ServicoReportes
    mapeamento: ServicoMapeamento

    @classmethod
    def criar(cls, relogio: Relogio | None = None, semear: bool = True,
              distancia_maxima_m: float = DISTANCIA_MAXIMA_M) -> "Estado":
        relogio = relogio or criar_relogio()
        catalogo = CatalogoArquivos()
        disponibilidade = ServicoDisponibilidade(catalogo)
        estado = cls(
            relogio=relogio,
            catalogo=catalogo,
            destinos=DestinosMock(),
            rotas=RotasEstimadas(),
            disponibilidade=disponibilidade,
            reservas=ServicoReservas(catalogo),
            sessoes=ServicoSessoes(catalogo, disponibilidade, distancia_maxima_m),
            reportes=ServicoReportes(catalogo, disponibilidade, distancia_maxima_m),
            mapeamento=ServicoMapeamento(catalogo, distancia_maxima_m),
        )
        if semear:
            estado._semear_sinais()
        return estado

    def _semear_sinais(self) -> None:
        agora = self.relogio()
        for s in json.loads((PASTA_MOCK / "sinais_iniciais.json").read_text(encoding="utf-8")):
            self.disponibilidade.registrar(Sinal(
                alvo_id=s["alvo_id"],
                fonte=s["fonte"],
                criado_em=agora - timedelta(minutes=s["minutos_atras"]),
                vagas_livres=s.get("vagas_livres"),
                livre=s.get("livre"),
            ))


def obter_estado(request: Request) -> Estado:
    return request.app.state.estado


def obter_usuario(x_usuario_id: str = Header(default="demo")) -> str:
    """Sem login no MVP: o app manda um id fixo. Depois: validar o JWT do Supabase Auth."""
    return x_usuario_id
