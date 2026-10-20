"""Modelo de disponibilidade sem dados ao vivo (modelo v1).

Enquanto não há usuários nem parceiros reportando, a chance de vaga sai de:

1. Demanda por local e horário — cada estabelecimento real do OpenStreetMap (bar,
   restaurante, comércio, escritório, clínica, escola...) atrai carros conforme a
   categoria, o tipo de dia e a hora. Esses carros se distribuem pelas vagas a até
   ~400 m a pé, mais para as próximas e as maiores. Somam-se os carros de moradores e
   do movimento geral (uma fração da capacidade).
2. Dias separados — seg–qui, sex, sáb e dom. A madrugada (0h–5h) pertence à noite do
   dia anterior: 1h de sábado ainda é "sexta à noite".
3. Erlang B — com a demanda A (carros querendo parar ao mesmo tempo) e a capacidade c,
   a chance de chegar e encontrar tudo ocupado é B(c, A), a mesma fórmula usada para
   dimensionar linhas telefônicas (sistema de perda M/M/c/c). Ela vale para qualquer
   distribuição do tempo de permanência e, quando A passa de c, a chance de vaga cai
   de verdade.
4. Honestidade — sem dado ao vivo, o app mostra "Fácil / Moderado / Difícil (estimativa)",
   não uma porcentagem.

Todos os números abaixo são SUPOSIÇÕES a calibrar com as contagens de campo
(seção 6 do planejamento). Eles ficam juntos aqui para facilitar esse ajuste.
"""

import json
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from app.catalogo import Catalogo
from app.geo import distancia_m

PASTA_OSM = Path(__file__).parent.parent / "dados_osm"

INICIO_DO_DIA = 5                  # 0h–5h contam como a noite do dia anterior
RAIO_INFLUENCIA_M = 400            # até onde as pessoas aceitam andar (~5 min)
DECAIMENTO_M = 150                 # quanto mais perto do estabelecimento, mais procurada
RAIO_EXPLICACAO_M = 300
# O OSM tem bem menos estabelecimentos do que existem: no Batel, ~56 bares e restaurantes mapeados.
FATOR_COBERTURA_OSM = 4.0
INTENSIDADE_PARA_CITAR = 0.3       # categoria só entra na explicação se estiver ativa

# Erlang B tem ganho de escala: numa quadra de 20 vagas com procura igual à capacidade, ainda
# há 84% de chance de vaga. Por isso "fácil" exige folga de verdade.
LIMITE_FACIL = 0.85
LIMITE_MODERADO = 0.50

Janelas = dict[str, list[tuple[float, float, float]]]  # tipo de dia → [(início, fim, intensidade)]
UTEIS = ("seg_qui", "sex")


def _todos(janelas: list[tuple[float, float, float]], dias=("seg_qui", "sex", "sab", "dom")) -> Janelas:
    return {d: list(janelas) for d in dias}


def _juntar(*partes: Janelas) -> Janelas:
    resultado: Janelas = {}
    for parte in partes:
        for dia, janelas in parte.items():
            resultado.setdefault(dia, []).extend(janelas)
    return resultado


@dataclass(frozen=True)
class Categoria:
    rotulo_plural: str
    carros_no_pico: float           # carros estacionados ao mesmo tempo por estabelecimento, no pico
    janelas: Janelas = field(default_factory=dict)  # horas de 5 a 29 (29 = 5h do dia seguinte)


CATEGORIAS: dict[str, Categoria] = {
    "bar": Categoria("bares", 10, {
        "seg_qui": [(18, 23, 0.5), (23, 25, 0.3)],
        "sex": [(17, 19, 0.6), (19, 26, 1.0), (26, 28, 0.5)],
        "sab": [(12, 18, 0.5), (18, 26, 1.0), (26, 28, 0.5)],
        "dom": [(12, 19, 0.5), (19, 22, 0.3)],
    }),
    "balada": Categoria("baladas", 35, {
        "seg_qui": [(22, 26, 0.2)], "sex": [(22, 29, 1.0)], "sab": [(22, 29, 1.0)],
    }),
    "restaurante": Categoria("restaurantes", 8, _juntar(
        _todos([(11.5, 14.5, 0.8)]),
        {"seg_qui": [(19, 23, 0.6)], "sex": [(19, 24, 1.0)], "sab": [(19, 24, 1.0)],
         "dom": [(11.5, 15.5, 0.4), (19, 22, 0.5)]},  # almoço de domingo mais forte
    )),
    "lanchonete": Categoria("lanchonetes", 3, _juntar(
        _todos([(11, 14, 0.7), (18, 23, 0.5)]),
        {"sex": [(23, 26, 0.6)], "sab": [(23, 26, 0.6)]},
    )),
    "cafe": Categoria("cafés", 3, _todos([(8, 18, 0.6)])),
    "comercio": Categoria("lojas", 2, {d: [(9, 19, 0.8)] for d in UTEIS} | {"sab": [(9, 14, 0.8)]}),
    "shopping": Categoria("shoppings", 60, {d: [(10, 22, 0.7)] for d in UTEIS}
                          | {"sab": [(10, 22, 1.0)], "dom": [(14, 20, 0.9)]}),
    "escritorio": Categoria("escritórios", 8, {d: [(8, 18.5, 1.0)] for d in UTEIS}),
    "banco": Categoria("bancos", 4, {d: [(10, 16, 1.0)] for d in UTEIS}),
    "saude": Categoria("clínicas", 5, {d: [(8, 19, 0.9)] for d in UTEIS} | {"sab": [(8, 12, 0.5)]}),
    "hospital": Categoria("hospitais", 40, _todos([(7, 21, 0.8), (21, 29, 0.3)])),
    "escola": Categoria("escolas", 12, {d: [(7, 8.5, 1.0), (11.5, 13.5, 0.8), (17, 18.5, 1.0)] for d in UTEIS}),
    "universidade": Categoria("faculdades", 30, {d: [(7, 23, 0.7)] for d in UTEIS} | {"sab": [(8, 13, 0.4)]}),
    "cultura": Categoria("cinemas e teatros", 20, {"seg_qui": [(19, 23, 0.5)], "sex": [(19, 24, 1.0)],
                                                   "sab": [(15, 24, 1.0)], "dom": [(15, 22, 0.8)]}),
    "academia": Categoria("academias", 6, {d: [(6, 9, 0.8), (17, 22, 1.0)] for d in UTEIS}
                          | {"sab": [(8, 13, 0.6)]}),
    "igreja": Categoria("igrejas", 15, {"sab": [(18, 21, 0.4)], "dom": [(8, 12, 0.8), (18, 21, 0.6)]}),
}

# Moradores, visitantes e movimento geral que os estabelecimentos do mapa não explicam,
# como fração da capacidade. Sexta e sábado à noite têm mais gente na rua.
BASE: Janelas = {
    "seg_qui": [(5, 8, 0.35), (8, 19, 0.5), (19, 29, 0.4)],
    "sex": [(5, 8, 0.35), (8, 19, 0.5), (19, 29, 0.5)],
    "sab": [(5, 19, 0.35), (19, 29, 0.5)],
    "dom": [(5, 29, 0.3)],
}

DIAS_DA_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def dia_e_hora(momento: datetime) -> tuple[str, float, str]:
    """(tipo de dia, hora estendida de 5 a 29, nome do dia) — a madrugada é da noite anterior."""
    hora = momento.hour + momento.minute / 60
    dia = momento
    if momento.hour < INICIO_DO_DIA:
        dia, hora = momento - timedelta(days=1), hora + 24
    semana = dia.weekday()
    tipo = "seg_qui" if semana <= 3 else ("sex", "sab", "dom")[semana - 4]
    return tipo, hora, DIAS_DA_SEMANA[semana]


def _intensidade(janelas: Janelas, tipo: str, hora: float) -> float:
    return max((i for inicio, fim, i in janelas.get(tipo, []) if inicio <= hora < fim), default=0.0)


def erlang_b(capacidade: int, carga: float) -> float:
    """Chance de todas as `capacidade` vagas estarem ocupadas com `carga` carros querendo parar."""
    if carga <= 0:
        return 0.0
    b = 1.0
    for k in range(1, max(1, capacidade) + 1):
        b = carga * b / (k + carga * b)
    return b


def nivel(prob_livre: float) -> str:
    if prob_livre >= LIMITE_FACIL:
        return "facil"
    return "moderado" if prob_livre >= LIMITE_MODERADO else "dificil"


@dataclass
class Estimativa:
    prob_livre: float
    vagas_livres: int
    explicacao: str


def carregar_pois() -> list[dict]:
    arquivo = PASTA_OSM / "pois.json"
    return json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else []


class ModeloDemanda:
    def __init__(self, catalogo: Catalogo, pois: Optional[list[dict]] = None) -> None:
        self._catalogo = catalogo
        self._pois = carregar_pois() if pois is None else pois
        self._parcelas: dict[str, list[tuple[str, float]]] = {}  # alvo → [(categoria, carros no pico)]
        self._perto: dict[str, Counter] = {}                      # alvo → categorias a até 300 m
        self._distribuir()

    def _alvos(self) -> list[tuple[str, float, float, int]]:
        alvos = [(t.id, t.lat, t.lng, t.capacidade) for t in self._catalogo.trechos() if t.tipo == "comum"]
        alvos += [(e.id, e.lat, e.lng, e.capacidade) for e in self._catalogo.estacionamentos()]
        return alvos

    def _distribuir(self) -> None:
        """Reparte os carros de cada estabelecimento entre as vagas próximas (uma vez só)."""
        alvos = self._alvos()
        margem_lat = RAIO_INFLUENCIA_M / 111_320  # filtro rápido antes da distância exata
        for poi in self._pois:
            cat = CATEGORIAS.get(poi["categoria"])
            if cat is None:
                continue
            margem_lng = margem_lat / math.cos(math.radians(poi["lat"]))
            pesos = []
            for alvo_id, lat, lng, capacidade in alvos:
                if abs(lat - poi["lat"]) > margem_lat or abs(lng - poi["lng"]) > margem_lng:
                    continue
                d = distancia_m(poi["lat"], poi["lng"], lat, lng)
                if d <= RAIO_INFLUENCIA_M:
                    pesos.append((alvo_id, capacidade * math.exp(-d / DECAIMENTO_M)))
                if d <= RAIO_EXPLICACAO_M:
                    self._perto.setdefault(alvo_id, Counter())[poi["categoria"]] += 1
            total = sum(p for _, p in pesos)
            for alvo_id, peso in pesos:
                carros = cat.carros_no_pico * FATOR_COBERTURA_OSM * peso / total
                self._parcelas.setdefault(alvo_id, []).append((poi["categoria"], carros))

    def carga(self, alvo_id: str, capacidade: int, momento: datetime) -> float:
        tipo, hora, _ = dia_e_hora(momento)
        carga = capacidade * _intensidade(BASE, tipo, hora)
        for categoria, carros in self._parcelas.get(alvo_id, []):
            carga += carros * _intensidade(CATEGORIAS[categoria].janelas, tipo, hora)
        return carga

    def estimar(self, alvo_id: str, capacidade: int, momento: datetime) -> Estimativa:
        carga = self.carga(alvo_id, capacidade, momento)
        bloqueio = erlang_b(capacidade, carga)
        ocupadas = carga * (1 - bloqueio)  # carros efetivamente estacionados
        return Estimativa(
            prob_livre=1 - bloqueio,
            vagas_livres=max(0, round(capacidade - ocupadas)),
            explicacao=self._explicar(alvo_id, momento),
        )

    def _explicar(self, alvo_id: str, momento: datetime) -> str:
        tipo, hora, nome_dia = dia_e_hora(momento)
        quando = f"{nome_dia}, {momento:%H}h"
        ativos = [(n, cat) for cat, n in self._perto.get(alvo_id, Counter()).most_common()
                  if _intensidade(CATEGORIAS[cat].janelas, tipo, hora) >= INTENSIDADE_PARA_CITAR]
        if not ativos:
            return f"{quando} · pouco movimento previsto por perto"
        partes = [f"{n} {CATEGORIAS[cat].rotulo_plural if n > 1 else _singular(cat)}" for n, cat in ativos[:3]]
        return f"{quando} · perto de {', '.join(partes)}"


def _singular(categoria: str) -> str:
    return {"bar": "bar", "balada": "balada", "restaurante": "restaurante", "lanchonete": "lanchonete",
            "cafe": "café", "comercio": "loja", "shopping": "shopping", "escritorio": "escritório",
            "banco": "banco", "saude": "clínica", "hospital": "hospital", "escola": "escola",
            "universidade": "faculdade", "cultura": "cinema/teatro", "academia": "academia",
            "igreja": "igreja"}[categoria]
