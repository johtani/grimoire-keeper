"""Custom exceptions."""


class GrimoireAPIError(Exception):
    """Base exception for Grimoire API."""

    code = "internal_error"
    public_message = "An internal error occurred"
    status_code = 500


class ResourceNotFoundError(GrimoireAPIError):
    """A requested API resource does not exist."""

    code = "not_found"
    public_message = "The requested resource was not found"
    status_code = 404


class ResourceConflictError(GrimoireAPIError):
    """A request conflicts with the current resource state."""

    code = "conflict"
    public_message = "The request conflicts with the current resource state"
    status_code = 409


class ServiceUnavailableError(GrimoireAPIError):
    """A required service is temporarily unavailable."""

    code = "service_unavailable"
    public_message = "The service is temporarily unavailable"
    status_code = 503


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
