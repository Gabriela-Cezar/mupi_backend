# 09 — Ordem de execução (backend + app)

Data: 12/11/2026
Este arquivo é **igual** em `mupi_backend/requisitos/` e `mupi_application/requisitos/`. Ao alterar um, alterar o outro.
Substitui as tabelas "Ordem sugerida" dos arquivos `00_visao_geral.md`.

**Princípio:** construir em fatias verticais. Em cada etapa o backend entrega uma parte e o app passa a usá-la logo em seguida, para testar cada recurso de ponta a ponta antes de passar ao próximo.

**O app ainda não foi publicado:** o backend pode mudar o formato das respostas sem manter compatibilidade, desde que o app mude na mesma etapa. Não é preciso fazer as soluções provisórias previstas nos requisitos (ex.: `description` como bloco único no app, manter `/mupi-objects/{id}/image` até o app migrar).

---

## Estado em 12/11/2026

- **Backend:** FAL-01 a FAL-19 resolvidas (FAL-20, testes, segue contínua); migrações 0001 a 0005; USR-05 e USR-11 prontas.
- **App:** APP-FAL-01 a 10 e APP-AUT-05 prontas. Pendentes da etapa de correções: `.env` do app (APP-FAL-13), código duplicado (APP-FAL-11), `auth_service` ainda fora do `ApiClient` (APP-INF-01) e separação `MupiSummary`/`MupiContent` (vai para a Etapa 2).

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
- [ ] Apagar o `.env` do app (APP-FAL-13)
- [ ] Remover código duplicado e sem uso (APP-FAL-11)
- [ ] Migrar `auth_service` para o `ApiClient`; mensagens para 429 no login e no reenvio (APP-INF-01, APP-AUT-01, APP-AUT-02)
- [ ] Renomear o recurso atual "rota" para **"Como chegar"** (`DirectionsService`, `Directions`, "Encerrar trajeto") — libera o nome "rota" para a Etapa 5

## Etapa 1 — Arquivos no S3

Vem antes de tudo porque foto, áudio, capa de rota e imagem de insígnia dependem dela.

- [x] **Backend:** novas variáveis em `config.py` e `.env.example` (INF-03)
- [x] **Backend:** `storage_service` com `boto3`: salvar, gerar link assinado, apagar (INF-04)
- [x] **Backend:** script que move as imagens do banco para o S3 e migração que remove as colunas `data`/`image` (INF-04) — migrações 0006/0007; a foto do ponto já fica em `mupi_objects.photo_key` (adianta parte da PT-05)
- [ ] **Externo:** criar o bucket de desenvolvimento e o usuário IAM; rodar `alembic upgrade 0006` → `python -m app.scripts.move_images_to_s3` → `alembic upgrade head`
- [x] **App:** confirmar que o `AuthenticatedImage` funciona com link assinado completo (`https://...`) (APP-MAP-06) — já coberto por teste; nenhuma mudança necessária

## Etapa 2 — Novo modelo do ponto, painel e mapa

- [ ] **Backend:** vários temas por ponto — `mupi_object_themes`, migrando `theme_id` (PT-02, PT-03)
- [ ] **Backend:** blocos de texto — `mupi_object_sections`, migrando `description` (PT-04)
- [ ] **Backend:** foto única no S3 (PT-05), vídeos do YouTube com ID extraído (PT-07), campos de estabelecimento (PT-08), "existe individualmente" (PT-09)
- [ ] **Backend:** resumo do mapa, próximos e busca com `themes` (PT-10, PT-11); conteúdo completo na abertura (PT-13); remover rotas antigas de imagem/mídia (PT-14)
- [ ] **Backend:** painel de pontos e temas com desativar e excluir (ADM-04, ADM-05, ADM-08 e ADM-09 do ponto e do tema, ADM-12)
- [ ] **App:** `MupiSummary` com `themes` e `MupiContent` separados (APP-MAP-01, APP-PON-01)
- [ ] **App:** carregar todos os pontos com `GET /mupi-objects`, distância calculada no app, recarga periódica e ao voltar ao mapa (APP-MAP-02)
- [ ] **App:** marcadores de visitado, cartão de resumo com "Abrir" e "Como chegar" (APP-MAP-03, APP-MAP-05)
- [ ] **App:** menu, busca e "Abrir ponto" no aviso de chegada (APP-MAP-07, 08, 09)
- [ ] **App:** tela inteira do ponto — foto única, blocos com título em negrito, estabelecimento (APP-PON-02, 03, 07, 08)

## Etapa 3 — Mídia e proximidade

- [ ] **Backend:** áudio com validação pelo conteúdo e duração (PT-06)
- [ ] **Backend:** abertura recebe a precisão do GPS; distância máxima no `.env` com tolerância (VIS-01, VIS-02)
- [ ] **Backend:** gravar latitude, longitude e precisão na visita (VIS-03); teste de concorrência (VIS-05)
- [ ] **Backend:** devolver a distância máxima ao app (para o botão "Abrir" não repetir o valor)
- [ ] **App:** leitura em voz alta com `flutter_tts` (APP-PON-04)
- [ ] **App:** áudio com `just_audio` (APP-PON-05)
- [ ] **App:** YouTube dentro do app com `youtube_player_flutter` (APP-PON-06)
- [ ] **App:** só uma mídia tocando por vez (APP-PON-04, 05, 06)
- [ ] **App:** enviar a precisão do GPS e avisar "Sinal de GPS fraco" (APP-INF-05)
- [ ] **Publicar em produção na AWS** ao fim desta etapa: Lightsail + banco gerenciado + S3, HTTPS, backups, README (INF-02, INF-05, INF-06); app apontando para HTTPS (APP-INF-02)
- [ ] **Administradores começam a cadastrar o conteúdo real dos 40 pontos** em produção, em paralelo com as Etapas 4 a 6

## Etapa 4 — Insígnias, perfil e exclusão de conta

- [ ] **Backend:** quatro tipos de insígnia, `object_id` no lugar de `mupi_object_badges`, `ativa` (INS-01); a insígnia de rota (`route_id`) entra na Etapa 5
- [ ] **Backend:** concessão automática de visita e de quantidade, contagem que não diminui, avaliação retroativa, registro e retorno imediato (INS-02, 03, 05, 06, 07, 09)
- [ ] **Backend:** remover `POST /users/me/visits` e `POST /users/me/badges`
- [ ] **Backend:** painel de insígnias com bloqueio de exclusão (ADM-06, ADM-08, ADM-09)
- [ ] **Backend:** histórico de visitas `GET /users/me/visits` (VIS-04); perfil completo (USR-07, INS-08)
- [ ] **Backend:** exclusão de conta `DELETE /users/me` com senha, chamando `revoke_sessions` (USR-08, USR-05)
- [ ] **App:** perfil, insígnias conquistadas, em progresso e bloqueadas (APP-PER-01, 02, 03, 06)
- [ ] **App:** aviso de conquista (APP-PER-04)
- [ ] **App:** histórico de pontos visitados (APP-PER-05)
- [ ] **App:** "Sair" no perfil e "Excluir minha conta" com senha (APP-AUT-06, APP-AUT-08)

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
