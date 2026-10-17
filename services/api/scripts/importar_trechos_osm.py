"""Gera app/dados_mock/trechos.json (Centro, mockado) com o traçado real das ruas do OpenStreetMap.

O Batel tem um gerador próprio, que usa dados reais: scripts/gerar_batel_osm.py.

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
import json
import sys
from pathlib import Path

from osm_comum import (  # noqa: F401 — reexportados para os testes
    COMPRIMENTO_VAGA_M,
    RECUO_ESQUINA_M,
    Ruas,
    abreviar,
    caminho_mais_curto,
    comprimento,
    dist,
    esquinas,
    listar_esquinas,
    overpass,
    recortar,
)

PASTA = Path(__file__).parent
REFERENCIA = PASTA / "trechos_referencia.json"
CACHE = PASTA / "cache" / "osm_centro.json"
SAIDA = PASTA.parent / "app" / "dados_mock" / "trechos.json"

CAIXA = (-25.4400, -49.2830, -25.4260, -49.2620)  # sul, oeste, norte, leste — Centro

SUFIXOS = {"idoso": " — vagas de idoso", "pcd": " — vagas PCD", "carga_descarga": " — carga e descarga"}


def baixar_osm():
    sul, oeste, norte, leste = CAIXA
    dados = overpass(f'[out:json][timeout:90];way["highway"]["name"]({sul},{oeste},{norte},{leste});out geom;')
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(dados), encoding="utf-8")
    return dados


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
