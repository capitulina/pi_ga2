# API de transações de ações

Python 3.12, Flask, PostgreSQL 16, Docker Hub e GitHub Actions.

## Executar com Docker

1. Copie `.env.example` para `.env` (`Copy-Item .env.example .env` no PowerShell).
2. Defina uma senha em `POSTGRES_PASSWORD` e preencha `USERS_API_URL` com a URL do serviço do professor, terminando em `/users`, conforme o enunciado. O endereço não fica fixo no código.
3. Execute:

```sh
docker compose up -d --build --wait
```

A API fica em `http://localhost:8000`. Verifique `GET /health` ou use `docker compose logs -f api` para consultar os logs. `docker compose down` para os containers, preservando os dados. Não use `down -v` se quiser manter o banco.

O PostgreSQL não publica portas para fora da rede Docker. As tabelas são criadas automaticamente antes de iniciar o Gunicorn. O volume `postgres_data` preserva os dados nas atualizações. Para futuras alterações de esquema, use migrações: `create_all` não altera tabelas existentes.

## Rotas

| Método | Rota | Resultado |
| --- | --- | --- |
| GET | `/transacao` | Todas as transações, 200 |
| GET | `/transacao?cliente_id=1` | Transações do cliente, 200; lista vazia se não houver |
| POST | `/transacao` | Cria uma transação, 201 |
| DELETE | `/transacao/1` | Exclui uma transação, 204 sem corpo; 404 se não existir |
| GET | `/health` | 200 com banco acessível; 503 se indisponível |

Exemplo de corpo para POST:

```json
{
  "cliente_id": 1,
  "codigo_acao": "PETR4",
  "quantidade": 3,
  "preco_unitario": "10.15",
  "data_transacao": "2026-09-22"
}
```

Use um ID existente no serviço do professor: consulte `GET {USERS_API_URL}`. A aplicação valida o cliente em `GET {USERS_API_URL}/{cliente_id}` e espera um objeto JSON com `email`. Salva o ID e o e-mail na tabela `transacao`.

Exemplo no PowerShell:

```powershell
$body = @{
    cliente_id = 1
    codigo_acao = 'PETR4'
    quantidade = 3
    preco_unitario = '10.15'
    data_transacao = '2026-09-22'
} | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/transacao -Method Post -ContentType 'application/json' -Body $body
Invoke-RestMethod http://localhost:8000/transacao
Invoke-RestMethod 'http://localhost:8000/transacao?cliente_id=1'
Invoke-RestMethod http://localhost:8000/transacao/1 -Method Delete
```

Resposta de criação:

```json
{
  "id": 1,
  "cliente_id": 1,
  "cliente_email": "cliente@example.com",
  "codigo_acao": "PETR4",
  "quantidade": 3,
  "preco_unitario": "10.15",
  "valor_total": "30.45",
  "data_transacao": "2026-09-22"
}
```

O total é sempre calculado no backend (`quantidade × preco_unitario`). Valores monetários são retornados como strings com duas casas para preservar a precisão. Total e e-mail enviados pelo cliente são ignorados. Quantidade e ID devem ser inteiros positivos; preço deve ser positivo com no máximo duas casas; data deve seguir `AAAA-MM-DD`.

Erros usam JSON com `erro`: dados inválidos retornam 400; cliente inexistente retorna 404; falha ou resposta inesperada do serviço externo retorna 502; timeout retorna 504. JSON exige `Content-Type: application/json` (415 se ausente/incorreto).

## Docker Hub e deploy automático

O workflow `.github/workflows/deploy.yml` executa testes com PostgreSQL em pull requests e pushes. Em pushes para `main` ou `master`, publica as tags `latest` e SHA do commit em `USUARIO/transacoes-api`, depois atualiza um servidor Linux por SSH. O deploy usa a tag do commit e aguarda os healthchecks.

### Preparação do servidor (uma vez)

1. Disponibilize um servidor Linux com Docker Engine e Docker Compose v2 com suporte a `--wait`, SSH e porta 8000 acessível para avaliar a API.
2. O usuário SSH deve ter permissão para usar Docker e gravar em seu diretório pessoal.
3. Crie `~/transacoes-api/.env` com os campos de `.env.example`: senha forte, nome e usuário do banco, URL de usuários e porta da API. Proteja o arquivo com `chmod 600 ~/transacoes-api/.env`. Não o adicione ao Git.
4. Crie o repositório `transacoes-api` no Docker Hub. Se for privado, faça `docker login` no servidor com um token de leitura antes do deploy.
5. Configure uma chave SSH de deploy: pública em `~/.ssh/authorized_keys` do servidor e privada no Secret abaixo. Obtenha a linha de `known_hosts` e confira a impressão digital por um canal confiável antes de salvá-la.

No GitHub, acesse **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Conteúdo |
| --- | --- |
| `DOCKERHUB_USERNAME` | Usuário Docker Hub |
| `DOCKERHUB_TOKEN` | Token Docker Hub com permissão de publicação |
| `SSH_HOST` | IP ou domínio do servidor |
| `SSH_USER` | Usuário SSH |
| `SSH_PORT` | Porta SSH, opcional; padrão 22 |
| `SSH_PRIVATE_KEY` | Chave privada completa de deploy |
| `SSH_KNOWN_HOSTS` | Linha verificada de known_hosts; para porta não padrão, use `[host]:porta` |

Crie também o environment `production` no GitHub. Credenciais do banco e URL externa ficam nas variáveis de ambiente do servidor, carregadas do `.env`; o workflow não as embute na imagem. As credenciais `test` do job de testes são descartáveis e não são usadas em produção.

Após configurar, envie o código para `main` ou `master` e acompanhe a aba **Actions**. É possível executar novamente por **Run workflow**. Sem esses Secrets e o `.env` remoto, publicação/deploy falham; não há credenciais reais incluídas neste projeto.

## Testes

```sh
pip install -r requirements-dev.txt
python -m pytest -q
```

Sem configuração adicional, os testes usam SQLite em memória. Para testar com PostgreSQL, defina `TEST_DATABASE_URL=postgresql+psycopg://usuario:senha@host:5432/banco_testes`. Use um banco exclusivo de testes: as tabelas são removidas entre testes. O GitHub Actions usa PostgreSQL real. A API externa é simulada nos testes para verificar sucesso, cliente inexistente, erros e timeout sem depender da disponibilidade do professor.

Documentação usada: [Flask/Gunicorn](https://flask.palletsprojects.com/en/stable/deploying/gunicorn/) e [Docker no GitHub Actions](https://docs.docker.com/build/ci/github-actions/).
