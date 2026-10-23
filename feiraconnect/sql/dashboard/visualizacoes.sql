-- Visualizações dos produtos do vendedor no período.
SELECT COUNT(*) AS visualizacoes, COUNT(DISTINCT v.visitante) AS visitantes
FROM visualizacoes v
JOIN produtos p ON p.id = v.produto_id
WHERE p.vendedor_id = :vendedor
  AND v.criado_em >= :inicio AND v.criado_em < :fim;
