"""GitHub Webhook router.

This module handles incoming GitHub webhook requests, including signature
verification, event filtering, and triggering the auto-fix workflow.
"""

import hashlib
import hmac
import logging
from typing import Annotated

import httpx
from fastapi import BackgroundTasks, Header, HTTPException, Request
from fastapi.routing import APIRouter

from app.config import get_settings
from app.exceptions import AgentError, ClaudeAPIError, GitHubAPIError
from app.models.webhook import AutoFixContext, IssueCommentPayload, WebhookResponse
from app.services.agent_service import AgentService
from app.services.github_auth import get_auth_manager
from app.services.github_client import GitOpsClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify the HMAC signature of a webhook payload.

    Uses constant-time comparison to prevent timing attacks.

    Args:
        payload: The raw request body bytes.
        signature: The X-Hub-Signature-256 header value (format: "sha256=<hex>").
        secret: The webhook secret configured in GitHub App.

    Returns:
        True if the signature is valid, False otherwise.

    Note:
        The signature format is "sha256=<hex_digest>". We use hmac.compare_digest
        for constant-time comparison to prevent timing attacks.
    """
    if not signature.startswith("sha256="):
        return False

    expected_signature = signature[7:]  # Remove "sha256=" prefix

    # Calculate HMAC-SHA256 of the payload
    computed_signature = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(computed_signature, expected_signature)


async def _post_error_comment(
    git_client: GitOpsClient,
    issue_number: int,
    error_type: str,
    error_message: str,
) -> None:
    """Post an error comment to the issue.

    Args:
        git_client: GitOpsClient instance.
        issue_number: Issue number.
        error_type: Type of error (e.g., "GitHub API Error").
        error_message: Error message.
    """
    try:
        await git_client.create_issue_comment(
            issue_number,
            f"❌ **自动修复失败**\n\n"
            f"**错误类型**: {error_type}\n\n"
            f"**错误详情**:\n```\n{error_message}\n```\n\n"
            f"请检查 Issue 内容或联系管理员。",
        )
    except Exception as e:
        logger.error("Failed to post error comment: %s", e)


async def process_auto_fix(context: AutoFixContext) -> None:
    """Background task to process the auto-fix workflow.

    This function orchestrates the complete auto-fix pipeline:
    1. Get installation token for GitHub API access
    2. Initialize GitOpsClient and AgentService
    3. Run AI-powered bug analysis and fix generation
    4. Create fix PR via GitHub Git Database API
    5. Handle errors and notify users via comments

    Args:
        context: The auto-fix context containing all necessary information.
    """
    logger.info(
        "[AutoFix] Starting workflow for %s/%s issue #%d",
        context.repo_owner,
        context.repo_name,
        context.issue_number,
    )

    auth_manager = get_auth_manager()
    git_client: GitOpsClient | None = None
    http_client: httpx.AsyncClient | None = None

    try:
        # Step 1: Get installation token
        logger.info(
            "[AutoFix] Step 1/4: Getting installation token for installation %d",
            context.installation_id,
        )
        token = await auth_manager.get_installation_token(context.installation_id)

        # Step 2: Create GitOpsClient
        logger.info("[AutoFix] Step 2/4: Initializing GitOpsClient")
        http_client = httpx.AsyncClient(timeout=120.0)
        git_client = GitOpsClient(
            token=token,
            owner=context.repo_owner,
            repo=context.repo_name,
            http_client=http_client,
        )

        # Step 3: Create AgentService
        logger.info("[AutoFix] Step 3/4: Initializing AgentService")
        agent_service = AgentService(git_client=git_client)

        # Define comment callback
        async def post_comment(body: str) -> None:
            """Post a comment to the issue."""
            try:
                await git_client.create_issue_comment(context.issue_number, body)
            except GitHubAPIError as e:
                logger.warning("Failed to post comment: %s", e)

        # Step 4: Run the AI auto-fix workflow
        logger.info("[AutoFix] Step 4/4: Running AI auto-fix workflow")
        result = await agent_service.run_auto_fix_workflow(
            repo_owner=context.repo_owner,
            repo_name=context.repo_name,
            issue_number=context.issue_number,
            issue_title=context.issue_title,
            issue_body=context.issue_body or "",
            comment_callback=post_comment,
        )

        if result.success:
            logger.info(
                "[AutoFix] ✅ Completed successfully for %s/%s issue #%d - PR: %s",
                context.repo_owner,
                context.repo_name,
                context.issue_number,
                result.pr_url,
            )
        else:
            logger.error(
                "[AutoFix] ❌ Failed for %s/%s issue #%d: %s",
                context.repo_owner,
                context.repo_name,
                context.issue_number,
                result.error,
            )
            # Post error comment if agent didn't already
            if result.error and git_client:
                await _post_error_comment(
                    git_client,
                    context.issue_number,
                    "Agent Error",
                    result.error,
                )

    except GitHubAPIError as e:
        logger.error(
            "[AutoFix] GitHub API error: %s - %s",
            e.message,
            e.details,
        )
        # Try to post error comment
        if git_client:
            await _post_error_comment(
                git_client,
                context.issue_number,
                "GitHub API Error",
                e.message,
            )

    except ClaudeAPIError as e:
        logger.error(
            "[AutoFix] Claude API error: %s",
            e.message,
        )
        # Try to post error comment
        if git_client:
            await _post_error_comment(
                git_client,
                context.issue_number,
                "AI API Error",
                e.message,
            )

    except AgentError as e:
        logger.error(
            "[AutoFix] Agent error: %s",
            e.message,
        )
        # Try to post error comment
        if git_client:
            await _post_error_comment(
                git_client,
                context.issue_number,
                "Agent Error",
                e.message,
            )

    except Exception as e:
        logger.exception(
            "[AutoFix] Unexpected error for %s/%s issue #%d: %s",
            context.repo_owner,
            context.repo_name,
            context.issue_number,
            str(e),
        )
        # Try to post error comment
        if git_client:
            await _post_error_comment(
                git_client,
                context.issue_number,
                "Unexpected Error",
                str(e),
            )

    finally:
        # Close HTTP client
        if http_client:
            await http_client.aclose()


@router.post("", response_model=WebhookResponse)
async def handle_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: Annotated[str, Header()],
    x_hub_signature_256: Annotated[str, Header()],
    x_github_delivery: Annotated[str, Header()],
) -> WebhookResponse:
    """Handle incoming GitHub webhook requests.

    This endpoint:
    1. Verifies the HMAC signature
    2. Filters for issue_comment.created events
    3. Checks for @auto-fix trigger in comment body
    4. Queues background processing

    Args:
        request: The FastAPI request object.
        background_tasks: FastAPI background tasks manager.
        x_github_event: GitHub event type header.
        x_hub_signature_256: HMAC signature header.
        x_github_delivery: Unique delivery ID header.

    Returns:
        WebhookResponse indicating whether the event was accepted or ignored.

    Raises:
        HTTPException: 401 if signature verification fails.
        HTTPException: 400 if payload parsing fails.
    """
    # Get raw request body for signature verification
    payload_bytes = await request.body()

    # Get webhook secret from settings
    settings = get_settings()

    # Verify webhook signature
    if not verify_webhook_signature(
        payload_bytes,
        x_hub_signature_256,
        settings.github_webhook_secret,
    ):
        logger.warning(
            "[Webhook] Invalid signature for delivery %s",
            x_github_delivery,
        )
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse JSON payload
    try:
        payload_data = await request.json()
    except Exception as e:
        logger.error("[Webhook] Failed to parse payload: %s", e)
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Log the received event
    logger.info(
        "[Webhook] Received event: %s, delivery: %s",
        x_github_event,
        x_github_delivery,
    )

    # Filter: Only process issue_comment events
    if x_github_event != "issue_comment":
        logger.debug("[Webhook] Ignoring non-issue_comment event: %s", x_github_event)
        return WebhookResponse(
            status="ignored",
            message=f"Event type '{x_github_event}' is not supported",
            details={"event": x_github_event},
        )

    # Parse as IssueCommentPayload
    try:
        payload = IssueCommentPayload.model_validate(payload_data)
    except Exception as e:
        logger.error("[Webhook] Failed to parse issue_comment payload: %s", e)
        return WebhookResponse(
            status="error",
            message="Failed to parse payload",
            details={"error": str(e)},
        )

    # Filter: Only process 'created' action
    if payload.action != "created":
        logger.debug("[Webhook] Ignoring non-created action: %s", payload.action)
        return WebhookResponse(
            status="ignored",
            message=f"Action '{payload.action}' is not supported",
            details={"action": payload.action},
        )

    # Filter: Check for @auto-fix trigger
    if not payload.has_auto_fix_trigger():
        logger.debug("[Webhook] No @auto-fix trigger found")
        return WebhookResponse(
            status="ignored",
            message="No @auto-fix trigger found in comment",
            details={"comment_body": payload.comment.body[:100]},
        )

    # Filter: Check user authorization
    # Only allow OWNER, COLLABORATOR, and MEMBER to trigger auto-fix
    ALLOWED_ROLES = {"OWNER", "COLLABORATOR", "MEMBER", "ORGANIZATION_MEMBER"}
    author_association = payload.comment.author_association.upper()

    if author_association not in ALLOWED_ROLES:
        logger.warning(
            "[Webhook] Unauthorized user: %s (role: %s)",
            payload.comment.user.login,
            author_association,
        )
        return WebhookResponse(
            status="ignored",
            message="Unauthorized: Only repository owners and collaborators can trigger auto-fix",
            details={"author_association": author_association},
        )

    logger.info(
        "[Webhook] Authorized user: %s (role: %s)",
        payload.comment.user.login,
        author_association,
    )

    # Check if installation exists
    if not payload.installation:
        logger.warning("[Webhook] No installation found in payload")
        return WebhookResponse(
            status="error",
            message="No GitHub App installation found",
        )

    # Create auto-fix context
    context = AutoFixContext.from_payload(payload)

    logger.info(
        "[Webhook] ✅ Queuing auto-fix for %s/%s issue #%d",
        context.repo_owner,
        context.repo_name,
        context.issue_number,
    )

    # Queue background processing
    background_tasks.add_task(process_auto_fix, context)

    return WebhookResponse(
        status="accepted",
        message="Auto-fix request accepted and queued for processing",
        details={
            "repo": f"{context.repo_owner}/{context.repo_name}",
            "issue_number": context.issue_number,
        },
    )


@router.get("/health", response_model=dict[str, str])
async def health_check() -> dict[str, str]:
    """Health check endpoint for monitoring.

    Returns:
        A simple health status dictionary.
    """
    return {"status": "healthy"}
