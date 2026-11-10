# 08 — Infraestrutura, segurança e qualidade

Requisitos que não são funcionalidades visíveis, mas são necessários para o lançamento em janeiro.

---

## Banco de dados e código

### INF-01 — Migrações com Alembic [MVP]
- Adotar Alembic para todas as mudanças de banco (corrige FAL-14).
- Primeira migração reflete o banco atual; as seguintes aplicam as mudanças dos arquivos 02 a 07.
- Migrar dados existentes quando necessário (ex.: `theme_id` do ponto para a tabela de temas, `description` para blocos de texto, tipo `manual` para `point_visit`).

### INF-02 — Dependências [MVP]
- Criar `requirements.txt` com versões fixas (FastAPI, SQLAlchemy, psycopg, Alembic, PyJWT, pwdlib, resend, requests, polyline, python-multipart, jinja2, email-validator, google-auth, boto3).
- README com: como instalar, configurar o `.env`, rodar migrações, criar administrador e iniciar o servidor.

### INF-03 — Configuração [MVP]
- Todas as configurações em `app/core/config.py`, lidas do `.env` (corrige FAL-18).
- Novas variáveis: distância de proximidade, origens CORS permitidas, Client IDs do Google, nome do bucket e região do S3, credenciais AWS (quando não vierem de role), chave do OpenRouteService.
- `.env.example` versionado com todas as variáveis e sem valores reais.
- Renomear `.gitgnore` → `.gitignore` (FAL-10).

## Arquivos (fotos e áudios)

### INF-04 — Armazenamento de arquivos: Amazon S3 [MVP — decidido]
- Volume estimado no lançamento: 40 fotos (até 5 MB cada), capas de rotas, imagens de insígnias e alguns áudios (a maioria dos pontos não terá; cada um até ~20 MB).
- **Decisão:** arquivos no **Amazon S3**, na mesma região da API; no banco fica só a chave (caminho) do arquivo.
- Bucket **privado** (sem acesso público). O app recebe **links temporários assinados** (presigned URLs):
  - foto do ponto, capa de rota e imagem de insígnia: link com validade longa (ex.: 24 h), devolvido no mapa/listas;
  - áudio: link com validade de ~1 h, devolvido **apenas** na abertura do ponto com proximidade (PT-14, opção a).
- O S3 já atende requisições parciais (`Range`), então o áudio toca em streaming e permite avançar/voltar.
- Organização das chaves: `points/{id}/photo-{uuid}.jpg`, `points/{id}/audio-{uuid}.mp3`, `routes/{id}/cover-{uuid}.jpg`, `badges/{id}/image-{uuid}.png` (o uuid evita cache de arquivo antigo após substituição).
- Upload feito pelo backend a partir do painel (o volume é pequeno; não é necessário upload direto do navegador para o S3).
- O código acessa os arquivos por uma camada única (`storage_service`: salvar, gerar link, apagar), usando `boto3`.
- Excluir/substituir um arquivo no painel apaga o arquivo antigo no S3.
- Credenciais: usuário IAM (ou role da instância) com permissão **apenas** neste bucket (`s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`).
- Ativar versionamento do bucket (proteção contra exclusão acidental) com regra de ciclo de vida apagando versões antigas após 30 dias.
- **Migração:** script que move as imagens atualmente guardadas no banco (colunas `data`/`image`) para o S3 e depois remove essas colunas.

## Hospedagem

### INF-05 — Hospedagem: AWS [MVP — decidido]
- **Provedor:** AWS. Região sugerida: **São Paulo (`sa-east-1`)**, pela menor latência para os usuários (custo um pouco maior que `us-east-1`, irrelevante nesta escala).
- **API:** instância **Amazon Lightsail** (Linux, plano pequeno) rodando a aplicação em contêiner Docker, com Uvicorn/Gunicorn atrás de um proxy reverso (Nginx ou Caddy) com HTTPS (Let's Encrypt). IP estático do Lightsail.
- **Banco:** PostgreSQL gerenciado — **Lightsail Managed Database** (mais simples) ou **RDS** (plano mínimo). Sem acesso público; apenas a API se conecta.
- **Arquivos:** S3 (INF-04).
- **E-mail:** continua no Resend.
- **Domínio:** subdomínio para a API (ex.: `api.<dominio>`) e para o painel (pode ser o mesmo, em `/admin`). DNS no Route 53 ou no provedor atual do domínio.
- **Publicação:** imagem Docker construída a partir do repositório; publicação por script simples (ou GitHub Actions **[DESEJÁVEL]**) que roda as migrações do Alembic antes de reiniciar a API.
- **Custos:** criar **alertas de orçamento** (AWS Budgets) no primeiro dia — ex.: aviso em US$ 30/mês e US$ 50/mês. Estimativa inicial aproximada: US$ 25 a 45/mês (API + banco + S3), conferir na calculadora de preços da AWS.
- **Segurança da conta:** MFA no usuário raiz, não usar o usuário raiz no dia a dia, usuário IAM próprio para a desenvolvedora e credenciais separadas e mínimas para a aplicação.
- Ambientes: **desenvolvimento** (local, com PostgreSQL em Docker e um bucket S3 de desenvolvimento) e **produção**. **[DESEJÁVEL]** ambiente de testes separado para o beta.

### INF-06 — Backups [MVP]
- Backup diário automático do banco (recurso nativo do banco gerenciado), guardado por pelo menos 7 dias.
- Testar a restauração uma vez antes do lançamento.
- Arquivos: versionamento do bucket S3 (INF-04).
- Snapshot da instância Lightsail **[DESEJÁVEL]** (a instância não guarda dados; tudo deve poder ser recriado a partir do repositório e do `.env`).

### INF-07 — Domínio de e-mail [MVP]
- Confirmar que o domínio remetente está verificado no Resend (SPF/DKIM), para os códigos não caírem no spam.

## Segurança

### INF-08 — Limites de requisição [MVP]
- Limitar por IP e por e-mail: cadastro, reenvio, recuperação de senha, login (FAL-07, FAL-08) e login do painel.
- Limite geral razoável por usuário nas rotas do app.
- Respostas 429 com mensagem clara.

### INF-09 — Boas práticas [MVP]
- CORS restrito (FAL-09).
- Rotas de documentação automática (`/docs`, `/redoc`) desligadas ou protegidas em produção.
- `SECRET_KEY` forte e diferente entre ambientes.
- Logs sem senhas, códigos ou tokens.
- Mensagens de erro em português e consistentes.

## Qualidade

### INF-10 — Testes automatizados [MVP]
- Testes com `pytest` e banco PostgreSQL de teste cobrindo pelo menos:
  - cadastro, verificação, login, Google (com token simulado), recuperação e exclusão de conta;
  - abertura de ponto perto e longe, ponto só de rota com e sem rota ativa;
  - concessão de cada tipo de insígnia, sem duplicar, e avaliação retroativa;
  - rota: iniciar, impedir segunda rota, finalizar fora de ordem (erro), encerrar incompleta (erro), encerrar completa (insígnia), abandonar;
  - exclusões bloqueadas quando há histórico;
  - acesso ao painel sem login (bloqueado).
- Rodar os testes antes de cada publicação.

### INF-11 — Registro de erros [DESEJÁVEL]
- Monitoramento de erros em produção (ex.: Sentry, plano gratuito) para acompanhar problemas no beta.

## Beta e lançamento

### INF-12 — Beta com 10 usuários [MVP]
- Ambiente publicado com o conteúdo real dos 40 pontos (ou parte deles).
- Distribuição do app: TestFlight (iOS) e teste interno da Google Play (Android).
- Coletar no beta: problemas de GPS e da distância de proximidade (usar as coordenadas registradas nas visitas — VIS-03), clareza do fluxo de rota, falhas de login.
- Definir a data do beta (pendente).

### INF-13 — Documentação da API para o app Flutter [MVP]
- Manter a documentação automática do FastAPI atualizada (em desenvolvimento), com exemplos de resposta, e uma lista das rotas que mudaram em relação à versão atual (para a equipe do app ajustar).
