"""Custom exceptions."""


class GrimoireAPIError(Exception):
    """Base exception for Grimoire API."""

    pass


class ResourceNotFoundError(GrimoireAPIError):
    """A requested API resource does not exist."""

    code = "not_found"


class ResourceConflictError(GrimoireAPIError):
    """A request conflicts with the current resource state."""

    code = "conflict"


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


class DuplicateUrlError(DatabaseError):
    """A page URL conflicts with an existing page."""


class FileOperationError(GrimoireAPIError):
    """File operation error."""

    pass


class RepairDeletionConflictError(GrimoireAPIError):
    """Repair page cannot be deleted in its current state."""


class RepairDeletionError(GrimoireAPIError):
    """Repair page deletion failed and may be retried."""
