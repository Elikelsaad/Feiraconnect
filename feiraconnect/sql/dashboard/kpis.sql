-- Indicadores do período para UM vendedor.
-- Parâmetros: :vendedor (id), :inicio e :fim ('AAAA-MM-DD HH:MM:SS', fim exclusivo)
-- Faturamento = pagamentos aprovados no período (data da confirmação).
SELECT
    COALESCE(SUM(CASE WHEN pg.status = 'aprovado' THEN pg.valor END), 0)                AS faturamento,
    COUNT(DISTINCT CASE WHEN pg.status = 'aprovado' THEN pg.pedido_id END)              AS pedidos_pagos,
    COALESCE(SUM(CASE WHEN pg.status = 'estornado' THEN pg.valor END), 0)               AS estornado,
    COUNT(DISTINCT CASE WHEN pg.status = 'estornado' THEN pg.pedido_id END)             AS pedidos_cancelados,
    COALESCE(AVG(CASE WHEN pg.status = 'aprovado' THEN pg.valor END), 0)                AS ticket_medio
FROM pagamentos pg
WHERE pg.vendedor_id = :vendedor
  AND pg.confirmado_em >= :inicio AND pg.confirmado_em < :fim;
