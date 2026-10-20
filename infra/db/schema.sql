-- Schema PostgreSQL + PostGIS do VagaCerta — PRÓXIMA FASE.
-- O MVP atual usa dados mockados em memória (services/api/app/dados_mock/).
-- Este arquivo espelha aquelas entidades para quando a API ganhar um `CatalogoPostgres`.
-- ATENÇÃO: ainda não foi executado contra um banco; valide com `docker compose up` (ver infra/README.md).

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE cidades (
    id   text PRIMARY KEY,
    nome text NOT NULL
);

-- Regras ficam como dados (jsonb), não como código: a Prefeitura muda preço, horário e tempo máximo.
CREATE TABLE setores_estar (
    id              text PRIMARY KEY,
    cidade_id       text NOT NULL REFERENCES cidades (id),
    nome            text NOT NULL,
    geom            geography (Polygon, 4326),
    regras          jsonb NOT NULL  -- tempo_max_min, preco_fracao_15min, horario_cobranca
);

CREATE TABLE trechos_vaga (
    id         text PRIMARY KEY,
    setor_id   text NOT NULL REFERENCES setores_estar (id),
    nome       text NOT NULL,
    tipo       text NOT NULL CHECK (tipo IN ('comum', 'idoso', 'pcd', 'carga_descarga')),
    capacidade integer NOT NULL CHECK (capacidade > 0),
    geom       geography (LineString, 4326) NOT NULL
);
CREATE INDEX trechos_vaga_geom_idx ON trechos_vaga USING gist (geom);

CREATE TABLE parceiros (
    id   text PRIMARY KEY,
    nome text NOT NULL
);

CREATE TABLE estacionamentos (
    id               text PRIMARY KEY,
    parceiro_id      text REFERENCES parceiros (id), -- NULL = não parceiro (sem dado ao vivo)
    nome             text NOT NULL,
    endereco         text,
    geom             geography (Point, 4326) NOT NULL,
    capacidade       integer NOT NULL CHECK (capacidade > 0),
    preco_hora       numeric(8, 2) NOT NULL,
    preco_diaria     numeric(8, 2) NOT NULL,
    aceita_reserva   boolean NOT NULL DEFAULT false,
    cota_reserva     integer NOT NULL DEFAULT 0 CHECK (cota_reserva >= 0),
    setor_referencia text REFERENCES setores_estar (id),
    horario          jsonb NOT NULL,
    atributos        jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX estacionamentos_geom_idx ON estacionamentos USING gist (geom);

-- Localização e placa são dados pessoais (LGPD): guardar o mínimo e com prazo de retenção.
CREATE TABLE usuarios (
    id        uuid PRIMARY KEY,
    criado_em timestamptz NOT NULL DEFAULT now(),
    reputacao real NOT NULL DEFAULT 1.0 -- peso dos reportes de crowdsourcing
);

CREATE TABLE veiculos (
    id         uuid PRIMARY KEY,
    usuario_id uuid NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    placa      text NOT NULL,
    UNIQUE (usuario_id, placa)
);

-- Série temporal de todos os sinais de ocupação, particionada por mês.
-- alvo_id aponta para trechos_vaga.id ou estacionamentos.id.
CREATE TABLE sinais_ocupacao (
    id           bigint GENERATED ALWAYS AS IDENTITY,
    alvo_id      text NOT NULL,
    fonte        text NOT NULL CHECK (fonte IN ('cancela', 'atendente', 'usuario', 'saida')),
    criado_em    timestamptz NOT NULL,
    vagas_livres integer CHECK (vagas_livres >= 0),
    livre        boolean,
    usuario_id   uuid REFERENCES usuarios (id) ON DELETE SET NULL,
    PRIMARY KEY (id, criado_em)
) PARTITION BY RANGE (criado_em);
CREATE TABLE sinais_ocupacao_2026_10 PARTITION OF sinais_ocupacao
    FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
CREATE TABLE sinais_ocupacao_2026_11 PARTITION OF sinais_ocupacao
    FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
CREATE TABLE sinais_ocupacao_2026_12 PARTITION OF sinais_ocupacao
    FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');
CREATE INDEX sinais_ocupacao_alvo_idx ON sinais_ocupacao (alvo_id, criado_em DESC);

-- Estado consolidado (no Piloto, espelhado no Redis).
CREATE TABLE ocupacao_atual (
    alvo_id          text PRIMARY KEY,
    vagas_livres     integer NOT NULL,
    prob_livre       real NOT NULL CHECK (prob_livre BETWEEN 0 AND 1),
    confianca        real NOT NULL CHECK (confianca BETWEEN 0 AND 1),
    fonte            text NOT NULL,
    atualizado_em    timestamptz NOT NULL
);

CREATE TABLE reservas (
    id                text PRIMARY KEY,
    estacionamento_id text NOT NULL REFERENCES estacionamentos (id),
    usuario_id        uuid NOT NULL REFERENCES usuarios (id),
    codigo            text NOT NULL UNIQUE,
    criada_em         timestamptz NOT NULL DEFAULT now(),
    expira_em         timestamptz NOT NULL,
    status            text NOT NULL CHECK (status IN ('ativa', 'expirada', 'cancelada', 'utilizada'))
);
-- No máximo uma reserva ativa por usuário.
CREATE UNIQUE INDEX reservas_uma_ativa_por_usuario ON reservas (usuario_id) WHERE status = 'ativa';

CREATE TABLE sessoes_estacionamento (
    id           text PRIMARY KEY,
    tipo         text NOT NULL CHECK (tipo IN ('rua', 'estacionamento')),
    alvo_id      text NOT NULL,
    usuario_id   uuid NOT NULL REFERENCES usuarios (id),
    placa        text NOT NULL,
    inicio       timestamptz NOT NULL,
    fim_previsto timestamptz NOT NULL,
    valor_pago   numeric(8, 2) NOT NULL,
    status       text NOT NULL CHECK (status IN ('ativa', 'encerrada'))
);

CREATE TABLE pagamentos (
    id            text PRIMARY KEY,
    sessao_id     text NOT NULL REFERENCES sessoes_estacionamento (id),
    valor         numeric(8, 2) NOT NULL,
    metodo        text NOT NULL CHECK (metodo IN ('pix', 'cartao', 'simulado')),
    referencia_psp text, -- id no gateway de pagamento
    criado_em     timestamptz NOT NULL DEFAULT now()
);

-- "Encontrou a vaga?" — base da taxa de acerto.
CREATE TABLE feedbacks_chegada (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    alvo_id       text NOT NULL,
    usuario_id    uuid REFERENCES usuarios (id) ON DELETE SET NULL,
    encontrou     boolean NOT NULL,
    registrado_em timestamptz NOT NULL DEFAULT now()
);

-- Consulta central (seção 5 do planejamento): candidatos a até 600 m do destino.
-- SELECT e.id, e.nome, o.vagas_livres, o.prob_livre, o.atualizado_em,
--        ST_Distance(e.geom, d.geom) AS distancia_m
-- FROM estacionamentos e
-- JOIN ocupacao_atual o ON o.alvo_id = e.id
-- CROSS JOIN (SELECT ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography AS geom) d
-- WHERE ST_DWithin(e.geom, d.geom, 600)
-- ORDER BY distancia_m
-- LIMIT 20;
