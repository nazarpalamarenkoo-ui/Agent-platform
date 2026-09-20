from pydantic_settings import BaseSettings

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
    
    QDRANT_URL: str
    QDRANT_COLLECTION: str 
    
    SEARXNG_URL: str
    
    JWT_SECRET_KEY: str
    
    MODEL_API_KEY: str
    class Config:
        env_file = ".env"

settings = Settings()