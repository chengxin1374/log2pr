"""Custom exceptions for log2pr.

This module defines custom exceptions for GitHub API operations
and application-level error handling.
"""

from typing import Any, Optional


class Log2prError(Exception):
    """Base exception for all log2pr errors.

    Attributes:
        message: Human-readable error message.
        details: Additional context or debug information.
    """

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error message.
            details: Additional context or debug information.
        """
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        """Return string representation of the error."""
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message


class GitHubAPIError(Log2prError):
    """Base exception for GitHub API errors.

    Attributes:
        status_code: HTTP status code from the API response.
        response_body: Raw response body from the API.
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Initialize the GitHub API error.

        Args:
            message: Human-readable error message.
            status_code: HTTP status code from the API response.
            response_body: Raw response body from the API.
            details: Additional context or debug information.
        """
        self.status_code = status_code
        self.response_body = response_body
        enhanced_details = details or {}
        if status_code:
            enhanced_details["status_code"] = status_code
        if response_body:
            enhanced_details["response_body"] = response_body[:500]  # Truncate long responses
        super().__init__(message, enhanced_details)


class GitHubAuthError(GitHubAPIError):
    """Exception raised when GitHub authentication fails.

    This includes JWT generation failures, token expiration,
    and permission denied errors.
    """

    pass


class GitHubResourceNotFoundError(GitHubAPIError):
    """Exception raised when a GitHub resource is not found.

    This includes missing files, branches, repositories, etc.
    """

    pass


class GitHubBranchError(GitHubAPIError):
    """Exception raised when branch operations fail.

    This includes branch creation, deletion, and reference updates.
    """

    pass


class GitHubCommitError(GitHubAPIError):
    """Exception raised when commit operations fail.

    This includes blob creation, tree creation, and commit creation.
    """

    pass


class GitHubPRError(GitHubAPIError):
    """Exception raised when pull request operations fail.

    This includes PR creation, updates, and merges.
    """

    pass


class GitHubRateLimitError(GitHubAPIError):
    """Exception raised when GitHub API rate limit is exceeded.

    Attributes:
        reset_at: Unix timestamp when the rate limit resets.
    """

    def __init__(
        self,
        message: str = "GitHub API rate limit exceeded",
        reset_at: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the rate limit error.

        Args:
            message: Human-readable error message.
            reset_at: Unix timestamp when the rate limit resets.
            **kwargs: Additional arguments passed to parent.
        """
        self.reset_at = reset_at
        details = kwargs.pop("details", {}) or {}
        if reset_at:
            details["reset_at"] = reset_at
        super().__init__(message, details=details, **kwargs)


class ClaudeAPIError(Log2prError):
    """Exception raised when Claude API operations fail.

    Attributes:
        status_code: HTTP status code from the API response.
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Initialize the Claude API error.

        Args:
            message: Human-readable error message.
            status_code: HTTP status code from the API response.
            details: Additional context or debug information.
        """
        self.status_code = status_code
        enhanced_details = details or {}
        if status_code:
            enhanced_details["status_code"] = status_code
        super().__init__(message, enhanced_details)


class AgentError(Log2prError):
    """Exception raised when the AI agent encounters an error.

    This includes failures in analysis, code generation, and tool usage.
    """

    pass
