# Mudanças da API para o app (INF-13)

Comparação entre a **versão inicial** do backend (commit `058f545`,
10/11/2026) e a versão atual (migração `0017`, 17/11/2026). Só as rotas do
app; o painel (`/admin`) é servido pelo próprio backend.

Detalhes de cada rota (campos, exemplos): `/docs` no desenvolvimento, com
`API_DOCS=true` no `.env`. Em produção a documentação fica desligada (INF-09).

O app atual (`mupi_application`) já usa todas as mudanças abaixo.

## Regras gerais

- **Login em todas as rotas do app.** Antes, a lista, a busca, os pontos
  próximos e o "Como chegar" eram públicos. Agora, só `/auth/*` funciona
  sem o token (`Authorization: Bearer ...`).
- **401 = sessão expirada ou inválida** (o app volta ao login). Senha
  errada ao excluir a conta responde **403**, para não ser confundida com
  sessão expirada.
- **429 = muitas requisições**, com a espera no cabeçalho `Retry-After` e
  a mensagem pronta em `detail`. Vale para login, cadastro, e-mails e
  exclusão de conta, e há um limite geral de 120 requisições por minuto
  por usuário em todas as rotas com login (INF-08).
- **Mensagens em português** em `detail`, prontas para mostrar.
- **Arquivos (fotos, áudios, imagens das insígnias) por link temporário**
  (`photo_url`, `image_url`, `audio.url`): link assinado do S3, válido por
  1 hora. Não guardar o link; pedir os dados de novo quando precisar.
- **Token de sessão vale 30 dias** e é renovado em `POST /auth/refresh`.

## Rotas removidas

| Rota antiga | Substituída por |
|---|---|
| `POST /users/me/visits` (check-in) | `POST /mupi-objects/{id}/open`: abrir o ponto já registra a visita |
| `POST /users/me/badges` (coletar insígnia manual) | Não existe mais insígnia manual: as insígnias são concedidas sozinhas (visita ao ponto, quantidade de visitas, por tema, conclusão de rota) |
| `GET /mupi-objects/{id}/image` | `photo_url` no resumo do ponto |
| `GET /mupi-objects/badges/{id}/image` | `image_url` na insígnia |
| `GET /mupi-objects/media/{id}` | Fotos, áudio e vídeos vêm no conteúdo do ponto (`open`) |

## Rotas que mudaram

### `POST /auth/login`, `POST /auth/verify-email`, demais `/auth/*`
- Mesmos caminhos. O login responde como antes (`access_token`,
  `token_type`, `user_id`, `email`), mas o token agora vale 30 dias e deixa
  de valer ao trocar a senha, excluir a conta ou "sair de todos os aparelhos".
- `POST /auth/recovery-password` também serve para **criar uma senha** em
  conta que só entra com o Google.
- Limites com 429 (ver Regras gerais).

### `GET /users/me` (perfil)
Campos novos:
- `in_progress`: insígnias de quantidade ainda não conquistadas, com `progress`;
- `locked`: insígnias de visita a ponto ou de conclusão de rota ainda não
  conquistadas, só `{id, type}` (não revela o ponto nem a rota);
- `active_route`: a rota em andamento (mesmo formato de
  `GET /users/me/active-route`) ou `null`;
- `has_password` e `google_linked`: como confirmar a exclusão da conta.

Nas insígnias (`badges`, `in_progress`, `awarded`):
- `rule.type` agora é `point_visit`, `visit_count`, `theme_visit_count` ou
  `route_completion` (não existe mais `manual`);
- `collected_at_route`: rota onde a insígnia foi conquistada (ou `null`);
- `image_url` é o link temporário.

### `GET /mupi-objects`, `/mupi-objects/nearby`, `/mupi-objects/search`
- Exigem login.
- Devolvem o **resumo** do ponto, sem o conteúdo: `id`, `name`,
  `latitude`, `longitude`, `themes`, `photo_url`, `has_video`, `has_audio`,
  `address`, `visited` (o usuário já abriu o ponto) e `distance` (nearby e
  search).
- Saíram: `description`, `active`, `badges` e `media`. O conteúdo completo
  só vem ao abrir o ponto estando perto.
- Pontos "só de rota" não aparecem.

### `GET /mupi-objects/{id}/route` ("Como chegar")
- Exige login. Mesma resposta (`mupi_id`, `distance`, `duration`,
  `coordinates`).

## Rotas novas

### Conta
| Rota | O que faz |
|---|---|
| `POST /auth/google` | Entra com o Google: `{id_token}`. Entra, vincula ao mesmo e-mail ou cria a conta. 503 se o Google estiver desligado no servidor |
| `POST /auth/refresh` | Renova o token de sessão (o app chama ao abrir) |
| `GET /users/me/visits` | Histórico de visitas, da mais recente à mais antiga: `id`, `name`, `photo_url`, `visited_at`, `available` |
| `DELETE /users/me` | Exclui a conta: `{password}` ou `{id_token}` do Google (recente, até 10 min). 403 se não confirmar |
| `POST /users/me/logout-all` | Encerra a sessão em todos os aparelhos |

### Pontos
| Rota | O que faz |
|---|---|
| `POST /mupi-objects/{id}/open` | Abre o ponto: `{latitude, longitude, accuracy?}`. Perto: registra a visita e devolve o conteúdo completo (resumo + `sections`, `videos`, `audio`, `opening_hours`, `accessibility`, `badges`, `route_content`) e `new_visit`, `visits_total`, `awarded`. Longe: 403 com a distância |
| `GET /app-settings` | `visit_max_distance_m` e `visit_gps_tolerance_m`: a mesma regra de distância do backend, para ligar o botão "Abrir" |

Com uma rota em andamento que tenha **conteúdo próprio para o ponto**, o
`open` devolve o conteúdo da rota (nome, foto, blocos, áudio, vídeos e
informações do local) e `route_content: {route_id, route_name}`. Fora da
rota, `route_content` é `null`.

### Rotas (percursos)
| Rota | O que faz |
|---|---|
| `GET /routes` | Rotas ativas: resumo com `cover_url`, `distance_m`, `minutes`, `difficulty`, `age_rating`, `themes`, `points_count`, `completed` |
| `GET /routes/{id}` | Resumo + `description`, `points` em ordem, `path` (trajeto) e `waypoints` |
| `POST /routes/{id}/start` | Inicia a rota. 409 se já houver outra em andamento (`detail.active_route` diz qual) |
| `GET /users/me/active-route` | `{active_route, notice}`: a rota em andamento (`route`, `next_index`, `next_point`, `current_leg`, `all_finished`...) e o aviso, uma vez, se o administrador encerrou a rota |
| `POST /users/me/active-route/points/{id}/finish` | Finaliza o próximo ponto (precisa ter aberto o ponto e estar perto) |
| `POST /users/me/active-route/complete` | Conclui a rota: `route`, `completions` (vezes concluída) e `awarded` |
| `DELETE /users/me/active-route` | Abandona a rota |

## Como manter esta lista

A cada mudança numa rota do app, registrar aqui o que mudou e se o app
precisa mudar (regra do plano, `09_ordem_de_execucao.md`).
