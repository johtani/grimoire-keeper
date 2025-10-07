# Slack Bot 使用方法

## 基本コマンド

### `/grimoire` コマンド

#### URL処理
```
/grimoire https://example.com
```
URLを処理して要約・キーワード抽出を開始します。処理IDが返されます。

#### ステータス確認
```
/grimoire status 123
```
処理ID（例：123）の処理状況を確認します。

**ステータスの種類:**
- `processing`: 処理中
- `completed`: 完了
- `failed`: 失敗

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