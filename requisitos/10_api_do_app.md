# 10 — API do app

Referência das rotas que o app usa. Campos completos e exemplos: `/docs` no
desenvolvimento (`API_DOCS=true` no `.env`). O painel (`/admin`) não está aqui.

A cada mudança numa destas rotas, atualizar esta página e dizer se o app
precisa mudar.

## Regras gerais

- **Login:** todas as rotas, menos `/auth/*`, exigem `Authorization: Bearer <token>`.
- **Erros:** `detail` traz a mensagem em português, pronta para mostrar.
  - **401** = sessão expirada ou inválida (o app volta ao login).
  - **403** = recusado com a sessão válida (longe do ponto, senha errada ao excluir a conta).
  - **409** = conflito de estado (ex.: já há uma rota ativa).
  - **429** = muitas requisições; espera no cabeçalho `Retry-After` (INF-04).
- **Arquivos:** `photo_url`, `cover_url`, `image_url` e `audio.url` são links
  assinados e temporários: **imagens 24 h, áudio 1 h**. Não guardar o link;
  pedir os dados de novo.
- **Sessão:** o token vale 30 dias; renovar com `POST /auth/refresh` ao abrir o app.

## Conta (`CON`)

| Rota | Corpo | Resposta / observação |
|---|---|---|
| `POST /auth/register` | `{email, password}` | Envia o código de verificação |
| `POST /auth/verify-email` | `{email, codigo}` | Cria a conta |
| `POST /auth/resend-verification` | `{email}` | Reenvia o código (60 s entre envios) |
| `POST /auth/login` | `{email, password}` | `{access_token, token_type, user_id, email}` |
| `POST /auth/google` | `{id_token}` | Igual ao login; 503 com o Google desligado no servidor |
| `POST /auth/refresh` | — | Token novo |
| `POST /auth/recovery-password` | `{email}` | Envia o código (resposta igual com ou sem conta) |
| `POST /auth/verify-recovery-code` | `{email, codigo}` | `{reset_token}` (10 min) |
| `POST /auth/reset-password` | `{reset_token, password}` | Grava a senha e encerra as sessões |
| `POST /users/me/logout-all` | — | Encerra a sessão em todos os aparelhos |
| `DELETE /users/me` | `{password}` ou `{id_token}` | Exclui a conta; 403 se não confirmar |

## Pontos (`PON`, `VIS`)

| Rota | Parâmetros / corpo | Resposta |
|---|---|---|
| `GET /mupi-objects` | — | Lista de resumos |
| `GET /mupi-objects/nearby` | `latitude, longitude, radius` | Resumos no raio, com `distance` |
| `GET /mupi-objects/search` | `name, latitude, longitude` | Até 50 resumos, com `distance` |
| `POST /mupi-objects/{id}/open` | `{latitude, longitude, accuracy?}` | Conteúdo completo + `new_visit`, `visits_total`, `awarded`; 403 longe |
| `GET /mupi-objects/{id}/route` | `latitude, longitude` | "Como chegar": `distance`, `duration`, `coordinates` |
| `GET /app-settings` | — | `visit_max_distance_m`, `visit_gps_tolerance_m` |

**Resumo do ponto:** `id`, `name`, `latitude`, `longitude`, `themes`,
`photo_url`, `has_video`, `has_audio`, `address`, `visited` e, na busca e
nos próximos, `distance`.

**Conteúdo (abertura):** o resumo + `sections` (`title`, `body`), `videos`
(`youtube_id`, `title`, `url`), `audio` (`url`, `duration_seconds`) ou `null`,
`opening_hours`, `accessibility`, `badges` e `route_content`
(`{route_id, route_name}` quando é o conteúdo da rota ativa, ROT-12; senão `null`).

## Rotas (`ROT`)

| Rota | Resposta / observação |
|---|---|
| `GET /routes` | Resumos: `id`, `name`, `cover_url`, `distance_m`, `minutes`, `difficulty`, `age_rating`, `themes`, `points_count`, `completed` |
| `GET /routes/{id}` | Resumo + `description`, `points` em ordem, `path` (`[longitude, latitude]`) e `waypoints` (posição de cada ponto em `path`) |
| `POST /routes/{id}/start` | `{active_route, notice}`; 409 com outra rota ativa (`detail.message`, `detail.active_route`) |
| `GET /users/me/active-route` | `{active_route, notice}`: `notice` traz, uma vez, o aviso de rota encerrada pelo painel |
| `POST /users/me/active-route/points/{id}/finish` | `{latitude, longitude, accuracy?}`: finaliza o próximo ponto |
| `POST /users/me/active-route/complete` | `{route, completions, awarded}` |
| `DELETE /users/me/active-route` | Abandona a rota |

**Rota ativa:** `route` (detalhes), `started_at`, `next_index`, `next_point`
(`{id, name}`), `current_leg`, `all_finished`.

## Perfil (`INS`, `VIS`)

| Rota | Resposta |
|---|---|
| `GET /users/me` | `id`, `email`, `created_at`, `has_password`, `google_linked`, `visits_total`, `badges_collected`, `badges_total`, `badges`, `in_progress`, `locked`, `active_route` |
| `GET /users/me/visits` | `id`, `name`, `photo_url`, `visited_at`, `available`, do mais recente ao mais antigo |

**Insígnia:** `id`, `name`, `description`, `image_url`, `rule` (`type`:
`point_visit`, `visit_count`, `theme_visit_count` ou `route_completion`;
`required_count`; `theme`); as conquistadas trazem também `collected_at`,
`collected_at_object` e `collected_at_route`; as em progresso, `progress`.
