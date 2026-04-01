"""Default configuration values, timeouts, and limits for orbit."""

from pathlib import Path

# Model defaults
DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TOP_P = 1.0
DEFAULT_TOP_K = 40
DEFAULT_STOP_SEQUENCES: list[str] = []

# Timeout defaults (seconds)
DEFAULT_TIMEOUT = 120
DEFAULT_CONNECT_TIMEOUT = 10
DEFAULT_READ_TIMEOUT = 60
DEFAULT_STREAM_TIMEOUT = 300
DEFAULT_HEALTH_CHECK_TIMEOUT = 5

# Retry defaults
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0
DEFAULT_RETRY_BACKOFF_FACTOR = 2.0
DEFAULT_RETRY_MAX_DELAY = 30.0

# Cache defaults
DEFAULT_CACHE_TTL = 3600  # 1 hour
DEFAULT_CACHE_MAX_SIZE = 1000
DEFAULT_CACHE_STRATEGY = "lru"

# History and conversation
DEFAULT_HISTORY_LIMIT = 100
DEFAULT_CONVERSATION_MAX_TURNS = 50
DEFAULT_SUMMARY_THRESHOLD = 20

# Rate limiting
RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_BURST = 10

# Token limits
MAX_CONTEXT_TOKENS = 200_000
MAX_OUTPUT_TOKENS = 16_384
MIN_OUTPUT_TOKENS = 1
TOKEN_PADDING = 500

# File limits
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_FILES_PER_REQUEST = 20
MAX_SEARCH_RESULTS = 100
MAX_GLOB_RESULTS = 500

# Plugin limits
MAX_PLUGIN_COUNT = 50
MAX_PLUGIN_HOOKS = 100
PLUGIN_LOAD_TIMEOUT = 10

# Directory defaults
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "orbit"
DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "orbit"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "orbit"
DEFAULT_LOG_DIR = Path.home() / ".local" / "share" / "orbit" / "logs"
DEFAULT_PLUGIN_DIR = Path.home() / ".config" / "orbit" / "plugins"

# Logging
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DEFAULT_LOG_MAX_SIZE = 5 * 1024 * 1024  # 5 MB
DEFAULT_LOG_BACKUP_COUNT = 3

# Server defaults
DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 7429
DEFAULT_SERVER_WORKERS = 1
DEFAULT_SERVER_CORS_ORIGINS = ["http://localhost:*"]

# Migration
CURRENT_SCHEMA_VERSION = 3
MIN_SCHEMA_VERSION = 1

# Misc
DEFAULT_ENCODING = "utf-8"
DEFAULT_LINE_ENDING = "\n"
SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".json", ".yaml", ".yml",
    ".toml", ".md", ".txt", ".sh", ".bash",
    ".css", ".html", ".xml", ".sql", ".rb",
    ".go", ".rs", ".java", ".c", ".cpp", ".h",
}
