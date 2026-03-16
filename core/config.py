from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    timezone: str = "Asia/Kolkata"

    # Database
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/erp"

    # Auth/JWT
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    refresh_token_days: int = 30
    password_pepper: str = ""

    # Legacy Telegram + Sheets (optional)
    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None
    google_sa_json_path: str = "service_account.json"
    platform_spreadsheet_id: str = ""
    company_template_spreadsheet_id: str = ""
    key_pepper: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
