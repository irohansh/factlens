from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    BASE_DIR: Path = BASE_DIR
    HOST: str = os.getenv("FACTLENS_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("FACTLENS_PORT", "8000"))
    DEBUG: bool = os.getenv("FACTLENS_DEBUG", "true").lower() in ("true", "1", "yes")
    
    DB_PATH: Path = BASE_DIR / os.getenv("FACTLENS_DB_PATH", "data/factlens.db")
    UPLOAD_DIR: Path = BASE_DIR / os.getenv("UPLOAD_DIR", "data/uploads")
    
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
    MAX_PAGE_COUNT: int = int(os.getenv("MAX_PAGE_COUNT", "120"))
    ALLOWED_EXTENSIONS: set = {"pdf"}
    
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
    API_SECRET_KEY: str = os.getenv("API_SECRET_KEY", "").strip()

    @classmethod
    def init_dirs(cls) -> None:
        cls.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        cls.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

settings = Settings()
settings.init_dirs()
