"""Modelos de domínio e de resposta da API."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

Contexto = Literal["urgencia", "trabalho", "lazer"]
TipoVaga = Literal["comum", "idoso", "pcd", "carga_descarga"]
Credencial = Literal["nenhuma", "idoso", "pcd"]
FonteSinal = Literal["cancela", "atendente", "usuario", "saida"]

# Faixa de horário [hora_inicio, hora_fim) por tipo de dia; None = fechado / sem cobrança.
Horario = dict[str, Optional[tuple[int, int]]]


class Coordenada(BaseModel):
    lat: float
    lng: float


# --- Catálogo ---------------------------------------------------------------


class Setor(BaseModel):
    id: str
    nome: str
    tempo_max_min: int
    preco_fracao_15min: float
    horario_cobranca: Horario
    perfil_ocupacao: dict[str, list[float]]  # taxa de ocupação por hora (24 valores) por tipo de dia


class Trecho(BaseModel):
    id: str
    setor_id: str
    nome: str
    tipo: TipoVaga
    capacidade: int
    coordenadas: list[tuple[float, float]]

    @property
    def lat(self) -> float:
        return sum(c[0] for c in self.coordenadas) / len(self.coordenadas)

    @property
    def lng(self) -> float:
        return sum(c[1] for c in self.coordenadas) / len(self.coordenadas)


class Atributos(BaseModel):
    coberto: bool
    altura_max_m: Optional[float]
    recarga_ev: bool
    vagas_pcd: bool


class Estacionamento(BaseModel):
    id: str
    nome: str
    endereco: str
    lat: float
    lng: float
    capacidade: int
    preco_hora: float
    preco_diaria: float
    parceiro_id: Optional[str]
    aceita_reserva: bool
    cota_reserva: int
    setor_referencia: str
    horario: Horario
    atributos: Atributos


class Parceiro(BaseModel):
    id: str
    nome: str


class Destino(BaseModel):
    id: str
    nome: str
    endereco: str
    lat: float
    lng: float


# --- Disponibilidade ----------------------------------------------------------


class EstadoVaga(BaseModel):
    prob_livre: float
    vagas_livres_estimadas: int
    confianca: float
    fonte: str
    atualizado_ha_min: Optional[int]
    rotulo: str


class VagaNoMapa(BaseModel):
    id: str
    tipo: Literal["rua", "estacionamento"]
    nome: str
    lat: float
    lng: float
    tipo_vaga: Optional[TipoVaga] = None
    coordenadas: Optional[list[tuple[float, float]]] = None
    estado: EstadoVaga


# --- Recomendação --------------------------------------------------------------


class Candidato(BaseModel):
    id: str
    tipo: Literal["rua", "estacionamento"]
    nome: str
    lat: float
    lng: float
    caminhada_m: int
    caminhada_min: int
    tempo_carro_min: Optional[int]
    preco_estimado: float
    estado: EstadoVaga
    pode_reservar: bool
    nota: float
    componentes: dict[str, float]
    motivos: list[str]
    avisos: list[str]


class Descartado(BaseModel):
    id: str
    nome: str
    motivo: str


class RespostaRecomendacao(BaseModel):
    destino: Coordenada
    contexto: Contexto
    duracao_min: int
    chegada_prevista: datetime
    candidatos: list[Candidato]
    descartados: list[Descartado]
    mensagem: Optional[str] = None


# --- Reservas, sessões e reportes -----------------------------------------------


class Reserva(BaseModel):
    id: str
    estacionamento_id: str
    usuario_id: str
    codigo: str
    criada_em: datetime
    expira_em: datetime
    status: Literal["ativa", "expirada", "cancelada", "utilizada"]


class Sessao(BaseModel):
    id: str
    tipo: Literal["rua", "estacionamento"]
    alvo_id: str
    usuario_id: str
    placa: str
    inicio: datetime
    fim_previsto: datetime
    valor_pago: float
    pagamento: Literal["simulado"] = "simulado"
    status: Literal["ativa", "encerrada"]


class FeedbackChegada(BaseModel):
    alvo_id: str
    usuario_id: str
    encontrou: bool
    registrado_em: datetime
