"""Composio integration for CoWork abilities.

Provides tools for:
- GitHub (read/write repos, PRs, search)
- Google Drive (file access, docs)
- VS Code Desktop (remote execution)
- Browser (web access, screenshots)
- Claude Deep Search (research)
"""
from __future__ import annotations

import json
from typing import Optional
import httpx
import structlog
from composio import Composio
from composio.client.collections import DEFAULT_ENTITY_ID

from ..config import settings

logger = structlog.get_logger(__name__)


class ComposioToolsClient:
    """Composio client for CoWork integrations."""

    def __init__(self, github_pat: str):
        self.github_pat = github_pat
        self.composio = Composio()
        self._tools_cache: dict[str, list] = {}

    async def get_github_tools(self) -> list[dict]:
        """Get GitHub tools (read/write repos, PRs, search)."""
        if "github" in self._tools_cache:
            return self._tools_cache["github"]

        try:
            github_toolkit = await self.composio.toolkits.get_toolkit(
                toolkit_name="github",
                connected_account_id=DEFAULT_ENTITY_ID,
            )
            tools = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "schema": tool.schema,
                }
                for tool in github_toolkit.tools
            ]
            self._tools_cache["github"] = tools
            return tools
        except Exception as e:
            logger.error("failed to get github tools", error=str(e))
            return []

    async def get_google_drive_tools(self) -> list[dict]:
        """Get Google Drive tools (file access, docs)."""
        if "google_drive" in self._tools_cache:
            return self._tools_cache["google_drive"]

        try:
            drive_toolkit = await self.composio.toolkits.get_toolkit(
                toolkit_name="googledrive",
                connected_account_id=DEFAULT_ENTITY_ID,
            )
            tools = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "schema": tool.schema,
                }
                for tool in drive_toolkit.tools
            ]
            self._tools_cache["google_drive"] = tools
            return tools
        except Exception as e:
            logger.error("failed to get google drive tools", error=str(e))
            return []

    async def get_browser_tools(self) -> list[dict]:
        """Get Browser tools (web access, screenshots)."""
        if "browser" in self._tools_cache:
            return self._tools_cache["browser"]

        try:
            browser_toolkit = await self.composio.toolkits.get_toolkit(
                toolkit_name="browser",
                connected_account_id=DEFAULT_ENTITY_ID,
            )
            tools = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "schema": tool.schema,
                }
                for tool in browser_toolkit.tools
            ]
            self._tools_cache["browser"] = tools
            return tools
        except Exception as e:
            logger.error("failed to get browser tools", error=str(e))
            return []

    async def get_all_tools(self) -> list[dict]:
        """Get all available CoWork tools."""
        all_tools = []
        all_tools.extend(await self.get_github_tools())
        all_tools.extend(await self.get_google_drive_tools())
        all_tools.extend(await self.get_browser_tools())
        return all_tools

    async def execute_tool(
        self,
        tool_name: str,
        params: dict,
        entity_id: str = DEFAULT_ENTITY_ID,
    ) -> dict:
        """Execute a Composio tool."""
        try:
            result = await self.composio.tools.execute(
                tool_name=tool_name,
                params=params,
                entity_id=entity_id,
            )
            logger.info("tool executed", tool=tool_name, result_id=result.id)
            return {
                "success": True,
                "tool": tool_name,
                "result": result.output,
                "execution_id": result.id,
            }
        except Exception as e:
            logger.error("tool execution failed", tool=tool_name, error=str(e))
            return {
                "success": False,
                "tool": tool_name,
                "error": str(e),
            }


_composio_client: Optional[ComposioToolsClient] = None


def get_composio_client() -> ComposioToolsClient:
    """Get or create Composio client."""
    global _composio_client
    if _composio_client is None:
        _composio_client = ComposioToolsClient(github_pat=settings.github_pat)
    return _composio_client
