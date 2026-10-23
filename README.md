# FeiraConnect 2.0 — Plataforma de feiras livres (Python + Flask + SQL)

Marketplace de feira livre com **três tipos de conta**, cada um com o seu painel:

| Conta | O que faz |
|---|---|
| **Vendedor** | É o administrador do próprio acesso: cadastra produtos com **até 10 fotos HD/4K** e comentários em cada foto, informa a **conta bancária** e as formas de recebimento (PIX, crédito e débito Visa/Mastercard/Elo), recebe **aviso no site no momento do pagamento**, acompanha **visualizações, comentários, pedidos, entregas pelo GPS** e o **financeiro em tempo real**, e tem um **dashboard de vendas** do dia, do mês, do trimestre e do ano. |
| **Cliente** | Compra, paga com PIX (QR Code com o valor) ou cartão salvo, **acompanha a entrega no mapa**, **cancela em até 20 minutos** após a confirmação, comenta e dá de **1 a 5 estrelas** (Péssimo, Ruim, Regular, Bom, Excelente). Não altera nada nos produtos. |
| **Entregador** | Aceita entregas, compartilha a **posição GPS** durante o trajeto e confirma a entrega. |

## Como rodar

Requisito: **Python 3.10 ou mais novo** (no Windows, marque “Add Python to PATH” ao instalar).

```bash
cd feiraconnect
python -m venv venv
# Windows: venv\Scripts\activate      Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
python seed.py          # cria o banco com dados de exemplo (só na primeira vez)
python run.py           # abre em http://127.0.0.1:5000
```

No Windows também dá para dar dois cliques em **`rodar_windows.bat`**.

### Contas de teste (senha de todas: `feira123`)

| Tipo | Logins |
|---|---|
| Vendedor | `raimunda`, `chico`, `joana`, `antonio`, `graca`, `elias` |
| Cliente | `elikel`, `ana`, `denilson`, `thiago`, `luana` |
| Entregador | `carlos` (moto), `bruno` (bicicleta), `sandra` (carro) |

Experimente: entre como **raimunda** em uma janela e como **ana** em uma janela anônima. Compre um produto da Banca da Dona Raimunda com cartão e veja o aviso **“💰 Pagamento recebido”** aparecer na tela da vendedora em poucos segundos. O pedido `FCDEMOGPS` (cliente `elikel`) já está a caminho, para ver o rastreio.

`python seed.py --reset` apaga tudo e recria os exemplos.

## Regras implementadas

- **Login** de 3 a 10 caracteres e **senha** de 6 a 10 (letras e números), guardada com hash. Cinco senhas erradas bloqueiam o login por 15 minutos.
- **CPF/CNPJ** conferidos pelos dígitos verificadores; idade mínima de 18 anos; foto obrigatória no cadastro; CEP preenche a rua automaticamente (ViaCEP); botão de GPS marca a posição.
- **Fotos do produto:** até 10 por produto, mínimo HD (1280×720), até 4K (maior lado de 3840 px). O sistema corrige a rotação das fotos do celular, remove os metadados (inclusive a localização) e gera uma miniatura leve para as listas. A foto, a legenda, a ordem e a capa podem ser trocadas quantas vezes o vendedor quiser.
- **Visualizações:** 1 por visitante por dia (o próprio vendedor não conta).
- **Pagamentos:** cada vendedor recebe na própria conta. Uma compra com produtos de vários feirantes vira um pedido por feirante, cada um com o seu PIX ou cobrança no cartão.
- **Aviso de pagamento:** registrado na hora da confirmação. O sino e os alertas na tela consultam o servidor a cada 8 segundos.
- **Cancelamento:** o cliente pode cancelar em até 20 minutos após a confirmação (valor ajustável em `configuracoes`). O estoque volta e o pagamento é marcado como estornado.
- **Rastreio:** o entregador envia a posição a cada 5 segundos enquanto a página da entrega estiver aberta. Cliente e vendedor veem o trajeto no mapa. Ninguém fora do pedido acessa essas posições.
- **Segurança:** proteção CSRF em todos os formulários, sessão renovada ao entrar, cada vendedor só vê os próprios dados, CPF mascarado nas telas e cartão salvo apenas com bandeira e 4 últimos dígitos (nunca o número inteiro nem o CVV).

## Estrutura do código

```
feiraconnect/                 (pasta do projeto)
├── run.py                    inicia o site
├── config.py                 configurações (chave secreta, banco, modo de teste, token do PIX)
├── seed.py                   dados de exemplo
├── requirements.txt
├── tests/test_fluxo.py       testes automáticos do fluxo completo (python -m pytest -q)
├── dados_exemplo/fotos/      fotos HD usadas pelo seed
└── feiraconnect/             (o sistema)
    ├── __init__.py           cria o app, segurança, menus
    ├── db.py                 conexão, migrações e consultas
    ├── validacao.py          CPF, CNPJ, CEP, celular, login, senha
    ├── imagens.py            fotos HD/4K, miniaturas, fotos de perfil
    ├── servicos.py           regras: pagamento, aviso, cancelamento, etapas da entrega
    ├── relatorios.py         períodos do dashboard (dia, mês, trimestre, ano)
    ├── pix.py                PIX Copia e Cola e QR Code (padrão do Banco Central)
    ├── utils.py              dinheiro, distância GPS, frete, cartões
    ├── blueprints/
    │   ├── auth.py           entrar, sair e os 3 cadastros
    │   ├── loja.py           vitrine, produto, avaliações, carrinho, checkout
    │   ├── vendedor.py       painel do vendedor
    │   ├── cliente.py        área do cliente
    │   ├── entregador.py     área do entregador
    │   └── api.py            tempo real (avisos, rastreio, financeiro) e webhook do PIX
    ├── sql/
    │   ├── migrations/       estrutura do banco, versionada (001_estrutura_inicial.sql)
    │   └── dashboard/        consultas SQL do dashboard (kpis, série, formas de pagamento…)
    ├── templates/            páginas HTML
    └── static/               CSS, JavaScript, imagens, fotos enviadas (uploads/)
```

## Como atualizar o sistema no futuro

O projeto foi organizado para receber melhorias sem quebrar o que já funciona:

1. **Mudar o banco de dados:** crie um arquivo novo em `feiraconnect/sql/migrations/`, por exemplo `002_cupom_desconto.sql`, com os comandos `ALTER TABLE` / `CREATE TABLE`. Ele roda sozinho, uma única vez, na próxima vez que o site iniciar. Nunca edite uma migração que já foi aplicada.
2. **Novo relatório no dashboard:** escreva a consulta em `sql/dashboard/nome.sql` (parâmetros `:vendedor`, `:inicio`, `:fim`) e chame `db.consulta_sql("nome")` em `relatorios.py`.
3. **Nova área ou função:** crie um arquivo em `blueprints/` e registre-o em `feiraconnect/__init__.py`.
4. **Regra de negócio** (prazo de cancelamento, frete, etapas do pedido): ficam em `servicos.py` e `utils.py`.
5. **Cores e visual:** variáveis no topo de `static/css/style.css`.
6. Rode `python -m pytest -q` depois de cada mudança para conferir que o fluxo principal continua funcionando.

A versão atual aparece no rodapé do site (`__version__` em `feiraconnect/__init__.py`).

### Dashboard e SQL

Os números do dashboard do vendedor saem das consultas em `feiraconnect/sql/dashboard/`. Elas também podem ser usadas em ferramentas como Power BI, Metabase ou DBeaver, que se conectam ao arquivo `feiraconnect.db` (SQLite). Para trocar o SQLite por PostgreSQL ou MySQL no futuro, basta ajustar `db.py`. As consultas usam SQL padrão, exceto a função de data `strftime`.

## Antes de vender de verdade

- **Cartão:** o `MODO_TESTE` (ligado por padrão em `config.py`) aprova os cartões sem cobrar. Para cobrar de verdade, integre um gateway (Mercado Pago, PagBank, Cielo, Stone, Asaas…) no ponto marcado em `blueprints/loja.py` (função `checkout`) e defina `MODO_TESTE=0`.
- **PIX:** o QR Code já é um PIX válido com o valor do pedido e cai direto na chave do vendedor. A confirmação pode ser feita pelo vendedor (“Confirmar que o PIX caiu na conta”) ou automaticamente pelo seu banco/PSP, chamando `POST /api/webhook/pix` com o cabeçalho `X-Webhook-Token` (defina a variável `PIX_WEBHOOK_TOKEN`).
- **GPS e câmera** só funcionam em `localhost` ou em site com **HTTPS**.
- **Publicação:** use um servidor WSGI (`pip install waitress` e depois `waitress-serve --port=8000 run:app`), defina `SECRET_KEY` e `HTTPS=1`, e faça backup do `feiraconnect.db` e da pasta `static/uploads/`.
- **LGPD:** o sistema guarda CPF, endereço e dados bancários. Publique uma política de privacidade e restrinja o acesso ao servidor e aos backups.

## Créditos

Ilustrações dos produtos e ícones: Twemoji (CC-BY 4.0). Mapas: Leaflet (BSD-2) e © colaboradores do OpenStreetMap. Gráficos: Chart.js (MIT). Fontes: Inter e Lexend (SIL OFL). Busca de CEP: ViaCEP.

Projeto TCC FAMETRO — FeiraConnect.
