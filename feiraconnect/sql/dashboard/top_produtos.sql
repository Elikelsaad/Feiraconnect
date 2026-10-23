-- Produtos que mais faturaram no período, com visualizações e nota média.
SELECT
    i.produto_id,
    i.nome,
    SUM(i.quantidade)                      AS quantidade,
    ROUND(SUM(i.quantidade * i.preco), 2)  AS valor,
    (SELECT COUNT(*) FROM visualizacoes v
      WHERE v.produto_id = i.produto_id AND v.criado_em >= :inicio AND v.criado_em < :fim) AS visualizacoes,
    (SELECT ROUND(AVG(a.nota), 1) FROM avaliacoes a WHERE a.produto_id = i.produto_id) AS nota
FROM itens_pedido i
JOIN pedidos p ON p.id = i.pedido_id
WHERE p.vendedor_id = :vendedor
  AND p.status NOT IN ('cancelado', 'aguardando_pagamento')
  AND p.pago_em >= :inicio AND p.pago_em < :fim
GROUP BY i.produto_id, i.nome
ORDER BY valor DESC
LIMIT 8;
