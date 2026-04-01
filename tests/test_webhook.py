"""Unit tests for webhook functionality.

This module contains tests for:
- HMAC signature verification
- Webhook event filtering
- Auto-fix trigger detection
"""

import hashlib
import hmac
import os
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.routers.webhook import verify_webhook_signature


# Test constants
TEST_SECRET = "test_webhook_secret"
TEST_APP_ID = "12345"
TEST_ANTHROPIC_TOKEN = "test_token"


@pytest.fixture(autouse=True)
def setup_env() -> Generator[None, None, None]:
    """Set up environment variables for all tests."""
    # Set required environment variables
    os.environ["GITHUB_APP_ID"] = TEST_APP_ID
    os.environ["GITHUB_WEBHOOK_SECRET"] = TEST_SECRET
    os.environ["ANTHROPIC_AUTH_TOKEN"] = TEST_ANTHROPIC_TOKEN
    os.environ["DEBUG"] = "true"

    # Clear the settings cache
    get_settings.cache_clear()

    yield

    # Cleanup
    os.environ.pop("GITHUB_APP_ID", None)
    os.environ.pop("GITHUB_WEBHOOK_SECRET", None)
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
    os.environ.pop("DEBUG", None)
    get_settings.cache_clear()


@pytest.fixture
def test_client() -> TestClient:
    """Create a test client for the FastAPI app."""
    from app.main import create_app

    app = create_app()
    return TestClient(app)


@pytest.fixture
def settings() -> Settings:
    """Get the current settings."""
    return get_settings()


class TestWebhookSignatureVerification:
    """Tests for HMAC signature verification."""

    def test_valid_signature(self) -> None:
        """Test that valid signature is accepted."""
        secret = "test_secret"
        payload = b'{"test": "data"}'

        # Generate valid signature
        expected_sig = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        signature = f"sha256={expected_sig}"

        assert verify_webhook_signature(payload, signature, secret) is True

    def test_invalid_signature(self) -> None:
        """Test that invalid signature is rejected."""
        secret = "test_secret"
        payload = b'{"test": "data"}'
        signature = "sha256=invalid_signature"

        assert verify_webhook_signature(payload, signature, secret) is False

    def test_missing_sha256_prefix(self) -> None:
        """Test that signature without sha256 prefix is rejected."""
        secret = "test_secret"
        payload = b'{"test": "data"}'
        signature = "invalid_signature_without_prefix"

        assert verify_webhook_signature(payload, signature, secret) is False

    def test_wrong_secret(self) -> None:
        """Test that signature with wrong secret is rejected."""
        secret = "correct_secret"
        payload = b'{"test": "data"}'

        # Generate signature with wrong secret
        wrong_sig = hmac.new(
            b"wrong_secret",
            payload,
            hashlib.sha256,
        ).hexdigest()
        signature = f"sha256={wrong_sig}"

        assert verify_webhook_signature(payload, signature, secret) is False

    def test_empty_payload(self) -> None:
        """Test that empty payload works correctly."""
        secret = "test_secret"
        payload = b""

        expected_sig = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        signature = f"sha256={expected_sig}"

        assert verify_webhook_signature(payload, signature, secret) is True


class TestWebhookEndpoint:
    """Tests for webhook endpoint."""

    def _generate_signature(self, payload: bytes, secret: str) -> str:
        """Generate a valid HMAC signature for testing."""
        sig = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return f"sha256={sig}"

    def test_health_check(self, test_client: TestClient) -> None:
        """Test health check endpoint."""
        response = test_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    def test_invalid_signature_rejected(self, test_client: TestClient) -> None:
        """Test that requests with invalid signatures are rejected."""
        payload = b'{"test": "data"}'

        response = test_client.post(
            "/webhook",
            content=payload,
            headers={
                "X-GitHub-Event": "issue_comment",
                "X-Hub-Signature-256": "sha256=invalid",
                "X-GitHub-Delivery": "test-delivery-id",
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 401

    def test_non_issue_comment_event_ignored(
        self,
        test_client: TestClient,
        settings: Settings,
    ) -> None:
        """Test that non issue_comment events are ignored."""
        payload = b'{"test": "data"}'
        signature = self._generate_signature(payload, settings.github_webhook_secret)

        response = test_client.post(
            "/webhook",
            content=payload,
            headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": signature,
                "X-GitHub-Delivery": "test-delivery-id",
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"
        assert "push" in data["message"]

    def test_non_created_action_ignored(
        self,
        test_client: TestClient,
        settings: Settings,
    ) -> None:
        """Test that non 'created' actions are ignored."""
        payload = b'''{
            "action": "edited",
            "issue": {"id": 1, "number": 42, "title": "Test", "state": "open", "user": {"id": 1, "login": "test"}, "html_url": "https://github.com/test/repo/issues/42"},
            "comment": {"id": 1, "body": "@auto-fix", "user": {"id": 1, "login": "test"}, "html_url": "https://github.com/test/repo/issues/42#issuecomment-1"},
            "repository": {"id": 1, "name": "repo", "full_name": "test/repo", "owner": {"id": 1, "login": "test"}, "private": false},
            "sender": {"id": 1, "login": "test"}
        }'''
        signature = self._generate_signature(payload, settings.github_webhook_secret)

        response = test_client.post(
            "/webhook",
            content=payload,
            headers={
                "X-GitHub-Event": "issue_comment",
                "X-Hub-Signature-256": signature,
                "X-GitHub-Delivery": "test-delivery-id",
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"
        assert "edited" in data["message"]

    def test_no_auto_fix_trigger_ignored(
        self,
        test_client: TestClient,
        settings: Settings,
    ) -> None:
        """Test that comments without @auto-fix are ignored."""
        payload = b'''{
            "action": "created",
            "issue": {"id": 1, "number": 42, "title": "Test", "state": "open", "user": {"id": 1, "login": "test"}, "html_url": "https://github.com/test/repo/issues/42"},
            "comment": {"id": 1, "body": "This is a regular comment", "user": {"id": 1, "login": "test"}, "html_url": "https://github.com/test/repo/issues/42#issuecomment-1"},
            "repository": {"id": 1, "name": "repo", "full_name": "test/repo", "owner": {"id": 1, "login": "test"}, "private": false},
            "sender": {"id": 1, "login": "test"}
        }'''
        signature = self._generate_signature(payload, settings.github_webhook_secret)

        response = test_client.post(
            "/webhook",
            content=payload,
            headers={
                "X-GitHub-Event": "issue_comment",
                "X-Hub-Signature-256": signature,
                "X-GitHub-Delivery": "test-delivery-id",
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"
        assert "@auto-fix" in data["message"]

    def test_valid_auto_fix_request_accepted(
        self,
        test_client: TestClient,
        settings: Settings,
    ) -> None:
        """Test that valid @auto-fix requests are accepted."""
        payload = b'''{
            "action": "created",
            "issue": {"id": 1, "number": 42, "title": "Test Issue", "state": "open", "user": {"id": 1, "login": "test"}, "html_url": "https://github.com/test/repo/issues/42"},
            "comment": {"id": 1, "body": "@auto-fix please help", "user": {"id": 1, "login": "test"}, "html_url": "https://github.com/test/repo/issues/42#issuecomment-1", "author_association": "OWNER"},
            "repository": {"id": 1, "name": "repo", "full_name": "test/repo", "owner": {"id": 1, "login": "test"}, "private": false},
            "installation": {"id": 12345},
            "sender": {"id": 1, "login": "test"}
        }'''
        signature = self._generate_signature(payload, settings.github_webhook_secret)

        response = test_client.post(
            "/webhook",
            content=payload,
            headers={
                "X-GitHub-Event": "issue_comment",
                "X-Hub-Signature-256": signature,
                "X-GitHub-Delivery": "test-delivery-id",
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["details"]["issue_number"] == 42


class TestIssueCommentPayload:
    """Tests for IssueCommentPayload model."""

    def test_has_auto_fix_trigger_found(self) -> None:
        """Test that @auto-fix is detected in comment body."""
        from app.models.webhook import Comment, Issue, IssueCommentPayload, Repository, User

        payload = IssueCommentPayload(
            action="created",
            issue=Issue(
                id=1,
                number=42,
                title="Test",
                user=User(id=1, login="test"),
                html_url="https://github.com/test/repo/issues/42",
            ),
            comment=Comment(
                id=1,
                body="@auto-fix please help",
                user=User(id=1, login="test"),
                html_url="https://github.com/test/repo/issues/42#issuecomment-1",
            ),
            repository=Repository(
                id=1,
                name="repo",
                full_name="test/repo",
                owner=User(id=1, login="test"),
            ),
            sender=User(id=1, login="test"),
        )

        assert payload.has_auto_fix_trigger() is True

    def test_auto_fix_case_insensitive(self) -> None:
        """Test that @auto-fix detection is case-insensitive."""
        from app.models.webhook import Comment, Issue, IssueCommentPayload, Repository, User

        payload = IssueCommentPayload(
            action="created",
            issue=Issue(
                id=1,
                number=42,
                title="Test",
                user=User(id=1, login="test"),
                html_url="https://github.com/test/repo/issues/42",
            ),
            comment=Comment(
                id=1,
                body="@AUTO-FIX please help",
                user=User(id=1, login="test"),
                html_url="https://github.com/test/repo/issues/42#issuecomment-1",
            ),
            repository=Repository(
                id=1,
                name="repo",
                full_name="test/repo",
                owner=User(id=1, login="test"),
            ),
            sender=User(id=1, login="test"),
        )

        assert payload.has_auto_fix_trigger() is True

    def test_no_auto_fix_trigger(self) -> None:
        """Test that comments without @auto-fix return False."""
        from app.models.webhook import Comment, Issue, IssueCommentPayload, Repository, User

        payload = IssueCommentPayload(
            action="created",
            issue=Issue(
                id=1,
                number=42,
                title="Test",
                user=User(id=1, login="test"),
                html_url="https://github.com/test/repo/issues/42",
            ),
            comment=Comment(
                id=1,
                body="Just a regular comment",
                user=User(id=1, login="test"),
                html_url="https://github.com/test/repo/issues/42#issuecomment-1",
            ),
            repository=Repository(
                id=1,
                name="repo",
                full_name="test/repo",
                owner=User(id=1, login="test"),
            ),
            sender=User(id=1, login="test"),
        )

        assert payload.has_auto_fix_trigger() is False
