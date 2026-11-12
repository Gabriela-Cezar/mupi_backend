# 01 — Correções e falhas detectadas no código atual

Falhas encontradas na leitura do projeto (Etapa 1). Todas devem ser corrigidas antes do beta, salvo quando indicado.
Cada item traz: onde está, o problema, o impacto e o que deve ser feito.

---

## Falhas que quebram funcionalidades

### FAL-01 — Reenvio do código de verificação sempre falha [MVP]
- **Situação:** ✅ Resolvida
- **Onde:** `app/controller/auth_controller.py`, rota `POST /auth/resend-verification`.
- **Problema:** a função `renovar_codigo` é usada, mas não é importada de `auth_user_email_service`.
- **Impacto:** toda chamada gera erro 500 (`NameError`). O usuário que não recebeu o código não consegue concluir o cadastro.
- **Correção:** importar `renovar_codigo`. Remover também o bloco de import duplicado de `app.core.security` no mesmo arquivo.
- **Critério de aceite:** a rota responde 200 e envia o novo código; responde 429 dentro do intervalo de 60 s; responde 404 quando não há cadastro pendente.

### FAL-02 — O tema do ponto é validado mas descartado [MVP]
- **Situação:** ✅ Resolvida
- **Onde:** `app/controller/mupi_object_controller.py`, `create_mupi_object`.
- **Problema:** `theme_id` é lido e validado, mas não é passado ao criar o `MupiObject`.
- **Impacto:** nenhum ponto fica com tema; as insígnias "visitar N pontos de um tema" nunca são concedidas.
- **Correção:** será resolvida pela mudança para vários temas por ponto (ver `03_pontos_mupi_e_conteudo.md`, PT-03). Até lá, gravar o `theme_id`.

### FAL-03 — Formulários do painel incompletos [MVP]
- **Situação:** ✅ Resolvida
- **Onde:** `app/templates/admin/badge_form.html` e `mupi_object_form.html`.
- **Problema:** o formulário de insígnia não tem campos de tipo de regra, quantidade e tema; o formulário de ponto não tem campo de tema.
- **Impacto:** pelo painel só é possível criar insígnias do tipo "manual" e pontos sem tema.
- **Correção:** os formulários serão refeitos (ver `07_painel_administrativo.md`).

## Falhas de segurança

### FAL-04 — Painel administrativo sem autenticação [MVP — crítico]
- **Situação:** ✅ Resolvida
- **Onde:** todas as rotas `/admin/*`.
- **Impacto:** qualquer pessoa com o endereço pode cadastrar pontos, temas e insígnias.
- **Correção:** login de administrador (ver `07_painel_administrativo.md`, ADM-01).

### FAL-05 — Rota de teste de e-mail aberta [MVP — crítico]
- **Situação:** ✅ Resolvida
- **Onde:** `app/controller/email_controller.py`, `POST /email/test`.
- **Impacto:** qualquer pessoa pode usar o servidor para enviar e-mails para qualquer endereço, gastando a cota do Resend e podendo prejudicar a reputação do domínio remetente.
- **Correção:** remover a rota ou deixá-la acessível apenas a administradores logados.

### FAL-06 — Conteúdo dos pontos é público [MVP]
- **Situação:** ✅ Resolvida
- **Onde:** `GET /mupi-objects`, `/nearby`, `/search`, `/media/{id}`, `/{id}/image`.
- **Problema:** todas as rotas devolvem o conteúdo completo de todos os pontos sem login e sem verificar proximidade.
- **Impacto:** contraria a regra de que o conteúdo só aparece perto do ponto e de que o login é obrigatório.
- **Correção:** separar resumo do mapa e conteúdo completo (ver `03` e `04`).

### FAL-07 — Envio de e-mail sem limite de frequência [MVP]
- **Situação:** ✅ Resolvida
- **Onde:** `POST /auth/register` e `POST /auth/recovery-password`.
- **Problema:** não há intervalo mínimo nem limite de pedidos por e-mail ou por IP (só o reenvio tem intervalo).
- **Impacto:** alguém pode disparar dezenas de e-mails para uma pessoa ou esgotar a cota do Resend.
- **Correção:** aplicar intervalo mínimo de 60 s por e-mail e limite por IP (ver `08_infraestrutura.md`, INF-08).

### FAL-08 — Login sem proteção contra tentativas repetidas [MVP]
- **Situação:** ✅ Resolvida
- **Onde:** `POST /auth/login`.
- **Correção:** limitar tentativas por e-mail e por IP (ex.: 10 por 15 min), respondendo 429.

### FAL-09 — CORS liberado para qualquer origem [MVP]
- **Situação:** ✅ Resolvida
- **Onde:** `main.py`.
- **Problema:** `allow_origins=["*"]` junto com `allow_credentials=True`.
- **Correção:** como o app é Flutter mobile (não depende de CORS) e o painel é servido pelo próprio backend, restringir as origens a uma lista configurada no `.env` (pode ficar vazia em produção).

### FAL-10 — Arquivo de ignorados com nome errado [MVP]
- **Situação:** ✅ Resolvida (na criação do repositório; histórico verificado sem vazamentos)
- **Onde:** raiz do projeto, arquivo `.gitgnore`.
- **Impacto:** quando o projeto for para o git, o `.env` com as chaves (Resend, banco, OpenRouteService, SECRET_KEY) será enviado.
- **Correção:** renomear para `.gitignore`. Criar `.env.example` sem valores reais. Se o `.env` já foi compartilhado em algum lugar, trocar as chaves.

## Falhas de integridade de dados

### FAL-11 — Exclusões apagam o histórico dos usuários [MVP]
- **Situação:** ✅ Resolvida no banco (migração 0003: `ON DELETE RESTRICT` em `user_visits.object_id` e `user_badges.badge_id`; o banco recusa excluir ponto visitado ou insígnia conquistada). As telas de exclusão do painel, com mensagem e opção de desativar, ficam para a ADM-09. Obs.: o commit 14ba7c6, chamado "FAL-11", contém na verdade a FAL-14.
- **Onde:** `app/model/user_visit.py` e `user_badge.py` (`ondelete="CASCADE"` para pontos e insígnias).
- **Problema:** excluir um ponto apaga as visitas de todos os usuários a ele; excluir uma insígnia apaga a conquista de todos que a tinham.
- **Impacto:** contraria a regra "a insígnia continua com o usuário".
- **Correção:** ver `07_painel_administrativo.md`, ADM-09 (exclusão bloqueada quando há histórico; usar desativação).

### FAL-12 — Desativar um ponto reduz o progresso dos usuários [MVP]
- **Situação:** ✅ Resolvida
- **Onde:** `app/service/badge_service.py`, `visit_counts` (filtra `MupiObject.active`).
- **Impacto:** se um ponto for desativado, quem o visitou "perde" a visita na contagem e o progresso das insígnias diminui.
- **Correção:** contar todas as visitas registradas, independentemente de o ponto estar ativo (ver `06_insignias.md`, INS-05).

### FAL-13 — Códigos de verificação guardados na memória [MVP]
- **Situação:** ✅ Resolvida (tabela `email_codes`, migração 0004; só o hash HMAC do código é guardado; códigos vencidos há mais de 1 dia são apagados ao gerar um novo)
- **Onde:** `app/service/auth_user_email_service.py` (dicionários em memória).
- **Impacto:** reiniciar o servidor apaga os códigos pendentes; com mais de um processo, o código gerado em um processo não é reconhecido no outro.
- **Correção:** guardar os códigos no banco (ver `02_usuarios_e_autenticacao.md`, USR-09).

### FAL-14 — Recriação de tabelas apaga dados [MVP]
- **Situação:** ✅ Resolvida (Alembic adotado; migrações 0001 e 0002 aplicadas no banco de desenvolvimento em 11/11/2026, com backup antes; scripts que apagavam tabelas removidos)
- **Onde:** `create_tables.py` e `reset_mupi_tables.py` (fazem `drop_all`).
- **Impacto:** qualquer mudança no modelo exige apagar dados.
- **Correção:** adotar Alembic (ver `08_infraestrutura.md`, INF-01). Manter os scripts apenas para desenvolvimento, com aviso claro, ou removê-los.

## Problemas menores

### FAL-15 — Caminho dos templates depende da pasta de execução [MVP]
- **Situação:** ✅ Resolvida (na FAL-04: templates compartilhados com caminho absoluto)
- **Onde:** `Jinja2Templates(directory="app/templates")` em `mupi_object_controller.py`.
- **Impacto:** se o servidor for iniciado de outra pasta, o painel não encontra os templates.
- **Correção:** usar caminho absoluto baseado no arquivo, como já é feito para os arquivos estáticos em `main.py`.

### FAL-16 — Imagem de ponto inativo é servida [MVP]
- **Situação:** ✅ Resolvida (na FAL-06)
- **Onde:** `GET /mupi-objects/{object_id}/image` não filtra pontos ativos.
- **Correção:** será substituída pela nova forma de servir arquivos (ver `03`, PT-06).

### FAL-17 — Busca por nome não trata caracteres especiais [DESEJÁVEL]
- **Situação:** ✅ Resolvida (`icontains(..., autoescape=True)` nas buscas do app e do painel)
- **Onde:** buscas com `ilike(f"%{name}%")`.
- **Problema:** `%` e `_` digitados pelo usuário funcionam como curingas.
- **Correção:** escapar esses caracteres.

### FAL-18 — Configuração lida de formas diferentes [MVP]
- **Situação:** ✅ Resolvida (todas as variáveis de ambiente são lidas em `app/core/config.py`; um teste impede `os.getenv` em outros arquivos)
- **Onde:** `OPENROUTESERVICE_API_KEY` é lida com `os.getenv` dentro da rota; as demais chaves passam por `app/core/config.py`.
- **Correção:** centralizar em `config.py`, junto com as novas configurações (distância de proximidade, origens CORS, armazenamento, Google).

### FAL-19 — Falta lista de dependências [MVP]
- **Situação:** ✅ Resolvida (`requirements.txt` e `requirements-dev.txt`, testados num ambiente Python limpo; o README do INF-02 continua pendente)
- **Correção:** criar `requirements.txt` (ou `pyproject.toml`) com versões fixas (ver INF-02).

### FAL-20 — Não existem testes automatizados [MVP]
- **Situação:** 🟡 Em andamento (testes criados a cada correção; ver INF-10)
- **Correção:** ver `08_infraestrutura.md`, INF-10.

### FAL-21 — A localização enviada pelo celular não é verificada [registrado, sem correção no MVP]
- **Problema:** a proximidade é calculada com a coordenada enviada pelo app; um usuário com GPS falso pode "visitar" pontos de longe.
- **Decisão sugerida:** aceitar o risco no lançamento (não há prêmios de valor). Registrar latitude, longitude e precisão de cada visita para permitir análise futura.
