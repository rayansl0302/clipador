# Clip Studio

Plataforma self-hosted para cortar vídeos longos e publicar cortes curtos. O Postiz não faz parte deste código: o envio usa a API pública dele.

## Como rodar

Pré-requisitos: Docker e GNU Make. No Windows, se `make` não existir, instale com administrador (`choco install make -y`) ou use `%LOCALAPPDATA%\Programs\make`.

```bash
make up
make logs
make test
make down
```

- Web: http://localhost:3000 (a home mostra **API ok**)
- API: http://localhost:8000/health
- MinIO: http://localhost:9001 (`clip` / `clipsecret`)

Copie `.env.example` para `.env` só se for mudar algum valor. Sem esse arquivo, o Compose usa os mesmos padrões. As senhas do exemplo são só da máquina local.

Cadastro, login e um projeto novo: abra a web, crie a conta e cole um link ou envie um arquivo. O progresso da lista atualiza sozinho.

O padrão local não usa chave paga. `TRANSCRIBE_PROVIDER=local` transcreve com faster-whisper na CPU (modelo `base` na primeira execução) e `LLM_PROVIDER=heuristic` sugere cortes pela densidade de fala e pela energia do áudio. Groq, OpenAI e Anthropic continuam disponíveis se você quiser mais qualidade: a Groq tem cota gratuita com limite; OpenAI e Anthropic cobram por uso. Sem chave e com `TRANSCRIBE_PROVIDER=groq`, o job falha com mensagem explícita. O pacote `av` fica abaixo da versão 19 porque o faster-whisper 1.2.1 ainda passa `metadata_errors` para `av.open`.

## Variáveis

| Variável | Uso |
|---|---|
| `DATABASE_URL` | Postgres. Aceita `postgres://` e `postgresql://`; a API converte para `postgresql+psycopg://` |
| `REDIS_URL` | Fila RQ |
| `S3_ENDPOINT` | Storage visto pela API e pelo worker |
| `S3_PUBLIC_ENDPOINT` | Host usado na URL assinada de download |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET`, `S3_REGION` | Credenciais do bucket |
| `JWT_SECRET`, `COOKIE_SECURE`, `COOKIE_SAMESITE` | Sessão em cookie httpOnly |
| `ALLOW_SIGNUP` | `false` fecha o cadastro depois da primeira conta |
| `CORS_ORIGINS` | Origem do web, separada por vírgula |
| `API_URL` | URL da API vista pelo servidor Next. Pode ser `host:porta`; a home prefixa `http://` |
| `NEXT_PUBLIC_API_URL` | URL da API no browser, em desenvolvimento |
| `API_PUBLIC_URL` | URL pública da API em produção, lida em tempo de execução |
| `MAX_VIDEO_DURATION_SECONDS`, `MAX_UPLOAD_BYTES` | Limites do vídeo |
| `WORKER_CONCURRENCY` | Processos do worker. Padrão 1 |
| `TRANSCRIBE_PROVIDER` | `local` (padrão, grátis), `groq` ou `openai` |
| `TRANSCRIBE_MAX_BYTES` | Tamanho de cada bloco enviado ao provedor. Padrão 20 MB, abaixo do limite de 25 MB documentado |
| `GROQ_API_KEY`, `GROQ_WHISPER_MODEL` | Groq. Modelo padrão `whisper-large-v3-turbo` |
| `OPENAI_API_KEY`, `OPENAI_WHISPER_MODEL` | OpenAI. Timestamps por palavra só no `whisper-1` |
| `FASTER_WHISPER_MODEL`, `LOCAL_CHUNK_SECONDS` | faster-whisper |
| `LLM_PROVIDER`, `LLM_MODEL`, `ANTHROPIC_API_KEY` | Cortes. Padrão `heuristic`, sem chave. `anthropic` ou `openai` se houver chave |
| `POSTIZ_URL`, `POSTIZ_API_KEY` | Origem do Postiz e a chave. O cliente chama `{POSTIZ_URL}/api/public/v1` |

## Decisões

- Job pesado (download, transcrição, render) só no worker. A requisição só grava o upload no storage e enfileira.
- A transcrição longa é fatiada por tamanho. O tempo de cada palavra recebe o deslocamento do bloco.
- Cortes do modelo passam por validação: 20–60 s, fronteira de frase, sem sobreposição, no máximo 20. Se o modelo falhar, entra a heurística.
- O render é 1080x1920 com corte central, `loudnorm` e legenda ASS. O crop central é o ponto previsto para face tracking.
- Legenda editada que não bate mais com as palavras originais distribui o texto novo ao longo do corte.
- API e worker usam imagens separadas, as duas com FFmpeg, yt-dlp e fonte DejaVu. Migração Alembic roda só no start da API, uma vez por processo.
- Arquivo de trabalho fica em `/tmp/clip-*` e some no `finally`. Um job `cleanup` periódico apaga sobras velhas.
- Remover um projeto exige o texto `eu aceito`. A API apaga o vídeo, o áudio e os MP4s em `projects/{id}/` e, em seguida, o projeto, os cortes, a transcrição e os jobs.
- O Postiz recebe o MP4 por `POST /api/public/v1/upload` (campo `file`) e o agendamento por `POST /api/public/v1/posts`, com `Authorization` igual à chave, sem prefixo Bearer. Canais em `GET /integrations`. Ajustes de TikTok, YouTube e Instagram seguem o schema publicado.

## Testes

`make test` cobre parsing do JSON do modelo, regras de corte, legenda ASS, comandos FFmpeg, senha/JWT e um render curto de 1080x1920 quando o FFmpeg está na imagem.

## Deploy no Render

O plano gratuito dorme ocioso e não serve para este fluxo. O worker começa em `1c-2g` (2 GB). Se o FFmpeg for morto por memória, suba para `2c-4g` no `render.yaml` e sincronize o Blueprint.

1. Conecte o repositório no Render e crie o Blueprint a partir do `render.yaml` da raiz.
2. Preencha no painel as variáveis `sync: false`: chaves de API, `CORS_ORIGINS` (URL do web), `API_PUBLIC_URL` (URL pública da API, com `https://`), credenciais R2 e Postiz.
3. `JWT_SECRET` é gerado pelo Render. Não copie o valor para o Git.
4. O primeiro deploy da API roda `alembic upgrade head` antes do Uvicorn. O worker não migra.
5. Confira `GET /health`, o login e um vídeo curto até o MP4 no R2.

`API_URL` do web aponta para o host interno da API (`hostport`). A página inicial aceita esse valor sem esquema.

Backups do Postgres, conforme a documentação do Render: no banco pago, a página Recovery exporta um backup lógico (retenção de 7 dias; o plano free não gera esse export). Dump manual, com a external database URL:

```bash
pg_dump --dbname="<EXTERNAL_DATABASE_URL>" -n public --no-owner > clip.sql
psql --dbname="<EXTERNAL_DATABASE_URL>" < clip.sql
```

Restaure só em um banco vazio. Para perda recente, a própria documentação recomenda point-in-time recovery no painel, não o dump.

### Postiz no mesmo Blueprint

O serviço `postiz` usa a imagem oficial `ghcr.io/gitroomhq/postiz-app`, empacotada em `infra/postiz/Dockerfile`, com Postgres e Key Value próprios. `STORAGE_PROVIDER=cloudflare` porque o disco do Render some a cada deploy. As variáveis R2 e as URLs (`FRONTEND_URL`, `NEXT_PUBLIC_BACKEND_URL`, `MAIN_URL`) ficam vazias no arquivo para preencher no painel. `NEXT_PUBLIC_BACKEND_URL` é a origem pública com sufixo `/api`.

Dois pontos da imagem foram testados localmente e resolvidos:

- **Porta.** O nginx da imagem fixa a 5000 e o backend lê `PORT`. Com `PORT=10000` (padrão do Render) o proxy `/api/` apontava para 3000 e devolvia 502. O Dockerfile faz o nginx ouvir em `PORT` e devolve o backend à 3000.
- **Temporal.** Desde a v2.12 o backend não sobe sem Temporal (erro `ECONNREFUSED :7233`). O Blueprint inclui o serviço privado `temporal` (`temporalio/auto-setup`, sem Elasticsearch) e dois Postgres (estado e visibility). `SKIP_ADD_CUSTOM_SEARCH_ATTRIBUTES=true` é necessário: sem ele a imagem registra 2 atributos Text e o Postiz estoura o limite de 3 do visibility em SQL. O Dockerfile do Postiz monta `TEMPORAL_ADDRESS=<host do temporal>:7233`.

Ainda não verificado no Render: a conexão do Temporal com o Postgres do Render sem TLS. Se o log do `temporal` reclamar de SSL, acrescente `POSTGRES_TLS_ENABLED=true` e `VISIBILITY_POSTGRES_TLS_ENABLED=true`.

Callbacks OAuth das redes: o Postiz usa `FRONTEND_URL` como base. Cadastre no app de cada rede a URL que o próprio Postiz mostra ao conectar o canal, no domínio final. Não há um path único inventado aqui; a referência é a [documentação de configuração do Postiz](https://docs.postiz.com/self-host/configuration/reference).

## O que este repositório cobre

Fases 0 a 9: esqueleto, conta e projeto, ingestão, transcrição em blocos, sugestão de cortes, editor com atalhos, render 9:16, envio ao Postiz, Blueprint do Render e acabamento (fila de revisão, templates, zip, ajustes, teste do render).
