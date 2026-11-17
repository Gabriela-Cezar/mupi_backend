# 04 — Rotas (`ROT`)

Rota: sequência fixa de pontos ligada por um trajeto a pé, feita um ponto
por vez. Não confundir com o "Como chegar" até um ponto (PON-11).

---

## Cadastro (backend)

### ROT-01 — Rota [Lançamento] ✅
- Campos: nome (único), descrição, **capa**, dificuldade (Fácil, Média,
  Difícil), classificação indicativa (Livre, 10, 12, 14, 16, 18 anos), temas,
  pontos em ordem e tempo estimado opcional (sem ele, vale o tempo de
  caminhada calculado).
- Um ponto pode estar em várias rotas, mas só uma vez na mesma rota.
- Onde: `model/route.py`, `route_form.py`, `admin_route_controller.py`.
- Testes: `test_admin_rotas.py`.

### ROT-02 — Trajeto a pé [Lançamento] ✅
- Ao salvar com pontos novos ou em outra ordem, o backend pede ao
  OpenRouteService o trajeto a pé passando por todos os pontos (um pedido) e
  guarda as coordenadas, a posição de cada ponto no trajeto, a distância e o
  tempo de caminhada.
- Falha no cálculo: a rota é salva **desativada**, com o erro, e o painel
  oferece "Recalcular trajeto".
- Onde: `route_path_service.py`.
- Testes: `test_trajeto_da_rota.py` (OpenRouteService simulado).

### ROT-03 — Ativar e desativar [Lançamento] ✅
- Só ativa com **capa, 2 ou mais pontos ativos e trajeto calculado**; senão
  é salva desativada e o painel diz o que falta.
- **Desativar um ponto desativa as rotas que passam por ele.**
- Testes: `test_admin_rotas.py`.

### ROT-04 — Rota alterada durante o uso [Lançamento] ✅
- Mudar os pontos ou a ordem, ou desativar a rota, **encerra o progresso** de
  quem a está fazendo. O painel avisa quantas pessoas estão fazendo a rota.
- O app recebe o aviso **uma vez**, na próxima consulta da rota ativa.
- Mudar nome, descrição, capa ou o conteúdo dos pontos na rota não afeta o
  progresso.
- Testes: `test_rota_ativa.py`.

### ROT-05 — Excluir [Lançamento] ✅
- Rota já concluída por alguém ou com insígnia de conclusão não pode ser
  excluída; o painel oferece desativar.
- Ponto que está em alguma rota não pode ser excluído.
- Testes: `test_admin_rotas.py`, `test_insignia_de_rota.py`.

### ROT-06 — Eventos de rota [Lançamento] ✅
- Tabela `route_events`: rota iniciada, abandonada, concluída e encerrada pelo
  painel, com usuário e data. Base para as estatísticas (ADM-10).

## Uso (API)

### ROT-07 — Listar e ver [Lançamento] ✅
- `GET /routes`: rotas ativas com o resumo (capa, distância, tempo,
  dificuldade, classificação, temas, quantidade de pontos, se o usuário já concluiu).
- `GET /routes/{id}`: resumo + descrição, pontos em ordem (com o nome e a
  foto da rota, ROT-12) e o trajeto completo.
- Testes: `test_rotas_no_app.py`.

### ROT-08 — Iniciar [Lançamento] ✅
- `POST /routes/{id}/start`. **Uma rota ativa por vez:** com outra em
  andamento, 409 dizendo qual. Iniciar de novo a mesma rota não muda nada.
- Testes: `test_rota_ativa.py`.

### ROT-09 — Fazer a rota [Lançamento] ✅
- `GET /users/me/active-route`: rota ativa, próximo ponto, trecho atual e se
  todos já foram finalizados (ou o aviso do ROT-04).
- `POST /users/me/active-route/points/{id}/finish`: finaliza o **próximo**
  ponto, em ordem; exige ter **aberto o ponto** e estar perto.
- `POST /users/me/active-route/complete`: com todos finalizados, conclui:
  devolve quantas vezes o usuário já concluiu e as insígnias ganhas.
- `DELETE /users/me/active-route`: abandona (perde o progresso).
- A rota ativa também vem no perfil (`active_route`).
- Onde: `active_route_controller.py`, `active_route_service.py`.
- Testes: `test_rota_ativa.py`, `test_insignia_de_rota.py`.

## No app

### ROT-10 — Rotas no app [Lançamento] 📱
- "Rotas" no menu: lista com capa e resumo; detalhes com o mapa do trajeto,
  os pontos e "Iniciar rota". Com outra rota em andamento, pergunta se quer
  abandoná-la e iniciar esta.
- **Rota ativa no mapa:** trajeto com o trecho feito, o atual em destaque e o
  que falta; pontos numerados com o estado; caminho de onde o usuário está
  até o primeiro ponto; barra no topo com o próximo ponto, "Como chegar ao
  próximo" e "Abandonar" (com confirmação); aviso ao chegar ao próximo ponto.
- **Finalizar ponto** na tela do ponto; com todos finalizados, "Concluir rota"
  leva à tela de conclusão com as insígnias.
- Rota encerrada pelo painel: janela "Rota encerrada" com o motivo.
- Onde: app `routes_view.dart`, `route_detail_view.dart`, `active_route_store.dart`,
  `active_route_bar.dart`, `finish_route_point_button.dart`, `route_completed_view.dart`.
- Testes: app `routes_view_test.dart`, `active_route_flow_test.dart`,
  `map_active_route_test.dart`, `active_route_store_test.dart`, `route_service_test.dart`.

### ROT-11 — Seta para o próximo ponto [Desejável] ⬜
- Com o próximo ponto fora da tela, uma seta na borda indicando a direção.

## Conteúdo do ponto na rota

### ROT-12 — Conteúdo próprio do ponto dentro de uma rota [Lançamento] ✅
- Para cada ponto de uma rota, o administrador pode cadastrar outro conteúdo:
  nome e foto (em branco = os do ponto), blocos de texto, áudio, vídeos e
  informações do local. O formulário começa com uma cópia do conteúdo do
  ponto; "Usar o conteúdo do ponto" desfaz.
- Quem abre o ponto **com aquela rota ativa** vê o conteúdo da rota no lugar
  do conteúdo do ponto (sem áudio na rota, não toca o do ponto). Fora dela, ou
  em outra rota, vale o conteúdo normal. A posição e as insígnias são sempre
  as do ponto.
- Detalhes da rota e o próximo ponto da rota ativa usam o nome e a foto da rota.
- Ponto que sai da rota perde o conteúdo nela; excluir a rota apaga os arquivos.
- **App:** a tela do ponto mostra "Na rota X".
- Onde: `model/route_point_content.py`, `route_point_content_service.py`,
  `admin_route_point_content_controller.py`.
- Testes: `test_conteudo_do_ponto_na_rota.py`; app `mupi_content_test.dart`, `mupi_view_test.dart`.

## Futuro

### ROT-13 — Rota de estabelecimento parceiro e filtros [Futuro] 💡
- Rota ligada a um estabelecimento; filtros por tema, dificuldade e distância.
