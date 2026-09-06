from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "SWAT Reality Intelligence Engine"
    app_version: str = "0.1.0"
    api_key: str = "change-me"
    db_url: str = "sqlite:///./data/rie.db"
    fetch_timeout_seconds: float = 12.0
    max_source_chars: int = 30000
    user_agent: str = "SWAT-RIE/0.1 (+https://norug.es)"
    autonomous_search_enabled: bool = False
    search_provider: str = "bing"
    bing_search_api_key: str | None = None
    bing_search_endpoint: str = "https://api.bing.microsoft.com/v7.0/search"
    max_discovered_evidence: int = 5
    reverse_search_providers: str = "Google Lens,Bing Visual Search,Yandex Images,TinEye,InVID"
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RIE_", extra="ignore")

settings = Settings()
