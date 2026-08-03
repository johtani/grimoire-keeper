# Weaviate 1.38 migration tools

Weaviate `1.33.1` から `1.38.8` への本番移行を補助する一時ツール群です。すべての
確認ツールは、明示したJSONレポート以外のデータやサービスを変更しません。

## ツール

- `preflight.py`: 停止作業前の環境、データ、容量、baseline、readiness確認
- `migrate.sh`: バックアップ、新環境起動、再インデックスの実行
- `check_counts.py`: SQLiteと新Weaviateコレクションの件数確認
- `rollback_check.py`: ロールバック情報、旧ボリューム、バックアップ内容とSHA-256の確認

代表検索の採取と比較には、汎用の `tools/search_regression/` を使用します。

具体的な実行順とコマンドは `docs/development.md` を参照してください。

## 保持期間

このディレクトリ内のツールは今回のパス、バージョン、移行方式に依存するため、
ロールバック保持期間の終了後は不要です。次を1つのPRで削除します。

1. `tools/weaviate_1_38_migration/`
2. `apps/api/tests/unit/tools/test_weaviate_1_38_migration.py`
3. `docs/development.md` のこの移行専用コマンド
4. 不要なら `.gitignore` の `data/migration/`
5. `apps/api/Dockerfile.prod` の移行ツールCOPY
6. `scripts/deploy.sh` の移行前ガード（移行完了後も残すか別途判断）

`tools/` にほかのツールがなければ、空になる `tools/__init__.py` も削除できます。

実データを含む `data/migration/` と旧WeaviateボリュームはGit操作では削除されません。
保持期間終了後も、削除対象を別途確認してから扱ってください。
