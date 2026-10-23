-- Quantidade de itens vendidos e entregas concluídas no período.
SELECT
    COALESCE(SUM(i.quantidade), 0)                                      AS itens,
    COUNT(DISTINCT CASE WHEN p.status = 'entregue' THEN p.id END)       AS entregues
FROM pedidos p
JOIN itens_pedido i ON i.pedido_id = p.id
WHERE p.vendedor_id = :vendedor
  AND p.status NOT IN ('cancelado', 'aguardando_pagamento')
  AND p.pago_em >= :inicio AND p.pago_em < :fim;
