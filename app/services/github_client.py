"""GitHub Git Database API client for in-memory Git operations.

This module provides GitOpsClient, a class that handles all Git operations
through GitHub REST API without requiring local Git installation.

IMPORTANT: All operations are performed via HTTP requests to GitHub API.
No local git commands are used.
"""

import base64
import logging
import random
import string
import time
from typing import Any, Optional

import httpx

from app.exceptions import (
    GitHubAPIError,
    GitHubBranchError,
    GitHubCommitError,
    GitHubPRError,
    GitHubRateLimitError,
    GitHubResourceNotFoundError,
)

logger = logging.getLogger(__name__)


class GitOpsClient:
    """GitHub Git Database API client for in-memory Git operations.

    This class provides methods to perform all Git operations through
    GitHub REST API, enabling Serverless deployment without local Git.

    Attributes:
        token: GitHub Installation Access Token.
        owner: Repository owner (user or organization).
        repo: Repository name.
        base_url: GitHub API base URL.
        client: httpx AsyncClient instance.
    """

    # GitHub API configuration
    GITHUB_API_URL = "https://api.github.com"
    GITHUB_API_VERSION = "2022-11-28"

    # Rate limiting
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 1.0  # seconds

    def __init__(
        self,
        token: str,
        owner: str,
        repo: str,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        """Initialize the GitOpsClient.

        Args:
            token: GitHub Installation Access Token.
            owner: Repository owner (user or organization).
            repo: Repository name.
            http_client: Optional httpx AsyncClient. If not provided,
                        a new client will be created internally.
        """
        self.token = token
        self.owner = owner
        self.repo = repo
        self.base_url = self.GITHUB_API_URL
        self._client = http_client
        self._owns_client = http_client is None

        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        """Close the HTTP client if we own it."""
        if self._owns_client and self._client:
            await self._client.aclose()

    def _get_headers(self) -> dict[str, str]:
        """Get standard headers for GitHub API requests.

        Returns:
            Dictionary of HTTP headers.
        """
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self.GITHUB_API_VERSION,
        }

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an HTTP request with retry logic for rate limiting.

        Args:
            method: HTTP method (GET, POST, etc.).
            url: Request URL.
            **kwargs: Additional arguments for httpx.

        Returns:
            HTTP response.

        Raises:
            GitHubRateLimitError: If rate limit is exceeded after retries.
            GitHubAPIError: For other API errors.
        """
        last_error: Optional[Exception] = None

        for attempt in range(self.MAX_RETRIES):
            try:
                response = await self._client.request(  # type: ignore
                    method,
                    url,
                    headers=self._get_headers(),
                    **kwargs,
                )

                # Handle rate limiting
                if response.status_code == 403:
                    remaining = response.headers.get("X-RateLimit-Remaining", "1")
                    if remaining == "0":
                        reset_at = int(response.headers.get("X-RateLimit-Reset", "0"))
                        wait_time = max(reset_at - time.time(), 0)

                        if attempt < self.MAX_RETRIES - 1:
                            logger.warning(
                                "Rate limit exceeded, waiting %.0f seconds (attempt %d/%d)",
                                wait_time,
                                attempt + 1,
                                self.MAX_RETRIES,
                            )
                            await asyncio_delay(wait_time + 1)
                            continue

                        raise GitHubRateLimitError(
                            "GitHub API rate limit exceeded",
                            reset_at=reset_at,
                            status_code=403,
                            response_body=response.text,
                        )

                # Handle other errors
                if response.status_code >= 400:
                    self._handle_error_response(response)

                return response

            except httpx.HTTPError as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAY_BASE * (2**attempt)
                    logger.warning(
                        "HTTP error, retrying in %.1f seconds: %s",
                        delay,
                        str(e),
                    )
                    await asyncio_delay(delay)

        raise GitHubAPIError(
            f"Request failed after {self.MAX_RETRIES} retries",
            details={"last_error": str(last_error)},
        )

    def _handle_error_response(self, response: httpx.Response) -> None:
        """Handle HTTP error responses and raise appropriate exceptions.

        Args:
            response: The HTTP response.

        Raises:
            GitHubResourceNotFoundError: For 404 errors.
            GitHubAPIError: For other errors.
        """
        status_code = response.status_code
        url = str(response.url)

        try:
            body = response.json()
            message = body.get("message", response.text)
        except Exception:
            body = None
            message = response.text

        logger.error(
            "GitHub API error: %d %s - %s",
            status_code,
            url,
            message,
        )

        if status_code == 404:
            raise GitHubResourceNotFoundError(
                f"Resource not found: {url}",
                status_code=status_code,
                response_body=response.text,
            )

        raise GitHubAPIError(
            f"GitHub API error: {message}",
            status_code=status_code,
            response_body=response.text,
        )

    # =========================================================================
    # File and Code Operations
    # =========================================================================

    async def get_file_content(
        self,
        file_path: str,
        ref: str = "main",
    ) -> str:
        """Get the content of a file from the repository.

        Args:
            file_path: Path to the file in the repository.
            ref: Git reference (branch, tag, or commit SHA).

        Returns:
            The file content as a string (Base64 decoded).

        Raises:
            GitHubResourceNotFoundError: If the file doesn't exist.
            GitHubAPIError: For other API errors.
        """
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/contents/{file_path}"
        params = {"ref": ref}

        logger.info("Fetching file content: %s @ %s", file_path, ref)

        response = await self._request_with_retry("GET", url, params=params)
        data = response.json()

        # Decode base64 content
        content_base64 = data.get("content", "")
        content = base64.b64decode(content_base64).decode("utf-8")

        logger.info("Successfully fetched file: %s (%d bytes)", file_path, len(content))
        return content

    async def search_code(
        self,
        query: str,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """Search for code in the repository.

        Args:
            query: Search query string.
            per_page: Number of results per page (max 100).

        Returns:
            List of search results, each containing file info and matches.

        Raises:
            GitHubAPIError: For API errors.
        """
        # Build search query with repo filter
        full_query = f"{query} repo:{self.owner}/{self.repo}"
        url = f"{self.base_url}/search/code"
        params = {"q": full_query, "per_page": per_page}

        logger.info("Searching code: %s", query)

        response = await self._request_with_retry("GET", url, params=params)
        data = response.json()

        results = data.get("items", [])
        logger.info("Found %d results for query: %s", len(results), query)

        return results

    # =========================================================================
    # Git Database Operations
    # =========================================================================

    async def get_ref(self, ref: str) -> dict[str, Any]:
        """Get a Git reference (branch or tag).

        Args:
            ref: Reference name (e.g., "heads/main", "tags/v1.0").

        Returns:
            Reference object containing SHA and URL.

        Raises:
            GitHubResourceNotFoundError: If the reference doesn't exist.
            GitHubAPIError: For other API errors.
        """
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/git/ref/{ref}"

        logger.info("Getting reference: %s", ref)

        response = await self._request_with_retry("GET", url)
        data = response.json()

        logger.info("Reference %s points to SHA: %s", ref, data.get("object", {}).get("sha", "")[:8])
        return data

    async def get_commit(self, commit_sha: str) -> dict[str, Any]:
        """Get a Git commit object.

        Args:
            commit_sha: The commit SHA.

        Returns:
            Commit object containing tree SHA, parent SHAs, and message.

        Raises:
            GitHubResourceNotFoundError: If the commit doesn't exist.
            GitHubAPIError: For other API errors.
        """
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/git/commits/{commit_sha}"

        logger.info("Getting commit: %s", commit_sha[:8])

        response = await self._request_with_retry("GET", url)
        data = response.json()

        tree_sha = data.get("tree", {}).get("sha", "")
        logger.info("Commit %s has tree: %s", commit_sha[:8], tree_sha[:8])

        return data

    async def create_blob(self, content: str, encoding: str = "utf-8") -> str:
        """Create a Git blob object.

        Args:
            content: The content to store in the blob.
            encoding: Content encoding ("utf-8" or "base64").

        Returns:
            The SHA of the created blob.

        Raises:
            GitHubCommitError: If blob creation fails.
        """
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/git/blobs"
        data = {"content": content, "encoding": encoding}

        logger.info("Creating blob (%d bytes)", len(content))

        response = await self._request_with_retry("POST", url, json=data)
        result = response.json()

        blob_sha = result["sha"]
        logger.info("Created blob: %s", blob_sha[:8])

        return blob_sha

    async def create_tree(
        self,
        base_tree_sha: str,
        tree_items: list[dict[str, Any]],
    ) -> str:
        """Create a Git tree object.

        Args:
            base_tree_sha: SHA of the base tree to build upon.
            tree_items: List of tree items, each with path, mode, type, and SHA.

        Returns:
            The SHA of the created tree.

        Raises:
            GitHubCommitError: If tree creation fails.
        """
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/git/trees"
        data = {
            "base_tree": base_tree_sha,
            "tree": tree_items,
        }

        logger.info("Creating tree with %d items", len(tree_items))

        response = await self._request_with_retry("POST", url, json=data)
        result = response.json()

        tree_sha = result["sha"]
        logger.info("Created tree: %s", tree_sha[:8])

        return tree_sha

    async def create_commit(
        self,
        message: str,
        tree_sha: str,
        parent_sha: str,
        author: Optional[dict[str, str]] = None,
    ) -> str:
        """Create a Git commit object.

        Args:
            message: Commit message.
            tree_sha: SHA of the tree for this commit.
            parent_sha: SHA of the parent commit.
            author: Optional author info (name, email, date).

        Returns:
            The SHA of the created commit.

        Raises:
            GitHubCommitError: If commit creation fails.
        """
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/git/commits"
        data: dict[str, Any] = {
            "message": message,
            "tree": tree_sha,
            "parents": [parent_sha],
        }

        if author:
            data["author"] = author

        logger.info("Creating commit: %s", message[:50])

        response = await self._request_with_retry("POST", url, json=data)
        result = response.json()

        commit_sha = result["sha"]
        logger.info("Created commit: %s", commit_sha[:8])

        return commit_sha

    async def create_branch(
        self,
        branch_name: str,
        commit_sha: str,
    ) -> str:
        """Create a new branch reference.

        Args:
            branch_name: Name for the new branch.
            commit_sha: SHA of the commit to branch from.

        Returns:
            The full reference name (e.g., "refs/heads/new-branch").

        Raises:
            GitHubBranchError: If branch creation fails.
        """
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/git/refs"
        data = {
            "ref": f"refs/heads/{branch_name}",
            "sha": commit_sha,
        }

        logger.info("Creating branch: %s from commit %s", branch_name, commit_sha[:8])

        try:
            response = await self._request_with_retry("POST", url, json=data)
            result = response.json()

            ref = result.get("ref", f"refs/heads/{branch_name}")
            logger.info("Created branch: %s", ref)

            return ref

        except GitHubAPIError as e:
            if e.status_code == 422:
                raise GitHubBranchError(
                    f"Branch '{branch_name}' already exists or is invalid",
                    status_code=422,
                    response_body=e.response_body,
                ) from e
            raise

    async def create_pull_request(
        self,
        title: str,
        head: str,
        base: str = "main",
        body: str = "",
        draft: bool = False,
    ) -> dict[str, Any]:
        """Create a pull request.

        Args:
            title: PR title.
            head: Branch name to merge from.
            base: Branch name to merge into (default: "main").
            body: PR description.
            draft: Whether to create as draft PR.

        Returns:
            Pull request object containing number, URL, etc.

        Raises:
            GitHubPRError: If PR creation fails.
        """
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/pulls"
        data = {
            "title": title,
            "head": head,
            "base": base,
            "body": body,
            "draft": draft,
        }

        logger.info("Creating PR: %s (%s -> %s)", title, head, base)

        try:
            response = await self._request_with_retry("POST", url, json=data)
            result = response.json()

            pr_number = result.get("number", "?")
            pr_url = result.get("html_url", "")
            logger.info("Created PR #%d: %s", pr_number, pr_url)

            return result

        except GitHubAPIError as e:
            raise GitHubPRError(
                f"Failed to create pull request: {title}",
                status_code=e.status_code,
                response_body=e.response_body,
            ) from e

    async def create_issue_comment(
        self,
        issue_number: int,
        body: str,
    ) -> dict[str, Any]:
        """Create a comment on an issue.

        Args:
            issue_number: Issue number.
            body: Comment body (Markdown supported).

        Returns:
            Comment object.

        Raises:
            GitHubAPIError: If comment creation fails.
        """
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/issues/{issue_number}/comments"
        data = {"body": body}

        logger.info("Creating comment on issue #%d", issue_number)

        response = await self._request_with_retry("POST", url, json=data)
        result = response.json()

        logger.info("Created comment on issue #%d", issue_number)

        return result

    # =========================================================================
    # High-Level Operations
    # =========================================================================

    async def create_pull_request_flow(
        self,
        files: dict[str, str],
        pr_title: str,
        pr_body: str = "",
        branch_name: Optional[str] = None,
        base_branch: str = "main",
        commit_message: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute the complete PR creation flow.

        This method orchestrates the entire Git operation sequence:
        1. Get the latest commit SHA from base branch
        2. Get the tree SHA from that commit
        3. Create blobs for all modified files
        4. Create a new tree with the modified files
        5. Create a new commit
        6. Create a new branch
        7. Create a pull request

        Args:
            files: Dictionary mapping file paths to their new content.
            pr_title: Pull request title.
            pr_body: Pull request description (Markdown).
            branch_name: Name for the new branch. Auto-generated if not provided.
            base_branch: Base branch to create PR against (default: "main").
            commit_message: Commit message. Uses pr_title if not provided.

        Returns:
            Pull request object containing number, URL, etc.

        Raises:
            GitHubCommitError: If commit operations fail.
            GitHubBranchError: If branch creation fails.
            GitHubPRError: If PR creation fails.
        """
        logger.info(
            "Starting PR creation flow for %s/%s: %d files",
            self.owner,
            self.repo,
            len(files),
        )

        # Generate branch name if not provided
        if not branch_name:
            branch_name = self._generate_branch_name()

        # Use PR title as commit message if not provided
        if not commit_message:
            commit_message = pr_title

        try:
            # Step 1: Get latest commit SHA from base branch
            logger.info("Step 1/7: Getting base branch ref...")
            ref_data = await self.get_ref(f"heads/{base_branch}")
            base_commit_sha = ref_data["object"]["sha"]

            # Step 2: Get tree SHA from that commit
            logger.info("Step 2/7: Getting commit tree...")
            commit_data = await self.get_commit(base_commit_sha)
            base_tree_sha = commit_data["tree"]["sha"]

            # Step 3: Create blobs for all files
            logger.info("Step 3/7: Creating blobs for %d files...", len(files))
            tree_items = []
            for file_path, content in files.items():
                blob_sha = await self.create_blob(content)
                tree_items.append({
                    "path": file_path,
                    "mode": "100644",  # Regular file
                    "type": "blob",
                    "sha": blob_sha,
                })

            # Step 4: Create new tree
            logger.info("Step 4/7: Creating new tree...")
            new_tree_sha = await self.create_tree(base_tree_sha, tree_items)

            # Step 5: Create new commit
            logger.info("Step 5/7: Creating new commit...")
            new_commit_sha = await self.create_commit(
                message=commit_message,
                tree_sha=new_tree_sha,
                parent_sha=base_commit_sha,
            )

            # Step 6: Create new branch
            logger.info("Step 6/7: Creating new branch '%s'...", branch_name)
            await self.create_branch(branch_name, new_commit_sha)

            # Step 7: Create pull request
            logger.info("Step 7/7: Creating pull request...")
            pr = await self.create_pull_request(
                title=pr_title,
                head=branch_name,
                base=base_branch,
                body=pr_body,
            )

            logger.info(
                "PR creation flow completed successfully: PR #%d",
                pr.get("number", "?"),
            )

            return pr

        except Exception as e:
            logger.error("PR creation flow failed: %s", str(e))
            raise

    def _generate_branch_name(self) -> str:
        """Generate a unique branch name.

        Returns:
            A branch name like "fix/auto-fix-abc123".
        """
        suffix = "".join(
            random.choices(string.ascii_lowercase + string.digits, k=6)
        )
        return f"fix/auto-fix-{suffix}"


async def asyncio_delay(seconds: float) -> None:
    """Async delay function.

    Args:
        seconds: Number of seconds to wait.
    """
    import asyncio

    await asyncio.sleep(seconds)
