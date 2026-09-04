# Development

## API とジョブワーカーの実行モデル

API と永続ジョブワーカーは別プロセスです。開発時はそれぞれ別ターミナルで起動します。

```bash
bash scripts/dev.sh
uv run --package grimoire-api python -m grimoire_api.worker
```

API はジョブを SQLite の `jobs` テーブルへ登録するだけなので複数プロセスで実行できます。
worker は同じ SQLite に対して必ず1プロセスだけ起動してください。本番 Compose でも
`worker` サービスを scale せず、replica 数を1に保ちます。

APIプロセスに必須なのはSQLiteの `DATABASE_PATH` だけです。Jina、LLM、Weaviateが停止中、
または処理用APIキーが未設定でも、URL登録、状態確認、リトライ受付は利用できます。登録済みの
ジョブはSQLiteに保持され、必要な外部サービスを設定したworkerが復旧した後に処理されます。
検索などWeaviateを直接利用するAPIは、Weaviate停止中は縮退応答または503を返します。

### URL 処理メトリクス

URL 処理では受付、attempt、logical job completion を別の計測単位として扱います。
`job_id` と `attempt` は重複防止の実行境界に使いますが、高カーディナリティを避けるため
metric label には含めません。

| metric 名 | 種類 | 1カウント／計測の単位 | label |
| --- | --- | --- | --- |
| `url_processing_api_requests_total` | counter | `POST /process-url` の受付1回 | `outcome`: `queued` / `duplicate` / `failed`、`has_memo`: boolean |
| `url_processing_api_duration_seconds` | histogram | API受付の開始から応答生成まで | API counter と同じ |
| `url_processing_job_attempts_total` | counter | claim された attempt の終端状態遷移1回 | `outcome`: `succeeded` / `failed` / `interrupted`、`job_kind`: `initial` / `retry` / `reprocess` |
| `url_processing_job_attempt_duration_seconds` | histogram | Worker が attempt を開始してから終端状態へ更新するまで | attempt counter と同じ |
| `url_processing_job_completions_total` | counter | logical job (`jobs.id`) の終端状態遷移1回 | attempt counter と同じ |
| `url_processing_job_duration_seconds` | histogram | logical job の登録から終端状態への更新まで | attempt counter と同じ |

重複URLの受付は `outcome=duplicate` の API メトリクスだけを記録し、job メトリクスは
増加しません。リトライは新しい logical job として登録され、`job_kind=retry` で初回処理と
区別します。同一ジョブの終端更新が再度呼ばれた場合は状態遷移を成立させず、attempt と
completion のどちらも再計上しません。
Worker 再起動時に回収した running attempt は `outcome=interrupted` として一度だけ記録し、
同じ `job_id` を再claimした実行は新しい attempt として数えます。この時点では logical job が
終端状態ではないため completion は増加しません。

## Web UI と CORS

同梱の Web UI は nginx の `/api/` リバースプロキシを通して API にアクセスする
同一オリジン構成です。FastAPI と nginx は CORS レスポンスヘッダーを付与せず、
別オリジンで配信される Web UI から API ポートへ直接アクセスする構成は許可しません。

将来、外部オリジンからのブラウザアクセスが必要になった場合は、ワイルドカードではなく
必要なオリジン、メソッド、ヘッダーを明示した許可リストを設計してください。
認証情報の許可は実際に Cookie などを使用する場合に限ります。CORS はブラウザの制約であり、
非ブラウザクライアントから API へのアクセスを防ぐものではないため、API ポートの公開範囲は
ネットワーク側でも制限してください。

### 本番 Compose の公開範囲と脅威モデル

`docker-compose.prod.yml` がホストへ公開する Web (`8001`)、API (`8000`)、
Weaviate HTTP (`8089`) および gRPC (`50051`) は、すべて `127.0.0.1` に bind します。
そのため、管理画面、API、Weaviate へホスト外から直接接続することは想定していません。
Slack Bot はホスト公開ポートを経由せず、Compose 内部ネットワーク上の
`http://api:8000` へ接続します。API と worker も同じ内部ネットワーク上の
`weaviate:8080` へ接続します。

Weaviate は個人利用かつ外部ネットワークから到達不能であることを前提に、匿名アクセスを
有効のまま運用します。loopback は同一ホスト上の別ユーザーやプロセスを隔離しないため、
ホスト自体を信頼できない環境では追加の認証・アクセス制御が必要です。ホスト側の保守・移行
スクリプトは、loopback に限定した HTTP および gRPC ポートを引き続き利用できます。

### 本番 application container の最小権限

API、worker、Bot の production image は固定 UID/GID `10001:10001` の `grimoire`
ユーザーで動作します。Compose 側でも同じ数値 ID を指定し、root filesystem を
read-only、Linux capability をすべて削除、`no-new-privileges` を有効にしています。
Python と worker healthcheck が一時ファイルを作成できる場所は、`noexec`、`nosuid`、
`nodev` を付けた `/tmp` の tmpfs だけです。

永続データの書き込み権限はサービスの責務に合わせて制限します。

- API: URL登録、repair 操作などに必要な `database` は read-write。保存済み本文の
  `json` と repair report の `migration` は read-only
- worker: ジョブ状態、worker lock、SQLite WAL/SHM を置く `database` と、取得本文を
  保存・削除する `json` は read-write
- Bot: 永続 volume なし

`scripts/deploy.sh` は `/opt/grimoire-keeper-data/{database,json,migration}` を作成し、
既存ファイルを含めて `10001:10001`、ディレクトリを `0750` に設定します。これは既存の
root 所有ファイルを non-root container から利用可能にする移行も兼ねます。Weaviate data と
backup の所有権は application container 用 UID へ変更しません。手動でデータを配置する場合も、
起動前に次の所有権を設定してください。

SQLite の移行前バックアップは、`0600` の既存DBも読めるよう `sudo` でコピーし、作成後の
バックアップだけをデプロイ実行ユーザーの所有へ戻します。

```bash
sudo chown -R 10001:10001 \
  /opt/grimoire-keeper-data/database \
  /opt/grimoire-keeper-data/json \
  /opt/grimoire-keeper-data/migration
sudo chmod 0750 \
  /opt/grimoire-keeper-data/database \
  /opt/grimoire-keeper-data/json \
  /opt/grimoire-keeper-data/migration
```

設定の展開結果は `docker compose -f docker-compose.prod.yml config` で確認できます。
実行中の identity は `docker compose -f docker-compose.prod.yml exec api id` などで確認し、
UID が `0` でないことを検証してください。

## LLM の認証設定

要約LLMの認証情報には、プロバイダー共通の `LLM_API_KEY` を使用します。
Bitwarden Secrets Manager には `GRIMOIRE_KEEPER_LLM_API_KEY` という名前で登録し、
本番では `docker-compose.prod.yml` がWorkerへ `LLM_API_KEY` を渡します。開発時のWorkerは、
同じ名前の環境変数を設定したシェルから起動してください。`OPENAI_API_KEY` は Weaviate の
埋め込み用であり、要約LLM用とは別です。`scripts/dev.sh` はAPIだけを起動するため、これらの
処理用キーやBitwardenへの接続を必要としません。

ローカルの OpenAI 互換サーバーを使う場合、ホスト上でworkerを直接実行するときは
`LLM_API_BASE=http://localhost:8080/v1` を使用します。Composeのworkerからホスト上の
LLMへ接続するときは、コンテナ自身を指す `localhost` ではなく、次の設定を使用します。

```bash
DOCKER_LLM_API_BASE=http://host.docker.internal:8080/v1
```

この値はmacOSのDocker DesktopとLinuxの両方で利用できます。LinuxではComposeに設定済みの
`extra_hosts: host.docker.internal:host-gateway` が、ホストゲートウェイの名前解決を追加します。
別のホストやポートでLLMを公開する場合は `DOCKER_LLM_API_BASE` をそのURLへ変更してください。
認証不要のサーバーでは `LLM_API_KEY=dummy` を使用できます。

GeminiなどのクラウドLLMを使う場合は、直接実行用とCompose用の接続先を両方空にし、
`LLM_API_KEY` に実際のプロバイダーAPIキーを設定します。

```bash
LLM_API_BASE=
DOCKER_LLM_API_BASE=
```

Composeでは `DOCKER_LLM_API_BASE` が未定義の場合だけ
`http://host.docker.internal:8080/v1` を既定値として使用します。明示的な空値は維持されます。
クラウド構成でキーが空、または `dummy` の場合、workerは起動時に停止します。APIはAI処理用
キーを検証せず、SQLiteを使う受付・参照APIを継続します。

### Docker からローカル LLM へ接続できない場合

まずホスト上でLLMのOpenAI互換エンドポイントへ接続できることを確認します。

```bash
curl --fail-with-body http://localhost:8080/v1/models
```

次にComposeが展開した値と、実行中のworkerが受け取った値を確認します。

```bash
docker compose -f docker-compose.prod.yml config | grep -A1 LLM_API_BASE
docker compose -f docker-compose.prod.yml exec worker \
  python -c 'import os; print(os.environ["LLM_API_BASE"])'
```

workerコンテナ内からも同じエンドポイントへ接続できるか確認できます。

```bash
docker compose -f docker-compose.prod.yml exec worker \
  python -c 'import urllib.request; print(urllib.request.urlopen("http://host.docker.internal:8080/v1/models", timeout=5).status)'
docker compose -f docker-compose.prod.yml logs --tail=100 worker
```

ホスト側の確認だけ成功する場合は、LLMサーバーが `127.0.0.1` のみにbindされていないかを
確認してください。コンテナから接続するには `0.0.0.0` またはDockerブリッジから到達できる
アドレスでlistenする必要があります。外部インターフェースでlistenする場合は、LLMのポートを
信頼できないネットワークへ公開しないようファイアウォールも設定してください。Linuxでは
`docker compose -f docker-compose.prod.yml config` のworkerに `extra_hosts` と
`host-gateway` が含まれることも確認します。

`GOOGLE_API_KEY` は `LLMService` から参照される互換変数ではありません。既存環境で
Googleのキーをこの名前で管理している場合は、同じ値を
`GRIMOIRE_KEEPER_LLM_API_KEY` としてBitwardenへ登録し直してください。

## Weaviate 埋め込みモデルの設定と再インデックス

Weaviate の named vector は、次の非秘密環境変数で固定します。未指定時も同じ既定値が
コードと Compose の両方で使用され、Weaviate module のデフォルトには依存しません。

```bash
WEAVIATE_EMBEDDING_PROVIDER=text2vec-openai
WEAVIATE_EMBEDDING_MODEL=text-embedding-ada-002
WEAVIATE_EMBEDDING_DIMENSIONS=1536
```

`text-embedding-ada-002` の dimensions は 1536 固定です。
`text-embedding-3-small` は最大 1536、`text-embedding-3-large` は最大 3072 で、
3 系モデルでは上限以下の dimensions を指定できます。worker の schema 初期化は
`title_vector`、`memo_vector`、`content_vector` の provider、model、dimensions を
実コレクションと照合し、不一致なら既存ベクトルとの混在を防ぐため失敗します。

モデルまたは dimensions を変更する場合は、全ベクトルの再インデックスが必要です。

1. worker を停止し、SQLite、JSON キャッシュ、Weaviate 永続ボリュームをバックアップする。
2. 新しい `WEAVIATE_EMBEDDING_MODEL` と `WEAVIATE_EMBEDDING_DIMENSIONS` を `.env` に設定する。
3. 再構築対象と修復待ちデータを変更なしで確認する。

   ```bash
   uv run python scripts/reindex_weaviate.py --dry-run \
     --repair-pending-output data/migration/repair-pending.json
   ```

4. Weaviate の `GrimoirePage` と `GrimoireContentChunk` コレクションを削除する。
   SQLite と JSON は削除しない。コレクション削除は検索索引を失う操作なので、バックアップと
   worker の停止を再確認してから実施する。

   ```bash
   curl --fail-with-body -X DELETE http://localhost:8089/v1/schema/GrimoirePage
   curl --fail-with-body -X DELETE \
     http://localhost:8089/v1/schema/GrimoireContentChunk
   ```

5. 新しい設定を反映した環境で全件を再構築する。

   ```bash
   uv run python scripts/reindex_weaviate.py \
     --repair-pending-output data/migration/repair-pending.json
   ```

6. コマンドが `failed=0` で終了したこと、`GET /api/v1/system-info` が各 named vector に
   新しい model と dimensions を返すこと、代表的な検索が成功することを確認して worker を
   再開する。

失敗時は worker を停止したまま、旧設定へ戻して Weaviate 永続ボリュームのバックアップを
復元します。再構築中に SQLite を更新する処理を止めているため、SQLite と JSON の復元は
通常不要ですが、同時に変更した場合は同じバックアップ時点へ揃えて復元してください。

worker は `BEGIN IMMEDIATE` のトランザクションで queued ジョブを原子的に claim します。
停止要求を受けると新規 claim を止め、実行中ジョブを `WEAVIATE_WORKER_STOP_TIMEOUT` 秒まで
待機します。期限を超えた処理はキャンセルされ、`running` のまま残ったジョブは次回の
worker 起動時に `queued` へ戻されます。

worker は起動時に `DATABASE_PATH` の正規化パスへ `.worker.lock` を付けたファイルを使い、
OS の排他ファイルロックを取得します。同じ SQLite と JSON ストレージを扱う二つ目の worker
は、DB 初期化や中断ジョブの復旧を行う前に非0終了します。ロックはファイルの有無ではなく
カーネルが管理するため、worker のクラッシュ後は自動的に解放されます。ロックファイル自体が
残っていても stale lock にはならず、次の worker はそのままロックを再取得できます。

本番 worker は claim loop を supervisor で監視します。停止要求なしに loop が終了した場合は
プロセスを非0終了し、Compose の `restart: unless-stopped` で再起動します。コンテナの
healthcheck は `/tmp/grimoire-worker-health.json` に記録される loop の heartbeat と最終 claim
時刻を参照します。長時間のジョブ処理中も supervisor が heartbeat を更新します。

`recover_running()` は同じデータベースのすべての running ジョブを復旧対象にするため、
worker のローリング更新は行いません。次の順序で入れ替えます。

1. 旧 worker を停止し、コンテナが終了したことを確認する。
2. 新 worker を起動する。
3. ログで中断ジョブの復旧と処理再開を確認する。

worker を複数プロセスへ水平スケールするには、所有 worker ID、lease、有効期限、heartbeat
を導入する別対応が必要です。

### OpenTelemetry と Worker の診断

OpenTelemetry exporter は opt-in です。`OTEL_EXPORTER_OTLP_ENDPOINT` を設定するか、
`OTEL_ENABLED=true` を明示した場合だけ有効になります。どちらも未設定なら provider と
自動計装を作成しないため、collector のない環境で export retry は発生しません。
`OTEL_SDK_DISABLED=true` は他の設定より優先して無効化します。

プロセスはそれぞれ `grimoire-api`、`grimoire-bot`、`grimoire-worker` を
`service.name` に設定し、`service.component` でも識別できます。API は FastAPI、HTTPX、
SQLite、Bot は HTTPX、Worker は HTTPX と SQLite を自動計装します。

Worker は起動、claim、中断ジョブ復旧、pipeline step、完了、heartbeat を構造化ログに記録し、
claim 数、heartbeat 数、step／attempt／logical job の所要時間を metric に記録します。
ログの `page_id` と `job_id` は追跡用途に限り、metric label には使用しません。URL、memo、
検索語、Slack payload は span／ログへ記録せず、HTTPX span の URL 属性も redaction します。

## SQLiteスキーマの変更

SQLiteのスキーマは
`apps/api/src/grimoire_api/repositories/migrations.py` の連番マイグレーションと
`schema_migrations` テーブルで管理します。APIとworkerは起動時に未適用の変更を順番に
実行し、履歴と実スキーマが一致しない場合は起動を中止します。手動DDLや
`schema_migrations` の直接編集は行わないでください。

### 変更手順

1. 既存の `Migration` は変更、並べ替え、削除せず、`MIGRATIONS` の末尾へ新しい連番を
   追加する。一度リリースしたマイグレーションの内容と名前は履歴として不変にする。
2. `LATEST_SCHEMA_VERSION` を新しい番号へ更新する。
3. `_expected_tables()` と、インデックス・外部キーなどの整合性検査を新しい物理
   スキーマに合わせる。
4. DDL、データ変換、`schema_migrations` への履歴追加を同じトランザクション内で完了
   させる。例外を文字列で判定して握りつぶさない。
5. `IF NOT EXISTS` は、履歴のない既知の旧DBに同じオブジェクトが存在し得て、かつ
   移行後に列、一意性、条件などの定義を検証する場合にだけ使用する。
6. SQLiteが直接対応しないカラム削除、型変更、制約変更は、新テーブル作成、データ
   コピー、旧テーブル置換の順で行い、行数と変換後データを検証する。
7. データモデル、リポジトリ、初期化スクリプトも同じPRで更新する。

### 必須テスト

- 空DBが最新版まで移行されること
- 直前バージョンと、引き続き対応する各既知バージョンから移行できること
- 既存データ、外部キー、インデックスが保持されること
- 初期化を再実行しても状態が変わらないこと
- 移行途中の失敗でDDL、データ変更、履歴がすべてロールバックされること
- 未知の構成、破損スキーマ、履歴の飛び番、アプリより新しいバージョンを拒否すること

実装後は通常の必須チェックに加え、次のコマンドでDBの履歴と物理スキーマを確認します。

```bash
uv run python scripts/init_database.py check
```

### デプロイとロールバック

`scripts/deploy.sh` はAPIとworkerを停止した後、新しいイメージの
`migration-status` を読み取り専用で実行します。既存DBに未適用の変更または履歴のない
既知スキーマがある場合だけ、`/opt/grimoire-keeper-data/backups` へSQLiteディレクトリを
自動バックアップします。新規DBと移行済みDBではバックアップを省略し、未知・破損・
将来スキーマではデプロイを中止します。その後、単独プロセスで移行と `check` を完了
してからAPIとworkerを起動します。

スキーマ変更がなくてもバックアップしたい場合は、次のように実行します。

```bash
FORCE_SQLITE_BACKUP=true bash scripts/deploy.sh
```

### Production Docker image の更新

API と Bot の production image は、`uv lock --check` で workspace metadata との
一致を検査したルートの `uv.lock` を使い、`uv sync --frozen --no-dev` で構築します。
Python base image と uv image は tag と
multi-platform digest の両方を `apps/api/Dockerfile.prod` と
`apps/bot/Dockerfile.prod` に記録し、Web の nginx image も
`docker-compose.prod.yml` で同様に固定します。

定期更新または脆弱性対応では、公式 registry で新しい tag と digest を確認し、同じ
PR で該当する参照を更新してください。更新後は通常の必須チェックに加えて、CI の
`Production Image Smoke Tests` で次を確認します。

- API/Bot の両 image が lockfile から build できること
- application package と共有 package を import できること
- pytest、ruff、uv、build cache が runtime image に含まれないこと
- workspace metadata と `uv.lock` が不一致の場合に build が失敗すること

ローカルに Docker がある場合は、CI と同じ build を次のコマンドで先に確認できます。

```bash
docker build -f apps/api/Dockerfile.prod -t grimoire-api:smoke .
docker build -f apps/bot/Dockerfile.prod -t grimoire-bot:smoke .
```

現在の実装はアップグレードのみを提供し、down migrationは提供しません。新しい
スキーマへ移行した後に旧アプリへ戻す場合は、コードだけでなくSQLiteファイルも
自動バックアップから同じ時点へ戻してください。旧アプリが新しいスキーマを読み書き
できるとは仮定しません。

## Weaviate 1.38.8への移行

本番のWeaviateを `1.33.1` から `1.38.8` へ更新します。既存ボリュームの
インプレースアップグレードは行いません。SQLiteと保存済みJina JSONから、空の
`1.38.8` 環境に `GrimoirePage` と `GrimoireContentChunk` を再構築します。

### 互換性

- Weaviate `1.38.8` のリリースノートにbreaking changeはありません。
- `1.34.0` から `1.38.0` までの各minor初回リリースにもbreaking changeは
  ありません。`1.34.0` で既定フィルター戦略がACORNへ変わっているため、移行前後の
  代表検索結果は確認します。
- Weaviate公式対応表に従い、Python clientは `4.22.x` を使用します。
- `1.38.8` では古い形式のバックアップ復元サポートが削除されていますが、本移行は
  バックアップ復元APIを使わず、SQLiteとJina JSONから再インデックスします。
- 旧 `1.33.1` の `/opt/grimoire-keeper-data/weaviate` は変更・削除しません。

参考:

- [Weaviate 1.38.8 release](https://github.com/weaviate/weaviate/releases/tag/v1.38.8)
- [Database and client compatibility](https://docs.weaviate.io/weaviate/release-notes#weaviate-database-and-client-releases)

### 移行前の確認

移行用Pythonコマンドはすべて専用Dockerコンテナ内で実行します。本番サーバーへ
`uv`、Pythonパッケージ、`weaviate-client`をインストールする必要はありません。
ホストにはDocker Compose、`bws`、Git、`.env`、`BWS_ACCESS_TOKEN`が必要です。

最初にツールイメージとクエリファイルを準備します。この操作は稼働中サービスを
停止しません。ビルド後にコンテナ内のPythonと `weaviate-client`をimportできることも
確認します。

```bash
bash tools/weaviate_1_38_migration/run.sh prepare
```

1. 現在のAPIコミットとサービス状態を記録します。
2. タイトル、メモ、キーワード、本文検索から代表クエリと結果を保存します。
3. `/opt/grimoire-keeper-data` に、SQLite・Jina JSON・新しいWeaviate索引を保持
   できる空き容量があることを確認します。
4. `~/.config/bws.env` の `BWS_ACCESS_TOKEN` と `.env` を確認します。

代表クエリは `tools/search_regression/queries.example.json` をコピーして、実データに
合うタイトル、メモ、キーワード、本文の検索語へ変更します。移行前のAPIが稼働して
いる間に検索結果を保存します。

`prepare` が作成した `data/migration/search_queries.json` を編集し、移行前の結果を
保存します。

```bash
bash tools/weaviate_1_38_migration/run.sh capture-before
```

クエリファイルには `title_vector`、`memo_vector`、`content_vector` のベクトル検索と、
キーワード検索を複数指定できます。必要に応じてベクトル検索へ `filters` や
`exclude_keywords` も指定できます。スナップショットにはAPIレスポンスをそのまま
保存するため、URL、順位、スコア、タイトルなどを後から確認できます。プリフライトは
全クエリに1件以上の結果があることも確認するため、空になる検索語は調整してください。

再インデックス対象だけを確認する場合は次を実行します。このコマンドはWeaviateを
変更しません。

```bash
bash tools/weaviate_1_38_migration/run.sh dry-run
```

baseline採取後、サービスを停止する前に読み取り専用のプリフライトチェックを実行
します。環境、旧・新データパス、空き容量、クエリとbaselineの一致、現行サービスの
readinessをまとめて確認します。

```bash
bash tools/weaviate_1_38_migration/run.sh preflight
```

1項目でも失敗した場合は非0で終了します。問題を解消して全項目が `PASS` になるまで、
移行スクリプトは実行しません。チェックはサービスやデータを変更しません。

### 新環境の構築と再インデックス

リポジトリルートで次を実行します。

```bash
bash tools/weaviate_1_38_migration/migrate.sh
```

このスクリプトは次の順序で処理します。

1. 稼働中APIのコミットをロールバック情報として記録する。
2. 旧サービスを停止する。
3. SQLiteとJina JSONを `/opt/grimoire-keeper-data/backups` へ保存する。
4. `/opt/grimoire-keeper-data/weaviate-1.38.8` を新規データパスとして
   Weaviate `1.38.8` だけを起動する。
5. SQLiteとJina JSONから新しい2コレクションへ再インデックスする。
6. 成功済みSQLiteページ数と `GrimoirePage` 件数が一致し、本文チャンクが作成
   されていることを検証する。修復待ちがある場合は、修復待ちを除いた移行対象件数と
   `GrimoirePage`件数を比較する。
7. 検証済みマーカー `.grimoire-migration-ready` を作成する。

バックアップは、APIコンテナがroot所有・`0600`で作成したJSONも読めるよう
`sudo tar`で一時ファイルへ作成します。成功後に実行ユーザーへ所有権を戻してから
正式な `.tar.gz` 名へ変更するため、途中失敗したファイルはバックアップとして扱いません。

Jina APIやLLMは再実行しません。ページの `status` と `last_success_step` も変更
しません。個別ページの失敗または件数不一致があれば、スクリプトは非0で終了し、
APIへの切り替えは行いません。

保存済みJinaレスポンスがHTTP 4xx/5xxを示す場合、本文らしい文字列が含まれていても
エラーページを索引化せず、`preflight`と再インデックスで修復待ちとして検出します。
本文が空、タイトルが空、またはJSONが壊れている場合も同様です。

ただし移行全体は停止せず、これらを修復待ちとして再インデックスから除外し、
`data/migration/repair-pending.json`へ記録します。SQLiteとJSONは変更しません。
Weaviateや埋め込みAPIの障害は修復待ちにせず、移行を失敗させます。移行後はレポートの
ページをURL修正後にダウンロード工程から再処理します。

### 検証

readinessとコレクション件数を再確認できます。

```bash
curl -fsS http://localhost:8089/v1/.well-known/ready
bash tools/weaviate_1_38_migration/run.sh check-counts
```

移行前に保存した代表クエリを使い、以下を確認します。

- `title_vector` によるタイトル・要約検索
- `memo_vector` によるメモ検索
- キーワード検索
- `content_vector` による本文チャンク検索
- URL、日付、包含・除外キーワードのフィルター

再インデックス後は新しいWeaviateへ接続するAPIだけを検証用に起動し、同じクエリを
保存して移行前後を比較します。Webとbotはまだ起動しません。

```bash
bws run -- docker compose -f docker-compose.prod.yml up -d api

bash tools/weaviate_1_38_migration/run.sh capture-after
bash tools/weaviate_1_38_migration/run.sh compare
```

比較結果にはクエリごとの欠落・追加、順位変動、上位結果の重複率を出力します。
既定では、いずれかのクエリの重複率が `0.8` を下回ると非0で終了します。閾値を変更
する場合は、例えば `SEARCH_OVERLAP_THRESHOLD=0.9 bash .../run.sh compare` のように
指定します。機械判定だけでなく結果内容も確認してください。比較が不合格の場合は
検証用APIを停止し、`scripts/deploy.sh` は実行しません。

```bash
docker compose -f docker-compose.prod.yml stop api
```

### APIの切り替え

件数と代表検索が正常な場合だけ、全サービスを起動します。

```bash
bash scripts/deploy.sh
```

切り替え後にAPI readiness、検索、新規URL処理を確認します。

```bash
curl -fsS http://localhost:8000/api/v1/health
curl -fsS -X POST http://localhost:8000/api/v1/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"確認用クエリ","vector_name":"content_vector","limit":5}'
```

旧Weaviateボリュームは動作確認直後に削除せず、ロールバック期間が終わるまで保持
します。

### ロールバック

移行スクリプトが出力した `.txt` に、旧APIコミット、旧Weaviate image/data path、
SQLite・JSONバックアップの場所が記録されています。ロールバックでは必ず次の3点を
セットで戻します。

復元作業に入る前に、移行スクリプトが表示したロールバック情報ファイルを指定して、
旧APIコミット、旧ボリューム、バックアップアーカイブの内容とSHA-256を読み取り専用で確認
します。

```bash
bash tools/weaviate_1_38_migration/run.sh rollback-check \
  /opt/grimoire-keeper-data/backups/<rollback-info>.txt
```

全項目が `PASS` になるまで復元作業へ進みません。このコマンドはコンテナの停止、
データ復元、Gitのcheckoutを行いません。

1. APIを記録済みの旧コミットへ戻す。
2. SQLiteとJina JSONを移行前バックアップから復元する。
3. Weaviate `1.33.1` を旧 `/opt/grimoire-keeper-data/weaviate` で起動する。

最初に現行サービスを停止し、失敗時のデータを退避します。以下の
`<timestamp>`、`<backup-file>`、`<old-api-commit>` はロールバック情報の値に
置き換えます。

```bash
docker compose -f docker-compose.prod.yml down
sudo mv /opt/grimoire-keeper-data/database \
  /opt/grimoire-keeper-data/database.failed-<timestamp>
sudo mv /opt/grimoire-keeper-data/json \
  /opt/grimoire-keeper-data/json.failed-<timestamp>
sudo tar -xzf <backup-file> -C /opt/grimoire-keeper-data
git checkout <old-api-commit>
export WEAVIATE_IMAGE=cr.weaviate.io/semitechnologies/weaviate:1.33.1
export WEAVIATE_DATA_PATH=/opt/grimoire-keeper-data/weaviate
bash scripts/deploy.sh
```

ロールバック確認後、#154 のブランチへ戻します。旧・新どちらのWeaviateデータも、
削除は別途確認してから行います。

### 移行ツールの保持と削除

移行補助ツールとDocker実行定義は `tools/weaviate_1_38_migration/` にまとめています。
プリフライトとロールバック確認は今回の移行専用です。検索スナップショットは
`tools/search_regression/` にあり、将来のWeaviate更新、埋め込みモデル変更、検索設定
変更にも再利用できます。

旧ボリュームのロールバック保持期間が終わるまではツールと `data/migration/` の結果を
保持します。その後、検索比較を継続利用するか判断し、不要なら専用ディレクトリ、対応
テスト、このドキュメントの移行専用コマンドを同じPRで削除します。詳細は
`tools/weaviate_1_38_migration/README.md` を参照してください。
