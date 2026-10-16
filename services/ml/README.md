# Modelo de ocupação

**Modelo v0 (atual, mockado):** um perfil de ocupação média por hora e tipo de dia
(seg–sex, sábado, domingo) para cada setor, em `services/api/app/dados_mock/setores.json`
(campo `perfil_ocupacao`). A API converte esse perfil em probabilidade de vaga livre em
`app/servicos/disponibilidade.py`. Os números são ilustrativos.

**Próximos passos** (seção 6 do planejamento):

1. Substituir o perfil inventado pelas médias das **contagens de campo** da equipe
   (~10 quadras do Centro e do Batel, em 3 horários).
2. Medir a **taxa de acerto** com o "Encontrou a vaga?" do app (`GET /metricas`).
3. Modelo v1: LightGBM com hora, dia, feriado, chuva e eventos (jogos, shows),
   calibrado para que "70%" signifique 70% de verdade.
