from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    msg91_authkey: str
    msg91_integrated_number: str = "917340316302"
    webhook_secret: str
    admin_secret: str

    database_url: str = "sqlite:///./hotel_bot.db"
    menu_reset_hours: int = 24
    human_takeover_hours: int = 24

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
