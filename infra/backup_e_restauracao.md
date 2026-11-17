# Backup e restauração do banco (INF-06)

O backup só vale se a restauração funcionar. Teste uma vez antes do beta e
de novo depois de mudanças grandes no banco.

A conferência é sempre a mesma: restaurar num banco **novo e separado** e
comparar com a origem:

```
python -m app.scripts.check_restore --restored postgresql://USUARIO:SENHA@HOST:5432/BANCO_RESTAURADO
```

Ela compara a versão das migrações, as tabelas e as linhas de cada tabela
com o banco do `.env` (ou com `--source URL`). Só lê; não altera nada.
Linhas a mais na origem são normais se houve uso depois do backup; tabela
faltando ou versão diferente indicam backup incompleto.

Os arquivos (fotos, áudios, imagens) não estão no banco: ficam no S3, com
versionamento (ver `infra/aws/README.md`).

## No computador (PostgreSQL local)

1. Backup no formato do `pg_restore` (`-Fc`, compactado):
   ```
   pg_dump -h localhost -U mupi_user -Fc --no-owner -f backup_AAAA-MM-DD.dump mupi
   ```
2. Banco vazio para a restauração (uma vez; precisa do usuário administrador
   do PostgreSQL, pois o `mupi_user` não cria bancos):
   ```
   sudo -u postgres createdb -O mupi_user mupi_restauracao
   ```
3. Restaurar:
   ```
   pg_restore -h localhost -U mupi_user --no-owner -d mupi_restauracao backup_AAAA-MM-DD.dump
   ```
4. Conferir:
   ```
   python -m app.scripts.check_restore --restored postgresql://mupi_user:SENHA@localhost:5432/mupi_restauracao
   ```
5. Apagar o banco de teste:
   ```
   sudo -u postgres dropdb mupi_restauracao
   ```

Para voltar o banco de desenvolvimento a um backup (desfazer um erro), o
mesmo `pg_restore` com `--clean --if-exists -d mupi` substitui o conteúdo.
**Cuidado:** apaga o que foi feito depois do backup.

## Na AWS (banco gerenciado)

Configuração (uma vez, ao criar o banco):
- **Lightsail Managed Database:** os backups automáticos ficam ligados
  (padrão), guardados por 7 dias.
- **RDS:** *Backup retention period* de pelo menos **7 dias**.

Teste de restauração (antes do beta):
1. Criar um banco **novo** a partir do backup, sem tocar no de produção:
   - Lightsail: banco → **Snapshots e backups** → *Create new database*
     a partir de um ponto no tempo;
   - RDS: banco → **Actions** → *Restore to point in time* → novo
     identificador (ex.: `mupi-restauracao`), mesma VPC, sem acesso público.
2. Na instância da API (a única com acesso aos bancos), rodar a
   conferência com o endereço do banco restaurado:
   ```
   python -m app.scripts.check_restore --restored postgresql://USUARIO:SENHA@ENDERECO-RESTAURADO:5432/mupi
   ```
3. Anotar a data e o resultado abaixo e **apagar o banco restaurado**
   (ele é cobrado enquanto existir).

## Registro dos testes

| Data | Onde | Backup | Resultado |
|---|---|---|---|
| 17/11/2026 | Local | `backup_teste_restauracao_2026-11-17.dump` (migração 0017, 21 tabelas) | Arquivo conferido com `pg_restore --list`; restauração pendente do banco de teste (passo 2) |
