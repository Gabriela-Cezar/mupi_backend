# 07 — Infraestrutura e qualidade (`INF`)

Configuração, banco, arquivos, segurança, backups, testes e as partes
técnicas do app. A publicação em produção e nas lojas está em `08_publicacao.md`.

---

## Backend

### INF-01 — Configuração [Lançamento] ✅
- Tudo pelo `.env`, lido **só** em `app/core/config.py`; `.env.example`
  documenta cada variável.
- Obrigatórias: `DATABASE_URL`, `SECRET_KEY` (mínimo 32 caracteres; o
  servidor não sobe com uma curta), `RESEND_API_KEY`, `EMAIL_FROM`.
- Opcionais: `OPENROUTESERVICE_API_KEY`, `GOOGLE_CLIENT_IDS`,
  `VISIT_MAX_DISTANCE_M`, `VISIT_GPS_TOLERANCE_M`, `APP_REQUESTS_PER_MINUTE`,
  `API_DOCS`, `ADMIN_COOKIE_SECURE`, `CORS_ALLOWED_ORIGINS`,
  `CORS_ALLOWED_ORIGIN_REGEX`, `S3_BUCKET`, `S3_ENDPOINT_URL`, `AWS_REGION`,
  `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `LOCAL_STORAGE_DIR`.
- Valores inválidos (número negativo, S3 e pasta local ao mesmo tempo)
  impedem o servidor de subir com mensagem clara.
- Testes: `test_config.py`, `test_preparacao_do_beta.py`.

### INF-02 — Banco e migrações [Lançamento] ✅
- PostgreSQL; esquema só por migrações do Alembic (`0001` a `0017`), com
  nomes fixos para chaves e restrições. Cada migração sobe e desce nos testes.
- Migrações que apagam dados ao descer recusam quando há dados que seriam
  perdidos (ex.: contas sem senha na `0016`).
- Testes: `test_migrations.py` e `test_migracao_*.py`.

### INF-03 — Armazenamento de arquivos [Lançamento] ✅
- Produção: bucket S3 **privado**, com versionamento e versões antigas
  apagadas em 30 dias; usuário IAM só com acesso ao bucket
  (`infra/aws/`). `python -m app.scripts.check_storage` confere o bucket.
- Desenvolvimento: pasta local (`LOCAL_STORAGE_DIR`, `infra/arquivos_locais.md`)
  ou MinIO (`infra/minio/`).
- O tipo do arquivo é conferido pelo conteúdo, não pelo nome.
- Testes: `test_storage_service.py`, `test_armazenamento_local.py`, `test_check_storage.py`.

### INF-04 — Limites de requisição [Lançamento] 🟡
| O quê | Limite |
|---|---|
| Rotas do app com login | 120 por minuto por usuário (`APP_REQUESTS_PER_MINUTE`) |
| Login | 5 falhas por IP + e-mail e 20 por IP, a cada 15 min |
| E-mails (cadastro, reenvio, recuperação) | 1 por e-mail a cada 60 s; 10 por IP a cada 15 min |
| Códigos de e-mail | 5 tentativas por código |
| Renovação de sessão | 30 por usuário por hora |
| Exclusão de conta | 5 tentativas por conta a cada 15 min |
| Login do painel | 5 falhas por IP + e-mail a cada 15 min |

- Respostas 429 com a mensagem e o cabeçalho `Retry-After`.
- **Falta:** as contagens ficam na memória de um processo. Com mais de um
  processo (workers do Gunicorn) ou servidor, cada um conta separado. Para o
  beta, rodar **um processo**; se crescer, guardar as contagens no banco ou
  num Redis.
- Onde: `rate_limit.py`.
- Testes: `test_login_rate_limit.py`, `test_email_rate_limit.py`, `test_preparacao_do_beta.py`.

### INF-05 — Segurança [Lançamento] ✅
- Senhas com Argon2; códigos de e-mail guardados como hash.
- CORS fechado por padrão (só as origens do `.env`).
- Documentação automática (`/docs`, `/redoc`, `/openapi.json`) só com
  `API_DOCS=true`; desligada em produção.
- Logs sem senhas, códigos ou tokens.
- Painel com cookie `HttpOnly`/`Secure` e CSRF; links de arquivos assinados e
  temporários.
- Testes: `test_cors.py`, `test_admin_auth.py`, `test_preparacao_do_beta.py`.

### INF-06 — Backups [Lançamento] 🟡
- Restauração testada no PostgreSQL local em 17/11/2026 (mesmas tabelas,
  linhas e versão). `python -m app.scripts.check_restore` compara o banco
  restaurado com a origem; passo a passo em `infra/backup_e_restauracao.md`.
- **Falta:** backups automáticos de 7 dias no banco gerenciado e repetir o
  teste de restauração na AWS (PUB-01).
- Testes: `test_restauracao_de_backup.py`.

### INF-07 — Testes automatizados do backend [Lançamento] ✅
- `pytest` (1031 testes) com SQLite em memória, S3 simulado (moto),
  OpenRouteService e Google simulados. Rodam sem internet nem `.env` real.

### INF-08 — Registro de erros [Desejável] ⬜
- Monitoramento de falhas no backend e no app (ex.: Sentry) para acompanhar o beta.

## App

### INF-09 — Cliente da API [Lançamento] ✅
- `ApiClient`: envia o token, tempo limite de 15 s e mensagens em português
  para 401, 403, 404, 422, 429 (com a espera), 5xx e falta de internet.
- Endereço da API por `--dart-define=API_BASE_URL=...`; sem ele, o
  computador local (`127.0.0.1:8000`, ou `10.0.2.2:8000` no emulador Android).
- Onde: app `lib/core/api_client.dart`, `api_config.dart`.
- Testes: app `api_client_test.dart`.

### INF-10 — Testes automatizados do app [Lançamento] ✅
- `flutter test` (451 testes) e `flutter analyze` sem problemas. Serviços
  injetáveis e falsos em `test/support/` (GPS, rotas, Google, usuário, mídias).
- Nesta máquina, rodar numa cópia do projeto fora da pasta com acento
  ("Área de Trabalho"), que atrapalha o `flutter analyze`.

### INF-11 — Permissão de localização [Lançamento] 📱
- Só durante o uso: `ACCESS_FINE_LOCATION` e `ACCESS_COARSE_LOCATION` no
  Android; no iOS, "O MUPI usa sua localização para mostrar os pontos
  próximos e confirmar suas visitas." Nunca em segundo plano.

### INF-12 — Bateria e dados [Lançamento] 📱
- Em segundo plano o mapa para o GPS e a recarga dos pontos e retoma ao
  voltar (e tenta de novo se o GPS estava desligado).
- Cache das imagens pelo arquivo, sem a assinatura do link: a mesma foto não
  é baixada de novo a cada recarga.
- Testes: app `map_background_test.dart`, `authenticated_image_test.dart`.

### INF-13 — Acessibilidade [Lançamento] 📱
- Contraste WCAG AA, área de toque mínima, rótulos para o leitor de tela,
  fonte do celular até 200% sem quebrar as telas e leitura em voz alta (PON-17).
- **Falta:** conferir com o TalkBack e o VoiceOver num celular.
- Testes: app `test/accessibility/acessibilidade_test.dart` (11 telas).

### INF-14 — Limpeza do app [Lançamento] ⬜
- Remover o pacote `maplibre_gl`, que não é usado e aumenta o app.
- Apagar o `.env` antigo da pasta do app (tem a chave do Resend; o app não o usa).
- Trocar a `description` do `pubspec.yaml` ("A new Flutter project.").
