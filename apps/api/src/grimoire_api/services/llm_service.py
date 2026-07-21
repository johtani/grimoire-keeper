"""LLM service for summary and keyword generation."""

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from litellm import acompletion, token_counter
from pydantic import ValidationError

from ..config import settings
from ..models.external import FetchedDocument, PartialSummaryResult, SummaryResult
from ..repositories.file_repository import FileRepository
from ..utils.exceptions import LLMServiceError
from .chunking_service import ChunkingService

logger = logging.getLogger(__name__)


class LLMService:
    """LLM処理サービス."""

    def __init__(
        self,
        file_repo: FileRepository,
        api_key: str | None = None,
        chunking_service: ChunkingService | None = None,
    ):
        """初期化."""
        self.file_repo = file_repo
        self.api_key = api_key or settings.LLM_API_KEY
        self.input_token_limit = (
            settings.LLM_CONTEXT_WINDOW - settings.LLM_MAX_OUTPUT_TOKENS
        )
        if self.input_token_limit <= 0:
            raise LLMServiceError(
                "LLM_MAX_OUTPUT_TOKENS must be smaller than LLM_CONTEXT_WINDOW"
            )
        if settings.LLM_SUMMARY_CONCURRENCY <= 0:
            raise LLMServiceError("LLM_SUMMARY_CONCURRENCY must be greater than zero")
        self.chunking_service = chunking_service
        self.semaphore = asyncio.Semaphore(settings.LLM_SUMMARY_CONCURRENCY)

    async def generate_summary_keywords(self, page_id: int) -> SummaryResult:
        """ページの長さに応じて単発または分割で要約とキーワードを生成する."""
        if not self.api_key or not self.api_key.strip():
            raise LLMServiceError("LLM API key is not configured")

        try:
            raw_jina_data = await self.file_repo.load_json_file(page_id)
            try:
                document = FetchedDocument.from_jina_response(
                    raw_jina_data, source_url=f"artifact://page/{page_id}"
                )
            except (ValidationError, ValueError, TypeError):
                raise LLMServiceError(
                    f"Invalid stored Jina response: page_id={page_id}"
                ) from None
            title = document.title
            content = document.content

            prompt = self._build_prompt(title, content)
            prompt_tokens = self._count_tokens(prompt)
            if prompt_tokens <= self.input_token_limit:
                logger.info(
                    "LLM summary mode=single page_id=%d input_tokens=%d",
                    page_id,
                    prompt_tokens,
                )
                result = await self._complete_json(prompt, require_keywords=True)
                if not isinstance(result, SummaryResult):
                    raise LLMServiceError("Invalid final LLM response type")
                return result

            return await self._generate_chunked(page_id, title, document)
        except LLMServiceError:
            raise
        except Exception as e:
            raise LLMServiceError(f"LLM processing error: {str(e)}") from e

    async def _generate_chunked(
        self, page_id: int, title: str, document: FetchedDocument
    ) -> SummaryResult:
        """本文を部分要約し、必要なら階層的に縮約して最終結果を生成する."""
        chunking_service = self.chunking_service or ChunkingService(
            chunk_size=max(1, self.input_token_limit // 2)
        )
        raw_chunks = chunking_service.chunk_document(document)
        chunks: list[str] = []
        for chunk in raw_chunks:
            if chunk.strip():
                chunks.extend(
                    self._split_to_fit(
                        chunk,
                        lambda value: self._build_partial_prompt(title, value),
                    )
                )
        if not chunks:
            raise LLMServiceError(f"No summary chunks generated: page_id={page_id}")

        logger.info(
            "LLM summary mode=chunked page_id=%d chunk_count=%d",
            page_id,
            len(chunks),
        )
        summaries = await self._summarize_chunks(page_id, title, chunks)
        level = 0
        while self._count_tokens(self._build_final_prompt(title, summaries)) > (
            self.input_token_limit
        ):
            level += 1
            if level > 20:
                raise LLMServiceError(
                    f"Could not reduce summaries within token limit: page_id={page_id}"
                )
            summaries = await self._reduce_summaries(page_id, title, summaries, level)
            logger.info(
                "LLM summary reduction page_id=%d level=%d summary_count=%d",
                page_id,
                level,
                len(summaries),
            )

        result = await self._complete_json(
            self._build_final_prompt(title, summaries), require_keywords=True
        )
        if not isinstance(result, SummaryResult):
            raise LLMServiceError("Invalid final LLM response type")
        return result

    async def _summarize_chunks(
        self, page_id: int, title: str, chunks: list[str]
    ) -> list[str]:
        async def summarize(index: int, chunk: str) -> str:
            try:
                result = await self._complete_json(
                    self._build_partial_prompt(title, chunk), require_keywords=False
                )
                return result.summary
            except Exception as e:
                raise LLMServiceError(
                    "Partial summary failed: "
                    f"page_id={page_id}, chunk={index + 1}/{len(chunks)}, cause={e}"
                ) from e

        return list(
            await asyncio.gather(
                *(summarize(index, chunk) for index, chunk in enumerate(chunks))
            )
        )

    async def _reduce_summaries(
        self, page_id: int, title: str, summaries: list[str], level: int
    ) -> list[str]:
        pieces: list[str] = []
        for summary in summaries:
            pieces.extend(
                self._split_to_fit(
                    summary,
                    lambda value: self._build_reduction_prompt(title, [value]),
                )
            )
        groups = self._group_to_fit(
            pieces, lambda values: self._build_reduction_prompt(title, values)
        )

        async def reduce_group(index: int, group: list[str]) -> str:
            try:
                result = await self._complete_json(
                    self._build_reduction_prompt(title, group),
                    require_keywords=False,
                )
                return result.summary
            except Exception as e:
                raise LLMServiceError(
                    "Summary reduction failed: "
                    f"page_id={page_id}, level={level}, "
                    f"group={index + 1}/{len(groups)}, "
                    f"cause={e}"
                ) from e

        return list(
            await asyncio.gather(
                *(reduce_group(index, group) for index, group in enumerate(groups))
            )
        )

    def _split_to_fit(
        self, text: str, prompt_builder: Callable[[str], str]
    ) -> list[str]:
        """プロンプトが入力予算に収まるまで文字境界で安全に二分する."""
        if self._count_tokens(prompt_builder(text)) <= self.input_token_limit:
            return [text]
        if len(text) <= 1:
            raise LLMServiceError("Prompt overhead exceeds LLM input token limit")
        midpoint = len(text) // 2
        return self._split_to_fit(text[:midpoint], prompt_builder) + self._split_to_fit(
            text[midpoint:], prompt_builder
        )

    def _group_to_fit(
        self,
        values: list[str],
        prompt_builder: Callable[[list[str]], str],
    ) -> list[list[str]]:
        """順序を保ったまま入力予算内のグループにまとめる."""
        groups: list[list[str]] = []
        current: list[str] = []
        for value in values:
            candidate = [*current, value]
            if current and self._count_tokens(prompt_builder(candidate)) > (
                self.input_token_limit
            ):
                groups.append(current)
                current = [value]
            else:
                current = candidate
        if current:
            groups.append(current)
        return groups

    async def _complete_json(
        self, prompt: str, *, require_keywords: bool
    ) -> PartialSummaryResult | SummaryResult:
        """上限を検証してLLMを呼び、JSON応答を検証する."""
        input_tokens = self._count_tokens(prompt)
        if input_tokens > self.input_token_limit:
            raise LLMServiceError(
                f"LLM input token limit exceeded: {input_tokens} > "
                f"{self.input_token_limit}"
            )

        kwargs: dict[str, Any] = {
            "model": settings.LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "api_key": self.api_key,
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
            "max_tokens": settings.LLM_MAX_OUTPUT_TOKENS,
        }
        if settings.LLM_API_BASE:
            kwargs["api_base"] = settings.LLM_API_BASE

        try:
            async with self.semaphore:
                response = await acompletion(**kwargs)
        except Exception:
            raise LLMServiceError("LLM request failed") from None
        try:
            response_dict = response.model_dump()
            response_content = str(response_dict["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, AttributeError):
            raise LLMServiceError(
                "Failed to extract content from LLM response"
            ) from None
        if not response_content.strip():
            raise LLMServiceError("Empty response from LLM")

        try:
            result = json.loads(response_content)
        except json.JSONDecodeError:
            raise LLMServiceError("Failed to parse LLM response as JSON") from None
        try:
            model = SummaryResult if require_keywords else PartialSummaryResult
            return model.model_validate(result)
        except ValidationError as e:
            fields = sorted(
                {str(error["loc"][-1]) for error in e.errors() if error.get("loc")}
            )
            detail = f": {', '.join(fields)}" if fields else ""
            raise LLMServiceError(f"Invalid LLM response format{detail}") from None

    def _count_tokens(self, prompt: str) -> int:
        """モデルのトークナイザーを使い、失敗時はUTF-8バイト数で安全側に推定する."""
        try:
            return (
                int(
                    token_counter(
                        model=settings.LLM_MODEL,
                        text=prompt,
                        default_token_count=len(prompt.encode("utf-8")),
                    )
                )
                + 16
            )
        except Exception as e:
            estimated = len(prompt.encode("utf-8")) + 16
            logger.warning(
                "Token counting failed; using conservative estimate=%d: %s",
                estimated,
                e,
            )
            return estimated

    def _build_prompt(self, title: str, content: str) -> str:
        """単発要約プロンプトを構築する."""
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

    def _build_partial_prompt(self, title: str, content: str) -> str:
        """部分要約プロンプトを構築する."""
        return f"""Webページ「{title}」の以下の部分を要約してください。
後でページ全体を統合できるよう、重要な事実・固有名詞・論旨を保持してください。

内容:
{content}

次のJSON形式で回答してください:
{{"summary": "部分要約"}}"""

    def _build_reduction_prompt(self, title: str, summaries: list[str]) -> str:
        """中間要約を縮約するプロンプトを構築する."""
        ordered = "\n\n".join(
            f"[{index + 1}] {summary}" for index, summary in enumerate(summaries)
        )
        return f"""Webページ「{title}」の連続した部分要約を、
順序と重要事項を保って統合してください。

部分要約:
{ordered}

次のJSON形式で回答してください:
{{"summary": "統合した部分要約"}}"""

    def _build_final_prompt(self, title: str, summaries: list[str]) -> str:
        """最終統合プロンプトを構築する."""
        ordered = "\n\n".join(
            f"[{index + 1}] {summary}" for index, summary in enumerate(summaries)
        )
        return f"""以下はWebページ「{title}」を先頭から順に分割した部分要約です。
順序とページ全体の論旨を維持して、最終要約とキーワードを生成してください。

部分要約:
{ordered}

次のJSON形式で回答してください:
{{
  "summary": "ページ全体の要約（200文字程度）",
  "keywords": ["キーワード1", "キーワード2", ..., "キーワード20"]
}}

- 要約は内容の要点を200文字程度でまとめる
- キーワードは検索に有用な重要語を重複なく20個生成する"""
