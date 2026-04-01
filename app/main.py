"""FastAPI application entry point for log2pr.

This module creates and configures the FastAPI application instance,
registers routers, and sets up middleware.
"""

import logging
import sys
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import webhook


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for different log levels."""

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with colors.

        Args:
            record: Log record to format.

        Returns:
            Formatted log string.
        """
        # Get color for log level
        color = self.COLORS.get(record.levelname, "")

        # Format timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        # Build log message
        log_message = (
            f"\033[90m{timestamp}\033[0m "  # Gray timestamp
            f"{color}{record.levelname:8}{self.RESET} "  # Colored level
            f"\033[94m{record.name}\033[0m - "  # Blue logger name
            f"{record.getMessage()}"  # Message
        )

        # Add exception info if present
        if record.exc_info:
            log_message += "\n" + self.formatException(record.exc_info)

        return log_message


def setup_logging(debug: bool = False) -> None:
    """Configure application logging.

    Args:
        debug: Enable debug level logging.
    """
    # Set log level
    log_level = logging.DEBUG if debug else logging.INFO

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add colored console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(ColoredFormatter())
    root_logger.addHandler(console_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


# Configure logging
settings = get_settings()
setup_logging(settings.debug)

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    settings = get_settings()

    app = FastAPI(
        title="log2pr",
        description="From Traceback to Pull Request in seconds. No clones, pure API magic.",
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # Configure CORS for development
    if settings.debug:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Register routers
    app.include_router(webhook.router)

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Health check endpoint for monitoring and load balancers.

        Returns:
            A simple health status dictionary.
        """
        return {"status": "healthy"}

    logger.info("🚀 log2pr application initialized")

    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
