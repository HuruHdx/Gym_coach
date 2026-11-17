from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Gym Coach"
    app_token: str = "dev-token"
    # 用户登录 JWT（HS256）。空则回落到 app_token 派生，生产务必单独配置
    jwt_secret: str = ""
    jwt_expire_days: int = 30
    database_url: str = "sqlite:///./data/gym.db"
    llm_provider: str = "mock"  # mock | openai_compatible
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    # 意图改写：暂与主模型共用；换独立小模型时改 intent_rewrite_provider / 后续扩展字段即可
    intent_rewrite_mode: str = "llm"  # rules | llm | hybrid（暂默认纯模型，避开规则误命中）
    intent_rewrite_provider: str = "same"  # same | off（后续可加独立 openai_compatible）
    memory_token_budget: int = 1800
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5174,http://127.0.0.1:5174"
    )
    # 后台 gym-admin 登录口令；空则回落到 app_token
    admin_password: str = ""
    # 配了 key 才把同一张图送到 LangSmith；本地 Debug 轨迹始终写库
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "gym-coach"
    # 公共资源存储：local（默认写 static/）| s3（Cloudflare R2 / OSS 等）
    storage_backend: str = "local"
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket_name: str = ""
    s3_public_base_url: str = ""
    s3_region: str = "auto"


settings = Settings()
