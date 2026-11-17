# 09 — Plano: o que falta até o lançamento

Versão de 17/11/2026. Só o que falta; o que já foi feito está nos requisitos
(✅ e 📱). O plano anterior, com o histórico das etapas, está no git.

Meta: **beta com 10 usuários** e **lançamento em janeiro de 2027**.

---

## Etapa A — Ajustes no código que não dependem de nada

- [ ] Remover o pacote `maplibre_gl`, apagar o `.env` antigo do app e trocar a `description` do `pubspec.yaml` (INF-14)
- [ ] Android: aceitar conexão sem HTTPS só na versão de desenvolvimento (PUB-06)
- [ ] [Desejável] Botão "Sair de todos os aparelhos" no perfil (CON-07)
- [ ] [Desejável] Leaflet do painel servido pelo próprio backend (ADM-08)

## Etapa B — Decisões

- [ ] Nome do app no celular, **identificador definitivo** e ícone 1024×1024 (PUB-05)
- [ ] "Entrar com a Apple": fazer ou não (CON-09)
- [ ] Como os revisores das lojas vão abrir um ponto (PUB-08)
- [ ] Provedor de mapas para a produção (PUB-03)
- [ ] [Desejável] Mensagem do cadastro com e-mail já cadastrado (CON-10)

## Etapa C — Contas e serviços externos

- [ ] AWS: MFA, alerta de custos, usuário IAM, bucket de produção (PUB-01)
- [ ] Domínio da API e domínio remetente no Resend com SPF/DKIM (PUB-02)
- [ ] Google Cloud: projeto, consentimento OAuth e Client IDs web, Android e iOS (PUB-04)
- [ ] Contas Google Play e Apple Developer; conferir a regra dos 12 testadores por 14 dias (PUB-09)

## Etapa D — Produção

- [ ] Subir a API, o banco gerenciado e o S3 de produção com HTTPS; README de implantação (PUB-01)
- [ ] Teste de restauração do backup automático da AWS (INF-06)
- [ ] Trocar o provedor de mapas no app (PUB-03)
- [ ] Testar o login com Google com credenciais reais (CON-03)
- [ ] Implementar a decisão da Etapa B sobre a Apple (CON-09) e sobre os revisores (PUB-08), se exigirem código
- [ ] Aplicar nome, identificador, ícone, tela de abertura e versão (PUB-05)

## Etapa E — Conteúdo e lojas

- [ ] Administradores cadastram o conteúdo real dos 40 pontos, rotas e insígnias (PUB-10)
- [ ] Política de privacidade publicada e página de exclusão de conta na web (PUB-07)
- [ ] Keystore com backup, Play App Signing; formulários das lojas; conta de teste (PUB-08, PUB-09)
- [ ] Compilação de release apontando para a produção (PUB-06); envio ao TestFlight e ao teste fechado

## Etapa F — Beta

- [ ] Definir a data e convidar os 10 testadores (PUB-11)
- [ ] Conferir num celular tudo o que está 📱:
  - [ ] mapa, GPS fraco e permissão de localização (PON-12, INF-11)
  - [ ] "Como chegar" e aviso de chegada (PON-14)
  - [ ] abrir ponto perto e longe (VIS-05)
  - [ ] tela do ponto, leitura em voz alta, áudio e vídeo (PON-16 a 18)
  - [ ] fazer uma rota inteira andando (ROT-10)
  - [ ] GPS em segundo plano e consumo de dados (INF-12)
  - [ ] TalkBack, VoiceOver e fonte grande (INF-13)
- [ ] Ajustar a distância com as posições das visitas (VIS-07)
- [ ] Corrigir o que os testadores apontarem
- [ ] [Desejável] Registro de erros no backend e no app (INF-08)

## Etapa G — Lançamento e depois

- [ ] Publicação nas lojas (PUB-12)
- [ ] [Desejável] Miniaturas das fotos (PON-05), filtro por tema (PON-15), seta para o próximo ponto (ROT-11), estatísticas no painel (ADM-09)
- [ ] [Desejável] Contagens dos limites no banco ou Redis, se a API precisar de mais de um processo (INF-04)
- [ ] [Desejável] Recuperação de senha do administrador pelo painel (CON-11)

## Futuro (fora do lançamento)

Outros tipos de conteúdo e idiomas (PON-19), rota de parceiro e filtros
(ROT-13), ranking e notificações (INS-06), níveis de acesso no painel (ADM-10).
