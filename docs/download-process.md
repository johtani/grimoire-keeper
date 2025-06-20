# ダウンロード処理フロー

## 概要
Jina AI Readerからコンテンツをダウンロードし、JSONファイルとして保存する処理の詳細仕様です。

## 処理フロー

### 1. 事前準備
```python
# process_logsテーブルに処理開始を記録
INSERT INTO process_logs (page_id, url, status) 
VALUES (?, ?, 'started')
```

### 2. Jina AI Reader API呼び出し
```python
import requests

headers = {
    "Accept": "application/json",
    "Authorization": f"Bearer {jina_api_key}",
    "X-Return-Format": "markdown",
    "X-With-Images-Summary": "true"
}

response = requests.get(f"https://r.jina.ai/{url}", headers=headers)
```

### 3. レスポンス処理

#### 成功時 (status_code == 200)
```python
# JSONファイル保存
json_file_path = f"{json_storage_path}/{page_id}.json"
with open(json_file_path, 'w', encoding='utf-8') as f:
    json.dump(response.json(), f, ensure_ascii=False, indent=2)

# pagesテーブルにメモと一緒に保存
INSERT INTO pages (url, title, memo, created_at) 
VALUES (?, ?, ?, CURRENT_TIMESTAMP)

# ステータス更新
UPDATE process_logs 
SET status = 'download_complete' 
WHERE page_id = ? AND status = 'started'
```

#### エラー時 (status_code != 200 または例外発生)
```python
# エラー情報を記録
UPDATE process_logs 
SET status = 'download_error', 
    error_message = ? 
WHERE page_id = ? AND status = 'started'
```

## ファイル構造

### JSONファイル保存先
```
data/
└── json/
    ├── 1.json    # page_id=1のレスポンス
    ├── 2.json    # page_id=2のレスポンス
    └── ...
```

### JSONファイル内容例
```json
{
  "code": 200,
  "status": 20000,
  "data": {
    "title": "記事タイトル",
    "description": "記事の説明",
    "url": "https://example.com/article",
    "content": "記事本文（Markdown形式）",
    "publishedTime": "Mon, 01 Jan 2024 12:00:00 GMT",
    "metadata": { ... },
    "images": { ... },
    "external": { ... },
    "usage": {
      "tokens": 1500
    }
  },
  "meta": {
    "usage": {
      "tokens": 1500
    }
  }
}
```

## エラーハンドリング

### 想定されるエラー
1. **ネットワークエラー**: 接続タイムアウト、DNS解決失敗
2. **認証エラー**: 無効なJina APIキー
3. **レート制限**: API呼び出し制限に達した場合
4. **コンテンツエラー**: 取得対象URLが無効、アクセス不可
5. **ファイルシステムエラー**: ディスク容量不足、権限不足
6. **データベースエラー**: pagesテーブルへの保存失敗

### エラーメッセージ例
```python
error_messages = {
    "network_error": "ネットワーク接続エラー",
    "auth_error": "API認証エラー",
    "rate_limit": "APIレート制限に達しました",
    "invalid_url": "無効なURLまたはアクセス不可",
    "file_system_error": "ファイル保存エラー"
}
```

## 後続処理での利用

### JSONファイル読み込み
```python
def load_jina_response(page_id: int) -> dict:
    json_file_path = f"{json_storage_path}/{page_id}.json"
    with open(json_file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

# 使用例（LLM処理で利用）
response_data = load_jina_response(page_id)
content = response_data["data"]["content"]
title = response_data["data"]["title"]
```

### LLM処理への連携
ダウンロード完了後、保存されたJSONファイルを使用してLLM処理（要約・キーワード抽出）を実行します。詳細は `docs/llm-processing.md` を参照してください。

### データ抽出例
```python
def extract_page_data(response_data: dict) -> dict:
    data = response_data["data"]
    return {
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "content": data.get("content", ""),
        "published_time": data.get("publishedTime"),
        "usage_tokens": data.get("usage", {}).get("tokens", 0)
    }
```

## 監視・メンテナンス

### ディスク使用量監視
- JSONファイルサイズの定期チェック
- 古いファイルの自動削除機能

### 処理状況確認
```sql
-- ダウンロード状況の確認
SELECT status, COUNT(*) as count 
FROM process_logs 
WHERE status IN ('started', 'download_complete', 'download_error')
GROUP BY status;

-- エラー詳細の確認
SELECT url, error_message, created_at 
FROM process_logs 
WHERE status = 'download_error' 
ORDER BY created_at DESC;
```