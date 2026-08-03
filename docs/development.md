# Development

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

1. 現在のAPIコミットとサービス状態を記録します。
2. タイトル、メモ、キーワード、本文検索から代表クエリと結果を保存します。
3. `/opt/grimoire-keeper-data` に、SQLite・Jina JSON・新しいWeaviate索引を保持
   できる空き容量があることを確認します。
4. `~/.config/bws.env` の `BWS_ACCESS_TOKEN` と `.env` を確認します。

代表クエリは `scripts/search_migration_queries.example.json` をコピーして、実データに
合うタイトル、メモ、キーワード、本文の検索語へ変更します。移行前のAPIが稼働して
いる間に検索結果を保存します。

```bash
mkdir -p data/migration
cp scripts/search_migration_queries.example.json \
  data/migration/search_queries.json
uv run python scripts/search_migration_snapshot.py capture \
  --queries data/migration/search_queries.json \
  --label before-1.33.1 \
  --output data/migration/search-before-1.33.1.json
```

クエリファイルには `title_vector`、`memo_vector`、`content_vector` のベクトル検索と、
キーワード検索を複数指定できます。必要に応じてベクトル検索へ `filters` や
`exclude_keywords` も指定できます。スナップショットにはAPIレスポンスをそのまま
保存するため、URL、順位、スコア、タイトルなどを後から確認できます。

再インデックス対象だけを確認する場合は次を実行します。このコマンドはWeaviateを
変更しません。

```bash
uv run python scripts/reindex_weaviate.py --dry-run
```

### 新環境の構築と再インデックス

リポジトリルートで次を実行します。

```bash
bash scripts/migrate_weaviate_1_38.sh
```

このスクリプトは次の順序で処理します。

1. 稼働中APIのコミットをロールバック情報として記録する。
2. 旧サービスを停止する。
3. SQLiteとJina JSONを `/opt/grimoire-keeper-data/backups` へ保存する。
4. `/opt/grimoire-keeper-data/weaviate-1.38.8` を新規データパスとして
   Weaviate `1.38.8` だけを起動する。
5. SQLiteとJina JSONから新しい2コレクションへ再インデックスする。
6. 成功済みSQLiteページ数と `GrimoirePage` 件数が一致し、本文チャンクが作成
   されていることを検証する。
7. 検証済みマーカー `.grimoire-migration-ready` を作成する。

Jina APIやLLMは再実行しません。ページの `status` と `last_success_step` も変更
しません。個別ページの失敗または件数不一致があれば、スクリプトは非0で終了し、
APIへの切り替えは行いません。

### 検証

readinessとコレクション件数を再確認できます。

```bash
curl -fsS http://localhost:8089/v1/.well-known/ready
bws run -- docker compose -f docker-compose.prod.yml run --rm --no-deps api \
  uv run python ../../scripts/check_weaviate_migration.py
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

uv run python scripts/search_migration_snapshot.py capture \
  --queries data/migration/search_queries.json \
  --label after-1.38.8 \
  --output data/migration/search-after-1.38.8.json

uv run python scripts/search_migration_snapshot.py compare \
  --before data/migration/search-before-1.33.1.json \
  --after data/migration/search-after-1.38.8.json \
  --output data/migration/search-comparison.json \
  --fail-below-overlap 0.8
```

比較結果にはクエリごとの欠落・追加、順位変動、上位結果の重複率を出力します。
`--fail-below-overlap` を指定すると、いずれかのクエリが指定した重複率を下回った場合
に非0で終了します。閾値は移行前の結果を確認して決め、機械判定だけでなく結果内容も
確認してください。比較が不合格の場合は検証用APIを停止し、`scripts/deploy.sh` は
実行しません。

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
