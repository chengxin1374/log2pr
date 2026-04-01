"""AI Agent service for automated bug fixing.

This module implements the core AI agent that analyzes tracebacks,
navigates codebases, and generates fixes using AI with tool calling.
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.exceptions import AgentError, ClaudeAPIError
from app.prompts import (
    SYSTEM_PROMPT,
    TOOLS,
    build_initial_message,
    comment_analysis_complete,
    comment_analyzing_traceback,
    comment_fix_failed,
    comment_fix_success,
    comment_reading_file,
    comment_searching_code,
    generate_pr_body,
    generate_pr_title,
)
from app.services.github_client import GitOpsClient

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Agent execution state."""

    INITIALIZED = "initialized"
    ANALYZING = "analyzing"
    INVESTIGATING = "investigating"
    FIXING = "fixing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentResult:
    """Result of the agent's auto-fix workflow.

    Attributes:
        success: Whether the fix was successfully generated and submitted.
        analysis: The agent's analysis of the bug.
        files: Dictionary of file paths to their fixed content.
        pr_url: URL of the created pull request (if successful).
        error: Error message (if failed).
    """

    success: bool
    analysis: Optional[str] = None
    files: Optional[dict[str, str]] = None
    pr_url: Optional[str] = None
    error: Optional[str] = None


@dataclass
class AgentContext:
    """Context for the agent execution.

    Attributes:
        repo_owner: Repository owner.
        repo_name: Repository name.
        issue_number: Issue number.
        issue_title: Issue title.
        issue_body: Issue body containing the traceback.
        git_client: GitOpsClient instance.
        comment_callback: Async function to post comments.
    """

    repo_owner: str
    repo_name: str
    issue_number: int
    issue_title: str
    issue_body: str
    git_client: GitOpsClient
    comment_callback: Optional[Callable[[str], Any]] = None
    state: AgentState = AgentState.INITIALIZED
    messages: list[dict[str, Any]] = field(default_factory=list)
    files_read: dict[str, str] = field(default_factory=dict)


class AgentService:
    """AI Agent service for automated bug fixing.

    This service coordinates AI with GitHub tools to automatically
    analyze and fix bugs based on traceback information.

    Attributes:
        client: Anthropic async client.
        model: AI model to use.
        git_client: GitOpsClient for GitHub operations.
    """

    # Model configuration
    MODEL = "glm-5"
    MAX_TOKENS = 8192  # Reduced for faster responses
    MAX_TOOL_CALLS = 20  # Prevent infinite loops

    # Retry configuration
    MAX_RETRIES = 5
    RETRY_DELAY_BASE = 2.0  # Base delay in seconds
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        git_client: GitOpsClient,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        """Initialize the AgentService.

        Args:
            git_client: GitOpsClient instance for GitHub operations.
            api_key: API key. If not provided, reads from settings.
            base_url: API base URL. If not provided, reads from settings.
        """
        settings = get_settings()

        self.git_client = git_client
        self.api_key = api_key or settings.anthropic_auth_token
        self.base_url = base_url or settings.anthropic_base_url

        # Debug logging
        logger.debug("AgentService init - api_key param: %s", "None" if api_key is None else f"{len(api_key)} chars")
        logger.debug("AgentService init - settings token: %s", f"{len(settings.anthropic_auth_token)} chars" if settings.anthropic_auth_token else "EMPTY")
        logger.debug("AgentService init - self.api_key: %s", f"{len(self.api_key)} chars" if self.api_key else "EMPTY")
        logger.debug("AgentService init - base_url: %s", self.base_url)

        if not self.api_key:
            raise ValueError("API key is empty! Check ANTHROPIC_AUTH_TOKEN environment variable.")

        # Initialize Anthropic client with custom base URL for Baidu Qianfan
        self.client = AsyncAnthropic(
            api_key=self.api_key,
            base_url=self.base_url,
        )

        logger.info("AgentService initialized with model: %s", self.MODEL)

    async def post_comment(self, ctx: AgentContext, message: str) -> None:
        """Post a progress comment to the GitHub issue.

        Args:
            ctx: Agent context.
            message: Comment body (Markdown supported).
        """
        if ctx.comment_callback:
            await ctx.comment_callback(message)
        else:
            # Fallback to direct GitOpsClient call
            try:
                await self.git_client.create_issue_comment(ctx.issue_number, message)
            except Exception as e:
                logger.warning("Failed to post comment: %s", e)

    async def run_auto_fix_workflow(
        self,
        repo_owner: str,
        repo_name: str,
        issue_number: int,
        issue_title: str,
        issue_body: str,
        comment_callback: Optional[Callable[[str], Any]] = None,
    ) -> AgentResult:
        """Run the complete auto-fix workflow.

        This method orchestrates the entire debugging and fix generation process:
        1. Analyze the traceback
        2. Navigate the codebase using tools
        3. Generate a fix
        4. Create a pull request

        Args:
            repo_owner: Repository owner.
            repo_name: Repository name.
            issue_number: Issue number.
            issue_title: Issue title.
            issue_body: Issue body containing the traceback.
            comment_callback: Optional async function to post progress comments.

        Returns:
            AgentResult containing the outcome of the workflow.
        """
        logger.info(
            "Starting auto-fix workflow for %s/%s issue #%d",
            repo_owner,
            repo_name,
            issue_number,
        )

        # Initialize context
        ctx = AgentContext(
            repo_owner=repo_owner,
            repo_name=repo_name,
            issue_number=issue_number,
            issue_title=issue_title,
            issue_body=issue_body,
            git_client=self.git_client,
            comment_callback=comment_callback,
        )

        try:
            # Post initial status
            await self.post_comment(ctx, comment_analyzing_traceback())

            # Build initial message with issue context
            initial_message = build_initial_message(
                issue_title=ctx.issue_title,
                issue_body=ctx.issue_body,
                repo_owner=ctx.repo_owner,
                repo_name=ctx.repo_name,
            )
            ctx.messages = [{"role": "user", "content": initial_message}]

            # Run the ReAct loop
            result = await self._run_react_loop(ctx)

            return result

        except Exception as e:
            logger.exception("Auto-fix workflow failed: %s", str(e))
            ctx.state = AgentState.FAILED

            # Post failure comment
            await self.post_comment(ctx, comment_fix_failed(str(e)))

            return AgentResult(
                success=False,
                error=str(e),
            )

    async def _run_react_loop(self, ctx: AgentContext) -> AgentResult:
        """Run the ReAct (Reasoning + Acting) loop.

        This method implements the core agent loop:
        1. Send message to AI
        2. Handle tool calls
        3. Repeat until done or max iterations reached

        Args:
            ctx: Agent context.

        Returns:
            AgentResult with the final outcome.
        """
        ctx.state = AgentState.ANALYZING
        tool_call_count = 0

        while tool_call_count < self.MAX_TOOL_CALLS:
            logger.info("ReAct loop iteration %d", tool_call_count + 1)

            # Call AI
            response = await self._call_ai(ctx.messages)
            ctx.state = AgentState.INVESTIGATING

            # Handle the response
            assistant_content = response.content

            # Check for text content (AI's reasoning)
            # Handle both dict and object formats
            text_blocks = []
            for b in assistant_content:
                if isinstance(b, dict):
                    if b.get("type") == "text":
                        text_blocks.append(b)
                elif hasattr(b, "type") and b.type == "text":
                    text_blocks.append({"type": "text", "text": b.text})

            if text_blocks:
                reasoning = "\n".join(b.get("text", "") if isinstance(b, dict) else b.text for b in text_blocks)
                logger.info("AI reasoning: %s", reasoning[:500])
                ctx.messages.append({"role": "assistant", "content": assistant_content})

            # Check for tool use
            tool_blocks = []
            for b in assistant_content:
                if isinstance(b, dict):
                    if b.get("type") == "tool_use":
                        tool_blocks.append(b)
                elif hasattr(b, "type") and b.type == "tool_use":
                    tool_blocks.append({"type": "tool_use", "name": b.name, "input": b.input, "id": b.id})

            if not tool_blocks:
                # No tool calls - AI should have provided analysis
                # but didn't call submit_fix, which is unexpected
                logger.warning("AI did not make any tool calls")
                return AgentResult(
                    success=False,
                    error="Agent did not generate a fix. Please try again with more details.",
                )

            # Process tool calls
            tool_results = []
            for tool_block in tool_blocks:
                tool_name = tool_block.get("name") if isinstance(tool_block, dict) else tool_block.name
                tool_input = tool_block.get("input") if isinstance(tool_block, dict) else tool_block.input
                tool_id = tool_block.get("id") if isinstance(tool_block, dict) else tool_block.id

                logger.info("Tool call: %s with input: %s", tool_name, tool_input)

                tool_call_count += 1

                # Execute the tool
                try:
                    result = await self._execute_tool(ctx, tool_name, tool_input)

                    if result is None:
                        # submit_fix was called - workflow complete
                        return AgentResult(
                            success=True,
                            analysis=tool_input.get("analysis", ""),
                            files=tool_input.get("files", {}),
                        )

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })

                except Exception as e:
                    logger.error("Tool execution failed: %s", str(e))
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "is_error": True,
                        "content": f"Error: {str(e)}",
                    })

            # Add tool results to conversation
            ctx.messages.append({"role": "user", "content": tool_results})

        # Max iterations reached
        logger.warning("Max tool calls reached: %d", self.MAX_TOOL_CALLS)
        return AgentResult(
            success=False,
            error=f"Agent reached maximum tool call limit ({self.MAX_TOOL_CALLS}). "
            "The issue may be too complex for automatic fixing.",
        )

    async def _call_ai(self, messages: list[dict[str, Any]]) -> Any:
        """Call AI API with the current conversation using streaming.

        Includes retry logic for transient errors.

        Args:
            messages: List of conversation messages.

        Returns:
            AI API response (accumulated from stream).

        Raises:
            ClaudeAPIError: If the API call fails after all retries.
        """
        import asyncio

        last_error: Optional[Exception] = None

        for attempt in range(self.MAX_RETRIES):
            try:
                # Debug: log the actual API key being used
                logger.info("Calling AI API with model: %s (attempt %d/%d)", self.MODEL, attempt + 1, self.MAX_RETRIES)
                logger.debug("API key (first 30 chars): %s...", self.api_key[:30] if self.api_key else "EMPTY")
                logger.debug("Base URL: %s", self.base_url)

                # Use streaming for long-running requests
                content_blocks = []
                current_content = []
                current_block_type = None
                current_tool_use = None
                tool_use_blocks = []

                async with self.client.messages.stream(
                    model=self.MODEL,
                    max_tokens=self.MAX_TOKENS,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=messages,
                ) as stream:
                    async for event in stream:
                        if event.type == "content_block_start":
                            block_type = event.content_block.type
                            current_block_type = block_type
                            current_content = []

                            if block_type == "tool_use":
                                current_tool_use = {
                                    "id": event.content_block.id,
                                    "type": "tool_use",
                                    "name": event.content_block.name,
                                    "input": {},
                                }

                        elif event.type == "content_block_delta":
                            # Handle text delta
                            if hasattr(event.delta, "text") and event.delta.text:
                                current_content.append(event.delta.text)
                            # Handle thinking delta (for models that return thinking blocks)
                            elif hasattr(event.delta, "thinking") and event.delta.thinking:
                                current_content.append(event.delta.thinking)
                            # Handle partial JSON for tool use
                            elif hasattr(event.delta, "partial_json") and event.delta.partial_json:
                                if current_tool_use is not None:
                                    current_content.append(event.delta.partial_json)

                        elif event.type == "content_block_stop":
                            if current_tool_use is not None:
                                # Complete tool use block
                                json_str = "".join(current_content)
                                try:
                                    import json
                                    current_tool_use["input"] = json.loads(json_str) if json_str else {}
                                except json.JSONDecodeError:
                                    current_tool_use["input"] = {}
                                tool_use_blocks.append(current_tool_use)
                                current_tool_use = None
                            elif current_block_type in ("text", "thinking"):
                                # Text or thinking block - treat both as text
                                text = "".join(current_content)
                                if text.strip():  # Only add non-empty blocks
                                    content_blocks.append({
                                        "type": "text",
                                        "text": text,
                                    })
                            current_content = []
                            current_block_type = None

                # Build response object compatible with non-streaming API
                from types import SimpleNamespace

                all_blocks = content_blocks + tool_use_blocks

                response = SimpleNamespace(
                    content=all_blocks,
                    model=self.MODEL,
                    role="assistant",
                )

                logger.info("AI response: %d text blocks, %d tool calls", len(content_blocks), len(tool_use_blocks))
                return response

            except Exception as e:
                last_error = e
                error_str = str(e)

                # Check if this is a retryable error
                is_retryable = False
                status_code = None

                # Extract status code if available
                if hasattr(e, "status_code"):
                    status_code = e.status_code
                    is_retryable = status_code in self.RETRYABLE_STATUS_CODES
                elif hasattr(e, "response") and hasattr(e.response, "status_code"):
                    status_code = e.response.status_code
                    is_retryable = status_code in self.RETRYABLE_STATUS_CODES

                # Also retry on connection errors
                if "connection" in error_str.lower() or "timeout" in error_str.lower():
                    is_retryable = True

                if is_retryable and attempt < self.MAX_RETRIES - 1:
                    # Linear incremental backoff: 2s, 4s, 6s, 8s, 10s
                    delay = self.RETRY_DELAY_BASE * (attempt + 1)
                    logger.warning(
                        "AI API call failed (status: %s), retrying in %.1f seconds (attempt %d/%d): %s",
                        status_code or "unknown",
                        delay,
                        attempt + 1,
                        self.MAX_RETRIES,
                        error_str[:200],
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Non-retryable error or max retries reached
                    logger.error("AI API call failed: %s", error_str)
                    raise ClaudeAPIError(
                        f"AI API call failed: {error_str}",
                        details={"error": error_str, "attempt": attempt + 1},
                    ) from e

        # Should not reach here, but just in case
        raise ClaudeAPIError(
            f"AI API call failed after {self.MAX_RETRIES} attempts: {last_error}",
            details={"error": str(last_error)},
        ) from last_error

    async def _execute_tool(
        self,
        ctx: AgentContext,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Execute a tool call from AI.

        Args:
            ctx: Agent context.
            tool_name: Name of the tool to execute.
            tool_input: Tool input parameters.

        Returns:
            Tool result, or None if submit_fix was called.

        Raises:
            AgentError: If tool execution fails.
        """
        if tool_name == "search_code":
            return await self._tool_search_code(ctx, tool_input)

        elif tool_name == "get_file_content":
            return await self._tool_get_file_content(ctx, tool_input)

        elif tool_name == "submit_fix":
            return await self._tool_submit_fix(ctx, tool_input)

        else:
            raise AgentError(f"Unknown tool: {tool_name}")

    async def _tool_search_code(
        self,
        ctx: AgentContext,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the search_code tool.

        Args:
            ctx: Agent context.
            tool_input: Tool input with 'query' parameter.

        Returns:
            Search results.
        """
        query = tool_input.get("query", "")
        logger.info("Searching code: %s", query)

        # Post progress comment
        await self.post_comment(ctx, comment_searching_code(query))

        results = await ctx.git_client.search_code(query)

        # Format results for AI
        formatted_results = []
        for item in results[:10]:  # Limit to top 10 results
            formatted_results.append({
                "path": item.get("path", ""),
                "name": item.get("name", ""),
                "html_url": item.get("html_url", ""),
            })

        return {
            "query": query,
            "total_count": len(results),
            "results": formatted_results,
        }

    async def _tool_get_file_content(
        self,
        ctx: AgentContext,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the get_file_content tool.

        Args:
            ctx: Agent context.
            tool_input: Tool input with 'file_path' parameter.

        Returns:
            File content information.
        """
        file_path = tool_input.get("file_path", "")
        logger.info("Getting file content: %s", file_path)

        # Post progress comment
        await self.post_comment(ctx, comment_reading_file(file_path))

        # Check if we already read this file
        if file_path in ctx.files_read:
            return {
                "path": file_path,
                "content": ctx.files_read[file_path],
                "cached": True,
            }

        content = await ctx.git_client.get_file_content(file_path)
        ctx.files_read[file_path] = content

        return {
            "path": file_path,
            "content": content,
            "lines": len(content.splitlines()),
        }

    async def _tool_submit_fix(
        self,
        ctx: AgentContext,
        tool_input: dict[str, Any],
    ) -> None:
        """Execute the submit_fix tool.

        This tool triggers the PR creation flow.

        Args:
            ctx: Agent context.
            tool_input: Tool input with 'analysis' and 'files' parameters.

        Returns:
            None to signal workflow completion.
        """
        analysis = tool_input.get("analysis", "")
        files = tool_input.get("files", {})

        logger.info("Submitting fix with %d files", len(files))
        ctx.state = AgentState.FIXING

        # Validate files
        if not files:
            raise AgentError("No files provided in the fix")

        # Post analysis comment
        await self.post_comment(ctx, comment_analysis_complete(analysis, list(files.keys())))

        # Verify all files have been read
        for file_path in files:
            if file_path not in ctx.files_read:
                logger.warning(
                    "Agent modified file %s without reading it first",
                    file_path,
                )

        # Create PR
        pr_title = generate_pr_title(ctx.issue_number, ctx.issue_title, analysis)
        pr_body = generate_pr_body(ctx.issue_number, ctx.issue_title, analysis, files)

        pr = await ctx.git_client.create_pull_request_flow(
            files=files,
            pr_title=pr_title,
            pr_body=pr_body,
        )

        pr_url = pr.get("html_url", "")
        pr_number = pr.get("number", "?")

        # Post success comment
        await self.post_comment(ctx, comment_fix_success(pr_number, pr_url))

        ctx.state = AgentState.COMPLETED

        # Return None to signal completion
        return None
