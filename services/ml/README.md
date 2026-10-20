# Modelo de ocupação

## Modelo v1 (atual): demanda dos estabelecimentos + Erlang B

Implementado em `services/api/app/servicos/demanda.py`. Vale quando não há dado ao vivo
(nenhum parceiro, cancela ou usuário reportou a vaga recentemente):

1. **Demanda por local e horário** — 1.551 estabelecimentos reais do OpenStreetMap no Centro e
   no Batel (`app/dados_osm/pois.json`, gerado por `scripts/baixar_pois_osm.py`). Cada categoria
   (bar, restaurante, comércio, escritório, clínica, escola...) atrai carros conforme o dia e a
   hora; esses carros se repartem pelas vagas a até 400 m, mais para as próximas e as maiores.
   Soma-se uma fração da capacidade para moradores e movimento geral.
2. **Dias separados** — seg–qui, sex, sáb e dom; a madrugada pertence à noite anterior.
3. **Erlang B** — com a demanda A e a capacidade c, a chance de encontrar tudo ocupado é B(c, A).
4. **Honestidade** — sem dado ao vivo, o app mostra "Fácil / Moderado / Difícil (estimativa)"
   em cores claras, com a explicação ("Sexta, 22h · perto de 12 restaurantes, 6 bares").

Resultado no Batel (205 trechos): sexta 22h → 43 fácil / 102 moderado / 60 difícil;
domingo 7h → 151 / 44 / 10.

## O que calibrar com as contagens de campo

Todos os números do topo de `demanda.py` são suposições:

| Parâmetro | Hoje | Como calibrar |
|---|---|---|
| `carros_no_pico` por categoria | bar 10, restaurante 8, balada 35... | contar carros perto de alguns estabelecimentos no pico |
| `FATOR_COBERTURA_OSM` | 4,0 | comparar estabelecimentos do OSM com os que existem em 10 quadras |
| `BASE` (moradores e movimento geral) | 0,3–0,5 da capacidade | contagens em ruas residenciais |
| Janelas de horário | ex.: bares fortes sex/sáb 19h–2h | observação |
| `LIMITE_FACIL` / `LIMITE_MODERADO` | 0,85 / 0,50 | taxa de acerto do "Encontrou a vaga?" (`GET /metricas`) |

Próximo passo (v2): com contagens e reportes acumulados, ajustar esses parâmetros
automaticamente (regressão) e calibrar as probabilidades.
