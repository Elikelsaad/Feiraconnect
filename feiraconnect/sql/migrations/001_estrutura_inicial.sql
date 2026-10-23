-- =====================================================================
-- FeiraConnect — Migração 001: estrutura inicial do banco de dados
-- Cada migração roda UMA vez e fica registrada em schema_migrations.
-- Para evoluir o sistema, crie 002_descricao.sql, 003_..., nunca edite
-- uma migração que já foi aplicada em produção.
-- =====================================================================

-- ---------------------------------------------------------------- contas
-- Login e dados comuns aos três perfis: vendedor, cliente, entregador
CREATE TABLE usuarios (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    papel           TEXT NOT NULL CHECK (papel IN ('vendedor','cliente','entregador')),
    login           TEXT NOT NULL UNIQUE COLLATE NOCASE,   -- 3 a 10 caracteres
    senha_hash      TEXT NOT NULL,
    nome_completo   TEXT NOT NULL,
    documento_tipo  TEXT NOT NULL CHECK (documento_tipo IN ('CPF','CNPJ')),
    documento       TEXT NOT NULL,                          -- só dígitos
    nascimento      TEXT NOT NULL,                          -- AAAA-MM-DD
    celular         TEXT NOT NULL DEFAULT '',
    foto            TEXT NOT NULL DEFAULT '',
    ativo           INTEGER NOT NULL DEFAULT 1,
    ultimo_acesso   TEXT,
    criado_em       TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE (papel, documento)
);

-- Endereço (usado por vendedor e cliente)
CREATE TABLE enderecos (
    usuario_id   INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
    cep          TEXT NOT NULL,
    logradouro   TEXT NOT NULL DEFAULT '',
    numero       TEXT NOT NULL,
    complemento  TEXT NOT NULL DEFAULT '',
    bairro       TEXT NOT NULL,
    cidade       TEXT NOT NULL,
    uf           TEXT NOT NULL DEFAULT 'AM',
    referencia   TEXT NOT NULL DEFAULT '',
    lat          REAL,
    lng          REAL
);

CREATE TABLE vendedores (
    usuario_id       INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
    ponto_comercial  TEXT NOT NULL,            -- nome da banca / loja
    feira            TEXT NOT NULL DEFAULT '', -- feira onde trabalha
    descricao        TEXT NOT NULL DEFAULT '',
    banca_lat        REAL,
    banca_lng        REAL
);

-- Conta bancária do vendedor para receber os pagamentos
CREATE TABLE contas_bancarias (
    vendedor_id         INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
    banco_codigo        TEXT NOT NULL,
    banco_nome          TEXT NOT NULL,
    agencia             TEXT NOT NULL,
    conta               TEXT NOT NULL,
    conta_digito        TEXT NOT NULL DEFAULT '',
    conta_tipo          TEXT NOT NULL CHECK (conta_tipo IN ('corrente','poupanca','pagamento')),
    titular             TEXT NOT NULL,
    titular_documento   TEXT NOT NULL,
    pix_tipo            TEXT NOT NULL DEFAULT '',
    pix_chave           TEXT NOT NULL DEFAULT '',
    aceita_credito      INTEGER NOT NULL DEFAULT 1,
    aceita_debito       INTEGER NOT NULL DEFAULT 1,
    aceita_pix          INTEGER NOT NULL DEFAULT 1,
    bandeira_visa       INTEGER NOT NULL DEFAULT 1,
    bandeira_mastercard INTEGER NOT NULL DEFAULT 1,
    bandeira_elo        INTEGER NOT NULL DEFAULT 1,
    atualizado_em       TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE entregadores (
    usuario_id   INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
    veiculo      TEXT NOT NULL DEFAULT 'moto' CHECK (veiculo IN ('moto','carro','bicicleta')),
    placa        TEXT NOT NULL DEFAULT '',
    disponivel   INTEGER NOT NULL DEFAULT 1
);

-- Cartões do cliente: NUNCA guardamos número completo nem CVV
CREATE TABLE cartoes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id   INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    tipo         TEXT NOT NULL CHECK (tipo IN ('credito','debito')),
    bandeira     TEXT NOT NULL CHECK (bandeira IN ('Visa','Mastercard','Elo')),
    final        TEXT NOT NULL,
    titular      TEXT NOT NULL,
    validade     TEXT NOT NULL,   -- MM/AA
    token        TEXT NOT NULL,   -- referência do cartão no gateway (aqui: simulado)
    criado_em    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- ---------------------------------------------------------------- catálogo
CREATE TABLE categorias (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    nome   TEXT NOT NULL,
    slug   TEXT NOT NULL UNIQUE,
    icone  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE produtos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vendedor_id     INTEGER NOT NULL REFERENCES usuarios(id),
    categoria_id    INTEGER REFERENCES categorias(id),
    nome            TEXT NOT NULL,
    descricao       TEXT NOT NULL DEFAULT '',
    preco           REAL NOT NULL CHECK (preco >= 0),
    preco_original  REAL,
    unidade         TEXT NOT NULL DEFAULT 'un',
    estoque         INTEGER NOT NULL DEFAULT 0 CHECK (estoque >= 0),
    origem          TEXT NOT NULL DEFAULT '',
    promocao_dia    INTEGER NOT NULL DEFAULT 0,
    fim_de_feira    INTEGER NOT NULL DEFAULT 0,
    ativo           INTEGER NOT NULL DEFAULT 1,
    visualizacoes   INTEGER NOT NULL DEFAULT 0,
    vendidos        INTEGER NOT NULL DEFAULT 0,
    criado_em       TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    atualizado_em   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX ix_produtos_vendedor ON produtos(vendedor_id);

-- Até 10 imagens (HD ou 4K) por produto, cada uma com sua legenda
CREATE TABLE produto_imagens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id  INTEGER NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    arquivo     TEXT NOT NULL,     -- versão completa (até 3840 px)
    miniatura   TEXT NOT NULL,     -- versão leve para listas (800 px)
    largura     INTEGER NOT NULL DEFAULT 0,
    altura      INTEGER NOT NULL DEFAULT 0,
    legenda     TEXT NOT NULL DEFAULT '',
    ordem       INTEGER NOT NULL DEFAULT 0,
    criado_em   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX ix_imagens_produto ON produto_imagens(produto_id, ordem);

-- Uma visualização por visitante por dia
CREATE TABLE visualizacoes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id  INTEGER NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    visitante   TEXT NOT NULL,
    dia         TEXT NOT NULL,
    criado_em   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE (produto_id, visitante, dia)
);

-- Avaliação do cliente: 1 Péssimo · 2 Ruim · 3 Regular · 4 Bom · 5 Excelente
CREATE TABLE avaliacoes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id  INTEGER NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    cliente_id  INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    nota        INTEGER NOT NULL CHECK (nota BETWEEN 1 AND 5),
    comentario  TEXT NOT NULL DEFAULT '',
    criado_em   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    atualizado_em TEXT,
    UNIQUE (produto_id, cliente_id)
);

-- ---------------------------------------------------------------- vendas
-- Uma compra do cliente gera um pedido por vendedor
CREATE TABLE pedidos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo          TEXT NOT NULL UNIQUE,
    compra_codigo   TEXT NOT NULL,
    cliente_id      INTEGER NOT NULL REFERENCES usuarios(id),
    vendedor_id     INTEGER NOT NULL REFERENCES usuarios(id),
    entregador_id   INTEGER REFERENCES usuarios(id),
    endereco        TEXT NOT NULL,
    referencia      TEXT NOT NULL DEFAULT '',
    destino_lat     REAL,
    destino_lng     REAL,
    origem_lat      REAL,
    origem_lng      REAL,
    entrega_modo    TEXT NOT NULL CHECK (entrega_modo IN ('moto','carro','bicicleta','retirada')),
    entrega_valor   REAL NOT NULL DEFAULT 0,
    distancia_km    REAL NOT NULL DEFAULT 0,
    subtotal        REAL NOT NULL,
    total           REAL NOT NULL,
    status          TEXT NOT NULL DEFAULT 'aguardando_pagamento'
                    CHECK (status IN ('aguardando_pagamento','pago','em_preparo','aguardando_entregador',
                                      'saiu_entrega','entregue','cancelado')),
    criado_em       TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    pago_em         TEXT,
    saiu_em         TEXT,
    entregue_em     TEXT,
    cancelado_em    TEXT,
    cancelado_por   TEXT,
    motivo_cancelamento TEXT NOT NULL DEFAULT ''
);
CREATE INDEX ix_pedidos_vendedor ON pedidos(vendedor_id, criado_em);
CREATE INDEX ix_pedidos_cliente  ON pedidos(cliente_id, criado_em);

CREATE TABLE itens_pedido (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id   INTEGER NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
    produto_id  INTEGER REFERENCES produtos(id),
    nome        TEXT NOT NULL,
    preco       REAL NOT NULL,
    quantidade  INTEGER NOT NULL CHECK (quantidade > 0)
);

-- Movimentação financeira: cada pagamento e cada estorno
CREATE TABLE pagamentos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id      INTEGER NOT NULL REFERENCES pedidos(id),
    vendedor_id    INTEGER NOT NULL REFERENCES usuarios(id),
    modalidade     TEXT NOT NULL CHECK (modalidade IN ('credito','debito','pix')),
    bandeira       TEXT NOT NULL DEFAULT '',
    cartao_final   TEXT NOT NULL DEFAULT '',
    parcelas       INTEGER NOT NULL DEFAULT 1,
    valor          REAL NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente','aprovado','recusado','estornado')),
    pix_txid       TEXT NOT NULL DEFAULT '',
    pix_payload    TEXT NOT NULL DEFAULT '',
    criado_em      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    confirmado_em  TEXT,
    estornado_em   TEXT
);
CREATE INDEX ix_pagamentos_vendedor ON pagamentos(vendedor_id, confirmado_em);

-- Avisos no site (ex.: "Pagamento recebido")
CREATE TABLE notificacoes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id  INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    tipo        TEXT NOT NULL,
    titulo      TEXT NOT NULL,
    mensagem    TEXT NOT NULL DEFAULT '',
    link        TEXT NOT NULL DEFAULT '',
    lida        INTEGER NOT NULL DEFAULT 0,
    criado_em   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX ix_notificacoes_usuario ON notificacoes(usuario_id, lida, id);

-- Posições GPS enviadas pelo entregador durante a entrega
CREATE TABLE rastreamento (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id   INTEGER NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
    lat         REAL NOT NULL,
    lng         REAL NOT NULL,
    precisao    REAL,
    velocidade  REAL,
    criado_em   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX ix_rastreamento_pedido ON rastreamento(pedido_id, id);

-- ---------------------------------------------------------------- sistema
CREATE TABLE configuracoes (
    chave  TEXT PRIMARY KEY,
    valor  TEXT
);

-- Tentativas de login (proteção contra força bruta)
CREATE TABLE tentativas_login (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    login      TEXT NOT NULL,
    ip         TEXT NOT NULL,
    sucesso    INTEGER NOT NULL,
    criado_em  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
