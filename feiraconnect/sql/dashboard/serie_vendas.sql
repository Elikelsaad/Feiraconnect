-- Série temporal do faturamento, agrupada pelo formato de data recebido:
--   '%H' por hora (dia) · '%Y-%m-%d' por dia (mês) · '%Y-%W' por semana (trimestre) · '%Y-%m' por mês (ano)
SELECT
    strftime(:formato, pg.confirmado_em)  AS grupo,
    ROUND(SUM(pg.valor), 2)               AS valor,
    COUNT(DISTINCT pg.pedido_id)          AS pedidos
FROM pagamentos pg
WHERE pg.vendedor_id = :vendedor
  AND pg.status = 'aprovado'
  AND pg.confirmado_em >= :inicio AND pg.confirmado_em < :fim
GROUP BY grupo
ORDER BY grupo;
