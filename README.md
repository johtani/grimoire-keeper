# Grimoire Keeper 設計書

## 概要
URLを投稿すると、ページ内容を要約・キーワード抽出してベクトルDBに保存し、後で検索できるようにするSlackボット

## システム構成

### 1. アーキテクチャ
```
[Slack] → [Slackボット] → [バックエンドAPI] → [Weaviate]
                                ↓
                           [SQLite3]
```

### 2. リポジトリ構成
- `apps/bot/` - Slackボット
- `apps/api/` - バックエンドAPI
- `shared/` - 共通ライブラリ

## 機能要件

### Slackボット機能
1. **URL投稿検知**
   - メッセージ内のURLを検出
   - バックエンドAPIに処理を依頼

2. **検索コマンド**
   - `/search [キーワード]` でベクトル検索
   - 関連する保存済みページを返す

3. **ステータス表示**
   - 処理中・完了・エラーの通知

### バックエンドAPI機能
1. **コンテンツ取得・処理**
   - Jina AI ReaderでURL内容取得（Markdown形式）
   - LiteLLMで要約・キーワード抽出

2. **データ保存**
   - SQLite3にメタデータ保存
   - JSONファイルに生レスポンス保存
   - Weaviateにベクトル保存

3. **検索機能**
   - ベクトル類似度検索
   - 結果のランキング

## 技術スタック

### Slackボット
- **言語**: Python 3.13
- **フレームワーク**: slack-bolt-python
- **依存関係**:
  - slack-bolt
  - requests
  - python-dotenv

### バックエンドAPI
- **言語**: Python 3.13
- **フレームワーク**: FastAPI
- **依存関係**:
  - fastapi
  - uvicorn
  - litellm
  - weaviate-client
  - sqlite3 (標準ライブラリ)
  - requests
  - pydantic
  - google-generativeai (Gemini API用)

## データベース設計

### SQLite3テーブル
```sql
-- ページメタデータ
CREATE TABLE pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    keywords TEXT, -- JSON配列として保存
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    weaviate_id TEXT -- WeaviateのオブジェクトID
);

-- 処理ログ
CREATE TABLE process_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id INTEGER,
    url TEXT NOT NULL,
    status TEXT NOT NULL, -- 'before_download', 'complete_download', 'error_download', 'processing', 'completed', 'failed'
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (page_id) REFERENCES pages(id)
);
```

### JSONファイル保存
- **保存場所**: `data/json/{page_id}.json`
- **ファイル名**: pagesテーブルのidを使用
- **内容**: Jina AI Readerの生レスポンス
```

### Weaviate スキーマ
```json
{
  "class": "GrimoirePage",
  "properties": [
    {
      "name": "url",
      "dataType": ["text"]
    },
    {
      "name": "title", 
      "dataType": ["text"]
    },
    {
      "name": "content",
      "dataType": ["text"]
    },
    {
      "name": "summary",
      "dataType": ["text"]
    },
    {
      "name": "keywords",
      "dataType": ["text[]"]
    },
    {
      "name": "createdAt",
      "dataType": ["date"]
    }
  ],
  "vectorizer": "text2vec-openai"
}
```

## API設計

### バックエンドAPI エンドポイント

#### POST /api/v1/process-url
URLを処理してデータベースに保存
```json
{
  "url": "https://example.com",
  "slack_channel": "#general",
  "slack_user": "user123"
}
```

#### GET /api/v1/search
ベクトル検索
```json
{
  "query": "機械学習",
  "limit": 5
}
```

#### GET /api/v1/pages/{page_id}
特定ページの詳細取得

#### GET /api/v1/health
ヘルスチェック

## 処理フロー

### URL投稿時の処理
1. Slackボットがメッセージ内のURLを検出
2. バックエンドAPI `/process-url` を呼び出し
3. process_logsに `before_download` ステータスで登録
4. Jina AI Readerでコンテンツ取得
   - 成功: JSONファイル保存、ステータス `complete_download`
   - 失敗: エラーメッセージ保存、ステータス `error_download`
5. Google Gemini (LiteLLM経由) で要約・キーワード抽出
6. SQLite3とWeaviate (OpenAI embeddings) に保存
7. Slackに完了通知

### 検索時の処理
1. `/search` コマンドを受信
2. バックエンドAPI `/search` を呼び出し
3. Weaviateでベクトル検索実行
4. 結果をSlackに表示

## 設定・環境変数

### Slackボット
```env
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
BACKEND_API_URL=http://localhost:8000
```

### バックエンドAPI
```env
OPENAI_API_KEY=sk-...        # Weaviate vectorizer用
GOOGLE_API_KEY=sk-...        # Gemini要約・キーワード抽出用
JINA_API_KEY=...
WEAVIATE_URL=http://localhost:8080
DATABASE_PATH=./grimoire.db
JSON_STORAGE_PATH=./data/json  # JSONファイル保存先
```

## デプロイ・運用

### 開発環境
- Slackボット: ローカル実行 + ngrok
- バックエンドAPI: uvicorn
- Weaviate: Docker Compose

### 本番環境（案）
- Slackボット: ローカル実行
- バックエンドAPI: ローカル実行 (uvicorn)
- Weaviate: Docker (ローカル)
- SQLite3: ファイルベース (ローカル)

## 拡張可能性
- 複数のLLMプロバイダー対応
- ページ更新の検知・再処理
- 検索結果のフィルタリング
- ユーザー別の保存・検索
- Web UI の提供