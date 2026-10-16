# Infraestrutura (próxima fase)

O MVP atual roda **só com dados mockados em memória** e não precisa de nada desta pasta.
Ela prepara a troca dos mocks por serviços reais, seguindo o planejamento técnico.

## PostGIS + Redis

```bash
docker compose -f infra/docker-compose.yml up -d
docker compose -f infra/docker-compose.yml exec postgis psql -U vagacerta -c '\dt'
```

O `schema.sql` é aplicado automaticamente na primeira subida do container.
**Ele ainda não foi executado contra um banco** — a primeira subida serve de validação.

Para trocar o mock pelo banco, crie um `CatalogoPostgres` em
`services/api/app/catalogo.py` com a mesma interface `Catalogo` e um script que
carregue os JSONs de `services/api/app/dados_mock/` nas tabelas.

## OSRM (tempo de carro sem custo por chamada)

Hoje a API estima o tempo de carro pela distância (`RotasEstimadas`). Para usar rotas reais:

```bash
mkdir -p infra/osrm && cd infra/osrm
curl -LO https://download.geofabrik.de/south-america/brazil/sul-latest.osm.pbf
# Opcional: recortar só a região de Curitiba com `osmium extract` para economizar memória.
docker run -t -v "$PWD:/data" osrm/osrm-backend osrm-extract -p /opt/car.lua /data/sul-latest.osm.pbf
docker run -t -v "$PWD:/data" osrm/osrm-backend osrm-partition /data/sul-latest.osrm
docker run -t -v "$PWD:/data" osrm/osrm-backend osrm-customize /data/sul-latest.osrm
docker run -t -p 5000:5000 -v "$PWD:/data" osrm/osrm-backend osrm-routed --algorithm mld /data/sul-latest.osrm
```

Depois, crie um `RotasOSRM` em `services/api/app/provedores/rotas.py` que chame
`GET http://localhost:5000/route/v1/driving/{lng1},{lat1};{lng2},{lat2}?overview=false`.
