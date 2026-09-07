from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "SWAT Reality Intelligence Engine"
    app_version: str = "0.1.0"
    api_key: str = "change-me"
    public_url: str = "http://localhost:8000"
    webauthn_rp_id: str = "localhost"
    webauthn_origin: str = "http://localhost:8000"
    webauthn_rp_name: str = "SWAT RIE"
    db_url: str = "sqlite:///./data/rie.db"
    fetch_timeout_seconds: float = 12.0
    max_source_chars: int = 30000
    max_upload_bytes: int = 50 * 1024 * 1024
    remote_media_enabled: bool = True
    remote_media_timeout_seconds: int = 90
    artifact_dir: str = "./data/artifacts"
    transcription_enabled: bool = False
    whisper_model: str = "tiny"
    video_keyframe_fps: float = 0.2
    user_agent: str = "SWAT-RIE/0.1 (+https://norug.es)"
    autonomous_search_enabled: bool = False
    search_provider: str = "bing"
    bing_search_api_key: str | None = None
    bing_search_endpoint: str = "https://api.bing.microsoft.com/v7.0/search"
    max_discovered_evidence: int = 5
    reverse_search_providers: str = "Google Lens,Bing Visual Search,Yandex Images,TinEye,InVID"
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RIE_", extra="ignore")

settings = Settings()
