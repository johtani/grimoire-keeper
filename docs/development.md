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

worker は `BEGIN IMMEDIATE` のトランザクションで queued ジョブを原子的に claim します。
停止要求を受けると新規 claim を止め、実行中ジョブを `WEAVIATE_WORKER_STOP_TIMEOUT` 秒まで
待機します。期限を超えた処理はキャンセルされ、`running` のまま残ったジョブは次回の
worker 起動時に `queued` へ戻されます。

`recover_running()` は同じデータベースのすべての running ジョブを復旧対象にするため、
worker のローリング更新は行いません。次の順序で入れ替えます。

1. 旧 worker を停止し、コンテナが終了したことを確認する。
2. 新 worker を起動する。
3. ログで中断ジョブの復旧と処理再開を確認する。

worker を複数プロセスへ水平スケールするには、所有 worker ID、lease、有効期限、heartbeat
を導入する別対応が必要です。

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
