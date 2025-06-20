"""LLM service for summary and keyword generation."""

import json
from typing import Any

from litellm import completion

from ..config import settings
from ..repositories.file_repository import FileRepository
from ..utils.exceptions import LLMServiceError


class LLMService:
    """LLM処理サービス."""

    def __init__(self, file_repo: FileRepository, api_key: str = None):
        """初期化.

        Args:
            file_repo: ファイルリポジトリ
            api_key: Google API キー
        """
        self.file_repo = file_repo
        self.api_key = api_key or settings.GOOGLE_API_KEY

    async def generate_summary_keywords(self, page_id: int) -> dict[str, Any]:
        """要約とキーワード生成.

        Args:
            page_id: ページID

        Returns:
            要約とキーワードを含む辞書

        Raises:
            LLMServiceError: LLM処理エラー
        """
        if not self.api_key:
            raise LLMServiceError("Google API key is not configured")

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
                temperature=0.3,
            )

            # JSON解析
            result = json.loads(response.choices[0].message.content)

            # 結果検証
            if (
                not isinstance(result, dict)
                or "summary" not in result
                or "keywords" not in result
            ):
                raise LLMServiceError("Invalid LLM response format")

            if not isinstance(result["keywords"], list):
                raise LLMServiceError("Keywords must be a list")

            return result

        except json.JSONDecodeError as e:
            raise LLMServiceError(f"Failed to parse LLM response as JSON: {str(e)}")
        except Exception as e:
            raise LLMServiceError(f"LLM processing error: {str(e)}")

    def _build_prompt(self, title: str, content: str) -> str:
        """プロンプト構築.

        Args:
            title: ページタイトル
            content: ページコンテンツ

        Returns:
            構築されたプロンプト
        """
        return f"""以下のWebページの内容を分析して、要約とキーワードを生成してください。

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
- 重複は避ける"""
