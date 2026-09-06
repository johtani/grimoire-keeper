# Slack Bot 使用方法

## 基本コマンド

### `/grimoire` コマンド

#### URL処理
```
/grimoire https://example.com
```
URLを処理して要約・キーワード抽出を開始します。処理IDが返されます。

登録は非同期です。Bot が「処理を受け付けました」と返した時点では `queued` で、独立した Job Worker が順番に `processing` へ進めます。同じ URL が登録済みの場合は `already_exists` として、既存ページの現在状態を表示します。

#### ステータス確認
```
/grimoire status 123
```
処理ID（例：123）の処理状況を確認します。

**ステータスの種類:**
- `queued`（待機中）: Worker の処理待ち。しばらく待ってから再確認する
- `processing`: 処理中
- `completed`: 完了
- `failed`: 失敗。表示される `POST /api/v1/retry/<処理ID>` を API に送信して再処理を登録できる
- `error`: 状態取得中のエラー。API/Worker のログと稼働状態を確認する

状態遷移は通常 `queued → processing → completed`、処理エラー時は `queued → processing → failed` です。`already_exists` はジョブ状態ではなく URL 登録時の応答で、既存ページが `queued`、`processing`、`completed`、`failed` のどれかを続けて表示します。

#### 検索
```
/grimoire search AI
```
保存されたコンテンツから「AI」に関連する記事を検索します。

#### ヘルプ
```
/grimoire help
```
使用方法を表示します。

## メンション機能

ボットをメンションしてURLを送信することも可能です：

```
@grimoire-bot https://example.com
```

## 使用例

1. **URL処理の開始**
   ```
   /grimoire https://techblog.example.com/ai-article
   ```
   → 処理ID: 123 が返される

2. **処理状況の確認**
   ```
   /grimoire status 123
   ```
   → 処理状況とページ情報を表示

3. **関連記事の検索**
   ```
   /grimoire search machine learning
   ```
   → 機械学習に関連する記事を表示

## 注意事項

- 処理には数分かかる場合があります
- 処理IDは後でステータス確認に使用するため控えておいてください
- 検索は処理完了後のコンテンツのみが対象です
- Worker が停止している間もジョブは SQLite に `queued` のまま保持され、API や Bot の再起動だけでは処理されません。`docker compose -f docker-compose.prod.yml ps worker` と `docker compose -f docker-compose.prod.yml logs --tail=100 worker` で確認してください
- 管理画面 `http://localhost:8001` または `/grimoire status <処理ID>` で状態を確認できます
- Slack Bot 自体には retry コマンドはありません。失敗したページは API の `POST /api/v1/retry/<処理ID>` を使用してください
