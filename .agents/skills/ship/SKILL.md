---
name: ship
description: lint・テストを通してコミットし、PR を作成後に差分をレビューする標準ワークフロー
---

変更をコミットして PR を作成する標準ワークフローを実行します。

## 前提確認

1. **ブランチを確認する**
   ```bash
   git branch --show-current
   ```
   - `main` または `master` の場合は **即座に停止** してユーザーに報告する
   - フィーチャーブランチにいることを確認してから次へ進む

## 手順

2. **全ユニットテストを実行する**
   ```bash
   uv run pytest apps/api/tests/unit/ -v
   ```
   - 失敗があれば修正してから次へ進む
   - インテグレーションテストは Weaviate 起動が必要なのでスキップ可

3. **lint & フォーマットを実行する**
   ```bash
   uv run ruff format .
   uv run ruff check .
   uv run mypy .
   ```
   - ruff エラーがあれば `--fix` で自動修正を試みる: `uv run ruff check --fix .`
   - 自動修正できないエラーは手動で修正する
   - mypy エラーがあれば手動で修正する (mypy 設定により apps/bot と apps/api/tests は除外)
   - 修正後は再度テストを実行して回帰がないことを確認する

4. **変更をコミットする**
   - `git diff --stat` で変更範囲を確認する
   - 引数でコミットメッセージが指定されていればそれを使う
   - なければ変更内容から conventional commit メッセージを作成する
     - 形式: `feat:`, `fix:`, `refactor:`, `test:`, `docs:` + 日本語説明
   - `git add <関連ファイル>` (`.env` や機密ファイルは含めない)
   - `git commit -m "..."`

5. **プッシュして PR を作成する**
   ```bash
   git push -u origin <ブランチ名>
   gh pr create --title "..." --body "..."
   ```
   PR 本文の形式:
   ```
   ## Summary
   - 変更内容を箇条書き

   ## Test plan
   - [ ] ユニットテストがすべてパス
   - [ ] 動作確認の手順

   🤖 Generated with [Codex](https://Codex.com/Codex)
   ```

6. **作成した PR をレビューする**
   - `gh pr diff` と `gh pr view` で、作成した PR の差分・説明・対象ブランチを確認する
   - バグ、回帰、セキュリティ、データ損失、テスト不足を優先してレビューする
   - 指摘には該当ファイルと行番号、影響、修正案を含める
   - 問題がなければ、その旨と残存リスクをユーザーに報告する
   - 問題があれば次を行う:
     1. 問題を修正する
     2. 手順2・3のテストとチェックを再実行する
     3. 修正を追加コミットして同じブランチへ push する
     4. PR を再レビューし、重大な指摘がなくなるまで繰り返す
   - 自分の PR に GitHub の approve review は投稿しない

## 絶対厳守ルール
- **main/master へ直接コミットしない**
- テストや lint が失敗したまま進まない
- PR レビューで重大な指摘が残ったまま完了しない
- `.env`、シークレット、大容量バイナリをコミットしない
