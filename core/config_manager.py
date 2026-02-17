"""Centralized configuration management with validation"""
import os
import yaml
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

class SecurityConfig(BaseModel):
    max_file_writes: int = Field(default=10, ge=1)
    max_file_size_mb: int = Field(default=1, ge=1)
    max_plan_steps: int = Field(default=20, ge=1, le=100)
    allowed_roots: List[str] = Field(default=[".", "./output", "./workspace", "./temp"])
    blocked_paths: List[str] = Field(default=[
        "C:\\Windows", "C:\\Program Files", "C:\\System32",
        "/etc", "/usr", "/bin", "/sbin", "/root",
        "~/.ssh", "~/.aws", "~/.config"
    ])
    blocked_extensions: List[str] = Field(default=[".exe", ".bat", ".cmd", ".ps1", ".sh", ".dll"])

class LLMConfig(BaseModel):
    default_model: str = "qwen"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=100)
    max_retries: int = Field(default=3, ge=1, le=10)
    timeout_seconds: int = Field(default=120, ge=10)
    ollama_url: str = "http://localhost:11434"

class TimeoutConfig(BaseModel):
    sandbox_test: int = Field(default=30, ge=5)
    llm_request: int = Field(default=120, ge=10)
    health_check: int = Field(default=5, ge=1)
    startup_wait: int = Field(default=2, ge=1)

class APIConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1024, le=65535)
    url: str = "http://localhost:8000"

class SessionConfig(BaseModel):
    conversation_history_limit: int = Field(default=20, ge=1)

class ImprovementConfig(BaseModel):
    max_iterations: int = Field(default=10, ge=1)
    auto_approve_low_risk: bool = True
    sandbox_timeout: int = Field(default=120, ge=10)
    approval_timeout: int = Field(default=300, ge=30)
    max_retries: int = Field(default=3, ge=1, le=10)
    warmup_enabled: bool = False
    max_error_history: int = Field(default=10, ge=1)
    rate_limit_delay: float = Field(default=0.5, ge=0.0)
    max_logs_display: int = Field(default=50, ge=10)
    code_preview_chars: int = Field(default=3000, ge=500)
    protected_files: List[str] = Field(default=[
        'core/immutable_brain_stem.py',
        'core/config_manager.py',
        'api/server.py'
    ])

class Config(BaseModel):
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    timeouts: TimeoutConfig = Field(default_factory=TimeoutConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    improvement: ImprovementConfig = Field(default_factory=ImprovementConfig)
    
    # Database paths
    db_plan_history: str = "data/plan_history.db"
    db_analytics: str = "data/analytics.db"
    db_conversations: str = "data/conversations.db"
    
    @classmethod
    def load(cls, config_path: str = "config.yaml") -> "Config":
        """Load config from YAML with environment variable overrides"""
        config_file = Path(config_path)
        
        if config_file.exists():
            with open(config_file, 'r') as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}
        
        config = cls(**data)
        
        # Environment variable overrides
        if api_url := os.getenv("CUA_API_URL"):
            config.api.url = api_url
        if api_port := os.getenv("CUA_API_PORT"):
            config.api.port = int(api_port)
        if max_writes := os.getenv("CUA_MAX_FILE_WRITES"):
            config.security.max_file_writes = int(max_writes)
        if ollama_url := os.getenv("OLLAMA_URL"):
            config.llm.ollama_url = ollama_url
        
        return config

# Global config instance
_config: Optional[Config] = None

def get_config() -> Config:
    """Get global config instance"""
    global _config
    if _config is None:
        _config = Config.load()
    return _config

def reload_config():
    """Reload config from file"""
    global _config
    _config = Config.load()
