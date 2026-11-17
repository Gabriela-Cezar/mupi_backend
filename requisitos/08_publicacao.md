# 08 — Publicação (`PUB`)

Produção, identidade do app, lojas e beta. Quase tudo aqui depende de contas,
decisões ou arquivos de fora do código.

---

## Servidor

### PUB-01 — Produção na AWS [Lançamento] ⬜
- Região São Paulo: **Lightsail** com a API em contêiner atrás de um proxy com
  HTTPS (Caddy ou Nginx + Let's Encrypt), **banco PostgreSQL gerenciado** sem
  acesso público (backups automáticos de 7 dias) e **bucket S3 de produção**
  (`infra/aws/`).
- `.env` de produção: `SECRET_KEY` própria, sem `API_DOCS`, `CORS` vazio,
  `GOOGLE_CLIENT_IDS`, bucket de produção; **um processo** da API (INF-04).
- Depois de subir: `alembic upgrade head`, `create_admin` para os 3
  administradores, `check_storage` e o teste de restauração (INF-06).
- Escrever o passo a passo da implantação (README de produção).
- Segurança da conta: MFA no usuário raiz, alerta de custos, usuário IAM próprio.

### PUB-02 — Domínio e e-mail [Lançamento] ⬜
- Domínio da API (ex.: `api.mupi.com.br`) e do painel.
- Domínio remetente verificado no Resend (SPF e DKIM), para os códigos não
  caírem no spam.

### PUB-03 — Mapas em produção [Lançamento] ⬜
- O app usa os servidores públicos do OpenStreetMap, que **não permitem uso
  por apps em produção** com muitos usuários. Escolher um provedor de mapas
  (vários têm plano gratuito) e trocar o endereço dos mapas, mantendo a
  atribuição.

### PUB-04 — Google Cloud [Lançamento] ⬜
- Projeto, tela de consentimento OAuth e Client IDs: web, Android (SHA-1 de
  debug e do certificado de release/Play App Signing) e iOS. Os IDs vão para
  `GOOGLE_CLIENT_IDS` no backend e para o `--dart-define` do app (CON-03).

## App

### PUB-05 — Identidade do app [Lançamento] ⬜
- Nome que aparece no celular (hoje "mupi").
- **Identificador definitivo** (hoje `com.example.mupi`, que as lojas não
  aceitam), por exemplo `br.com.mupi.app`. **Não muda depois de publicado.**
- Ícone (imagem de 1024×1024) e tela de abertura, no Android e no iOS.
- Versão `1.0.0+N`, aumentando o N a cada envio às lojas.

### PUB-06 — Versão das lojas apontando para a produção [Lançamento] ⬜
- Compilar com `--dart-define=API_BASE_URL=https://...` (e os Client IDs do
  Google). Sem isso, o app tenta o computador local.
- Tirar `usesCleartextTraffic="true"` da versão de release do Android (deixar
  só na de desenvolvimento), para só aceitar HTTPS.

### PUB-07 — Política de privacidade e exclusão de conta pela web [Lançamento] ⬜
- Política publicada num endereço, dizendo o que é coletado: e-mail, conta
  Google (identificador e e-mail), **posição e precisão do GPS na primeira
  abertura de cada ponto**, visitas, insígnias e rotas; para quê; por quanto
  tempo; como excluir.
- O **Google Play exige também um link na web** para pedir a exclusão da conta
  (além da exclusão no app, CON-08). Pode ser uma página simples explicando o
  caminho no app e um contato.
- Formulários de segurança de dados (Google Play) e de privacidade (App Store).

### PUB-08 — Revisão das lojas [Lançamento] ⬜
- As lojas pedem uma **conta de teste** para os revisores.
- **Decidir:** o conteúdo só abre perto do ponto, e os revisores estão longe.
  Opções: um ponto de demonstração com instruções e um vídeo do app em uso;
  ou uma conta de revisão com a distância liberada (exige mudar o backend).

### PUB-09 — Contas de desenvolvedor e assinatura [Lançamento] ⬜
- Contas Google Play e Apple Developer (anual).
- Keystore de release do Android guardado com **backup fora do computador**
  (perder impede atualizar o app) e Play App Signing ligado.
- **Google Play:** conferir se a conta pessoal nova exige **teste fechado com
  12 testadores por 14 dias** antes da produção (contas de organização são
  isentas). Pode afetar a data de lançamento.

## Beta e lançamento

### PUB-10 — Conteúdo real [Lançamento] ⬜
- Administradores cadastram os 40 pontos (textos, fotos, áudios, vídeos),
  os temas, as insígnias e as rotas na produção.

### PUB-11 — Beta com 10 usuários [Lançamento] ⬜
- Data do beta; envio pelo TestFlight e pelo teste fechado do Google Play;
  forma de coletar as observações dos testadores.
- Durante o beta: ajustar a distância (VIS-07), corrigir problemas de GPS,
  rotas e login, e conferir tudo o que está marcado como 📱.

### PUB-12 — Lançamento [Lançamento] ⬜
- Janeiro de 2027: publicação nas lojas depois dos ajustes do beta.
