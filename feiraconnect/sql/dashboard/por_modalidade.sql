-- Faturamento por forma de pagamento (PIX, crédito, débito) e bandeira.
SELECT
    pg.modalidade,
    CASE WHEN pg.bandeira = '' THEN '—' ELSE pg.bandeira END AS bandeira,
    COUNT(*)                 AS quantidade,
    ROUND(SUM(pg.valor), 2)  AS valor
FROM pagamentos pg
WHERE pg.vendedor_id = :vendedor
  AND pg.status = 'aprovado'
  AND pg.confirmado_em >= :inicio AND pg.confirmado_em < :fim
GROUP BY pg.modalidade, pg.bandeira
ORDER BY valor DESC;
