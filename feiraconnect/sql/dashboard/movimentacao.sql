-- Extrato financeiro: cada pagamento com data/hora, valor e forma de pagamento.
-- :desde_id permite buscar só as novidades (atualização em tempo real).
SELECT
    pg.id, pg.status, pg.modalidade, pg.bandeira, pg.cartao_final, pg.parcelas, pg.valor,
    pg.criado_em, pg.confirmado_em, pg.estornado_em,
    COALESCE(pg.estornado_em, pg.confirmado_em, pg.criado_em) AS momento,
    p.codigo, u.nome_completo AS cliente
FROM pagamentos pg
JOIN pedidos p  ON p.id = pg.pedido_id
JOIN usuarios u ON u.id = p.cliente_id
WHERE pg.vendedor_id = :vendedor
  AND COALESCE(pg.estornado_em, pg.confirmado_em, pg.criado_em) >= :inicio
  AND COALESCE(pg.estornado_em, pg.confirmado_em, pg.criado_em) <  :fim
ORDER BY momento DESC, pg.id DESC
LIMIT :limite;
