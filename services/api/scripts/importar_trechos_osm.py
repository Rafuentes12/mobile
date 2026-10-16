"""Gera app/dados_mock/trechos.json com o traçado real das ruas, vindo do OpenStreetMap.

Entrada: scripts/trechos_referencia.json — o que a equipe levanta na rua para cada trecho:
    "rua X, entre a rua Y e a rua Z" (nomes como estão no OSM), tipo e capacidade.
    Para vagas especiais (idoso, PCD, carga e descarga), "junto_a" diz em qual esquina elas ficam.

Para cada trecho, o script:
  1. acha na rua X as esquinas com Y e com Z (nós que as duas ruas compartilham);
  2. segue a rua de uma esquina à outra — e recusa se houver outra esquina no meio
     (o trecho deve ser uma única quadra) ou se a quadra for calçadão;
  3. tira 5 m de cada ponta (o CTB proíbe estacionar a menos de 5 m da esquina);
  4. em vagas especiais, usa só o comprimento das vagas, a partir da esquina "junto_a".

Uso (de dentro de services/api):
    .venv/bin/python scripts/importar_trechos_osm.py                 # usa o cache se existir
    .venv/bin/python scripts/importar_trechos_osm.py --baixar        # baixa de novo do OSM
    .venv/bin/python scripts/importar_trechos_osm.py --esquinas "Rua Cruz Machado"

Dados © colaboradores do OpenStreetMap, licença ODbL (https://www.openstreetmap.org/copyright).
"""

import argparse
import heapq
import json
import math
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PASTA = Path(__file__).parent
REFERENCIA = PASTA / "trechos_referencia.json"
CACHE = PASTA / "cache" / "osm_centro_batel.json"
SAIDA = PASTA.parent / "app" / "dados_mock" / "trechos.json"

OVERPASS = "https://overpass-api.de/api/interpreter"
CAIXA = (-25.4520, -49.3000, -25.4240, -49.2620)  # sul, oeste, norte, leste — Centro e Batel

# Ruas por onde passa carro (onde pode existir vaga).
VEICULARES = {"primary", "secondary", "tertiary", "residential", "unclassified", "living_street",
              "trunk", "primary_link", "secondary_link", "tertiary_link"}
# Ruas que delimitam quarteirões (inclui calçadões, que também "cortam" a quadra).
DELIMITADORAS = VEICULARES | {"pedestrian"}

RECUO_ESQUINA_M = 5.0
COMPRIMENTO_VAGA_M = 5.5

ABREVIACOES = {"Rua ": "R. ", "Alameda ": "Al. ", "Avenida ": "Av. ", "Travessa ": "Tv. ", "Praça ": "Pça. ",
               "Desembargador ": "Des. ", "Doutor ": "Dr. ", "Presidente ": "Pres. ", "Marechal ": "Mal. "}
SUFIXOS = {"idoso": " — vagas de idoso", "pcd": " — vagas PCD", "carga_descarga": " — carga e descarga"}


# --- Geometria local (metros num plano tangente; suficiente para quadras) -------------------

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


# --- Dados do OSM --------------------------------------------------------------------------


def baixar_osm():
    sul, oeste, norte, leste = CAIXA
    consulta = f'[out:json][timeout:90];way["highway"]["name"]({sul},{oeste},{norte},{leste});out geom;'
    pedido = urllib.request.Request(
        OVERPASS,
        data=urllib.parse.urlencode({"data": consulta}).encode(),
        headers={"User-Agent": "VagaCerta-MVP-academico/0.1 (PUCPR)"},
    )
    print("Baixando ruas do OpenStreetMap (Overpass API)...", file=sys.stderr)
    with urllib.request.urlopen(pedido, timeout=120) as resposta:
        dados = json.load(resposta)
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(dados), encoding="utf-8")
    return dados


class Ruas:
    def __init__(self, dados):
        self.posicao = {}           # nó → (lat, lng)
        self.nomes_no_no = {}       # nó → nomes das ruas delimitadoras que passam por ele
        self.vias = []              # (nome, highway, [nós])
        for via in dados["elements"]:
            if via.get("type") != "way" or "geometry" not in via:
                continue
            nome, tipo = via["tags"]["name"], via["tags"]["highway"]
            for no, g in zip(via["nodes"], via["geometry"]):
                self.posicao[no] = (g["lat"], g["lon"])
                if tipo in DELIMITADORAS:
                    self.nomes_no_no.setdefault(no, set()).add(nome)
            self.vias.append((nome, tipo, via["nodes"]))

    def grafo(self, nome):
        vizinhos = {}
        for n, tipo, nos in self.vias:
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


def abreviar(nome):
    for longo, curto in ABREVIACOES.items():
        nome = nome.replace(longo, curto)
    return nome


def esquinas(ruas, vizinhos, rua, transversal):
    return {no for no in vizinhos if transversal in ruas.transversais(no, rua)}


def gerar_trecho(ruas, ref):
    nome, (rua_y, rua_z) = ref["rua_osm"], ref["entre"]
    vizinhos = ruas.grafo(nome)
    if not vizinhos:
        raise ValueError(f"rua '{nome}' não encontrada no OSM (ou só existe como calçadão) dentro da área")
    nos_y, nos_z = esquinas(ruas, vizinhos, nome, rua_y), esquinas(ruas, vizinhos, nome, rua_z)
    for transversal, nos in ((rua_y, nos_y), (rua_z, nos_z)):
        if not nos:
            raise ValueError(f"'{nome}' não cruza '{transversal}' — use --esquinas para ver as opções")

    caminho = caminho_mais_curto(ruas, vizinhos, nos_y, nos_z)
    if caminho is None:
        raise ValueError(f"não há trecho de {nome} para carros entre {rua_y} e {rua_z} (calçadão?)")
    no_meio = [ruas.transversais(no, nome) for no in caminho[1:-1] if ruas.transversais(no, nome)]
    if no_meio:
        raise ValueError(f"entre {rua_y} e {rua_z} há outras esquinas ({', '.join(n[0] for n in no_meio)}) "
                         "— divida em uma quadra por trecho")

    quadra = [ruas.posicao[no] for no in caminho]
    total = comprimento(quadra)
    if ref["tipo"] == "comum":
        inicio, fim = RECUO_ESQUINA_M, total - RECUO_ESQUINA_M
    else:
        tamanho = ref["capacidade"] * COMPRIMENTO_VAGA_M
        if ref.get("junto_a", rua_y) == rua_y:
            inicio, fim = RECUO_ESQUINA_M, min(total - RECUO_ESQUINA_M, RECUO_ESQUINA_M + tamanho)
        else:
            inicio, fim = max(RECUO_ESQUINA_M, total - RECUO_ESQUINA_M - tamanho), total - RECUO_ESQUINA_M
    linha = recortar(quadra, inicio, fim)

    descricao = f"{abreviar(nome)}, entre {abreviar(rua_y)} e {abreviar(rua_z)}{SUFIXOS.get(ref['tipo'], '')}"
    cabe = int((fim - inicio) // COMPRIMENTO_VAGA_M)
    aviso = f"  ⚠ capacidade {ref['capacidade']} > {cabe} vagas que cabem" if ref["capacidade"] > cabe else ""
    print(f"{ref['id']}: {descricao} · {fim - inicio:.0f} m{aviso}", file=sys.stderr)

    return {
        "id": ref["id"],
        "setor_id": ref["setor_id"],
        "nome": descricao,
        "tipo": ref["tipo"],
        "capacidade": ref["capacidade"],
        "coordenadas": [[round(lat, 6), round(lng, 6)] for lat, lng in linha],
    }


def listar_esquinas(ruas, rua):
    vizinhos = ruas.grafo(rua)
    if not vizinhos:
        print(f"'{rua}' não encontrada (confira o nome exato no OSM).", file=sys.stderr)
        return
    # Ordena as esquinas seguindo a rua a partir de uma ponta.
    pontas = [no for no, v in vizinhos.items() if len(v) == 1] or list(vizinhos)
    ordem, visto, pilha = [], set(), [pontas[0]]
    while pilha:
        no = pilha.pop()
        if no in visto:
            continue
        visto.add(no)
        ordem.append(no)
        pilha.extend(sorted(vizinhos[no] - visto, key=lambda n: -dist(ruas.posicao[no], ruas.posicao[n])))
    print(f"Esquinas de {rua} (em ordem ao longo da via):")
    for no in ordem:
        if ruas.transversais(no, rua):
            lat, lng = ruas.posicao[no]
            print(f"  {', '.join(ruas.transversais(no, rua))}  ({lat:.5f}, {lng:.5f})")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baixar", action="store_true", help="ignora o cache e baixa de novo do OSM")
    parser.add_argument("--esquinas", metavar="RUA", help="só lista as esquinas de uma rua e sai")
    args = parser.parse_args()

    dados = baixar_osm() if args.baixar or not CACHE.exists() else json.loads(CACHE.read_text(encoding="utf-8"))
    ruas = Ruas(dados)
    if args.esquinas:
        listar_esquinas(ruas, args.esquinas)
        return
    referencias = json.loads(REFERENCIA.read_text(encoding="utf-8"))

    trechos, erros = [], []
    for ref in referencias:
        try:
            trechos.append(gerar_trecho(ruas, ref))
        except ValueError as e:
            erros.append(f"{ref['id']}: {e}")
    if erros:
        print("\nNão gerei o arquivo; corrija trechos_referencia.json:\n  " + "\n  ".join(erros), file=sys.stderr)
        sys.exit(1)

    linhas = ",\n".join("  " + json.dumps(t, ensure_ascii=False) for t in trechos)
    SAIDA.write_text(f"[\n{linhas}\n]\n", encoding="utf-8")
    print(f"\n{len(trechos)} trechos gravados em {SAIDA.relative_to(PASTA.parent)}", file=sys.stderr)


if __name__ == "__main__":
    main()
