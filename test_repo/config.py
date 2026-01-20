"""
Global configuration settings for the Secure Document Search API.
This module contains all global state that other modules depend on.
Complex configuration management with validation, environment variable support,
and hierarchical settings that can be overridden at runtime.
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List, Union
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

class LogLevel(Enum):
    """Logging level enumeration."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

@dataclass
class DatabaseConfig:
    """Database configuration settings."""
    timeout: int = 30
    max_connections: int = 10
    pool_recycle: int = 3600
    pool_pre_ping: bool = True
    echo: bool = False
    pool_size: int = 5
    max_overflow: int = 10
    
    def validate(self) -> List[str]:
        """Validate database configuration."""
        errors = []
        if self.timeout <= 0:
            errors.append("DB_TIMEOUT must be positive")
        if self.max_connections <= 0:
            errors.append("DB_MAX_CONNECTIONS must be positive")
        if self.pool_size <= 0:
            errors.append("DB_POOL_SIZE must be positive")
        return errors

@dataclass
class PostgresConfig:
    """PostgreSQL-specific configuration."""
    host: str = "localhost"
    port: int = 5432
    database: str = "search_db"
    user: str = "admin"
    password: str = "secret"
    ssl_mode: str = "prefer"
    connect_timeout: int = 10
    application_name: str = "search_api"
    
    def get_connection_string(self) -> str:
        """Generate PostgreSQL connection string."""
        return (
            f"postgresql://{self.user}:{self.password}@"
            f"{self.host}:{self.port}/{self.database}?sslmode={self.ssl_mode}"
        )

@dataclass
class SecurityConfig:
    """Security and authentication configuration."""
    jwt_secret_key: str = "default-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    jwt_refresh_expiration_days: int = 7
    bcrypt_rounds: int = 12
    session_timeout_minutes: int = 30
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 15
    require_https: bool = False
    cors_origins: List[str] = None
    
    def __post_init__(self):
        """Initialize default CORS origins."""
        if self.cors_origins is None:
            self.cors_origins = ["http://localhost:3000", "http://localhost:8080"]

@dataclass
class SearchEngineConfig:
    """Search engine configuration."""
    embedding_dimension: int = 384
    max_search_results: int = 100
    default_top_k: int = 10
    similarity_threshold: float = 0.7
    rerank_top_k: int = 50
    enable_hybrid_search: bool = True
    bm25_weight: float = 0.3
    semantic_weight: float = 0.7
    min_query_length: int = 2
    max_query_length: int = 500
    
    def validate(self) -> List[str]:
        """Validate search engine configuration."""
        errors = []
        if not 0.0 <= self.similarity_threshold <= 1.0:
            errors.append("SIMILARITY_THRESHOLD must be between 0 and 1")
        if not 0.0 <= self.bm25_weight <= 1.0:
            errors.append("BM25_WEIGHT must be between 0 and 1")
        if not 0.0 <= self.semantic_weight <= 1.0:
            errors.append("SEMANTIC_WEIGHT must be between 0 and 1")
        if abs(self.bm25_weight + self.semantic_weight - 1.0) > 0.01:
            errors.append("BM25_WEIGHT + SEMANTIC_WEIGHT should sum to 1.0")
        return errors

@dataclass
class IndexingConfig:
    """Document indexing configuration."""
    max_file_size_mb: int = 50
    supported_extensions: List[str] = None
    index_batch_size: int = 100
    chunk_size: int = 512
    chunk_overlap: int = 50
    enable_incremental: bool = True
    reindex_interval_hours: int = 24
    parallel_workers: int = 4
    
    def __post_init__(self):
        """Initialize default supported extensions."""
        if self.supported_extensions is None:
            self.supported_extensions = [".py", ".js", ".ts", ".md", ".txt", ".json", ".yaml", ".yml"]

@dataclass
class APIConfig:
    """API server configuration."""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    reload: bool = False
    workers: int = 4
    timeout_keep_alive: int = 5
    max_request_size: int = 10 * 1024 * 1024  # 10MB
    rate_limit_per_minute: int = 60
    enable_metrics: bool = True
    metrics_port: int = 9090

class Settings:
    """
    Global application settings with hierarchical configuration support.
    Settings can be loaded from environment variables, config files, or defaults.
    """
    
    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize settings with optional config file.
        
        Args:
            config_file: Path to JSON configuration file
        """
        # Load from file if provided
        file_config = {}
        if config_file and os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    file_config = json.load(f)
                logger.info(f"Loaded configuration from {config_file}")
            except Exception as e:
                logger.warning(f"Failed to load config file {config_file}: {e}")
        
        # Database Configuration
        self.db = DatabaseConfig(
            timeout=int(os.getenv("DB_TIMEOUT", file_config.get("db", {}).get("timeout", 30))),
            max_connections=int(os.getenv("DB_MAX_CONNECTIONS", file_config.get("db", {}).get("max_connections", 10))),
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", file_config.get("db", {}).get("pool_recycle", 3600))),
            pool_pre_ping=bool(os.getenv("DB_POOL_PRE_PING", file_config.get("db", {}).get("pool_pre_ping", True))),
            pool_size=int(os.getenv("DB_POOL_SIZE", file_config.get("db", {}).get("pool_size", 5))),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", file_config.get("db", {}).get("max_overflow", 10)))
        )
        
        # Postgres-specific
        self.postgres = PostgresConfig(
            host=os.getenv("POSTGRES_HOST", file_config.get("postgres", {}).get("host", "localhost")),
            port=int(os.getenv("POSTGRES_PORT", file_config.get("postgres", {}).get("port", "5432"))),
            database=os.getenv("POSTGRES_DB", file_config.get("postgres", {}).get("database", "search_db")),
            user=os.getenv("POSTGRES_USER", file_config.get("postgres", {}).get("user", "admin")),
            password=os.getenv("POSTGRES_PASSWORD", file_config.get("postgres", {}).get("password", "secret")),
            ssl_mode=os.getenv("POSTGRES_SSL_MODE", file_config.get("postgres", {}).get("ssl_mode", "prefer")),
            connect_timeout=int(os.getenv("POSTGRES_CONNECT_TIMEOUT", file_config.get("postgres", {}).get("connect_timeout", "10")))
        )
        
        # SQLite Legacy
        self.sqlite_db_path = os.getenv("SQLITE_DB_PATH", file_config.get("sqlite", {}).get("db_path", "legacy_index.db"))
        
        # Security Configuration
        self.security = SecurityConfig(
            jwt_secret_key=os.getenv("JWT_SECRET_KEY", file_config.get("security", {}).get("jwt_secret_key", "default-secret-key-change-in-production")),
            jwt_algorithm=os.getenv("JWT_ALGORITHM", file_config.get("security", {}).get("jwt_algorithm", "HS256")),
            jwt_expiration_hours=int(os.getenv("JWT_EXPIRATION_HOURS", file_config.get("security", {}).get("jwt_expiration_hours", "24"))),
            bcrypt_rounds=int(os.getenv("BCRYPT_ROUNDS", file_config.get("security", {}).get("bcrypt_rounds", "12")))
        )
        
        # Search Engine Configuration
        self.search = SearchEngineConfig(
            embedding_dimension=int(os.getenv("EMBEDDING_DIMENSION", file_config.get("search", {}).get("embedding_dimension", "384"))),
            max_search_results=int(os.getenv("MAX_SEARCH_RESULTS", file_config.get("search", {}).get("max_search_results", "100"))),
            default_top_k=int(os.getenv("DEFAULT_TOP_K", file_config.get("search", {}).get("default_top_k", "10"))),
            similarity_threshold=float(os.getenv("SIMILARITY_THRESHOLD", file_config.get("search", {}).get("similarity_threshold", "0.7")))
        )
        
        # Indexing Configuration
        self.indexing = IndexingConfig(
            max_file_size_mb=int(os.getenv("MAX_FILE_SIZE_MB", file_config.get("indexing", {}).get("max_file_size_mb", "50"))),
            index_batch_size=int(os.getenv("INDEX_BATCH_SIZE", file_config.get("indexing", {}).get("index_batch_size", "100")))
        )
        
        # API Configuration
        self.api = APIConfig(
            host=os.getenv("API_HOST", file_config.get("api", {}).get("host", "0.0.0.0")),
            port=int(os.getenv("API_PORT", file_config.get("api", {}).get("port", "8000"))),
            debug=bool(os.getenv("API_DEBUG", file_config.get("api", {}).get("debug", "false").lower() == "true"))
        )
        
        # Logging
        log_level_str = os.getenv("LOG_LEVEL", file_config.get("logging", {}).get("level", "INFO"))
        try:
            self.log_level = LogLevel[log_level_str.upper()]
        except KeyError:
            self.log_level = LogLevel.INFO
            logger.warning(f"Invalid log level {log_level_str}, defaulting to INFO")
        
        self.log_file = os.getenv("LOG_FILE", file_config.get("logging", {}).get("file"))
        
        # Validate all configurations
        self._validate()
    
    def _validate(self):
        """Validate all configuration settings."""
        errors = []
        errors.extend(self.db.validate())
        errors.extend(self.search.validate())
        
        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            logger.error(error_msg)
            raise ValueError(error_msg)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary."""
        return {
            "db": asdict(self.db),
            "postgres": asdict(self.postgres),
            "sqlite_db_path": self.sqlite_db_path,
            "security": asdict(self.security),
            "search": asdict(self.search),
            "indexing": asdict(self.indexing),
            "api": asdict(self.api),
            "log_level": self.log_level.value,
            "log_file": self.log_file
        }
    
    def save(self, config_file: str):
        """Save settings to JSON file."""
        try:
            with open(config_file, 'w') as f:
                json.dump(self.to_dict(), f, indent=2)
            logger.info(f"Saved configuration to {config_file}")
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            raise

# Global settings instance (singleton pattern)
_settings: Optional[Settings] = None

def get_settings(config_file: Optional[str] = None) -> Settings:
    """Get or create global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings(config_file)
    return _settings

# Backward compatibility: create default settings instance
settings = get_settings()

# Legacy accessors for backward compatibility
DB_TIMEOUT = settings.db.timeout
DB_MAX_CONNECTIONS = settings.db.max_connections
POSTGRES_HOST = settings.postgres.host
POSTGRES_PORT = settings.postgres.port
POSTGRES_DB = settings.postgres.database
POSTGRES_USER = settings.postgres.user
POSTGRES_PASSWORD = settings.postgres.password
SQLITE_DB_PATH = settings.sqlite_db_path
JWT_SECRET_KEY = settings.security.jwt_secret_key
JWT_ALGORITHM = settings.security.jwt_algorithm
JWT_EXPIRATION_HOURS = settings.security.jwt_expiration_hours
BCRYPT_ROUNDS = settings.security.bcrypt_rounds
EMBEDDING_DIMENSION = settings.search.embedding_dimension
MAX_SEARCH_RESULTS = settings.search.max_search_results
DEFAULT_TOP_K = settings.search.default_top_k
SIMILARITY_THRESHOLD = settings.search.similarity_threshold
MAX_FILE_SIZE_MB = settings.indexing.max_file_size_mb
SUPPORTED_EXTENSIONS = settings.indexing.supported_extensions
INDEX_BATCH_SIZE = settings.indexing.index_batch_size
API_HOST = settings.api.host
API_PORT = settings.api.port
API_DEBUG = settings.api.debug
LOG_LEVEL = settings.log_level.value
LOG_FILE = settings.log_file
