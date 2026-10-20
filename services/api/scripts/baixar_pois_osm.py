"""Baixa do OpenStreetMap os estabelecimentos que geram procura por vaga (Centro e Batel).

São a base do modelo de disponibilidade sem dados ao vivo (app/servicos/demanda.py):
bares e restaurantes à noite, comércio e escritórios de dia, escolas na entrada e saída...

Uso (de dentro de services/api):
    .venv/bin/python scripts/baixar_pois_osm.py

Dados © colaboradores do OpenStreetMap, licença ODbL (https://www.openstreetmap.org/copyright).
"""

import json
import sys
from collections import Counter
from pathlib import Path

from osm_comum import overpass

SAIDA = Path(__file__).parent.parent / "app" / "dados_osm" / "pois.json"

# Centro + Batel, com ~400 m de margem (a distância a pé que o modelo considera).
CAIXA = (-25.4520, -49.3020, -25.4220, -49.2580)  # sul, oeste, norte, leste

# Tag do OSM → categoria do modelo de demanda.
CATEGORIAS = {
    ("amenity", "bar"): "bar", ("amenity", "pub"): "bar", ("amenity", "biergarten"): "bar",
    ("amenity", "nightclub"): "balada",
    ("amenity", "restaurant"): "restaurante",
    ("amenity", "fast_food"): "lanchonete", ("amenity", "food_court"): "lanchonete",
    ("amenity", "cafe"): "cafe", ("amenity", "ice_cream"): "cafe",
    ("amenity", "bank"): "banco",
    ("amenity", "clinic"): "saude", ("amenity", "doctors"): "saude", ("amenity", "dentist"): "saude",
    ("amenity", "hospital"): "hospital",
    ("amenity", "school"): "escola", ("amenity", "kindergarten"): "escola",
    ("amenity", "university"): "universidade", ("amenity", "college"): "universidade",
    ("amenity", "cinema"): "cultura", ("amenity", "theatre"): "cultura", ("amenity", "arts_centre"): "cultura",
    ("amenity", "place_of_worship"): "igreja",
    ("leisure", "fitness_centre"): "academia", ("leisure", "sports_centre"): "academia",
    ("shop", "mall"): "shopping",
}


def categoria(tags):
    for (chave, valor), nome in CATEGORIAS.items():
        if tags.get(chave) == valor:
            return nome
    if "shop" in tags:
        return "comercio"
    if "office" in tags:
        return "escritorio"
    return None


def main():
    sul, oeste, norte, leste = CAIXA
    caixa = f"({sul},{oeste},{norte},{leste})"
    filtros = sorted({f'nwr["{k}"="{v}"]{caixa};' for k, v in CATEGORIAS} | {f'nwr["shop"]{caixa};', f'nwr["office"]{caixa};'})
    dados = overpass(f"[out:json][timeout:180];({''.join(filtros)});out center tags;")

    pois, vistos = [], set()
    for e in dados["elements"]:
        cat = categoria(e.get("tags", {}))
        posicao = (e["lat"], e["lon"]) if "lat" in e else (e.get("center", {}).get("lat"), e.get("center", {}).get("lon"))
        if cat is None or posicao[0] is None or (e["type"], e["id"]) in vistos:
            continue
        vistos.add((e["type"], e["id"]))
        pois.append({"categoria": cat, "lat": round(posicao[0], 6), "lng": round(posicao[1], 6),
                     "nome": e["tags"].get("name")})
    pois.sort(key=lambda p: (p["categoria"], p["lat"], p["lng"]))

    linhas = ",\n".join("  " + json.dumps(p, ensure_ascii=False) for p in pois)
    SAIDA.write_text(f"[\n{linhas}\n]\n", encoding="utf-8")
    print(f"{len(pois)} estabelecimentos gravados em {SAIDA.name}:", dict(Counter(p['categoria'] for p in pois).most_common()),
          file=sys.stderr)


if __name__ == "__main__":
    main()
