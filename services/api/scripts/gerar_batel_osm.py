"""Gera as vagas REAIS do bairro Batel a partir de dados abertos.

Fontes:
  - Limite do bairro: IPPUC/GeoCuritiba (camada oficial "Divisa de Bairros").
  - Ruas, faixas de pedestre, pontos de ônibus, hidrantes, entradas de garagem e
    estacionamentos: OpenStreetMap (© colaboradores do OSM, licença ODbL).
  - Trechos com EstaR: lista da Setran publicada em 01/11/2019 (batel_estar_setran_2019.json).

Como o OSM quase nunca diz onde se pode estacionar, a regra é a do CTB: na rua pode,
salvo exceções. Para cada quadra (rua entre duas esquinas) dentro do Batel:
  1. descarta rotatórias, pontes, túneis, vias expressas e acessos;
  2. conta os lados com estacionamento (mão única = 1, mão dupla = 2), menos os lados
     com faixa de ônibus, ciclofaixa ou proibição marcada no OSM;
  3. tira 5 m de cada esquina e desconta faixas de pedestre, pontos de ônibus, hidrantes
     e entradas de garagem mapeadas; aplica um fator para garagens não mapeadas;
  4. estima a capacidade em vagas de 5,5 m.
Quadras que a Setran listou como EstaR recebem esse regime; as demais ficam "a confirmar"
(pode ser EstaR ou rua livre) até a equipe ou os usuários confirmarem.

Uso (de dentro de services/api):
    .venv/bin/python scripts/gerar_batel_osm.py            # usa o cache se existir
    .venv/bin/python scripts/gerar_batel_osm.py --baixar   # baixa de novo (IPPUC + OSM)
"""

import argparse
import json
import math
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

from osm_comum import (
    COMPRIMENTO_VAGA_M,
    RECUO_ESQUINA_M,
    Ruas,
    abreviar,
    caminho_mais_curto,
    comprimento,
    dist,
    dist_ponto_linha,
    esquinas,
    overpass,
    ponto_no_meio,
    ponto_no_poligono,
    recortar,
    xy,
)

PASTA = Path(__file__).parent
CACHE_OSM = PASTA / "cache" / "osm_batel.json"
CACHE_LIMITE = PASTA / "cache" / "batel_limite_ippuc.json"
FONTE_ESTAR = PASTA / "batel_estar_setran_2019.json"
SAIDA = PASTA.parent / "app" / "dados_osm"

IPPUC_BAIRROS = ("https://geocuritiba.ippuc.org.br/server/rest/services/Hosted/"
                 + urllib.parse.quote("DIVISA_DE_BAIRROS_REGIONAL_visualização")
                 + "/FeatureServer/0/query")
MARGEM_GRAUS = 0.0015              # baixa um pouco além do limite para pegar as esquinas da borda
CENTRO_DA_CIDADE = (-25.4297, -49.2717)  # Praça Tiradentes ("sentido centro")
SETOR = "batel"

# Descontos (metros) — estimativas a calibrar com as contagens de campo.
DESCONTO_FAIXA_PEDESTRE_M = 6.0    # por lado
DESCONTO_PONTO_ONIBUS_M = 15.0
DESCONTO_HIDRANTE_M = 5.0
DESCONTO_GARAGEM_M = 4.0
DISTANCIA_PONTO_ONIBUS_M = 20.0
DISTANCIA_HIDRANTE_M = 8.0
FATOR_GARAGENS_NAO_MAPEADAS = 0.75
AREA_POR_VAGA_M2 = 25.0            # estacionamento de superfície, incluindo circulação
QUADRA_LONGA_M = 200.0             # quadras maiores são divididas em partes de até 150 m,
PARTE_MAXIMA_M = 150.0             # para a distância a pé e a chance de vaga serem úteis
PARECE_ESTACIONAMENTO = re.compile(r"estaciona|park|garag|shopping", re.IGNORECASE)

NAO_ESTACIONA = {"no", "no_parking", "no_stopping", "no_standing", "separate", "fire_lane"}
ESTACIONA = {"yes", "lane", "street_side", "on_kerb", "half_on_kerb", "shoulder", "parallel",
             "diagonal", "perpendicular", "marked", "inline", "free", "ticket", "disc"}
ACESSO_PROIBIDO = {"private", "permit", "no", "residents", "delivery", "employees"}


# --- Download ----------------------------------------------------------------------------------


def baixar_limite():
    consulta = urllib.parse.urlencode({"where": "nm_bairro='BATEL'", "outFields": "nm_bairro",
                                       "outSR": 4326, "f": "geojson"})
    print("Baixando o limite do Batel (IPPUC/GeoCuritiba)...", file=sys.stderr)
    with urllib.request.urlopen(f"{IPPUC_BAIRROS}?{consulta}", timeout=60) as resposta:
        geometria = json.load(resposta)["features"][0]["geometry"]
    anel = geometria["coordinates"][0] if geometria["type"] == "Polygon" else geometria["coordinates"][0][0]
    limite = [[round(lat, 6), round(lng, 6)] for lng, lat in anel]
    CACHE_LIMITE.parent.mkdir(exist_ok=True)
    CACHE_LIMITE.write_text(json.dumps(limite), encoding="utf-8")
    return limite


def baixar_osm(limite):
    lats, lngs = [p[0] for p in limite], [p[1] for p in limite]
    caixa = (min(lats) - MARGEM_GRAUS, min(lngs) - MARGEM_GRAUS, max(lats) + MARGEM_GRAUS, max(lngs) + MARGEM_GRAUS)
    consulta = f"""[out:json][timeout:180];
( way["highway"]{caixa};
  node["highway"~"^(crossing|bus_stop)$"]{caixa};
  node["public_transport"="platform"]{caixa};
  node["emergency"="fire_hydrant"]{caixa};
  nwr["amenity"="parking"]{caixa};
  nwr["leisure"="park"]["name"]{caixa};
); out geom;"""
    dados = overpass(consulta)
    CACHE_OSM.parent.mkdir(exist_ok=True)
    CACHE_OSM.write_text(json.dumps(dados), encoding="utf-8")
    return dados


# --- Leitura dos elementos do OSM ---------------------------------------------------------------


class ElementosBatel:
    def __init__(self, dados):
        self.ruas = Ruas(dados)
        self.cruzamentos, self.pontos_onibus, self.hidrantes = set(), [], []
        self.saidas_garagem = Counter()     # nó da rua → nº de acessos de garagem que chegam nele
        self.estacionamentos, self.parques = [], {}
        for e in dados["elements"]:
            tags = e.get("tags", {})
            if e["type"] == "node":
                ponto = (e["lat"], e["lon"])
                if tags.get("highway") == "crossing":
                    self.cruzamentos.add(e["id"])
                if tags.get("highway") == "bus_stop" or tags.get("public_transport") == "platform":
                    if all(dist(ponto, p) > 10 for p in self.pontos_onibus):
                        self.pontos_onibus.append(ponto)
                if tags.get("emergency") == "fire_hydrant":
                    self.hidrantes.append(ponto)
            if e["type"] == "way" and tags.get("highway") == "service" and not tags.get("name"):
                for no in (e["nodes"][0], e["nodes"][-1]):
                    self.saidas_garagem[no] += 1
            if tags.get("amenity") == "parking":
                self.estacionamentos.append(e)
            if tags.get("leisure") == "park" and e["type"] == "way":
                self.parques.setdefault(tags["name"], []).extend((g["lat"], g["lon"]) for g in e["geometry"])


# --- Quadras ------------------------------------------------------------------------------------


def quadras_da_rua(ruas, nome):
    """Divide a rua em quadras: caminhos entre esquinas (ou pontas) consecutivas."""
    vizinhos = ruas.grafo(nome)
    especiais = {no for no in vizinhos if ruas.transversais(no, nome) or len(vizinhos[no]) != 2}
    vistas, quadras = set(), []
    for inicio in sorted(especiais):
        for prox in sorted(vizinhos[inicio]):
            if (inicio, prox) in vistas:
                continue
            caminho, anterior, atual = [inicio, prox], inicio, prox
            vistas.update({(inicio, prox), (prox, inicio)})
            while atual not in especiais:
                seguinte = next(iter(vizinhos[atual] - {anterior}))
                vistas.update({(atual, seguinte), (seguinte, atual)})
                anterior, atual = atual, seguinte
                caminho.append(atual)
            quadras.append(caminho)
    return quadras


def _lado_permitido(tags, lado):
    for chave in (f"parking:{lado}", "parking:both", f"parking:lane:{lado}", "parking:lane:both",
                  f"parking:{lado}:restriction", "parking:both:restriction",
                  f"parking:condition:{lado}", "parking:condition:both"):
        valor = tags.get(chave)
        if valor in NAO_ESTACIONA:
            return False
        if valor in ESTACIONA:
            return True
    return None


def _lados_com_faixa(tags, prefixo, valores, mao_unica):
    if tags.get(f"{prefixo}:both") in valores or tags.get(prefixo) in valores:
        return 1 if mao_unica else 2
    return sum(tags.get(f"{prefixo}:{lado}") in valores for lado in ("left", "right"))


def motivo_exclusao(tags):
    if tags.get("junction") in ("roundabout", "circular"):
        return "rotatória"
    if tags.get("bridge", "no") != "no" or tags.get("tunnel", "no") != "no":
        return "ponte, viaduto ou túnel"
    if tags["highway"] in ("trunk", "motorway") or tags["highway"].endswith("_link"):
        return "via expressa ou acesso"
    if tags.get("access") in ("no", "private"):
        return "acesso restrito"
    return None


def estimar_quadra(el, nome, caminho):
    ruas = el.ruas
    linha = [ruas.posicao[no] for no in caminho]
    total = comprimento(linha)
    tags = ruas.tags_aresta[(caminho[0], caminho[1])]
    if motivo := motivo_exclusao(tags):
        return None, motivo

    mao_unica = tags.get("oneway") in ("yes", "1", "-1", "true")
    lados = 1 if mao_unica else 2
    permitidos = {lado: _lado_permitido(tags, lado) for lado in ("left", "right")}
    lados -= sum(v is False for v in permitidos.values())
    if mao_unica and all(v is True for v in permitidos.values()):
        lados = 2
    lados -= _lados_com_faixa(tags, "busway", {"lane", "opposite_lane"}, mao_unica)
    if "designated" in (tags.get("bus:lanes", "") + tags.get("lanes:bus", "") + tags.get("psv:lanes", "")):
        lados -= 1
    lados -= _lados_com_faixa(tags, "cycleway", {"lane", "track", "opposite_lane"}, mao_unica)
    lados = max(0, min(2, lados))
    if lados == 0:
        return None, "sem lado livre (faixa de ônibus, ciclofaixa ou proibição no OSM)"

    util_por_lado = total - 2 * RECUO_ESQUINA_M
    if util_por_lado < COMPRIMENTO_VAGA_M:
        return None, "quadra curta demais"

    def longe_das_pontas(ponto):
        return dist(ponto, linha[0]) > 8 and dist(ponto, linha[-1]) > 8

    descontos = Counter()
    for no in caminho[1:-1]:
        if no in el.cruzamentos and longe_das_pontas(ruas.posicao[no]):
            descontos["faixas de pedestre"] += DESCONTO_FAIXA_PEDESTRE_M * lados
        if el.saidas_garagem[no]:
            descontos["garagens mapeadas"] += DESCONTO_GARAGEM_M * el.saidas_garagem[no]
    for ponto in el.pontos_onibus:
        if dist_ponto_linha(ponto, linha) <= DISTANCIA_PONTO_ONIBUS_M and longe_das_pontas(ponto):
            descontos["pontos de ônibus"] += DESCONTO_PONTO_ONIBUS_M
    for ponto in el.hidrantes:
        if dist_ponto_linha(ponto, linha) <= DISTANCIA_HIDRANTE_M:
            descontos["hidrantes"] += DESCONTO_HIDRANTE_M

    metros = max(0.0, lados * util_por_lado - sum(descontos.values())) * FATOR_GARAGENS_NAO_MAPEADAS
    capacidade = math.floor(metros / COMPRIMENTO_VAGA_M)
    if capacidade < 1:
        return None, "sem espaço após os descontos"

    pontas = [ruas.transversais(caminho[0], nome), ruas.transversais(caminho[-1], nome)]
    if pontas[0] and pontas[1]:
        descricao = f"{abreviar(nome)}, entre {abreviar(pontas[0][0])} e {abreviar(pontas[1][0])}"
    elif pontas[0] or pontas[1]:
        descricao = f"{abreviar(nome)}, a partir da {abreviar((pontas[0] or pontas[1])[0])}"
    else:
        descricao = abreviar(nome)

    return {
        "rua": nome,
        "nome": descricao,
        "capacidade": capacidade,
        "lados": lados,
        "linha": recortar(linha, RECUO_ESQUINA_M, total - RECUO_ESQUINA_M),
        "estimativa": {
            "comprimento_m": round(total),
            "lados": lados,
            "descontos_m": {k: round(v) for k, v in descontos.items()},
            "fator_garagens_nao_mapeadas": FATOR_GARAGENS_NAO_MAPEADAS,
            "mao_unica": mao_unica,
        },
    }, None


# --- EstaR (lista da Setran) --------------------------------------------------------------------


def _resolver_ponta(el, vizinhos, rua, ponta):
    ruas = el.ruas
    if isinstance(ponta, str):
        return esquinas(ruas, vizinhos, rua, ponta), ponta
    if "marco" in ponta:
        contorno = el.parques.get(ponta["marco"], [])
        if not contorno:
            return set(), ponta["marco"]
        melhor = min(vizinhos, key=lambda no: dist_ponto_linha(ruas.posicao[no], contorno))
        perto = dist_ponto_linha(ruas.posicao[melhor], contorno) <= 80
        return ({melhor} if perto else set()), ponta["marco"]
    if "fim_sentido" in ponta:
        pontas = [no for no, v in vizinhos.items() if len(v) == 1]
        if not pontas:
            return set(), "fim da rua"
        return {min(pontas, key=lambda no: dist(ruas.posicao[no], CENTRO_DA_CIDADE))}, "fim da rua (sentido centro)"
    raise ValueError(f"ponta desconhecida: {ponta}")


def arestas_estar(el, fonte):
    """{(rua, aresta): status} para as arestas dentro dos trechos de EstaR listados."""
    marcadas, relatorio = {}, []
    for item in fonte["trechos"]:
        rua = item["rua"]
        vizinhos = el.ruas.grafo(rua)
        de, nome_de = _resolver_ponta(el, vizinhos, rua, item["de"])
        ate, nome_ate = _resolver_ponta(el, vizinhos, rua, item["ate"])
        rotulo = f"{abreviar(rua)} ({nome_de} → {nome_ate}, {item['status']})"
        faltando = [n for n, nos in ((nome_de, de), (nome_ate, ate)) if not nos]
        if faltando:
            relatorio.append(f"  ⚠ {rotulo}: não achei {', '.join(faltando)} nesta rua no OSM — trecho ignorado")
            continue
        caminho = caminho_mais_curto(el.ruas, vizinhos, de, ate)
        if caminho is None:
            relatorio.append(f"  ⚠ {rotulo}: a rua está interrompida no OSM entre as pontas — trecho ignorado")
            continue
        for a, b in zip(caminho, caminho[1:]):
            for aresta in ((a, b), (b, a)):
                # "implantado" tem prioridade sobre "previsto".
                if marcadas.get((rua, aresta)) != "implantado":
                    marcadas[(rua, aresta)] = item["status"]
        relatorio.append(f"  ✓ {rotulo}: {comprimento([el.ruas.posicao[n] for n in caminho]):.0f} m")
    return marcadas, relatorio


def regime_da_quadra(rua, caminho, marcadas, fonte):
    status = [marcadas.get((rua, (a, b))) for a, b in zip(caminho, caminho[1:])]
    contagem = Counter(s for s in status if s)
    if sum(contagem.values()) * 2 < len(status):  # menos da metade da quadra na lista
        return "a_confirmar", "estimado", "Estimado do OpenStreetMap: pode ser EstaR ou rua livre — confira a placa"
    data = fonte["fonte"]["publicado_em"][:4]
    if contagem["implantado"] >= contagem["previsto"]:
        return "estar", "fonte_oficial", f"EstaR implantado segundo a Setran ({data})"
    return "estar", "estimado", f"EstaR previsto pela Setran em {data} — confira a placa"


# --- Estacionamentos ----------------------------------------------------------------------------


def _area_m2(contorno):
    pontos = [xy(p) for p in contorno]
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pontos, pontos[1:] + pontos[:1]))) / 2


def estacionamentos_reais(el, limite):
    resultado, ignorados = [], Counter()
    for e in el.estacionamentos:
        tags = e.get("tags", {})
        if tags.get("parking") == "street_side":
            ignorados["vaga de rua (já coberta pelas quadras)"] += 1
            continue
        if tags.get("access") in ACESSO_PROIBIDO:
            ignorados["acesso privado"] += 1
            continue
        nome = tags.get("name") or tags.get("operator")
        if not (nome or tags.get("access") in ("yes", "customers", "public") or tags.get("fee") == "yes"):
            ignorados["sem nome nem indicação de acesso público (provavelmente de prédio)"] += 1
            continue
        if e["type"] == "node":
            centro, contorno = (e["lat"], e["lon"]), None
        elif e["type"] == "way":
            contorno = [(g["lat"], g["lon"]) for g in e["geometry"]]
            centro = (sum(p[0] for p in contorno) / len(contorno), sum(p[1] for p in contorno) / len(contorno))
        else:
            ignorados["relação (não suportado)"] += 1
            continue
        if not ponto_no_poligono(centro, limite):
            ignorados["fora do Batel"] += 1
            continue

        tipo = tags.get("parking", "surface")
        coberto = tipo in ("multi-storey", "underground")
        if str(tags.get("capacity", "")).isdigit():
            capacidade, estimada = int(tags["capacity"]), False
        elif contorno and len(contorno) > 3:
            andares = 3 if coberto else 1
            capacidade, estimada = max(5, round(_area_m2(contorno) / AREA_POR_VAGA_M2 * andares)), True
        else:
            capacidade, estimada = 20, True
        gratuito = tags.get("fee") == "no"
        resultado.append({
            "id": f"osm-{e['type'][0]}{e['id']}",
            "nome": nome or "Estacionamento sem nome no mapa",
            "endereco": tags.get("addr:street", "Batel") + (f", {tags['addr:housenumber']}" if "addr:housenumber" in tags else ""),
            "lat": round(centro[0], 6),
            "lng": round(centro[1], 6),
            "capacidade": capacidade,
            "capacidade_estimada": estimada,
            "preco_hora": 0.0 if gratuito else None,
            "preco_diaria": 0.0 if gratuito else None,
            "parceiro_id": None,
            "aceita_reserva": False,
            "cota_reserva": 0,
            "setor_referencia": SETOR,
            "horario": {"seg_sex": [0, 24], "sab": [0, 24], "dom": [0, 24]} if tags.get("opening_hours") == "24/7" else None,
            "acesso": _acesso(tags, nome),
            "fonte": "OpenStreetMap",
            "atributos": {
                "coberto": coberto,
                "altura_max_m": _numero(tags.get("maxheight")),
                "recarga_ev": False,
                "vagas_pcd": _numero(tags.get("capacity:disabled")) not in (None, 0),
            },
        })
    return sorted(resultado, key=lambda x: x["id"]), ignorados


def _acesso(tags, nome):
    """'clientes' quando o OSM diz, ou quando o nome é de outro negócio (farmácia, laboratório...)."""
    if tags.get("access") == "customers":
        return "clientes"
    if tags.get("access") in ("yes", "public") or not nome or PARECE_ESTACIONAMENTO.search(nome):
        return "publico"
    return "clientes"


def dividir(quadra):
    """Divide quadras longas em partes de até PARTE_MAXIMA_M, repartindo a capacidade."""
    total = comprimento(quadra["linha"])
    if total <= QUADRA_LONGA_M:
        return [quadra]
    n = math.ceil(total / PARTE_MAXIMA_M)
    partes = []
    for i in range(n):
        inicio, fim = total * i / n, total * (i + 1) / n
        capacidade = math.floor(quadra["capacidade"] * (i + 1) / n) - math.floor(quadra["capacidade"] * i / n)
        if capacidade < 1:
            continue
        partes.append({**quadra, "nome": f"{quadra['nome']} (parte {i + 1} de {n})", "capacidade": capacidade,
                       "linha": recortar(quadra["linha"], inicio, fim), "parte": i + 1})
    return partes


def _numero(texto):
    try:
        return float(str(texto).replace(",", ".").split()[0])
    except (TypeError, ValueError, IndexError):
        return None


# --- Principal ----------------------------------------------------------------------------------


def gravar(nome_arquivo, itens):
    linhas = ",\n".join("  " + json.dumps(i, ensure_ascii=False) for i in itens)
    (SAIDA / nome_arquivo).write_text(f"[\n{linhas}\n]\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baixar", action="store_true", help="ignora o cache e baixa de novo (IPPUC + OSM)")
    args = parser.parse_args()

    limite = baixar_limite() if args.baixar or not CACHE_LIMITE.exists() else json.loads(CACHE_LIMITE.read_text())
    limite_t = [tuple(p) for p in limite]
    dados = baixar_osm(limite) if args.baixar or not CACHE_OSM.exists() else json.loads(CACHE_OSM.read_text())
    el = ElementosBatel(dados)
    fonte = json.loads(FONTE_ESTAR.read_text(encoding="utf-8"))
    marcadas, relatorio_estar = arestas_estar(el, fonte)

    trechos, excluidas = [], Counter()
    for nome in el.ruas.nomes_veiculares():
        for caminho in quadras_da_rua(el.ruas, nome):
            linha = [el.ruas.posicao[no] for no in caminho]
            if not ponto_no_poligono(ponto_no_meio(linha), limite_t):
                continue
            quadra, motivo = estimar_quadra(el, nome, caminho)
            if quadra is None:
                excluidas[motivo] += 1
                continue
            regime, situacao, texto_fonte = regime_da_quadra(nome, caminho, marcadas, fonte)
            a, b = sorted((caminho[0], caminho[-1]))
            for parte in dividir(quadra):
                sufixo = f"-p{parte['parte']}" if "parte" in parte else ""
                trechos.append({
                    "id": f"osm-q{a}-{b}{sufixo}",
                    "setor_id": SETOR,
                    "nome": parte["nome"],
                    "tipo": "comum",
                    "capacidade": parte["capacidade"],
                    "regime": regime,
                    "situacao": situacao,
                    "fonte": texto_fonte,
                    "estimativa": parte["estimativa"],
                    "coordenadas": [[round(lat, 6), round(lng, 6)] for lat, lng in parte["linha"]],
                })
    trechos.sort(key=lambda t: t["id"])
    estacionamentos, ignorados = estacionamentos_reais(el, limite_t)

    SAIDA.mkdir(exist_ok=True)
    gravar("batel_trechos.json", trechos)
    gravar("batel_estacionamentos.json", estacionamentos)
    (SAIDA / "batel_limite.json").write_text(json.dumps(limite), encoding="utf-8")
    regimes = Counter((t["regime"], t["situacao"]) for t in trechos)
    metadados = {
        "gerado_em": date.today().isoformat(),
        "fontes": {
            "limite": "IPPUC/GeoCuritiba — Divisa de Bairros",
            "ruas_e_estacionamentos": "© colaboradores do OpenStreetMap (ODbL)",
            "estar": fonte["fonte"],
        },
        "quadras": len(trechos),
        "vagas_estimadas": sum(t["capacidade"] for t in trechos),
        "quadras_por_regime": {f"{r}/{s}": n for (r, s), n in regimes.items()},
        "quadras_excluidas": dict(excluidas),
        "estacionamentos": len(estacionamentos),
        "estacionamentos_ignorados": dict(ignorados),
    }
    (SAIDA / "batel_metadados.json").write_text(json.dumps(metadados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\nEstaR (lista da Setran, 2019):", *relatorio_estar, sep="\n", file=sys.stderr)
    print(f"\n{len(trechos)} quadras com estacionamento estimado, ~{metadados['vagas_estimadas']} vagas", file=sys.stderr)
    for (r, s), n in sorted(regimes.items()):
        print(f"  {r:12s} {s:14s} {n:4d} quadras", file=sys.stderr)
    print("Quadras excluídas:", dict(excluidas), file=sys.stderr)
    print(f"{len(estacionamentos)} estacionamentos; ignorados: {dict(ignorados)}", file=sys.stderr)
    print(f"Arquivos gravados em {SAIDA.relative_to(PASTA.parent)}/", file=sys.stderr)


if __name__ == "__main__":
    main()
