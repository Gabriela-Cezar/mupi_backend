# 01 — Contas e acesso (`CON`)

Cadastro, login por e-mail e pelo Google, sessão, recuperação de senha,
saída e exclusão de conta. O app exige login para tudo.

---

### CON-01 — Cadastro com verificação do e-mail [Lançamento] ✅
- O usuário informa e-mail e senha (8 a 128 caracteres). O backend envia um
  **código de 6 dígitos** por e-mail; a conta só é criada quando o código é
  confirmado (`POST /auth/register` → `POST /auth/verify-email`).
- O código vale **10 minutos** e aceita **5 tentativas**; é guardado como hash.
- "Reenviar código" (`POST /auth/resend-verification`) só depois de **60 s**
  por e-mail; até **10 envios por IP a cada 15 min** (429 com a espera).
- E-mail já cadastrado: "E-mail já cadastrado". Conta criada pelo Google
  usa a recuperação de senha para ter senha (CON-05).
- **App:** telas "Primeiro acesso" e "Verificação do e-mail", com validação
  do e-mail e da senha antes de enviar e contagem regressiva do reenvio.
- Onde: `auth_controller.py`, `auth_user_email_service.py`, `email_service.py`;
  app `first_access_view.dart`, `logup_email_verification_view.dart`.
- Testes: `test_codigos_no_banco.py`, `test_renovar_codigo.py`, `test_resend_verification.py`, `test_email_rate_limit.py`; app `auth_service_test.dart`.

### CON-02 — Login com e-mail e senha [Lançamento] ✅
- `POST /auth/login` devolve o token de sessão (`access_token`), `user_id` e `email`.
- Mensagem igual para e-mail inexistente e senha errada; tempo de resposta
  igual nos dois casos (hash fictício).
- Limite de falhas: **5 por IP + e-mail** e **20 por IP** a cada 15 min (429).
  Login certo zera as falhas daquele e-mail.
- Conta desativada não entra.
- **App:** tela de login com preenchimento automático do sistema (salvar
  senha), botões "Primeiro acesso" e "Recuperar senha".
- Onde: `auth_controller.py`, `auth_service.py`; app `login_view.dart`, `auth_service.dart`.
- Testes: `test_login_rate_limit.py`; app `auth_service_test.dart`.

### CON-03 — Entrar com Google [Lançamento] 🟡
- `POST /auth/google` com o `id_token` do Google. O backend confere a
  assinatura, o emissor, o Client ID (`GOOGLE_CLIENT_IDS`) e se o e-mail é
  verificado. Então: entra na conta já ligada ao Google, **liga** a conta de
  mesmo e-mail ou **cria** uma conta sem senha.
- 503 se o Google estiver desligado no servidor; 401 com token inválido; 403
  com conta desativada. Mesmo limite por IP do login.
- **App:** botão "Entrar com Google" no login (no navegador, o botão do
  próprio Google). Client IDs por `--dart-define` (`GOOGLE_WEB_CLIENT_ID`,
  `GOOGLE_IOS_CLIENT_ID`); sem eles o botão não aparece. "Sair" também sai
  da conta Google.
- **Falta:** criar o projeto e os Client IDs no Google Cloud (web, Android com
  SHA-1 de debug e de release, iOS) e testar com contas reais (PUB-04).
- Onde: `google_auth_service.py`, `auth_controller.py`; app `lib/service/google/`,
  `lib/view/widgets/google/`.
- Testes: `test_login_com_google.py`; app `google_login_test.dart`.

### CON-04 — Sessão de 30 dias, renovada ao abrir o app [Lançamento] ✅
- O token vale **30 dias**. O app chama `POST /auth/refresh` ao abrir e recebe
  um token novo: quem usa o app ao menos uma vez por mês não precisa entrar
  de novo. Até 30 renovações por usuário por hora.
- O token deixa de valer ao trocar a senha, ao excluir a conta e em "sair de
  todos os aparelhos" (versão do token no usuário).
- **App:** guarda o token no armazenamento seguro do sistema. Ao abrir, uma
  tela de espera renova a sessão (até 5 s; sem internet, entra com o token
  guardado). Qualquer 401 de uma chamada com token leva ao login com
  "Sua sessão expirou. Entre novamente." e limpa os dados do usuário em memória.
- Onde: `security.py`, `dependencies.py`; app `session.dart`, `session_start.dart`,
  `session_expiry.dart`, `session_gate.dart`.
- Testes: `test_renovar_sessao.py`, `test_versao_da_sessao.py`; app `session_start_test.dart`, `session_expiry_test.dart`, `session_gate_test.dart`, `api_client_test.dart`.

### CON-05 — Recuperar ou criar senha [Lançamento] ✅
- `POST /auth/recovery-password` envia um código (mesmas regras do CON-01) e
  sempre responde "Se o e-mail estiver cadastrado, você receberá um código"
  (não revela se a conta existe).
- `POST /auth/verify-recovery-code` troca o código por uma autorização de
  **10 minutos**; `POST /auth/reset-password` grava a senha nova e encerra as
  sessões abertas.
- Em conta que só entra com o Google, o mesmo caminho **cria** uma senha;
  depois a pessoa entra dos dois jeitos.
- **App:** telas "Recuperar senha" (com o texto explicando os dois casos) e
  "Nova senha", com mostrar/ocultar senha.
- Onde: `auth_controller.py`; app `recovery_password_view.dart`, `change_password_view.dart`.
- Testes: `test_codigos_no_banco.py`, `test_versao_da_sessao.py`.

### CON-06 — Sair [Lançamento] ✅
- **App:** "Sair" no perfil, com confirmação. Apaga o token do
  aparelho, a rota ativa em memória e a conta Google escolhida.
- Onde: app `logout_button.dart`.
- Testes: app `logout_button_test.dart`.

### CON-07 — Sair de todos os aparelhos [Desejável] 🟡
- `POST /users/me/logout-all` invalida todos os tokens do usuário.
- **Falta:** botão no app (por exemplo no perfil, com confirmação).
- Onde: `user_controller.py`.

### CON-08 — Excluir a conta [Lançamento] ✅
- `DELETE /users/me` com `{password}` ou com um `id_token` do Google de no
  máximo **10 minutos** e da mesma conta. Senha errada: **403** (não 401, para
  o app não tratar como sessão expirada). **5 tentativas a cada 15 min** por conta.
- Apaga o usuário, visitas, insígnias, rota ativa, conclusões e códigos de
  e-mail. Pontos, insígnias e rotas cadastrados continuam.
- O perfil informa `has_password` e `google_linked` para o app saber como pedir
  a confirmação.
- **App:** "Excluir minha conta" no perfil: pede a senha, ou "Confirmar com o
  Google" (conta só Google), ou os dois (conta ligada). Sem o Google no
  aparelho, a conta só Google é orientada a criar uma senha. Ao terminar, volta
  ao login com "Sua conta foi excluída."
- Onde: `user_controller.py`; app `delete_account_view.dart`.
- Testes: `test_perfil_e_conta.py`, `test_login_com_google.py`; app `delete_account_view_test.dart`, `google_login_test.dart`.

### CON-09 — Entrar com a Apple [Lançamento, se exigido] ⬜
- A App Store costuma exigir "Entrar com a Apple" quando o app oferece login
  com Google (diretriz 4.8). **Decidir antes de publicar no iOS.**
- Se for feito: `POST /auth/apple` no mesmo modelo do CON-03 (campo
  `apple_sub`) e o botão no app.

### CON-10 — E-mail já cadastrado no cadastro [Desejável] ⬜
- Hoje o cadastro responde "E-mail já cadastrado", o que permite descobrir
  quem tem conta. Alternativa: responder sempre "Código enviado" e mandar ao
  dono do e-mail uma mensagem "você já tem conta". Avaliar se vale a mudança.

### CON-11 — Recuperar senha de administrador [Desejável] 🟡
- Hoje a senha de um administrador é redefinida no servidor com
  `python -m app.scripts.create_admin` (que também encerra as sessões dele).
- **Falta (opcional):** recuperação por e-mail no próprio painel.
