from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str = ""
    barista_ids: str = ""  # через запятую: "123,456"
    log_level: str = "INFO"
    log_format: str = "json"  # "json" | "text"

    class Config:
        env_file = Path(__file__).parent.parent / ".env"

    @property
    def barista_id_list(self) -> list[int]:
        if not self.barista_ids:
            return []
        return [int(x.strip()) for x in self.barista_ids.split(",") if x.strip()]

    def is_barista(self, user_id: int) -> bool:
        return user_id in self.barista_id_list

    def check_required(self) -> None:
        """Проверка обязательных переменных при старте"""
        if not self.bot_token:
            raise ValueError("BOT_TOKEN не задан в .env")


settings = Settings()
