from pydantic_settings import BaseSettings
from typing import Literal
class Settings(BaseSettings):
    DATABASE_URL: str
    DATABASE_URL_LOCAL: str
    # DB — connection pool
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    DB_POOL_PRE_PING: bool = True
    DB_USE_NULLPOOL: bool = False
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    # Redis 
    REDIS_URL: str
    QDRANT_URL: str
    QDRANT_COLLECTION: str 
    
    SEARXNG_URL: str
    
    JWT_SECRET_KEY: str
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: str
    MAIL_PORT: int
    MAIL_SERVER: str
    MAIL_STARTTLS: bool
    MAIL_SSL_TLS: bool
    USE_CREDENTIALS: bool
    
    PROJECT_NAME: str
    FRONTEND_URL: str
    
    MODEL_API_KEY: str
    
    AGENTIC_STRATEGY: Literal["heuristic", "llm"] = "llm"
    
    JUDGE_BASE_URL: str
    JUDGE_MODEL: str
    JUDGE_TIMEOUT: int
    JUDGE_BATCH_SIZE: int
    JUDGE_ACCEPTANCE_THRESHOLD: float
    JUDGE_API_KEY: str
    JUDGE_MAX_TOKENS: int
    JUDGE_USE_JSON_SCHEMA: bool
    DISCOVERY_MAX_RESULTS_PER_QUERY: int
    RANKER_TOP_N: int
    class Config:
        env_file = ".env"

settings = Settings()