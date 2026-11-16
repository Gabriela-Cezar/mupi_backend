# 09 — Ordem de execução (backend + app)

Data: 12/11/2026
Este arquivo é **igual** em `mupi_backend/requisitos/` e `mupi_application/requisitos/`. Ao alterar um, alterar o outro.
Substitui as tabelas "Ordem sugerida" dos arquivos `00_visao_geral.md`.

**Princípio:** construir em fatias verticais. Em cada etapa o backend entrega uma parte e o app passa a usá-la logo em seguida, para testar cada recurso de ponta a ponta antes de passar ao próximo.

**O app ainda não foi publicado:** o backend pode mudar o formato das respostas sem manter compatibilidade, desde que o app mude na mesma etapa. Não é preciso fazer as soluções provisórias previstas nos requisitos (ex.: `description` como bloco único no app, manter `/mupi-objects/{id}/image` até o app migrar).

---

## Estado em 12/11/2026

- **Backend:** FAL-01 a FAL-19 resolvidas (FAL-20, testes, segue contínua); migrações 0001 a 0005; USR-05 e USR-11 prontas.
- **App:** APP-FAL-01 a 11, APP-AUT-05 e APP-INF-01 prontas; "Como chegar" renomeado (13/11). Pendentes: apagar o `.env` do app (APP-FAL-13, manual) e separação `MupiSummary`/`MupiContent` (vai para a Etapa 2).
- **Desenvolvimento sem nuvem (13/11):** a escolha do provedor (AWS ou alternativa) não bloqueia as Etapas 2, 4, 5 e 6. Banco local; arquivos num S3 local (MinIO, via `S3_ENDPOINT_URL`) ou sem fotos (`photo_url` nulo). Só a publicação em produção (fim da Etapa 3) espera a decisão.
- **`flutter analyze` falha com o caminho com acento** ("Área de Trabalho", APP-FAL-15): o servidor de análise quebra. Enquanto a pasta não for movida, rodar a análise numa cópia do projeto fora dessa pasta.

---

## Etapa 0 — Tarefas externas e ajustes rápidos (agora)

Tarefas externas que demoram e não dependem de código:
- [ ] Conta AWS: MFA no usuário raiz, alertas de custo (Budgets), usuário IAM próprio, bucket S3 de desenvolvimento (INF-04, INF-05)
- [ ] Google Cloud Console: projeto e credenciais OAuth para Android (SHA-1 de debug e release) e iOS (USR-04, APP-AUT-04)
- [ ] Contas de desenvolvedor Apple (anual) e Google Play (APP-INF-13)
- [ ] **Google Play:** confirmar no Play Console se a conta pessoal nova exige teste fechado com 12 testadores por 14 dias antes de publicar em produção (o teste interno não conta). Contas de organização são isentas. Pode afetar a data de lançamento.
- [ ] **Decidir sobre "Entrar com a Apple"**: a App Store costuma exigi-lo quando há login com Google (diretriz 4.8; USR-12, APP-AUT-04)
- [ ] Domínio da API; domínio remetente verificado no Resend com SPF/DKIM (INF-07)
- [ ] Rascunho da política de privacidade (APP-INF-12)

App:
- [ ] Apagar o `.env` do app (APP-FAL-13) — fazer manualmente; o `EMAIL_FROM` e a chave do Resend já estão no `.env` do backend
- [x] Remover código duplicado e sem uso (APP-FAL-11)
- [x] Migrar `auth_service` para o `ApiClient`; mensagens para 429 no login e no reenvio (APP-INF-01, APP-AUT-01, APP-AUT-02) — o botão de reenvio espera o `Retry-After`
- [x] Renomear o recurso atual "rota" para **"Como chegar"** (`DirectionsService`, `Directions`, "Encerrar trajeto") — libera o nome "rota" para a Etapa 5. A rota do backend continua `GET /mupi-objects/{id}/route`

## Etapa 1 — Arquivos no S3

Vem antes de tudo porque foto, áudio, capa de rota e imagem de insígnia dependem dela.

- [x] **Backend:** novas variáveis em `config.py` e `.env.example` (INF-03)
- [x] **Backend:** `storage_service` com `boto3`: salvar, gerar link assinado, apagar (INF-04)
- [x] **Backend:** script que move as imagens do banco para o S3 e migração que remove as colunas `data`/`image` (INF-04) — migrações 0006/0007; a foto do ponto já fica em `mupi_objects.photo_key` (adianta parte da PT-05)
- [ ] **Externo:** criar o bucket de desenvolvimento e o usuário IAM; rodar `alembic upgrade 0006` → `python -m app.scripts.move_images_to_s3` → `alembic upgrade head`
- [x] **Backend:** armazenamento numa pasta local para desenvolver sem S3 (`LOCAL_STORAGE_DIR`, links assinados em `/local-files/...`; ver `infra/arquivos_locais.md`) — 16/11. As imagens do MinIO deixaram de ser publicadas. Banco local migrado até a 0008 usando a pasta local; o bucket real continua pendente
- [x] **App:** confirmar que o `AuthenticatedImage` funciona com link assinado completo (`https://...`) (APP-MAP-06) — já coberto por teste; nenhuma mudança necessária

## Etapa 2 — Novo modelo do ponto, painel e mapa

- [x] **Backend:** vários temas por ponto — `mupi_object_themes`, migrando `theme_id` (PT-02, PT-03) — migração 0008 (16/11)
- [x] **Backend:** blocos de texto — `mupi_object_sections`, migrando `description` (PT-04) — a `description` antiga vira o bloco "Sobre o ponto"
- [x] **Backend:** foto única no S3 (PT-05), vídeos do YouTube com ID extraído (PT-07), campos de estabelecimento (PT-08), "existe individualmente" (PT-09) — 16/11 (`mupi_object_videos`, `mupi_object_media` removida; substituir/remover a foto na edição do ponto)
- [x] **Backend:** resumo do mapa, próximos e busca com `themes` (PT-10, PT-11); conteúdo completo na abertura (PT-13); remover rotas antigas de imagem/mídia (PT-14) — 16/11
- [x] **Backend:** painel de pontos e temas com desativar e excluir (ADM-04, ADM-05, ADM-08 e ADM-09 do ponto e do tema, ADM-12) — 16/11. Tema não tem "desativar" (o ADM-08 não prevê); a lista de pontos ganha áudio na Etapa 3 e rotas na Etapa 5; o formulário de insígnia continua devolvendo JSON até o ADM-06 (Etapa 4)
- [x] **App:** `MupiSummary` com `themes` e `MupiContent` separados (APP-MAP-01, APP-PON-01) — 16/11; `MupiObject` removido
- [x] **App:** carregar todos os pontos com `GET /mupi-objects`, distância calculada no app, recarga periódica e ao voltar ao mapa (APP-MAP-02) — 16/11; recarga a cada 3 min, ao voltar da busca e ao voltar ao app; `getNearby` removido do app (a rota `/nearby` continua no backend)
- [x] **App:** marcadores de visitado, cartão de resumo com "Abrir" e "Como chegar" (APP-MAP-03, APP-MAP-05) — 16/11. O ponto só abre ao tocar em "Abrir" (nunca sozinho); longe, o botão mostra "Aproxime-se para abrir (X m)". Raio de 50 m fixo no app até o backend informar o valor (Etapa 3)
- [x] **App:** menu, busca e "Abrir ponto" no aviso de chegada (APP-MAP-07, 08, 09) — 16/11. Selo de visitado no menu e na busca; o menu espera a localização para mostrar os mais próximos; "Abrir ponto" mostra o cartão (o conteúdo abre só no "Abrir")
- [x] **App:** tela inteira do ponto — foto única, blocos com título em negrito, estabelecimento (APP-PON-02, 03, 07, 08) — 16/11. Foto em tela cheia com zoom e endereço abrindo o app de mapas (desejáveis); os vídeos ainda abrem no YouTube até a APP-PON-06 (Etapa 3)

## Etapa 3 — Mídia e proximidade

- [x] **Backend:** áudio com validação pelo conteúdo e duração (PT-06) — 16/11, migração 0010. MP3/M4A até 20 MB, duração com `mutagen`; enviar, substituir e remover no painel; coluna "Áudio" na lista; `has_audio` no resumo e `audio` (link de 1 h + duração) na abertura
- [x] **Backend:** abertura recebe a precisão do GPS; distância máxima no `.env` com tolerância (VIS-01, VIS-02) — 16/11. `VISIT_MAX_DISTANCE_M` (padrão 25 m) e `VISIT_GPS_TOLERANCE_M` (padrão 15 m); `accuracy` opcional na abertura
- [x] **Backend:** gravar latitude, longitude e precisão na visita (VIS-03); teste de concorrência (VIS-05) — 16/11, migração 0009
- [x] **Backend:** devolver a distância máxima ao app (para o botão "Abrir" não repetir o valor) — 16/11, `GET /app-settings`
- [x] **App:** leitura em voz alta com `flutter_tts` (APP-PON-04) — 16/11. "Ouvir tudo" e botão por bloco; pausar/continuar (retoma do começo do bloco)/parar; destaque no bloco lido; aviso de como instalar a voz pt-BR; para ao sair. A conferir num aparelho
- [x] **App:** áudio com `just_audio` (APP-PON-05) — 16/11. Player na tela do ponto (entre o nome e os blocos): tocar/pausar, barra para avançar/voltar, duração antes de tocar; só carrega no primeiro toque, para ao sair; marca "Áudio" no cartão. A conferir num aparelho
- [x] **App:** YouTube dentro do app com `youtube_player_flutter` (APP-PON-06) — 16/11, com o `youtube_player_iframe` (o `youtube_player_flutter` não funciona no navegador). Player numa janela suspensa sobre a tela do ponto (fechar para o vídeo), tela cheia opcional, "Este vídeo não está disponível" sem abrir o YouTube. A conferir num aparelho
- [x] **App:** só uma mídia tocando por vez (APP-PON-04, 05, 06) — 16/11. Áudio, leitura e vídeo: começar um pausa o outro
- [x] **App:** enviar a precisão do GPS e avisar "Sinal de GPS fraco" (APP-INF-05) — 16/11. O botão "Abrir" usa a regra de `GET /app-settings` (máxima + precisão até a tolerância), no lugar dos 50 m fixos; aviso com precisão pior que 50 m, sem bloquear
- [ ] **Publicar em produção na AWS** ao fim desta etapa: Lightsail + banco gerenciado + S3, HTTPS, backups, README (INF-02, INF-05, INF-06); app apontando para HTTPS (APP-INF-02)
- [ ] **Administradores começam a cadastrar o conteúdo real dos 40 pontos** em produção, em paralelo com as Etapas 4 a 6

## Etapa 4 — Insígnias, perfil e exclusão de conta

- [x] **Backend:** quatro tipos de insígnia, `object_id` no lugar de `mupi_object_badges`, `ativa` (INS-01); a insígnia de rota (`route_id`) entra na Etapa 5 — 16/11, migração 0011 (`manual` → `point_visit`)
- [x] **Backend:** concessão automática de visita e de quantidade, contagem que não diminui, avaliação retroativa, registro e retorno imediato (INS-02, 03, 05, 06, 07, 09) — 16/11; avalia a cada abertura (inclusive reabertura) e ao carregar o perfil
- [x] **Backend:** remover `POST /users/me/visits` e `POST /users/me/badges` — 16/11
- [x] **Backend:** painel de insígnias com bloqueio de exclusão (ADM-06, ADM-08, ADM-09) — 16/11. Lista (tipo, condição, situação, conquistas), formulário por tipo, imagem, ativar/desativar; insígnia conquistada não muda de regra nem pode ser excluída
- [x] **Backend:** histórico de visitas `GET /users/me/visits` (VIS-04); perfil completo (USR-07, INS-08) — 16/11. Histórico com pontos desativados marcados como indisponíveis; perfil com `locked` (insígnias de ponto não ganhas, só id e tipo) e `active_route` (nulo até a Etapa 5)
- [x] **Backend:** exclusão de conta `DELETE /users/me` com senha, chamando `revoke_sessions` (USR-08, USR-05) — 16/11. Senha errada = 403 (não 401); 5 tentativas a cada 15 min por conta; contas Google confirmarão com `id_token` quando esse login existir
- [x] **App:** perfil, insígnias conquistadas, em progresso e bloqueadas (APP-PER-01, 02, 03, 06) — 16/11. Pelo botão de perfil do menu do mapa; recarrega ao abrir e ao puxar a tela
- [x] **App:** aviso de conquista (APP-PER-04) — 16/11. Janela com imagem e nome (todas num único aviso), animação e vibração curta
- [x] **App:** histórico de pontos visitados (APP-PER-05) — 16/11, no perfil; tocar num ponto disponível mostra o cartão dele no mapa
- [x] **App:** "Sair" no perfil e "Excluir minha conta" com senha (APP-AUT-06, APP-AUT-08) — 16/11. O "Sair" saiu da barra do mapa

## Etapa 5 — Rotas (cerca de 2 semanas)

1. [ ] **Backend:** cadastro, pontos ordenados e trajeto pelo OpenRouteService (ROT-01, 02, 03) + painel de rotas (ADM-07). O painel vem antes porque o app precisa de rotas cadastradas para ser testado.
2. [ ] **App:** modelos `RouteSummary`, `RouteDetail`; lista e detalhes com o mapa do trajeto (APP-ROT-01, 02)
3. [ ] **Backend:** listar/ver (ROT-04), iniciar (ROT-05), rota ativa (ROT-06), finalizar ponto (ROT-07), encerrar (ROT-08), abandonar (ROT-09), rota alterada pelo administrador (ROT-10)
4. [ ] **Backend:** insígnia de conclusão de rota (INS-04); tabela de eventos de rota iniciada/abandonada/concluída (observação do ADM-10)
5. [ ] **App:** `ActiveRoute`; iniciar com tratamento do 409 (APP-ROT-03); rota ativa no mapa (APP-ROT-04)
6. [ ] **App:** finalizar ponto, tela de conclusão, abandonar, rota encerrada pelo administrador (APP-ROT-05, 06, 07, 08)

## Etapa 6 — Login com Google

- [ ] **Backend:** `POST /auth/google` com `google_sub` e `password_hash` opcional (USR-04)
- [ ] **Backend:** recuperação de senha cria senha em conta só Google (USR-06); exclusão de conta só Google com `id_token` (USR-08)
- [ ] **Backend [DESEJÁVEL]:** sair de todos os aparelhos (USR-13)
- [ ] **App:** botão "Entrar com Google" (APP-AUT-04); texto da recuperação para os dois casos (APP-AUT-03); exclusão de conta pelo Google (APP-AUT-08)
- [ ] "Entrar com a Apple", se decidido na Etapa 0

## Etapa 7 — Preparação do beta

- [ ] **Backend:** limite geral por usuário nas rotas do app (INF-08); `/docs` e `/redoc` desligados em produção (INF-09)
- [ ] **Backend:** testar a restauração de um backup (INF-06); lista de rotas alteradas para o app (INF-13)
- [ ] **App:** textos de permissão de localização (APP-INF-04); pausar o GPS em segundo plano (APP-INF-06)
- [ ] **App:** nome, ícone, identificador definitivo e versão (APP-INF-11)
- [ ] **App:** política de privacidade publicada, formulários das lojas, conta de teste para revisores (APP-INF-12)
- [ ] **App:** keystore guardado com backup; envio ao TestFlight e ao teste interno/fechado da Google Play (APP-INF-13)
- [ ] **App:** revisão de acessibilidade (APP-INF-09); `flutter analyze` sem problemas (APP-INF-08)
- [ ] Definir a data do beta (INF-12)

## Etapa 8 — Ajustes do beta

- [ ] Ajustar a distância máxima com as coordenadas registradas nas visitas (VIS-02, VIS-03)
- [ ] Corrigir problemas de GPS, fluxo de rotas e login apontados pelos testadores
- [ ] Se houver tempo: estatísticas (ADM-10), miniaturas das fotos (PT-05), filtro por tema (APP-MAP-10), monitoramento de erros (INF-11, APP-INF-10)

---

## Regras que valem em todas as etapas

- **Testes junto com cada requisito**, não no fim: `pytest` no backend (INF-10) e `flutter test` no app (APP-INF-07).
- **Desativar e excluir no painel** (ADM-08, ADM-09) são feitos na etapa de cada item: ponto e tema na 2, insígnia na 4, rota na 5.
- A cada mudança no backend, registrar se o app precisa mudar.

## Calendário aproximado

| Período | Etapas |
|---|---|
| 12/11 a 20/11 | 0 e 1 |
| 23/11 a 04/12 | 2 e 3 (publicação na AWS no fim) |
| 07/12 a 11/12 | 4 |
| 14/12 a 31/12 | 5 (com Natal e Ano Novo no meio) |
| início de janeiro | 6 e 7, beta |
| janeiro | 8 e lançamento |

O prazo está apertado. **Se for preciso cortar:** o login com Google (Etapa 6) pode ficar para depois do beta, porque o login por e-mail já funciona. As rotas devem ser mantidas.
