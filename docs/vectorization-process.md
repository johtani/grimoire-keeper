# ベクトル化処理（Weaviate保存）仕様

## 概要
LLM処理完了後、コンテンツをチャンキングしてWeaviateに保存する処理の詳細仕様です。

## 処理フロー

### 1. 事前準備
```python
# LLM処理完了後、ベクトル化処理を開始
# ステータスは 'llm_complete' から自動的に進行
```

### 2. データ読み込み
```python
# pagesテーブルから基本情報取得
page_data = get_page_data(page_id)
url = page_data["url"]
title = page_data["title"]
memo = page_data["memo"]
summary = page_data["summary"]
keywords = json.loads(page_data["keywords"])
created_at = page_data["created_at"]

# JSONファイルからコンテンツ取得
json_data = load_jina_response(page_id)
content = json_data["data"]["content"]
```

### 3. コンテンツチャンキング
```python
def chunk_content(content: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """
    コンテンツを重複ありで分割
    
    Args:
        content: 分割対象のMarkdownテキスト
        chunk_size: チャンクサイズ（文字数）
        overlap: 重複サイズ（文字数）
    
    Returns:
        分割されたチャンクのリスト
    """
    # 段落単位での分割を優先
    paragraphs = content.split('\n\n')
    chunks = []
    current_chunk = ""
    
    for paragraph in paragraphs:
        if len(current_chunk + paragraph) <= chunk_size:
            current_chunk += paragraph + '\n\n'
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = paragraph + '\n\n'
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    # サイズが大きすぎるチャンクを再分割
    final_chunks = []
    for chunk in chunks:
        if len(chunk) <= chunk_size:
            final_chunks.append(chunk)
        else:
            # 文字数ベースで強制分割
            sub_chunks = split_by_size(chunk, chunk_size, overlap)
            final_chunks.extend(sub_chunks)
    
    return final_chunks

def split_by_size(text: str, chunk_size: int, overlap: int) -> list[str]:
    """文字数ベースでの強制分割"""
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        
        if end >= len(text):
            break
            
        start = end - overlap
    
    return chunks
```

### 4. Weaviate保存
```python
import weaviate

def save_chunks_to_weaviate(page_id: int, chunks: list[str], metadata: dict):
    """チャンクをWeaviateに保存"""
    
    try:
        for i, chunk in enumerate(chunks):
            weaviate_object = {
                "pageId": page_id,
                "chunkId": i,
                "url": metadata["url"],
                "title": metadata["title"],
                "memo": metadata["memo"] or "",
                "content": chunk,
                "summary": metadata["summary"],
                "keywords": metadata["keywords"],
                "createdAt": metadata["created_at"].isoformat()
            }
            
            # Weaviateに保存
            result = weaviate_client.data_object.create(
                data_object=weaviate_object,
                class_name="GrimoireChunk"
            )
            
            # 最初のチャンクのIDをpagesテーブルに保存
            if i == 0:
                UPDATE pages 
                SET weaviate_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
        
        # ステータス更新
        UPDATE process_logs 
        SET status = 'vectorize_complete' 
        WHERE page_id = ? AND status = 'llm_complete'
        
        return True
        
    except Exception as e:
        # エラー処理
        UPDATE process_logs 
        SET status = 'vectorize_error', error_message = ? 
        WHERE page_id = ? AND status = 'llm_complete'
        
        return False
```

## Weaviateスキーマ詳細

### GrimoireChunkクラス
```json
{
  "class": "GrimoireChunk",
  "description": "Grimoire Keeperで管理するWebページのチャンク",
  "properties": [
    {
      "name": "pageId",
      "dataType": ["int"],
      "description": "pagesテーブルのID"
    },
    {
      "name": "chunkId",
      "dataType": ["int"],
      "description": "ページ内でのチャンク番号"
    },
    {
      "name": "url",
      "dataType": ["text"],
      "description": "元のURL"
    },
    {
      "name": "title",
      "dataType": ["text"],
      "description": "ページタイトル"
    },
    {
      "name": "memo",
      "dataType": ["text"],
      "description": "ユーザーメモ"
    },
    {
      "name": "content",
      "dataType": ["text"],
      "description": "チャンクの内容"
    },
    {
      "name": "summary",
      "dataType": ["text"],
      "description": "ページ全体の要約"
    },
    {
      "name": "keywords",
      "dataType": ["text[]"],
      "description": "キーワードリスト"
    },
    {
      "name": "createdAt",
      "dataType": ["date"],
      "description": "作成日時"
    }
  ],
  "vectorizer": "text2vec-openai",
  "moduleConfig": {
    "text2vec-openai": {
      "model": "text-embedding-3-small",
      "dimensions": 1536,
      "type": "text"
    }
  }
}
```

## 検索機能対応

### 1. ベクトル検索
```python
def vector_search(query: str, limit: int = 5) -> list[dict]:
    """ベクトル類似度検索"""
    
    result = weaviate_client.query.get("GrimoireChunk", [
        "pageId", "chunkId", "url", "title", "memo", 
        "content", "summary", "keywords", "createdAt"
    ]).with_near_text({
        "concepts": [query]
    }).with_limit(limit).do()
    
    return result["data"]["Get"]["GrimoireChunk"]
```

### 2. メタデータフィルタ検索
```python
def filtered_search(query: str, filters: dict, limit: int = 5) -> list[dict]:
    """フィルタ付きベクトル検索"""
    
    where_filter = build_where_filter(filters)
    
    result = weaviate_client.query.get("GrimoireChunk", [
        "pageId", "chunkId", "url", "title", "memo", 
        "content", "summary", "keywords", "createdAt"
    ]).with_near_text({
        "concepts": [query]
    }).with_where(where_filter).with_limit(limit).do()
    
    return result["data"]["Get"]["GrimoireChunk"]

def build_where_filter(filters: dict) -> dict:
    """フィルタ条件構築"""
    conditions = []
    
    if "url" in filters:
        conditions.append({
            "path": ["url"],
            "operator": "Like",
            "valueText": f"*{filters['url']}*"
        })
    
    if "keywords" in filters:
        conditions.append({
            "path": ["keywords"],
            "operator": "ContainsAny",
            "valueTextArray": filters["keywords"]
        })
    
    if "date_from" in filters:
        conditions.append({
            "path": ["createdAt"],
            "operator": "GreaterThanEqual",
            "valueDate": filters["date_from"]
        })
    
    if len(conditions) == 1:
        return conditions[0]
    elif len(conditions) > 1:
        return {
            "operator": "And",
            "operands": conditions
        }
    else:
        return {}
```

### 3. キーワード検索
```python
def keyword_search(keywords: list[str], limit: int = 5) -> list[dict]:
    """キーワードベース検索"""
    
    where_filter = {
        "path": ["keywords"],
        "operator": "ContainsAny",
        "valueTextArray": keywords
    }
    
    result = weaviate_client.query.get("GrimoireChunk", [
        "pageId", "chunkId", "url", "title", "memo", 
        "content", "summary", "keywords", "createdAt"
    ]).with_where(where_filter).with_limit(limit).do()
    
    return result["data"]["Get"]["GrimoireChunk"]
```

## エラーハンドリング

### 想定されるエラー
1. **Weaviate接続エラー**: サーバー停止、ネットワーク問題
2. **スキーマエラー**: クラス定義不整合
3. **データ形式エラー**: 不正なデータ型
4. **容量制限エラー**: Weaviateの容量上限
5. **OpenAI APIエラー**: ベクトル化API制限

### エラーメッセージ例
```python
error_messages = {
    "weaviate_connection_error": "Weaviate接続エラー",
    "schema_error": "Weaviateスキーマエラー",
    "data_format_error": "データ形式エラー",
    "capacity_limit_error": "Weaviate容量制限エラー",
    "openai_api_error": "OpenAI API エラー"
}
```

## 監視・メンテナンス

### 処理状況確認
```sql
-- ベクトル化処理状況の確認
SELECT status, COUNT(*) as count 
FROM process_logs 
WHERE status IN ('llm_complete', 'vectorize_complete', 'vectorize_error')
GROUP BY status;

-- エラー詳細の確認
SELECT url, error_message, created_at 
FROM process_logs 
WHERE status = 'vectorize_error' 
ORDER BY created_at DESC;
```

### Weaviate監視
```python
# オブジェクト数確認
def get_weaviate_stats():
    result = weaviate_client.query.aggregate("GrimoireChunk").with_meta_count().do()
    return result["data"]["Aggregate"]["GrimoireChunk"][0]["meta"]["count"]

# ディスク使用量確認
def get_weaviate_disk_usage():
    # Weaviate管理画面またはAPIで確認
    pass
```

### パフォーマンス最適化
- チャンクサイズの調整（1000文字が基準）
- 重複サイズの最適化（200文字が基準）
- バッチ処理での一括保存
- インデックス最適化