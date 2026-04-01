"""
orbit MCP (Model Context Protocol) module.

Provides MCP server implementations for code intelligence, project memory,
runtime state management, team coordination, and execution tracing.

Also exposes the external-server registry, bootstrap lifecycle manager, and
JSON-RPC client for communicating with third-party MCP servers.
"""

from .registry import (
    MCPServerConfig,
    MCPRegistry,
    get_registry,
)
from .server_bootstrap import (
    MCPBootstrap,
    get_bootstrap,
)
from .client import (
    MCPClient,
    MCPError,
    ToolInfo,
    get_client,
)
from .bootstrap import (
    McpServer,
    McpServerName,
    StdioTransport,
    ToolDefinition,
    ToolResult,
    TextContent,
    auto_start_stdio_mcp_server,
    error_result,
    run_stdio_server,
    should_auto_start_mcp_server,
    text_result,
)
from .code_intel import CodeIntelServer
from .memory_server import MemoryServer
from .state_server import StateServer
from .team_server import TeamServer
from .trace_server import TraceServer
from .state_paths import (
    ModeStateFileRef,
    ResolvedStateScope,
    get_all_scoped_state_dirs,
    get_all_scoped_state_paths,
    get_base_state_dir,
    get_read_scoped_state_dirs,
    get_read_scoped_state_paths,
    get_state_dir,
    get_state_path,
    list_mode_state_files_with_scope_preference,
    read_current_session_id,
    resolve_state_scope,
    resolve_working_directory_for_state,
)
from .validation import (
    DEFAULT_NOTEPAD_PRUNE_DAYS_OLD,
    parse_notepad_prune_days_old,
    validate_session_id,
    validate_state_mode_segment,
)

__all__ = [
    # External server registry
    "MCPServerConfig",
    "MCPRegistry",
    "get_registry",
    # External server lifecycle
    "MCPBootstrap",
    "get_bootstrap",
    # External server client
    "MCPClient",
    "MCPError",
    "ToolInfo",
    "get_client",
    # Bootstrap
    "McpServer",
    "McpServerName",
    "StdioTransport",
    "ToolDefinition",
    "ToolResult",
    "TextContent",
    "auto_start_stdio_mcp_server",
    "error_result",
    "run_stdio_server",
    "should_auto_start_mcp_server",
    "text_result",
    # Servers
    "CodeIntelServer",
    "MemoryServer",
    "StateServer",
    "TeamServer",
    "TraceServer",
    # State paths
    "ModeStateFileRef",
    "ResolvedStateScope",
    "get_all_scoped_state_dirs",
    "get_all_scoped_state_paths",
    "get_base_state_dir",
    "get_read_scoped_state_dirs",
    "get_read_scoped_state_paths",
    "get_state_dir",
    "get_state_path",
    "list_mode_state_files_with_scope_preference",
    "read_current_session_id",
    "resolve_state_scope",
    "resolve_working_directory_for_state",
    # Validation
    "DEFAULT_NOTEPAD_PRUNE_DAYS_OLD",
    "parse_notepad_prune_days_old",
    "validate_session_id",
    "validate_state_mode_segment",
]
