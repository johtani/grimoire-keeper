# LLM処理（要約・キーワード抽出）仕様

## 概要
Jina AI Readerで取得したコンテンツをLiteLLM経由でGoogle Gemini APIに送信し、要約とキーワードを生成する処理の詳細仕様です。

## 処理フロー

### 1. 事前準備
```python
# ダウンロード完了後、LLM処理を開始
# ステータスは 'download_complete' から自動的に進行
```

### 2. JSONファイル読み込み
```python
import json

def load_jina_response(page_id: int) -> dict:
    json_file_path = f"{json_storage_path}/{page_id}.json"
    with open(json_file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

response_data = load_jina_response(page_id)
content = response_data["data"]["content"]
title = response_data["data"]["title"]
```

### 3. LiteLLM経由でGemini API呼び出し
```python
from litellm import completion

def generate_summary_and_keywords(title: str, content: str) -> dict:
    prompt = f"""
以下のWebページの内容を分析して、要約とキーワードを生成してください。

タイトル: {title}

内容:
{content}

以下の形式でJSONで回答してください:
{{
  "summary": "ページの要約（200文字程度）",
  "keywords": ["キーワード1", "キーワード2", ..., "キーワード20"]
}}

要約は内容の要点を簡潔にまとめ、キーワードは内容を特徴づける重要な単語・フレーズを20個選んでください。
"""

    response = completion(
        model="gemini/gemini-1.5-flash",
        messages=[{"role": "user", "content": prompt}],
        api_key=google_api_key,
        temperature=0.3
    )
    
    return json.loads(response.choices[0].message.content)
```

### 4. レスポンス処理

#### 成功時
```python
try:
    result = generate_summary_and_keywords(title, content)
    
    # pagesテーブル更新
    UPDATE pages 
    SET summary = ?, keywords = ?, updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
    
    # ステータス更新
    UPDATE process_logs 
    SET status = 'llm_complete' 
    WHERE page_id = ? AND status = 'download_complete'
    
except Exception as e:
    # エラー処理
    UPDATE process_logs 
    SET status = 'llm_error', 
        error_message = ? 
    WHERE page_id = ? AND status = 'download_complete'
```

## プロンプト設計

### 要約・キーワード抽出プロンプト
```python
SUMMARY_KEYWORDS_PROMPT = """
以下のWebページの内容を分析して、要約とキーワードを生成してください。

タイトル: {title}

内容:
{content}

以下の形式でJSONで回答してください:
{{
  "summary": "ページの要約（200文字程度）",
  "keywords": ["キーワード1", "キーワード2", ..., "キーワード20"]
}}

要約の要件:
- 内容の要点を簡潔にまとめる
- 200文字程度で収める
- 読み手が内容を理解できるレベルの詳細度

キーワードの要件:
- 内容を特徴づける重要な単語・フレーズを選ぶ
- 技術用語、概念、人名、企業名、製品名などを含む
- 検索で見つけやすい単語を優先
- 20個ちょうど生成する
- 重複は避ける
"""
```

## データ保存形式

### pagesテーブル更新
```sql
UPDATE pages 
SET 
    summary = ?,           -- 生成された要約テキスト
    keywords = ?,          -- JSON配列形式 ["keyword1", "keyword2", ...]
    updated_at = CURRENT_TIMESTAMP
WHERE id = ?
```

### keywords フィールドの形式
```json
["機械学習", "Python", "データサイエンス", "AI", "深層学習", ...]
```

## エラーハンドリング

### 想定されるエラー
1. **API認証エラー**: 無効なGoogle API Key
2. **レート制限**: API呼び出し制限に達した場合
3. **コンテンツエラー**: 内容が長すぎる、不適切な内容
4. **JSON解析エラー**: LLMの回答が不正なJSON形式
5. **ネットワークエラー**: 接続タイムアウト

### エラーメッセージ例
```python
error_messages = {
    "api_auth_error": "Google API認証エラー",
    "rate_limit_error": "APIレート制限に達しました",
    "content_too_long": "コンテンツが長すぎます",
    "invalid_json_response": "LLM応答のJSON解析エラー",
    "network_error": "ネットワーク接続エラー"
}
```

## 処理ステータス

### process_logs のステータス
- `download_complete`: ダウンロード完了後、LLM処理開始前
- `llm_complete`: LLM処理完了
- `llm_error`: LLM処理エラー

## 設定・環境変数

### 必要な環境変数
```env
GOOGLE_API_KEY=your_google_api_key_here
LITELLM_LOG=INFO  # オプション: ログレベル
```

### LiteLLM設定例
```python
import litellm

# ログ設定
litellm.set_verbose = True

# タイムアウト設定
litellm.request_timeout = 60

# リトライ設定
litellm.num_retries = 3
```

## 使用例

### 完全な処理フロー
```python
async def process_llm_analysis(page_id: int):
    try:
        # 1. ダウンロード完了後のLLM処理開始
        # ステータスは既に 'download_complete'
        
        # 2. JSONファイル読み込み
        response_data = load_jina_response(page_id)
        title = response_data["data"]["title"]
        content = response_data["data"]["content"]
        
        # 3. LLM処理
        result = generate_summary_and_keywords(title, content)
        
        # 4. データベース更新
        update_page_summary_keywords(
            page_id, 
            result["summary"], 
            json.dumps(result["keywords"], ensure_ascii=False)
        )
        
        # 5. 処理完了ログ
        log_process_complete(page_id, 'llm_complete')
        
        return result
        
    except Exception as e:
        # エラーログ
        log_process_error(page_id, 'llm_error', str(e))
        raise
```

## 監視・メンテナンス

### 処理状況確認
```sql
-- LLM処理状況の確認
SELECT status, COUNT(*) as count 
FROM process_logs 
WHERE status IN ('download_complete', 'llm_complete', 'llm_error')
GROUP BY status;

-- エラー詳細の確認
SELECT url, error_message, created_at 
FROM process_logs 
WHERE status = 'llm_error' 
ORDER BY created_at DESC;
```

### コスト監視
- Google Gemini APIの使用量追跡
- トークン消費量の記録
- 月次コスト分析