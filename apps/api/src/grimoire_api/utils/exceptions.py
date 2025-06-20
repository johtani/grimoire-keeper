"""Custom exceptions."""


class GrimoireAPIError(Exception):
    """Base exception for Grimoire API."""

    pass


class JinaClientError(GrimoireAPIError):
    """Jina AI Reader client error."""

    pass


class LLMServiceError(GrimoireAPIError):
    """LLM service error."""

    pass


class VectorizerError(GrimoireAPIError):
    """Vectorizer service error."""

    pass


class DatabaseError(GrimoireAPIError):
    """Database operation error."""

    pass


class FileOperationError(GrimoireAPIError):
    """File operation error."""

    pass
