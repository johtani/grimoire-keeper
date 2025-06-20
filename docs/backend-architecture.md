# バックエンドアーキテクチャ設計

## 概要
バックエンドAPIの処理フローに基づいたクラス・関数設計です。

## ディレクトリ構造
```
apps/api/src/grimoire_api/
├── main.py                 # FastAPIアプリケーション
├── config.py              # 設定管理
├── models/                # データモデル
│   ├── __init__.py
│   ├── request.py         # リクエストモデル
│   ├── response.py        # レスポンスモデル
│   └── database.py        # データベースモデル
├── services/              # ビジネスロジック
│   ├── __init__.py
│   ├── url_processor.py   # URL処理サービス
│   ├── jina_client.py     # Jina AI Reader クライアント
│   ├── llm_service.py     # LLM処理サービス
│   ├── vectorizer.py      # ベクトル化サービス
│   └── search_service.py  # 検索サービス
├── repositories/          # データアクセス層
│   ├── __init__.py
│   ├── database.py        # データベース接続
│   ├── page_repository.py # ページデータ操作
│   ├── log_repository.py  # ログデータ操作
│   └── file_repository.py # ファイル操作
├── utils/                 # ユーティリティ
│   ├── __init__.py
│   ├── chunking.py        # テキストチャンキング
│   └── exceptions.py      # カスタム例外
└── routers/               # APIルーター
    ├── __init__.py
    ├── process.py         # URL処理エンドポイント
    ├── search.py          # 検索エンドポイント
    └── health.py          # ヘルスチェック
```

## データモデル

### リクエスト・レスポンスモデル
```python
# models/request.py
from pydantic import BaseModel, HttpUrl
from typing import Optional

class ProcessUrlRequest(BaseModel):
    url: HttpUrl
    memo: Optional[str] = None
    slack_channel: Optional[str] = None
    slack_user: Optional[str] = None

class SearchRequest(BaseModel):
    query: str
    limit: int = 5
    filters: Optional[dict] = None

# models/response.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class ProcessUrlResponse(BaseModel):
    status: str
    page_id: int
    message: str

class SearchResult(BaseModel):
    page_id: int
    chunk_id: int
    url: str
    title: str
    memo: Optional[str]
    content: str
    summary: str
    keywords: List[str]
    created_at: datetime
    score: float

class SearchResponse(BaseModel):
    results: List[SearchResult]
    total: int
    query: str
```

### データベースモデル
```python
# models/database.py
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime

@dataclass
class Page:
    id: Optional[int]
    url: str
    title: str
    memo: Optional[str]
    summary: Optional[str]
    keywords: Optional[str]  # JSON string
    created_at: datetime
    updated_at: datetime
    weaviate_id: Optional[str]

@dataclass
class ProcessLog:
    id: Optional[int]
    page_id: Optional[int]
    url: str
    status: str
    error_message: Optional[str]
    created_at: datetime
```

## サービス層

### URL処理サービス
```python
# services/url_processor.py
from typing import Dict, Any
import asyncio
from .jina_client import JinaClient
from .llm_service import LLMService
from .vectorizer import VectorizerService
from ..repositories.page_repository import PageRepository
from ..repositories.log_repository import LogRepository

class UrlProcessorService:
    def __init__(
        self,
        jina_client: JinaClient,
        llm_service: LLMService,
        vectorizer: VectorizerService,
        page_repo: PageRepository,
        log_repo: LogRepository
    ):
        self.jina_client = jina_client
        self.llm_service = llm_service
        self.vectorizer = vectorizer
        self.page_repo = page_repo
        self.log_repo = log_repo

    async def process_url(self, url: str, memo: str = None) -> Dict[str, Any]:
        """URL処理のメインフロー"""
        page_id = None
        
        try:
            # 1. 処理開始ログ
            page_id = await self.log_repo.create_log(url, "started")
            
            # 2. Jina AI Reader処理
            jina_result = await self.jina_client.fetch_content(url)
            await self._save_download_result(page_id, url, memo, jina_result)
            
            # 3. LLM処理
            llm_result = await self.llm_service.generate_summary_keywords(page_id)
            await self._save_llm_result(page_id, llm_result)
            
            # 4. ベクトル化処理
            await self.vectorizer.vectorize_content(page_id)
            
            # 5. 完了ログ
            await self.log_repo.update_status(page_id, "completed")
            
            return {
                "status": "success",
                "page_id": page_id,
                "message": "URL processing completed successfully"
            }
            
        except Exception as e:
            if page_id:
                await self.log_repo.update_status(page_id, "failed", str(e))
            raise

    async def _save_download_result(self, page_id: int, url: str, memo: str, result: Dict):
        """ダウンロード結果保存"""
        # JSONファイル保存
        await self.page_repo.save_json_file(page_id, result)
        
        # pagesテーブル保存
        await self.page_repo.create_page(
            url=url,
            title=result["data"]["title"],
            memo=memo
        )
        
        # ステータス更新
        await self.log_repo.update_status(page_id, "download_complete")

    async def _save_llm_result(self, page_id: int, result: Dict):
        """LLM結果保存"""
        await self.page_repo.update_summary_keywords(
            page_id=page_id,
            summary=result["summary"],
            keywords=result["keywords"]
        )
        await self.log_repo.update_status(page_id, "llm_complete")
```

### Jina AI Readerクライアント
```python
# services/jina_client.py
import httpx
from typing import Dict, Any
from ..config import settings
from ..utils.exceptions import JinaClientError

class JinaClient:
    def __init__(self):
        self.api_key = settings.JINA_API_KEY
        self.base_url = "https://r.jina.ai"
        
    async def fetch_content(self, url: str) -> Dict[str, Any]:
        """Jina AI ReaderでURL内容取得"""
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "X-Return-Format": "markdown",
            "X-With-Images-Summary": "true"
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/{url}",
                    headers=headers,
                    timeout=60.0
                )
                response.raise_for_status()
                return response.json()
                
            except httpx.HTTPError as e:
                raise JinaClientError(f"Jina API error: {str(e)}")
```

### LLMサービス
```python
# services/llm_service.py
import json
from typing import Dict, Any
from litellm import completion
from ..config import settings
from ..repositories.file_repository import FileRepository
from ..utils.exceptions import LLMServiceError

class LLMService:
    def __init__(self, file_repo: FileRepository):
        self.file_repo = file_repo
        self.api_key = settings.GOOGLE_API_KEY
        
    async def generate_summary_keywords(self, page_id: int) -> Dict[str, Any]:
        """要約とキーワード生成"""
        try:
            # JSONファイル読み込み
            jina_data = await self.file_repo.load_json_file(page_id)
            title = jina_data["data"]["title"]
            content = jina_data["data"]["content"]
            
            # プロンプト構築
            prompt = self._build_prompt(title, content)
            
            # LiteLLM呼び出し
            response = completion(
                model="gemini/gemini-1.5-flash",
                messages=[{"role": "user", "content": prompt}],
                api_key=self.api_key,
                temperature=0.3
            )
            
            # JSON解析
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            raise LLMServiceError(f"LLM processing error: {str(e)}")
    
    def _build_prompt(self, title: str, content: str) -> str:
        """プロンプト構築"""
        return f"""
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

### ベクトル化サービス
```python
# services/vectorizer.py
import weaviate
from typing import List, Dict, Any
from ..config import settings
from ..repositories.page_repository import PageRepository
from ..repositories.file_repository import FileRepository
from ..utils.chunking import TextChunker
from ..utils.exceptions import VectorizerError

class VectorizerService:
    def __init__(
        self, 
        page_repo: PageRepository, 
        file_repo: FileRepository,
        text_chunker: TextChunker
    ):
        self.page_repo = page_repo
        self.file_repo = file_repo
        self.text_chunker = text_chunker
        self.client = weaviate.Client(settings.WEAVIATE_URL)
        
    async def vectorize_content(self, page_id: int) -> None:
        """コンテンツのベクトル化とWeaviate保存"""
        try:
            # データ読み込み
            page_data = await self.page_repo.get_page(page_id)
            jina_data = await self.file_repo.load_json_file(page_id)
            content = jina_data["data"]["content"]
            
            # チャンキング
            chunks = self.text_chunker.chunk_text(content)
            
            # Weaviate保存
            await self._save_chunks_to_weaviate(page_data, chunks)
            
        except Exception as e:
            raise VectorizerError(f"Vectorization error: {str(e)}")
    
    async def _save_chunks_to_weaviate(self, page_data: Dict, chunks: List[str]):
        """チャンクをWeaviateに保存"""
        for i, chunk in enumerate(chunks):
            weaviate_object = {
                "pageId": page_data["id"],
                "chunkId": i,
                "url": page_data["url"],
                "title": page_data["title"],
                "memo": page_data["memo"] or "",
                "content": chunk,
                "summary": page_data["summary"],
                "keywords": json.loads(page_data["keywords"] or "[]"),
                "createdAt": page_data["created_at"].isoformat()
            }
            
            result = self.client.data_object.create(
                data_object=weaviate_object,
                class_name="GrimoireChunk"
            )
            
            # 最初のチャンクIDを保存
            if i == 0:
                await self.page_repo.update_weaviate_id(page_data["id"], result)
```

## リポジトリ層

### ページリポジトリ
```python
# repositories/page_repository.py
import sqlite3
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from ..models.database import Page
from .database import DatabaseConnection

class PageRepository:
    def __init__(self, db: DatabaseConnection):
        self.db = db
    
    async def create_page(self, url: str, title: str, memo: str = None) -> int:
        """ページ作成"""
        query = """
        INSERT INTO pages (url, title, memo, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """
        now = datetime.now()
        cursor = await self.db.execute(
            query, (url, title, memo, now, now)
        )
        return cursor.lastrowid
    
    async def get_page(self, page_id: int) -> Optional[Dict[str, Any]]:
        """ページ取得"""
        query = "SELECT * FROM pages WHERE id = ?"
        result = await self.db.fetch_one(query, (page_id,))
        return dict(result) if result else None
    
    async def update_summary_keywords(
        self, 
        page_id: int, 
        summary: str, 
        keywords: List[str]
    ) -> None:
        """要約・キーワード更新"""
        query = """
        UPDATE pages 
        SET summary = ?, keywords = ?, updated_at = ?
        WHERE id = ?
        """
        await self.db.execute(
            query, 
            (summary, json.dumps(keywords, ensure_ascii=False), datetime.now(), page_id)
        )
    
    async def update_weaviate_id(self, page_id: int, weaviate_id: str) -> None:
        """Weaviate ID更新"""
        query = "UPDATE pages SET weaviate_id = ? WHERE id = ?"
        await self.db.execute(query, (weaviate_id, page_id))
```

## ユーティリティ

### テキストチャンキング
```python
# utils/chunking.py
from typing import List

class TextChunker:
    def __init__(self, chunk_size: int = 1000, overlap: int = 200):
        self.chunk_size = chunk_size
        self.overlap = overlap
    
    def chunk_text(self, text: str) -> List[str]:
        """テキストをチャンクに分割"""
        # 段落単位での分割を優先
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""
        
        for paragraph in paragraphs:
            if len(current_chunk + paragraph) <= self.chunk_size:
                current_chunk += paragraph + '\n\n'
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = paragraph + '\n\n'
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        # 大きすぎるチャンクを再分割
        final_chunks = []
        for chunk in chunks:
            if len(chunk) <= self.chunk_size:
                final_chunks.append(chunk)
            else:
                sub_chunks = self._split_by_size(chunk)
                final_chunks.extend(sub_chunks)
        
        return final_chunks
    
    def _split_by_size(self, text: str) -> List[str]:
        """文字数ベースでの強制分割"""
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            
            if end >= len(text):
                break
                
            start = end - self.overlap
        
        return chunks
```

## APIルーター

### URL処理エンドポイント
```python
# routers/process.py
from fastapi import APIRouter, Depends, HTTPException
from ..models.request import ProcessUrlRequest
from ..models.response import ProcessUrlResponse
from ..services.url_processor import UrlProcessorService

router = APIRouter(prefix="/api/v1", tags=["process"])

@router.post("/process-url", response_model=ProcessUrlResponse)
async def process_url(
    request: ProcessUrlRequest,
    processor: UrlProcessorService = Depends()
):
    """URL処理エンドポイント"""
    try:
        result = await processor.process_url(
            url=str(request.url),
            memo=request.memo
        )
        return ProcessUrlResponse(**result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

この設計により、各責務が明確に分離され、テスタブルで保守しやすいアーキテクチャが実現できます。