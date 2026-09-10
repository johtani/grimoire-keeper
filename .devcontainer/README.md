# Grimoire Keeper devcontainer

devcontainerでは、VS Code、API、単一のJob Workerを`workspace`コンテナで実行し、
WeaviateだけをDocker Composeの別サービスとして起動します。APIとworkerは同じ
`/workspace/grimoire.db`および`apps/api/data/json`を使用します。

## 初回セットアップ

1. ホストの`~/.config/bws.env`へ`BWS_ACCESS_TOKEN`を保存し、権限を`0600`にします。
2. VS Codeで「Dev Containers: Reopen in Container」を実行します。
3. `.devcontainer/setup.sh`が`uv`、`gh`、`bws`とPython依存関係をインストールします。
4. Weaviateのready状態を確認します。

```bash
curl --fail-with-body http://weaviate:8080/v1/.well-known/ready
```

APIの`8000`番ポートはVS Codeがホストへ転送します。Weaviateはホストのloopbackへ
HTTP `8089`、gRPC `50051`を公開します。ホスト上のOpenAI互換ローカルLLM用の
`8080`番ポートとは競合しません。

## シークレットとローカルLLM

URL処理を行うworkerには`JINA_API_KEY`と`OPENAI_API_KEY`が必要です。クラウドLLMを
使う場合は`LLM_API_KEY`も設定します。値はリポジトリの`.env`へ保存せず、Bitwarden
Secrets Managerまたはターミナルの安全な環境変数注入を使用してください。ホストの
`~/.config/bws.env`はdevcontainer内の同じ場所へread-onlyでマウントされます。

ローカルLLMはホストの`8080`番ポートで起動します。workspaceには次の接続先が設定済みです。

```text
LLM_API_BASE=http://host.docker.internal:8080/v1
```

worker起動前に疎通を確認します。

```bash
curl --fail-with-body http://host.docker.internal:8080/v1/models
```

## APIとworkerの起動

初回だけデータベースを初期化します。

```bash
uv run python scripts/init_database.py init
```

別々のVS CodeターミナルでAPIとworkerを起動します。

```bash
# Terminal 1: API
set -a && source ~/.config/bws.env && set +a
bws run -- bash -c '
  export OPENAI_API_KEY="$GRIMOIRE_KEEPER_OPENAI_API_KEY"
  exec bash scripts/dev.sh
'
```

```bash
# Terminal 2: Job Worker（同じSQLiteに対して必ず1プロセス）
set -a && source ~/.config/bws.env && set +a
bws run -- bash -c '
  export JINA_API_KEY="$GRIMOIRE_KEEPER_JINA_API_KEY"
  export OPENAI_API_KEY="$GRIMOIRE_KEEPER_OPENAI_API_KEY"
  export LLM_API_KEY="${GRIMOIRE_KEEPER_LLM_API_KEY:-dummy}"
  exec uv run --package grimoire-api python -m grimoire_api.worker
'
```

ローカルLLMを使わない場合は、Bitwardenへ`GRIMOIRE_KEEPER_LLM_API_KEY`を登録し、
`LLM_API_BASE`を空にしてworkerを起動してください。Slack Botが必要な場合だけ、別ターミナルで
`uv run --package grimoire-bot python -m grimoire_bot.main`を実行します。

## URL登録から検索までの確認

```bash
curl --fail-with-body http://localhost:8000/api/v1/health/ready

curl --fail-with-body -X POST http://localhost:8000/api/v1/process-url \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com","memo":"devcontainer check"}'

# 返されたpage_idへ置き換え、completedになるまで確認
curl --fail-with-body http://localhost:8000/api/v1/process-status/{page_id}

curl --fail-with-body -X POST http://localhost:8000/api/v1/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"example domain","limit":5}'
```

登録後に`queued`のままなら、workerが起動していること、シークレット、ローカルLLM、
`http://weaviate:8080`への接続を確認してください。

## Weaviate 1.33.1から1.38.8への開発データ移行

この構成は`weaviate_1_38_8_data`という新しいvolumeを使用します。旧構成の
`weaviate_data`は参照も削除もしないため、`docker compose down -v`や手動のvolume削除を
行わない限り保持されます。1.33.1のデータディレクトリを1.38.8へ直接マウントしないでください。

SQLiteと`apps/api/data/json`を正として、Weaviateがreadyになった後に新volumeへ
再インデックスします。実行前にSQLiteとJSONをバックアップしてください。

```bash
uv run python scripts/reindex_weaviate.py --dry-run
uv run python scripts/reindex_weaviate.py
```

再インデックス後、上記のhealth、本文取得、代表的な検索を確認します。旧volumeは確認期間が
終わるまで保持し、削除する場合は`docker volume ls`で正確な名前を確認して別途判断します。

## 構成の確認

ホスト側では次のコマンドで、展開後のサービス、ポート、volumeを確認できます。

```bash
docker compose -f .devcontainer/docker-compose.yml config
docker compose -f .devcontainer/docker-compose.yml ps
curl --fail-with-body http://localhost:8089/v1/.well-known/ready
```
