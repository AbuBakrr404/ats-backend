"""
config.py
---------
Loads environment variables into a typed Settings object.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    supabase_url: str
    supabase_service_key: str
    supabase_jwt_secret: str
    allowed_origins: str = "http://localhost:5173"

    # ---- RAG ----
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    rag_chat_model: str = "claude-sonnet-4-6"
    rag_top_k: int = 20
    rag_threshold: float = 0.35
    rag_max_candidates_in_context: int = 5

    class Config:
        env_file = ".env"


settings = Settings()