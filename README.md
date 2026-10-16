# VagaCerta — MVP acadêmico (Fase 0)

Esqueleto do app de vagas de estacionamento em tempo real para Curitiba, seguindo o
[planejamento técnico](../Planejamento_Tecnico_VagaCerta.md).

> **Tudo é mockado.** Estacionamentos, preços e ocupação são fictícios (nomes com "Demo").
> Os nomes de rua são reais, com coordenadas aproximadas. Nenhum pagamento é cobrado.
> Nada é publicado nas lojas: o app roda no **Expo Go**.

## Estrutura

```
vagacerta/
├── apps/mobile     # App do motorista — Expo SDK 58 + Expo Router + react-native-maps
├── apps/web        # Painel do parceiro — Next.js 16
├── services/api    # API — Python 3.12 + FastAPI (monólito modular, dados em memória)
├── services/ml     # Notas do modelo de ocupação (v0 = perfil por hora nos mocks)
└── infra/          # PRÓXIMA FASE: PostGIS, Redis e OSRM (não usados pelo MVP)
```

## Como rodar

Pré-requisitos: Node 20+, Python 3.12 e o app **Expo Go** no celular.
O celular e o computador precisam estar **na mesma rede Wi-Fi**.

**1. API** (terminal 1)

```bash
cd services/api
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Documentação interativa: http://localhost:8000/docs.
`--host 0.0.0.0` permite que o celular acesse a API; o macOS pode pedir para liberar no firewall.

**2. App do motorista** (terminal 2)

```bash
cd apps/mobile
npm install
npx expo start
```

Escaneie o QR code com o Expo Go (Android) ou com a câmera (iPhone).
O app encontra a API sozinho pelo IP do computador. Se não encontrar, crie
`apps/mobile/.env` com `EXPO_PUBLIC_API_URL=http://SEU_IP:8000`.

**3. Painel do parceiro** (terminal 3)

```bash
cd apps/web
npm install
npm run dev
```

Abra http://localhost:3000. Mude as vagas livres de um estacionamento e veja o app
do motorista mostrar "N vagas · atendente · há menos de 1 min" na próxima atualização (até 30 s).

### Dica para demonstrações

As regras do EstaR dependem do horário: depois das 19h e aos domingos a rua é grátis e
alguns estacionamentos fecham. Para apresentar em "horário comercial" a qualquer hora:

```bash
VAGACERTA_AGORA=2026-10-20T10:30 .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

O relógio da API começa nesse horário e avança normalmente.

## O que o MVP já faz

| Funcionalidade | Onde |
|---|---|
| Busca de destino (lista mockada; Google Places depois) | `api/app/provedores/destinos.py` |
| Mapa com trechos de rua e estacionamentos coloridos pela chance de vaga | `mobile/src/app/index.tsx` |
| Recomendação por contexto (urgência, trabalho, lazer), duração e credencial (idoso/PCD) | `api/app/servicos/recomendacao.py` |
| Regras do EstaR: tempo máximo (2 h; 1 h na área calma), horário de cobrança, frações de 15 min | `api/app/servicos/regras.py` |
| Fusão de sinais com fonte e idade ("Livre agora · reporte de usuário · há 1 min") | `api/app/servicos/disponibilidade.py` |
| Reserva de 10 min **só em parceiros**, com cota por estacionamento | `api/app/servicos/reservas.py` |
| Navegação pelo Waze ou Google Maps (deep link, sem custo de API) | `mobile/src/lib/externos.ts` |
| Sessão com pagamento simulado, aviso local 10 min antes do fim, estender e encerrar | `mobile/src/app/sessao.tsx` |
| Encerrar sessão de rua avisa outros motoristas ("vaga liberada") | `api/app/servicos/sessoes.py` |
| Crowdsourcing "livre/ocupada" com antifraude simples (distância e intervalo) | `api/app/servicos/reportes.py` |
| "Encontrou a vaga?" → taxa de acerto | `GET /metricas` |
| Painel do parceiro informando vagas livres ("Mágico de Oz") | `web/src/componentes/PainelParceiro.tsx` |

## Verificações

```bash
cd services/api && .venv/bin/python -m pytest      # 26 testes
cd apps/mobile && npx tsc --noEmit && npx expo lint
cd apps/web && npx tsc --noEmit && npm run lint && npm run build
```

## Próximos passos (fora do MVP mockado)

1. **Mapa do Google no app:** criar chaves restritas e configurar o plugin `react-native-maps`
   no `app.json`; exige *development build* (`npx expo run:android`). No Expo Go o mapa funciona sem chave.
2. **Busca real:** `DestinosGooglePlaces` (Places API New com session token, chamado pela API).
3. **Banco:** `CatalogoPostgres` sobre `infra/db/schema.sql`.
4. **Rotas reais:** `RotasOSRM` (ver `infra/README.md`).
5. **Login:** Supabase Auth; a API passa a validar o JWT em vez do cabeçalho `X-Usuario-Id`.
6. **Tipos compartilhados:** gerar `apps/*/src/lib/tipos.ts` do OpenAPI (`openapi-typescript`).
