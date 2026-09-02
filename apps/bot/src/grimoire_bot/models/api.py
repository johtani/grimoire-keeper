"""Validated models for responses consumed from the backend API."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class ProcessStatus(str, Enum):
    """Statuses exposed by the process-status endpoint."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    ERROR = "error"


class ProcessStatusPage(BaseModel):
    """Page data nested in a process-status response."""

    model_config = ConfigDict(extra="forbid")

    id: int
    url: str
    title: str
    memo: str | None
    summary: str | None
    keywords: list[str]
    created_at: datetime


class ProcessStatusResponse(BaseModel):
    """Consumer contract for GET /api/v1/process-status/{page_id}."""

    model_config = ConfigDict(extra="forbid")

    status: ProcessStatus
    message: str
    page: ProcessStatusPage | None = None
