# Search regression snapshot tool

代表的なAPI検索結果をJSONへ保存し、変更前後の欠落、追加、順位変動、上位結果の
重複率を比較する汎用ツールです。

Weaviateのバージョン更新だけでなく、埋め込みモデル、検索設定、フィルター、
ランキング処理を変更するときの回帰確認にも利用できます。

```bash
uv run python -m tools.search_regression.snapshot capture --help
uv run python -m tools.search_regression.snapshot compare --help
```

`queries.example.json` をコピーし、対象環境に合う代表クエリへ変更してください。
クエリや結果に実データが含まれる場合はGitへコミットしません。
