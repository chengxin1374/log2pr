"""Prompts for the AI agent.

This module contains all prompt templates used by the agent service,
including system prompts, user message templates, and comment templates.
"""

from typing import Optional


# =============================================================================
# System Prompt - The Brain of the Agent
# =============================================================================

SYSTEM_PROMPT = """You are a **Senior Backend Engineer** with 15+ years of experience in Python debugging and code quality. You are part of an automated bug-fixing system called "log2pr".

## Your Mission
Analyze error tracebacks, identify root causes, and generate precise, defensive fixes that solve the immediate problem while preventing future issues.

## Your Capabilities
You have access to tools that let you:
1. **search_code**: Search for code patterns in the repository
2. **get_file_content**: Read the full content of any file

## Your Workflow
Follow this rigorous debugging process:

### Step 1: Traceback Analysis
- Parse the traceback to identify:
  - The exact error type and message
  - The file and line number where the error occurred
  - The call stack leading to the error
- Form hypotheses about the root cause

### Step 2: Code Investigation
- Use `search_code` to find relevant code patterns
- Use `get_file_content` to read files mentioned in the traceback
- Look for related files that might be involved (imports, callers, etc.)
- Verify your hypotheses by examining the actual code

### Step 3: Root Cause Identification
Before generating any fix, clearly state:
- What is the exact bug?
- Why does it happen?
- What files need to be modified?
- What is the minimal, safest fix?

### Step 4: Generate Fix
When you're ready to generate a fix:
1. Output your analysis in a clear, structured format
2. Use the `submit_fix` tool to submit your fix
3. The tool expects:
   - `analysis`: Your detailed analysis of the bug
   - `files`: A dictionary mapping file paths to their COMPLETE fixed content

## Coding Standards
When writing fixes, ALWAYS:

1. **Defensive Programming**:
   - Add null/undefined checks before accessing properties
   - Use try-except blocks for operations that might fail
   - Validate inputs at function boundaries
   - Handle edge cases explicitly

2. **Error Messages**:
   - Provide clear, actionable error messages
   - Include relevant context in exceptions

3. **Code Style**:
   - Follow PEP 8 conventions
   - Add docstrings to new functions
   - Keep changes minimal and focused
   - Do NOT remove existing functionality

4. **Safety First**:
   - Prefer explicit checks over implicit behavior
   - Add logging for debugging
   - Consider backward compatibility

## Important Rules
- NEVER guess file contents - always read files first
- NEVER make changes to files you haven't read
- ALWAYS verify the fix addresses the root cause
- ALWAYS provide COMPLETE file content, not diffs
- If you cannot confidently fix the issue, explain why

## Output Format
When submitting a fix via `submit_fix`, provide:
```
analysis: |
  Detailed analysis of the bug...
files:
  path/to/file.py: |
    Complete fixed file content...
```

Begin your analysis when provided with a traceback."""


# =============================================================================
# Tool Definitions
# =============================================================================

TOOLS = [
    {
        "name": "search_code",
        "description": "Search for code patterns in the repository. Use this to find files containing specific functions, classes, or patterns. Returns a list of matching files with snippets.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query. Can be a function name, class name, error message, or any code pattern.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_file_content",
        "description": "Get the complete content of a file from the repository. Use this to read files mentioned in the traceback or found via search. Always read a file before modifying it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path to the file in the repository (e.g., 'src/utils.py').",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "submit_fix",
        "description": "Submit your fix for the bug. Use this when you have completed your analysis and are ready to generate the fix. Provide your analysis and the complete content of all files that need to be modified.",
        "input_schema": {
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "string",
                    "description": "Your detailed analysis of the bug, including root cause and fix explanation.",
                },
                "files": {
                    "type": "object",
                    "description": "Dictionary mapping file paths to their complete fixed content.",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["analysis", "files"],
        },
    },
]


# =============================================================================
# User Message Templates
# =============================================================================

def build_initial_message(
    issue_title: str,
    issue_body: str,
    repo_owner: str,
    repo_name: str,
) -> str:
    """Build the initial message for the AI agent.

    Args:
        issue_title: Title of the GitHub issue.
        issue_body: Body of the issue containing the traceback.
        repo_owner: Repository owner.
        repo_name: Repository name.

    Returns:
        Formatted message string.
    """
    return f"""Please analyze and fix the following issue:

## Issue Title
{issue_title}

## Issue Body (contains traceback)
{issue_body or '(No content provided)'}

## Repository
{repo_owner}/{repo_name}

Begin by analyzing the traceback, then use the available tools to investigate the code and generate a fix."""


# =============================================================================
# Comment Templates (Progress Updates)
# =============================================================================

def comment_analyzing_traceback() -> str:
    """Comment when starting traceback analysis."""
    return """🔍 **正在分析 Traceback...**

我正在仔细阅读错误日志，定位问题根源。"""


def comment_searching_code(query: str) -> str:
    """Comment when searching for code.

    Args:
        query: The search query.

    Returns:
        Formatted comment.
    """
    return f"""🔎 **搜索代码**: `{query}`

正在查找相关代码..."""


def comment_reading_file(file_path: str) -> str:
    """Comment when reading a file.

    Args:
        file_path: Path to the file being read.

    Returns:
        Formatted comment.
    """
    return f"""📄 **读取文件**: `{file_path}`

正在分析源码..."""


def comment_analysis_complete(analysis: str, files: list[str]) -> str:
    """Comment when analysis is complete and ready to fix.

    Args:
        analysis: The bug analysis.
        files: List of files to be modified.

    Returns:
        Formatted comment.
    """
    file_list = "\n".join(f"- `{p}`" for p in files)
    return f"""✅ **分析完成！**

## 问题分析
{analysis}

## 修复文件
{file_list}

🚀 正在创建 Pull Request..."""


def comment_fix_success(pr_number: int, pr_url: str) -> str:
    """Comment when fix PR is created successfully.

    Args:
        pr_number: PR number.
        pr_url: PR URL.

    Returns:
        Formatted comment.
    """
    return f"""🎉 **修复完成！**

Pull Request 已创建: [#{pr_number}]({pr_url})

请审查并合并。感谢使用 log2pr！"""


def comment_fix_failed(error: str) -> str:
    """Comment when auto-fix fails.

    Args:
        error: Error message.

    Returns:
        Formatted comment.
    """
    return f"""❌ **自动修复失败**

在处理过程中遇到了错误：
```
{error}
```

请检查 Issue 内容或手动修复。"""


# =============================================================================
# PR Templates
# =============================================================================

def generate_pr_title(issue_number: int, issue_title: str, analysis: str) -> str:
    """Generate a PR title.

    Args:
        issue_number: Issue number.
        issue_title: Issue title.
        analysis: Bug analysis.

    Returns:
        PR title string.
    """
    # Try to extract error type from analysis or title
    error_type = "bug"
    error_indicators = [
        ("KeyError", "KeyError"),
        ("AttributeError", "AttributeError"),
        ("TypeError", "TypeError"),
        ("ValueError", "ValueError"),
        ("NullPointerException", "NullPointerException"),
        ("IndexError", "IndexError"),
        ("NameError", "NameError"),
        ("ImportError", "ImportError"),
        ("ModuleNotFoundError", "ModuleNotFoundError"),
    ]

    combined_text = f"{analysis} {issue_title}"
    for indicator, name in error_indicators:
        if indicator in combined_text:
            error_type = name
            break

    return f"fix: resolve {error_type} reported in issue #{issue_number}"


def generate_pr_body(
    issue_number: int,
    issue_title: str,
    analysis: str,
    files: dict[str, str],
) -> str:
    """Generate a PR body.

    Args:
        issue_number: Issue number.
        issue_title: Issue title.
        analysis: Bug analysis.
        files: Dictionary of fixed files.

    Returns:
        PR body string (Markdown).
    """
    file_list = "\n".join(f"- `{p}`" for p in files.keys())

    return f"""## 🤖 Automated Fix by log2pr

This PR automatically fixes the issue #{issue_number}.

### Issue
{issue_title}

### Root Cause Analysis
{analysis}

### Files Changed
{file_list}

### Changes
- Added defensive null checks
- Improved error handling
- Fixed the reported bug

---
*This PR was automatically generated by [log2pr](https://github.com/your-repo/log2pr).*"""
