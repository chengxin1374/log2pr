"""Configuration management for log2pr.

This module provides type-safe configuration loading from environment variables
using pydantic-settings.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get the project root directory (where .env file is located)
PROJECT_ROOT = Path(__file__).parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All settings can be overridden via environment variables or a .env file.

    Attributes:
        github_app_id: GitHub App ID for JWT generation.
        github_app_private_key_path: Path to the GitHub App private key file.
        github_webhook_secret: Secret for verifying GitHub webhook signatures.
        anthropic_auth_token: Auth token for Claude API (Baidu Qianfan).
        anthropic_base_url: Base URL for Claude API endpoint.
        host: Server host address.
        port: Server port number.
        debug: Enable debug mode.
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # GitHub App Configuration
    github_app_id: str = Field(..., description="GitHub App ID")
    github_app_private_key_path: str = Field(
        default="keys/private_key.pem",
        description="Path to GitHub App private key file",
    )
    github_webhook_secret: str = Field(..., description="GitHub webhook secret for HMAC verification")

    # Claude API Configuration (Baidu Qianfan)
    anthropic_auth_token: str = Field(..., description="Auth token for Claude API")
    anthropic_base_url: str = Field(
        default="https://qianfan.baidubce.com/anthropic/coding",
        description="Base URL for Claude API endpoint",
    )

    # Server Configuration
    host: str = Field(default="0.0.0.0", description="Server host address")
    port: int = Field(default=8000, description="Server port number")
    debug: bool = Field(default=False, description="Enable debug mode")



@lru_cache
def get_settings() -> Settings:
    """Get cached application settings.

    Returns:
        Settings: The application settings instance.

    Note:
        This function is cached to avoid re-reading environment variables
        on every call. Use this function instead of directly instantiating
        Settings class.
    """
    return Settings()


def clear_settings_cache() -> None:
    """Clear the settings cache.

    Use this if you need to reload settings after environment changes.
    """
    get_settings.cache_clear()
