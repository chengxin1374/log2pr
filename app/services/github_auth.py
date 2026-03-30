"""GitHub App authentication service.

This module provides JWT-based authentication for GitHub Apps, including
JWT generation and Installation Access Token retrieval.
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
import jwt

from app.config import get_settings


@dataclass
class CachedToken:
    """Cached installation token with expiration tracking.

    Attributes:
        token: The installation access token.
        expires_at: Unix timestamp when the token expires.
    """

    token: str
    expires_at: float


class GitHubAuthManager:
    """Manages GitHub App authentication.

    This class handles:
    - JWT generation using RSA private key
    - Installation Access Token retrieval
    - Token caching to minimize API calls

    Attributes:
        app_id: GitHub App ID.
        private_key: RSA private key in PEM format.
        webhook_secret: Secret for webhook signature verification.
        _token_cache: In-memory cache for installation tokens.
    """

    # GitHub API base URL
    GITHUB_API_URL = "https://api.github.com"

    # JWT validity duration in seconds (10 minutes as recommended by GitHub)
    JWT_EXPIRATION_SECONDS = 600

    # Token refresh buffer: refresh 60 seconds before expiration
    TOKEN_REFRESH_BUFFER_SECONDS = 60

    def __init__(
        self,
        app_id: Optional[str] = None,
        private_key_path: Optional[str] = None,
        webhook_secret: Optional[str] = None,
    ):
        """Initialize the GitHub Auth Manager.

        Args:
            app_id: GitHub App ID. If not provided, reads from settings.
            private_key_path: Path to private key file. If not provided, reads from settings.
            webhook_secret: Webhook secret. If not provided, reads from settings.

        Raises:
            FileNotFoundError: If the private key file doesn't exist.
            ValueError: If required configuration is missing.
        """
        settings = get_settings()

        self.app_id = app_id or settings.github_app_id
        self.webhook_secret = webhook_secret or settings.github_webhook_secret

        key_path = private_key_path or settings.github_app_private_key_path
        self.private_key = self._load_private_key(key_path)

        # In-memory token cache: installation_id -> CachedToken
        self._token_cache: dict[int, CachedToken] = {}

    def _load_private_key(self, key_path: str) -> str:
        """Load the RSA private key from file.

        Args:
            key_path: Path to the PEM private key file.

        Returns:
            The private key content as a string.

        Raises:
            FileNotFoundError: If the key file doesn't exist.
        """
        path = Path(key_path)
        if not path.exists():
            raise FileNotFoundError(f"Private key file not found: {key_path}")
        return path.read_text(encoding="utf-8")

    def generate_jwt(self) -> str:
        """Generate a JWT token for GitHub App authentication.

        The JWT is signed using RS256 algorithm with the app's private key.
        Token validity is set to 10 minutes as recommended by GitHub.

        Returns:
            A JWT token string.

        Raises:
            jwt.PyJWTError: If JWT generation fails.

        Note:
            GitHub requires that the JWT expires within 10 minutes.
            The token should be generated fresh for each API call.
        """
        now = int(time.time())
        payload = {
            "iss": self.app_id,  # Issuer: App ID
            "iat": now,  # Issued at: current time
            "exp": now + self.JWT_EXPIRATION_SECONDS,  # Expiration: 10 minutes from now
        }

        token = jwt.encode(
            payload,
            self.private_key,
            algorithm="RS256",
        )

        return token

    async def get_installation_token(
        self,
        installation_id: int,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> str:
        """Get an installation access token.

        This method retrieves an installation access token from GitHub API.
        Tokens are cached in memory to minimize API calls.

        Args:
            installation_id: The GitHub App installation ID.
            http_client: Optional httpx AsyncClient for making requests.
                        If not provided, a new client will be created.

        Returns:
            The installation access token.

        Raises:
            httpx.HTTPStatusError: If the API request fails.
        """
        # Check cache first
        cached = self._token_cache.get(installation_id)
        if cached:
            # Return cached token if not expiring soon
            if cached.expires_at > time.time() + self.TOKEN_REFRESH_BUFFER_SECONDS:
                return cached.token

        # Generate new token
        jwt_token = self.generate_jwt()

        url = f"{self.GITHUB_API_URL}/app/installations/{installation_id}/access_tokens"
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        # Use provided client or create a new one
        should_close_client = http_client is None
        client = http_client or httpx.AsyncClient()

        try:
            response = await client.post(url, headers=headers)
            response.raise_for_status()

            data = response.json()
            token = data["token"]
            expires_at_str = data["expires_at"]

            # Parse ISO 8601 timestamp to Unix timestamp
            # Format: "2024-01-01T00:00:00Z"
            from datetime import datetime

            expires_at_dt = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            expires_at = expires_at_dt.timestamp()

            # Cache the token
            self._token_cache[installation_id] = CachedToken(
                token=token,
                expires_at=expires_at,
            )

            return token

        finally:
            if should_close_client:
                await client.aclose()

    def clear_cache(self, installation_id: Optional[int] = None) -> None:
        """Clear the token cache.

        Args:
            installation_id: If provided, clear only this installation's token.
                           Otherwise, clear all cached tokens.
        """
        if installation_id is not None:
            self._token_cache.pop(installation_id, None)
        else:
            self._token_cache.clear()


# Global instance for convenience
_auth_manager: Optional[GitHubAuthManager] = None


def get_auth_manager() -> GitHubAuthManager:
    """Get the global GitHubAuthManager instance.

    Returns:
        GitHubAuthManager: The global authentication manager instance.

    Note:
        This function creates a new instance on first call and reuses it
        for subsequent calls. Use this for dependency injection.
    """
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = GitHubAuthManager()
    return _auth_manager
