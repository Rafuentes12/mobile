"""Funções compartilhadas pelos scripts que leem o OpenStreetMap.

Dados © colaboradores do OpenStreetMap, licença ODbL (https://www.openstreetmap.org/copyright).
"""

import heapq
import json
import math
import sys
import urllib.parse
import urllib.request

OVERPASS = "https://overpass-api.de/api/interpreter"
USER_AGENT = "VagaCerta-MVP-academico/0.1 (PUCPR)"

# Ruas por onde passa carro (onde pode existir vaga).
VEICULARES = {"primary", "secondary", "tertiary", "residential", "unclassified", "living_street",
              "trunk", "primary_link", "secondary_link", "tertiary_link"}
# Ruas que delimitam quarteirões (inclui calçadões, que também "cortam" a quadra).
DELIMITADORAS = VEICULARES | {"pedestrian"}

RECUO_ESQUINA_M = 5.0     # CTB: proibido estacionar a menos de 5 m da esquina
COMPRIMENTO_VAGA_M = 5.5  # vaga paralela ao meio-fio

ABREVIACOES = {"Rua ": "R. ", "Alameda ": "Al. ", "Avenida ": "Av. ", "Travessa ": "Tv. ", "Praça ": "Pça. ",
               "Desembargador ": "Des. ", "Doutor ": "Dr. ", "Presidente ": "Pres. ", "Marechal ": "Mal. "}


# --- Geometria local (metros num plano tangente; suficiente para a escala de bairros) ------

LAT0 = math.radians(-25.437)
M_POR_GRAU_LAT = 111_320.0
M_POR_GRAU_LNG = 111_320.0 * math.cos(LAT0)


def xy(p):
    return (p[1] * M_POR_GRAU_LNG, p[0] * M_POR_GRAU_LAT)


def latlng(q):
    return (q[1] / M_POR_GRAU_LAT, q[0] / M_POR_GRAU_LNG)


def dist(a, b):
    (ax, ay), (bx, by) = xy(a), xy(b)
    return math.hypot(ax - bx, ay - by)


def comprimento(linha):
    return sum(dist(linha[i], linha[i + 1]) for i in range(len(linha) - 1))


def dist_ponto_segmento(p, a, b):
    (px, py), (ax, ay), (bx, by) = xy(p), xy(a), xy(b)
    dx, dy = bx - ax, by - ay
    comp2 = dx * dx + dy * dy
    t = 0.0 if comp2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / comp2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def dist_ponto_linha(p, linha):
    if len(linha) == 1:
        return dist(p, linha[0])
    return min(dist_ponto_segmento(p, linha[i], linha[i + 1]) for i in range(len(linha) - 1))


def ponto_no_poligono(p, anel):
    """Ray casting; `anel` é uma lista de (lat, lng)."""
    lat, lng = p
    dentro = False
    j = len(anel) - 1
    for i in range(len(anel)):
        (lat_i, lng_i), (lat_j, lng_j) = anel[i], anel[j]
        if (lat_i > lat) != (lat_j > lat):
            cruzamento = lng_i + (lat - lat_i) * (lng_j - lng_i) / (lat_j - lat_i)
            if lng < cruzamento:
                dentro = not dentro
        j = i
    return dentro


def ponto_no_meio(linha):
    """Ponto a meio caminho ao longo da linha."""
    metade = comprimento(linha) / 2
    pedaco = recortar(linha, metade, metade + 0.01)
    return pedaco[0] if pedaco else linha[0]


def recortar(linha, inicio_m, fim_m):
    """Sub-linha entre as distâncias inicio_m e fim_m medidas ao longo da linha."""
    resultado, acumulado = [], 0.0
    for i in range(len(linha) - 1):
        a, b = linha[i], linha[i + 1]
        d = dist(a, b)
        for alvo in (inicio_m, fim_m):
            if acumulado <= alvo <= acumulado + d and d > 0:
                t = (alvo - acumulado) / d
                ponto = latlng(tuple(xa + t * (xb - xa) for xa, xb in zip(xy(a), xy(b))))
                if alvo == inicio_m and not resultado:
                    resultado.append(ponto)
                elif alvo == fim_m:
                    resultado.append(ponto)
                    return resultado
        if resultado and acumulado + d < fim_m:
            resultado.append(b)
        acumulado += d
    return resultado


# --- Download ---------------------------------------------------------------------------------


def overpass(consulta: str, timeout: int = 180) -> dict:
    pedido = urllib.request.Request(
        OVERPASS,
        data=urllib.parse.urlencode({"data": consulta}).encode(),
        headers={"User-Agent": USER_AGENT},
    )
    print("Baixando dados do OpenStreetMap (Overpass API)...", file=sys.stderr)
    with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
        return json.load(resposta)


# --- Grafo de ruas ----------------------------------------------------------------------------


class Ruas:
    """Ruas do OSM indexadas por nó, para achar esquinas e andar ao longo de uma rua."""

    def __init__(self, dados):
        self.posicao = {}       # nó → (lat, lng)
        self.nomes_no_no = {}   # nó → nomes das ruas delimitadoras que passam por ele
        self.vias = []          # (nome, highway, [nós], tags)
        self.tags_aresta = {}   # (nó a, nó b) → tags da via (ruas nomeadas para carros)
        for via in dados["elements"]:
            if via.get("type") != "way" or "geometry" not in via or "highway" not in via.get("tags", {}):
                continue
            tags = via["tags"]
            nome, tipo = tags.get("name"), tags["highway"]
            for no, g in zip(via["nodes"], via["geometry"]):
                self.posicao[no] = (g["lat"], g["lon"])
                if nome and tipo in DELIMITADORAS:
                    self.nomes_no_no.setdefault(no, set()).add(nome)
            self.vias.append((nome, tipo, via["nodes"], tags))
            if nome and tipo in VEICULARES:
                for a, b in zip(via["nodes"], via["nodes"][1:]):
                    self.tags_aresta[(a, b)] = self.tags_aresta[(b, a)] = tags

    def nomes_veiculares(self):
        return sorted({n for n, tipo, _, _ in self.vias if n and tipo in VEICULARES})

    def grafo(self, nome):
        vizinhos = {}
        for n, tipo, nos, _ in self.vias:
            if n != nome or tipo not in VEICULARES:
                continue
            for a, b in zip(nos, nos[1:]):
                vizinhos.setdefault(a, set()).add(b)
                vizinhos.setdefault(b, set()).add(a)
        return vizinhos

    def transversais(self, no, nome):
        return sorted(self.nomes_no_no.get(no, set()) - {nome})


def caminho_mais_curto(ruas, vizinhos, origens, destinos):
    """Dijkstra pela rua, de qualquer nó em `origens` até qualquer nó em `destinos`."""
    fila = [(0.0, no, None) for no in origens]
    anterior, visitados = {}, set()
    while fila:
        custo, no, veio_de = heapq.heappop(fila)
        if no in visitados:
            continue
        visitados.add(no)
        anterior[no] = veio_de
        if no in destinos:
            caminho = [no]
            while anterior[caminho[-1]] is not None:
                caminho.append(anterior[caminho[-1]])
            return list(reversed(caminho))
        for prox in vizinhos.get(no, ()):
            if prox not in visitados:
                heapq.heappush(fila, (custo + dist(ruas.posicao[no], ruas.posicao[prox]), prox, no))
    return None


def esquinas(ruas, vizinhos, rua, transversal):
    return {no for no in vizinhos if transversal in ruas.transversais(no, rua)}


def abreviar(nome):
    for longo, curto in ABREVIACOES.items():
        nome = nome.replace(longo, curto)
    return nome


def componentes_em_ordem(vizinhos, ruas):
    """Partes contínuas da rua, cada uma como lista de nós em ordem a partir de uma ponta."""
    restantes, partes = set(vizinhos), []
    while restantes:
        pontas = [no for no in restantes if len(vizinhos[no]) == 1] or sorted(restantes)
        ordem, visto, pilha = [], set(), [pontas[0]]
        while pilha:
            no = pilha.pop()
            if no in visto:
                continue
            visto.add(no)
            ordem.append(no)
            pilha.extend(sorted(vizinhos[no] - visto, key=lambda n: -dist(ruas.posicao[no], ruas.posicao[n])))
        partes.append(ordem)
        restantes -= visto
    return partes


def listar_esquinas(ruas, rua):
    vizinhos = ruas.grafo(rua)
    if not vizinhos:
        print(f"'{rua}' não encontrada (confira o nome exato no OSM).", file=sys.stderr)
        return
    partes = componentes_em_ordem(vizinhos, ruas)
    print(f"Esquinas de {rua} (em ordem ao longo da via):")
    for i, ordem in enumerate(partes, 1):
        if len(partes) > 1:
            print(f"  -- parte {i} de {len(partes)} --")
        for no in ordem:
            if ruas.transversais(no, rua):
                lat, lng = ruas.posicao[no]
                print(f"  {', '.join(ruas.transversais(no, rua))}  ({lat:.5f}, {lng:.5f})")
