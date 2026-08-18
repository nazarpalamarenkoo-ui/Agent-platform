from pydantic_settings import BaseSettings

class TestSettings(BaseSettings):
    # Test DB
    TEST_DATABASE_URL: str
    class Config:
        env_file = ".env.test"

test_settings = TestSettings()