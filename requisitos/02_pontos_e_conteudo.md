# 02 — Pontos e conteúdo (`PON`)

O ponto MUPI, seu conteúdo e como ele aparece no app: mapa, busca,
"Como chegar" e a tela do ponto. A abertura e a visita estão em `03_visitas.md`.

---

## Cadastro (backend)

### PON-01 — Ponto MUPI [Lançamento] ✅
- Campos: nome, latitude, longitude, ativo, **existe solto** (`standalone`),
  temas, blocos de texto, foto, áudio, vídeos e informações do local.
- Ponto **desativado** some do app (mapa, busca, abertura e rotas); quem já o
  visitou continua com a visita e as insígnias.
- Ponto **só de rota** (`standalone = false`) não aparece no mapa nem na busca;
  abre só com a rota ativa que o contém (VIS-03).
- Onde: `model/mupi_object.py`, `mupi_object_form.py`.
- Testes: `test_cadastro_do_ponto.py`, `test_admin_pontos.py`.

### PON-02 — Temas [Lançamento] ✅
- Tema: nome único (sem diferenciar maiúsculas) e descrição opcional. Um
  ponto e uma rota podem ter vários temas. Usado também nas insígnias "por tema".
- Onde: `model/theme.py`, `admin_theme_controller.py`.
- Testes: `test_admin_themes.py`.

### PON-03 — Blocos de texto [Lançamento] ✅
- Vários por ponto, na ordem do administrador: título (até 150 caracteres,
  em negrito no app) e texto (até 20.000, com as quebras de linha).
- Onde: `model/mupi_object_section.py`.

### PON-04 — Foto [Lançamento] ✅
- Uma por ponto (PNG, JPEG ou WebP, até 5 MB, tipo conferido pelo conteúdo).
  Aparece no resumo (mapa, busca) mesmo de longe.
- Trocar ou remover a foto apaga o arquivo anterior.
- Testes: `test_imagens_para_o_s3.py`, `test_admin_pontos.py`.

### PON-05 — Miniaturas das fotos [Desejável] ⬜
- Hoje o app baixa a foto inteira e reduz na tela. Gerar uma miniatura no
  envio (ex.: 400 px) e entregá-la no resumo economizaria dados no mapa.

### PON-06 — Áudio [Lançamento] ✅
- No máximo um por ponto, opcional: MP3 ou M4A, até 20 MB (cerca de 10 min).
  O backend confere o formato pelo conteúdo e guarda a duração.
- Entregue só na abertura, com link de 1 hora.
- Testes: `test_audio_do_ponto.py`.

### PON-07 — Vídeos do YouTube [Lançamento] ✅
- Vários por ponto, na ordem do administrador: link (`watch`, `youtu.be`,
  `shorts`), guardado como o ID do vídeo, e título opcional.
- O painel avisa que o vídeo precisa ser público ou não listado e permitir
  incorporação.
- Testes: `test_youtube.py`.

### PON-08 — Informações do local [Lançamento] ✅
- Endereço, horário de funcionamento e acessibilidade, opcionais, para
  estabelecimentos parceiros.

### PON-09 — Arquivos por link temporário [Lançamento] ✅
- Fotos, capas, imagens de insígnia e áudios ficam num bucket S3 **privado**.
  A API entrega **links assinados**: imagens valem **24 h**, áudio **1 h**.
- No desenvolvimento, uma pasta local (`LOCAL_STORAGE_DIR`) com links
  assinados servidos pelo próprio backend (INF-03).
- Onde: `storage_service.py`, `local_files_controller.py`.
- Testes: `test_storage_service.py`, `test_armazenamento_local.py`.

## Lista, busca e "Como chegar" (API)

### PON-10 — Resumo do ponto [Lançamento] ✅
- `GET /mupi-objects` (todos), `/nearby` (num raio) e `/search` (por nome,
  até 50, mais perto primeiro). Exigem login.
- Devolvem só o **resumo**: id, nome, posição, temas, link da foto, se tem
  vídeo, se tem áudio, endereço, **se o usuário já visitou** e a distância
  (nearby e search). O conteúdo só vem na abertura.
- Só pontos ativos e soltos. A busca trata `%` e `_` como texto.
- Onde: `mupi_object_controller.py`, `serializers.py`.
- Testes: `test_mupi_content_access.py`, `test_busca_por_nome.py`.

### PON-11 — "Como chegar" [Lançamento] ✅
- `GET /mupi-objects/{id}/route?latitude=&longitude=`: caminho a pé do
  usuário até o ponto pelo OpenRouteService (distância, duração e coordenadas).
- Sem a chave do OpenRouteService, responde com erro explicando; falha do
  serviço responde 502.

## No app

### PON-12 — Mapa [Lançamento] 📱
- O mapa acompanha a posição do usuário (fica centrado nele) e mostra os
  pontos com a foto; **ponto já visitado** fica mais claro e com um selo.
- A lista é carregada de uma vez (`GET /mupi-objects`), com a distância
  calculada no app; é recarregada **a cada 3 minutos** e ao voltar ao app.
- Tocar num ponto abre o **cartão de resumo** com "Abrir" e "Como chegar".
  O "Abrir" fica ligado só quando o usuário está perto (mesma regra do
  backend, lida de `GET /app-settings`), e o cartão avisa **"Sinal de GPS
  fraco"** com precisão pior que 50 m.
- Sem GPS ou sem permissão: mensagem e botão para abrir as configurações.
- Em segundo plano, o GPS e a recarga param (INF-12).
- Onde: app `map_view.dart`, `mupi_marker.dart`, `mupi_summary_card.dart`.
- Testes: app `mupi_marker_test.dart`, `mupi_summary_card_test.dart`, `map_background_test.dart`.

### PON-13 — Menu e busca [Lançamento] ✅
- Menu lateral do mapa: lista dos pontos do mais perto ao mais longe e os
  botões Buscar, Rotas e Perfil.
- Busca por nome com espera de 400 ms entre as letras digitadas.
- Onde: app `map_menu.dart`, `search_mupi_view.dart`.
- Testes: app `map_menu_test.dart`, `search_mupi_view_test.dart`.

### PON-14 — "Como chegar" no mapa [Lançamento] 📱
- Desenha o caminho até o ponto, apagando o trecho já andado; ao chegar a
  **25 m**, avisa e oferece **"Abrir ponto"**. "Encerrar trajeto" limpa o caminho.
- Onde: app `directions_service.dart`, `arrival_snack_bar.dart`.
- Testes: app `directions_service_test.dart`, `arrival_snack_bar_test.dart`.

### PON-15 — Filtro por tema no mapa [Desejável] ⬜
- Escolher um ou mais temas e ver só os pontos deles no mapa e no menu.

### PON-16 — Tela do ponto [Lançamento] 📱
- Tela inteira, nesta ordem: foto (toque abre em tela cheia com zoom), nome,
  temas, "Na rota X" (quando o conteúdo é o da rota, ROT-12), player do
  áudio, blocos de texto, vídeos, informações do local (o endereço abre o
  mapa do celular) e as insígnias do ponto.
- Texto em tamanho confortável, acompanhando a fonte do celular.
- Onde: app `mupi_view.dart`, `mupi_sections.dart`, `mupi_videos.dart`, `mupi_audio_player.dart`.
- Testes: app `mupi_view_test.dart`, `mupi_sections_test.dart`, `mupi_videos_test.dart`, `mupi_audio_player_test.dart`.

### PON-17 — Leitura em voz alta [Lançamento] 📱
- Botão para ouvir cada bloco ou todos em sequência, com o bloco lido em
  destaque. Usa a voz do sistema em português; sem a voz instalada, avisa.
- Texto longo é dividido em partes (o navegador corta falas longas).
- Onde: app `read_aloud_controller.dart`, `speech_playback.dart`.
- Testes: app `read_aloud_controller_test.dart`, `speech_playback_test.dart`.

### PON-18 — Áudio e vídeo no app [Lançamento] 📱
- Áudio: tocar e pausar, com a barra de tempo para pular a um trecho; toca
  enquanto baixa.
- Vídeo: abre numa janela por cima da tela do ponto, sem sair para o YouTube.
- **Uma mídia por vez:** começar o áudio, a leitura ou um vídeo para o que
  estava tocando; sair da tela para tudo.
- Onde: app `audio_playback.dart`, `video_session.dart`, `media_coordinator.dart`.
- Testes: app `media_coordinator_test.dart`, `mupi_audio_player_test.dart`, `mupi_videos_test.dart`.

## Futuro

### PON-19 — Outros tipos de conteúdo e idiomas [Futuro] 💡
- Galeria de fotos, documentos, outros idiomas.
