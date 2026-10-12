from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Gym Coach"
    app_token: str = "dev-token"
    database_url: str = "sqlite:///./data/gym.db"
    llm_provider: str = "mock"  # mock | openai_compatible
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    # 意图改写：暂与主模型共用；换独立小模型时改 intent_rewrite_provider / 后续扩展字段即可
    intent_rewrite_mode: str = "hybrid"  # rules | llm | hybrid
    intent_rewrite_provider: str = "same"  # same | off（后续可加独立 openai_compatible）
    memory_token_budget: int = 1800
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"


settings = Settings()
