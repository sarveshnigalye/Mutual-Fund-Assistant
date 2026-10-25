from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application configuration loaded from environment variables / .env file."""

    # LLM Configuration (Groq default)
    llm_provider: str = Field(default="groq", validation_alias="LLM_PROVIDER")
    groq_api_key: Optional[str] = Field(default="", validation_alias="GROQ_API_KEY")
    groq_model: str = Field(default="openai/gpt-oss-120b", validation_alias="GROQ_MODEL")
    llm_model: str = Field(default="openai/gpt-oss-120b", validation_alias="LLM_MODEL")
    llm_temperature: float = Field(default=0.1, validation_alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=300, validation_alias="LLM_MAX_TOKENS")

    # Optional Fallbacks
    google_api_key: Optional[str] = Field(default="", validation_alias="GOOGLE_API_KEY")
    openai_api_key: Optional[str] = Field(default="", validation_alias="OPENAI_API_KEY")

    # Embeddings
    embedding_provider: str = Field(default="local", validation_alias="EMBEDDING_PROVIDER")
    embedding_model: str = Field(default="all-MiniLM-L6-v2", validation_alias="EMBEDDING_MODEL")

    # Vector Store
    vectorstore_path: str = Field(default="./data/vectorstore", validation_alias="VECTORSTORE_PATH")
    vectorstore_collection: str = Field(default="mf_faq_corpus", validation_alias="VECTORSTORE_COLLECTION")

    # Retrieval
    retrieval_top_k: int = Field(default=5, validation_alias="RETRIEVAL_TOP_K")
    retrieval_similarity_threshold: float = Field(default=0.65, validation_alias="RETRIEVAL_SIMILARITY_THRESHOLD")

    # Chat Database
    chat_db_path: str = Field(default="./data/chat.db", validation_alias="CHAT_DB_PATH")

    # Server Configuration
    api_host: str = Field(default="0.0.0.0", validation_alias="API_HOST")
    api_port: int = Field(default=8000, validation_alias="API_PORT")
    streamlit_port: int = Field(default=8501, validation_alias="STREAMLIT_PORT")

    # Scraping
    browser_type: str = Field(default="edge", validation_alias="BROWSER_TYPE")
    scrape_delay_seconds: int = Field(default=2, validation_alias="SCRAPE_DELAY_SECONDS")
    chrome_driver_path: str = Field(default="auto", validation_alias="CHROME_DRIVER_PATH")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()

