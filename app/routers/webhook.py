"""GitHub Webhook router.

This module handles incoming GitHub webhook requests, including signature
verification, event filtering, and triggering the auto-fix workflow.
"""

import hashlib
import hmac
import logging
from typing import Annotated, Any

from fastapi import BackgroundTasks, Depends, Header, HTTPException, Request, Response
from fastapi.routing import APIRouter

from app.config import get_settings
from app.models.webhook import AutoFixContext, IssueCommentPayload, WebhookResponse
from app.services.github_auth import get_auth_manager

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


async def process_auto_fix(context: AutoFixContext) -> None:
    """Background task to process the auto-fix workflow.

    This function will be expanded in Phase 2-4 to include:
    - Fetching relevant source files via GitHub API
    - Analyzing the traceback with Claude AI
    - Generating and submitting a fix PR

    Args:
        context: The auto-fix context containing all necessary information.
    """
    logger.info(
        "Starting auto-fix for %s/%s issue #%d",
        context.repo_owner,
        context.repo_name,
        context.issue_number,
    )

    # TODO: Phase 2-4 implementation
    # 1. Get installation token
    # 2. Fetch issue details and traceback
    # 3. Analyze with Claude AI
    # 4. Create fix PR via GitHub API

    logger.info(
        "Auto-fix completed for %s/%s issue #%d",
        context.repo_owner,
        context.repo_name,
        context.issue_number,
    )


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
            "Invalid webhook signature for delivery %s",
            x_github_delivery,
        )
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse JSON payload
    try:
        payload_data = await request.json()
    except Exception as e:
        logger.error("Failed to parse webhook payload: %s", e)
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Log the received event
    logger.info(
        "Received webhook event: %s, delivery: %s",
        x_github_event,
        x_github_delivery,
    )

    # Filter: Only process issue_comment events
    if x_github_event != "issue_comment":
        return WebhookResponse(
            status="ignored",
            message=f"Event type '{x_github_event}' is not supported",
            details={"event": x_github_event},
        )

    # Parse as IssueCommentPayload
    try:
        payload = IssueCommentPayload.model_validate(payload_data)
    except Exception as e:
        logger.error("Failed to parse issue_comment payload: %s", e)
        return WebhookResponse(
            status="error",
            message="Failed to parse payload",
            details={"error": str(e)},
        )

    # Filter: Only process 'created' action
    if payload.action != "created":
        return WebhookResponse(
            status="ignored",
            message=f"Action '{payload.action}' is not supported",
            details={"action": payload.action},
        )

    # Filter: Check for @auto-fix trigger
    if not payload.has_auto_fix_trigger():
        return WebhookResponse(
            status="ignored",
            message="No @auto-fix trigger found in comment",
            details={"comment_body": payload.comment.body[:100]},
        )

    # Check if installation exists
    if not payload.installation:
        logger.warning("No installation found in payload")
        return WebhookResponse(
            status="error",
            message="No GitHub App installation found",
        )

    # Create auto-fix context
    context = AutoFixContext.from_payload(payload)

    logger.info(
        "Queuing auto-fix for %s/%s issue #%d",
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
