# 06 — Painel administrativo (`ADM`)

Painel web em `/admin`, servido pelo backend (páginas Jinja2). Todos os
administradores têm o mesmo acesso.

---

### ADM-01 — Login de administrador [Lançamento] ✅
- E-mail e senha; **5 falhas a cada 15 min** por IP + e-mail bloqueiam por um
  tempo. Sessão por cookie de **12 horas** (`HttpOnly`, `Secure`, `SameSite=Lax`).
- Todo envio de formulário exige o token CSRF da sessão.
- Administradores são criados (ou têm a senha redefinida) no servidor com
  `python -m app.scripts.create_admin`.
- Onde: `admin_auth.py`, `admin_auth_controller.py`, `create_admin.py`.
- Testes: `test_admin_auth.py`, `test_admin_service.py`.

### ADM-02 — Padrão das telas [Lançamento] ✅
- Menu: Pontos, Temas, Insígnias, Rotas e E-mail de teste.
- Depois de salvar, volta à lista com uma mensagem fixa (`?msg=`). Com erro,
  mostra o formulário de novo com a mensagem e o que foi digitado.
- Excluir sempre passa por uma tela de confirmação, que diz o que impede a
  exclusão ou o que acontece com ela; quando não pode excluir, oferece desativar.
- Onde: `admin_messages.py`, `templates/admin/`.
- Testes: `test_admin_forms.py`.

### ADM-03 — Pontos [Lançamento] ✅
- Lista com status e número de visitas; cadastro e edição com nome, temas,
  localização, ativo, "só aparece dentro de rotas", blocos de texto
  (adicionar, remover, reordenar), foto, áudio (com player e duração), vídeos
  e informações do local; mostra as insígnias de visita ligadas ao ponto.
- Ativar/desativar (desativar também desativa as rotas do ponto, ROT-03).
- Não exclui ponto já visitado, ligado a insígnia ou em alguma rota.
- Onde: `admin_mupi_object_controller.py`, `mupi_object_form.py`.
- Testes: `test_admin_pontos.py`, `test_cadastro_do_ponto.py`, `test_audio_do_ponto.py`.

### ADM-04 — Temas [Lançamento] ✅
- Cadastro, edição e exclusão (não exclui tema usado por insígnia).
- Testes: `test_admin_themes.py`.

### ADM-05 — Insígnias [Lançamento] ✅
- Formulário muda conforme o tipo (INS-01); imagem; ativar/desativar.
  Insígnia já conquistada não muda de regra nem é excluída (INS-03).
- Onde: `admin_badge_controller.py`, `badge_form.py`.
- Testes: `test_admin_insignias.py`.

### ADM-06 — Rotas [Lançamento] ✅
- Cadastro e edição com os pontos em ordem (adicionar, remover, reordenar),
  capa, temas, dificuldade, classificação e tempo estimado; mapa do trajeto
  (Leaflet) com os pontos numerados; "Recalcular trajeto"; lista do que falta
  para ativar; aviso de quantas pessoas estão fazendo a rota.
- "Conteúdo nesta rota" em cada ponto (ROT-12).
- Onde: `admin_route_controller.py`, `admin_route_point_content_controller.py`.
- Testes: `test_admin_rotas.py`, `test_conteudo_do_ponto_na_rota.py`.

### ADM-07 — E-mail de teste [Lançamento] ✅
- Envia um e-mail de teste pelo Resend, para conferir a configuração. Só
  para administradores logados.
- Testes: `test_email_test.py`.

### ADM-08 — Leaflet sem dependência de CDN [Desejável] ⬜
- O mapa do trajeto no painel carrega o Leaflet de `unpkg.com`. Servir o
  arquivo pelo próprio backend evita que o painel dependa de um site de fora.

### ADM-09 — Estatísticas [Desejável] ⬜
- Página com: usuários cadastrados e ativos, visitas por ponto e por período,
  rotas iniciadas, abandonadas e concluídas (de `route_events`), insígnias
  mais conquistadas.

### ADM-10 — Níveis de acesso e registro de alterações [Futuro] 💡
- Perfis com permissões diferentes; histórico de quem alterou o quê.
