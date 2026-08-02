# Development

## Weaviateデータモデルの移行

ページ代表データは `GrimoirePage`、本文は `GrimoireContentChunk` に保存します。
旧 `GrimoireChunk` は再インデックス中も削除されません。

このIssueでは再インデックス機能の実装までを行います。本番での新しいWeaviate
環境の準備、再インデックス、APIの切り替えは #154 の手順に従ってください。

まず対象を確認します。

```bash
uv run python scripts/reindex_weaviate.py --dry-run
```

#154 で用意した空のWeaviate環境を接続先に指定し、新しいコレクションを作成して
再インデックスします。

```bash
uv run python scripts/reindex_weaviate.py
```

コマンドはSQLiteの成功済みページと保存済みJina JSONだけを使用し、Jina APIや
LLMを再実行しません。ページの `status` と `last_success_step` も変更しません。
個別ページに失敗しても残りを続行し、最後に成功・失敗件数を表示します。

新コレクションの件数と検索結果を確認してから、#154 の手順でAPIを切り替えて
ください。問題がなければ、旧 `GrimoireChunk` はWeaviateの管理手段から手動で
削除できます。自動削除は行いません。
