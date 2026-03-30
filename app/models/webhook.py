"""GitHub Webhook event models.

This module defines Pydantic models for parsing GitHub webhook payloads,
specifically for issue_comment events.
"""

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    """GitHub user information.

    Attributes:
        id: User ID.
        login: Username.
        type: User type (User, Bot, Organization).
    """

    id: int
    login: str
    type: str = "User"


class Repository(BaseModel):
    """GitHub repository information.

    Attributes:
        id: Repository ID.
        name: Repository name.
        full_name: Full repository name (owner/repo).
        owner: Repository owner.
        private: Whether the repository is private.
    """

    id: int
    name: str
    full_name: str
    owner: User
    private: bool = False


class Issue(BaseModel):
    """GitHub issue information.

    Attributes:
        id: Issue ID.
        number: Issue number.
        title: Issue title.
        body: Issue body/content.
        state: Issue state (open, closed).
        user: Issue author.
        html_url: URL to the issue on GitHub.
    """

    id: int
    number: int
    title: str
    body: Optional[str] = None
    state: str = "open"
    user: User
    html_url: str


class Comment(BaseModel):
    """GitHub issue comment information.

    Attributes:
        id: Comment ID.
        body: Comment body/content.
        user: Comment author.
        html_url: URL to the comment on GitHub.
    """

    id: int
    body: str
    user: User
    html_url: str


class Installation(BaseModel):
    """GitHub App installation information.

    Attributes:
        id: Installation ID.
        account: Account where the app is installed.
    """

    id: int
    account: Optional[User] = None


class IssueCommentPayload(BaseModel):
    """Payload for issue_comment webhook event.

    This model represents the payload sent by GitHub when an issue comment
    is created, edited, or deleted.

    Attributes:
        action: The action that triggered the event (created, edited, deleted).
        issue: The issue the comment belongs to.
        comment: The comment that was created/edited/deleted.
        repository: The repository where the issue exists.
        installation: The GitHub App installation (if applicable).
        sender: The user who triggered the event.
    """

    action: str
    issue: Issue
    comment: Comment
    repository: Repository
    installation: Optional[Installation] = None
    sender: User

    def has_auto_fix_trigger(self) -> bool:
        """Check if the comment contains the @auto-fix trigger.

        Returns:
            True if the comment body contains '@auto-fix' (case-insensitive).
        """
        if not self.comment.body:
            return False
        return "@auto-fix" in self.comment.body.lower()

    def get_traceback_from_issue(self) -> Optional[str]:
        """Extract traceback content from the issue body.

        Returns:
            The traceback content if found, None otherwise.
        """
        if not self.issue.body:
            return None
        return self.issue.body


class WebhookHeaders(BaseModel):
    """Headers from GitHub webhook request.

    Attributes:
        x_github_event: The type of webhook event.
        x_hub_signature_256: HMAC signature for payload verification.
        x_github_delivery: Unique ID for the webhook delivery.
    """

    model_config = ConfigDict(populate_by_name=True)

    x_github_event: str = Field(alias="X-GitHub-Event")
    x_hub_signature_256: str = Field(alias="X-Hub-Signature-256")
    x_github_delivery: str = Field(alias="X-GitHub-Delivery")


class WebhookResponse(BaseModel):
    """Standard response for webhook endpoint.

    Attributes:
        status: Response status (accepted, ignored, error).
        message: Human-readable message.
        details: Additional details (optional).
    """

    status: str
    message: str
    details: Optional[dict[str, Any]] = None


class AutoFixContext(BaseModel):
    """Context for auto-fix processing.

    This model aggregates all information needed for the auto-fix flow.

    Attributes:
        installation_id: GitHub App installation ID.
        repo_owner: Repository owner login.
        repo_name: Repository name.
        issue_number: Issue number.
        issue_title: Issue title.
        issue_body: Issue body (containing traceback).
        comment_body: Comment body (containing @auto-fix).
        comment_id: Comment ID for replies.
    """

    installation_id: int
    repo_owner: str
    repo_name: str
    issue_number: int
    issue_title: str
    issue_body: Optional[str] = None
    comment_body: str
    comment_id: int

    @classmethod
    def from_payload(cls, payload: IssueCommentPayload) -> "AutoFixContext":
        """Create AutoFixContext from IssueCommentPayload.

        Args:
            payload: The issue_comment webhook payload.

        Returns:
            AutoFixContext instance with all required information.
        """
        installation_id = payload.installation.id if payload.installation else 0

        return cls(
            installation_id=installation_id,
            repo_owner=payload.repository.owner.login,
            repo_name=payload.repository.name,
            issue_number=payload.issue.number,
            issue_title=payload.issue.title,
            issue_body=payload.issue.body,
            comment_body=payload.comment.body,
            comment_id=payload.comment.id,
        )
