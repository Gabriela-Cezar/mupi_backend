# 03 — Pontos MUPI e conteúdo

Um ponto MUPI é um local físico específico (uma fachada, uma escultura, um estabelecimento), com conteúdo que só é liberado quando o usuário está próximo e abre o ponto no app.

---

## Modelo do ponto

### PT-01 — Dados do ponto [MVP]
| Campo | Tipo | Obrigatório | Observação |
|---|---|---|---|
| nome | texto (até 150) | sim | |
| latitude / longitude | número | sim | validação de faixa já existe |
| ativo | sim/não | sim | ponto inativo não aparece no app |
| existe individualmente | sim/não | sim (padrão: sim) | se "não", o ponto só aparece dentro de rotas (ver PT-09) |
| temas | lista | não | um ponto pode ter vários temas (PT-03) |
| foto | arquivo | ver PT-05 | uma única |
| áudio | arquivo | não | no máximo um (PT-06) |
| vídeos | lista de links do YouTube | não | PT-07 |
| blocos de texto | lista ordenada | não | PT-04 |
| endereço | texto (até 300) | não | PT-08 |
| horário de funcionamento | texto livre | não | PT-08 |
| informações de acessibilidade | texto livre | não | PT-08 |
| criado em / atualizado em | data | automático | já existe |

- O campo atual `description` é substituído pelos blocos de texto (migrar o conteúdo existente para um bloco, se houver).

### PT-02 — Temas [MVP]
- Tema: nome (único, até 100) e descrição opcional — já existe.
- Usados para agrupar pontos, classificar rotas e definir insígnias "visitar N pontos do tema".

### PT-03 — Vários temas por ponto [MVP]
- Nova tabela de ligação `mupi_object_themes` (ponto, tema).
- Remover a coluna `mupi_objects.theme_id` (migrar o valor existente, se houver, para a nova tabela).
- Excluir um tema remove apenas as ligações; os pontos continuam. Excluir tema usado por insígnia ou rota é bloqueado (ver `07`).

### PT-04 — Blocos de texto [MVP]
- Nova tabela `mupi_object_sections`: ponto, posição (ordem), título, texto.
- **Título:** texto livre escolhido pelo administrador, obrigatório, até 150 caracteres. O app exibe em negrito.
- **Texto:** texto simples com parágrafos (quebras de linha preservadas), sem limite prático (até ~20.000 caracteres).
- O administrador pode adicionar, editar, remover e reordenar blocos.
- A API devolve os blocos já ordenados, com título e texto separados (o app decide a formatação).
- **Leitura em voz alta (acessibilidade):** feita no próprio celular com o recurso de texto para fala do Flutter (ex.: pacote `flutter_tts`, voz em português). O backend não gera áudio; apenas entrega o texto limpo, sem marcações. O app deve permitir ouvir cada bloco (lendo título + texto) e, de preferência, todos em sequência.

### PT-05 — Foto [MVP]
- Uma foto por ponto, sem legenda e sem autor.
- Formatos: PNG, JPEG ou WebP, até 5 MB (validação pelo conteúdo do arquivo já existe).
- **Sugestão:** obrigatória para ativar o ponto, porque aparece no mapa. Se o administrador não enviar, o app mostra uma imagem padrão.
- Substituir a foto apaga a anterior.
- **Visível de longe:** a foto aparece no mapa mesmo quando o usuário está longe.
- **[DESEJÁVEL]** gerar uma versão reduzida (miniatura ~400 px) para o mapa e a lista, poupando dados móveis.

### PT-06 — Áudio [MVP]
- No máximo um áudio por ponto, opcional (a maioria dos pontos não terá).
- Formatos: MP3 ou M4A/AAC. Tamanho máximo: 20 MB (cobre ~10 min com folga).
- Verificar o formato pelo conteúdo do arquivo, como já é feito com imagens.
- O usuário inicia a reprodução (não toca sozinho). Não há transcrição.
- O arquivo deve ser servido com suporte a requisições parciais (cabeçalho `Range`), para o player do app começar a tocar sem baixar tudo e permitir avançar/voltar.
- Guardar a duração em segundos, se possível, para o app exibir antes de tocar.
- Armazenamento: ver `08_infraestrutura.md`, INF-04.

### PT-07 — Vídeos do YouTube [MVP]
- Lista ordenada de links, opcional.
- Aceitar apenas links do YouTube (`youtube.com/watch?v=`, `youtu.be/`, `youtube.com/shorts/`). O backend extrai e guarda o **ID do vídeo** e devolve ao app um formato único.
- Título opcional por vídeo (até 150 caracteres).
- Os vídeos ficam na conta do YouTube do projeto; o app só os exibe (ex.: `youtube_player_flutter`).
- Recomendação: publicar os vídeos como "não listado" ou "público" — vídeos "privados" não tocam no app.

### PT-08 — Informações de estabelecimento [MVP]
- Endereço, horário de funcionamento e acessibilidade são campos de texto do próprio ponto, opcionais, preenchidos quando o ponto é um estabelecimento parceiro (ou sempre que fizer sentido).
- Fazem parte do conteúdo liberado ao abrir o ponto. **Sugestão:** o endereço pode aparecer também no resumo do mapa, para ajudar o usuário a chegar.
- **[FUTURO]** cadastro próprio de estabelecimento parceiro (contato, site, logotipo) que possa ser ligado a pontos e também a rotas.

### PT-09 — Pontos que existem só dentro de rotas [MVP]
- Se "existe individualmente" = não:
  - o ponto **não aparece** no mapa geral, na busca nem nos pontos próximos;
  - só pode ser aberto por quem está com uma **rota ativa que contém o ponto** (ver `05_rotas.md`);
  - a visita a ele conta normalmente para as insígnias.

## API do app

Todas as rotas exigem login (USR-10) e só consideram pontos ativos.

### PT-10 — Mapa (resumo dos pontos) [MVP]
- `GET /mupi-objects` — pontos ativos que existem individualmente.
- Devolve apenas o resumo: id, nome, latitude, longitude, endereço da foto (e miniatura), temas (id e nome), se o usuário já visitou, se o ponto tem áudio/vídeo (para ícones), endereço (opcional, ver PT-08).
- **Não devolve** blocos de texto, áudio, vídeos nem informações de estabelecimento.
- 40 pontos no início: pode devolver todos de uma vez, sem paginação.

### PT-11 — Pontos próximos e busca [MVP]
- Manter `GET /mupi-objects/nearby` e `GET /mupi-objects/search`, devolvendo o mesmo resumo do PT-10, com a distância.
- Mesmo filtro: só pontos que existem individualmente.

### PT-12 — Rota a pé até um ponto [MVP]
- Manter `GET /mupi-objects/{id}/route` (posição do usuário → ponto), que já usa o OpenRouteService.
- Para ponto que só existe em rota, permitir apenas se a rota ativa do usuário o contém.

### PT-13 — Conteúdo completo do ponto [MVP]
- O conteúdo só é entregue na abertura do ponto com validação de proximidade, que também registra a visita. Ver `04_visitas.md`, VIS-01.
- Conteúdo devolvido: dados do resumo + blocos de texto ordenados + endereço do áudio (e duração) + vídeos + endereço, horário, acessibilidade + insígnias ganhas naquela abertura.

### PT-14 — Arquivos de mídia [MVP]
- A foto pode ser acessada a qualquer momento por usuário logado (é exibida no mapa).
- O áudio só é obtido depois que o ponto foi aberto: a abertura (VIS-01) devolve um link temporário assinado do S3, válido por ~1 h (ver INF-04).
- Foto, capa de rota e imagem de insígnia também são entregues por link assinado do S3, com validade longa.
- Remover as rotas antigas `/mupi-objects/{id}/image` e `/mupi-objects/media/{id}` depois que o app migrar.

## Futuro

### PT-15 — Outros tipos de conteúdo [FUTURO]
- O modelo deve permitir novos tipos de mídia sem reestruturar o ponto (ex.: galeria, realidade aumentada, links externos).

### PT-16 — Outros idiomas [FUTURO]
- Por enquanto só português. Se houver tradução no futuro, os textos (blocos, nome, campos de estabelecimento) precisarão de versões por idioma.
