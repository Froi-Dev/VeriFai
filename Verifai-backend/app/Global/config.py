import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

# Ensure PaddleOCR does not stall on startup checking remote model sources
os.environ.setdefault("DISABLE_MODEL_SOURCE_CHECK", "True")

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "VeriFai API"
    api_v1_prefix: str = "/api/v1"
    database_url: str
    database_pool_size: int = Field(default=10, ge=1, le=50)
    database_max_overflow: int = Field(default=5, ge=0, le=50)
    database_pool_timeout_seconds: float = Field(default=5.0, ge=1.0, le=30.0)
    jwt_secret: SecretStr = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=15, ge=5, le=60)
    refresh_token_expire_days: int = Field(default=14, ge=1, le=90)
    refresh_token_reuse_grace_seconds: int = Field(default=15, ge=1, le=60)
    session_idle_expire_hours: int = Field(default=24, ge=1, le=720)
    max_active_sessions: int = Field(default=10, ge=1, le=100)

    access_cookie_name: str = "verifai_access"
    refresh_cookie_name: str = "verifai_refresh"
    cookie_domain: str | None = None
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    environment: str = "development"
    trusted_hosts: str = "localhost,127.0.0.1,testserver"
    max_request_bytes: int = Field(default=10_485_760, ge=1024, le=10_485_760)
    data_encryption_key: SecretStr | None = None

    password_reset_expire_minutes: int = Field(default=20, ge=5, le=60)
    frontend_reset_url: str = "http://localhost:5173/auth/reset"
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_address: str | None = None
    smtp_use_tls: bool = True

    rate_limit_storage_uri: str = "memory://"
    rate_limit_register: str = "5/minute"
    rate_limit_login: str = "10/minute"
    rate_limit_refresh: str = "20/minute"
    rate_limit_password_reset: str = "3/hour"
    rate_limit_me: str = "30/minute"
    rate_limit_logout: str = "10/minute"
    rate_limit_health: str = "300/minute"
    rate_limit_text_detection: str = "10/minute"
    rate_limit_image_detection: str = "6/minute"
    rate_limit_news_verification: str = "6/minute"

    result_cache_url: str | None = None
    result_cache_max_entries: int = Field(default=1_000, ge=100, le=100_000)
    text_result_cache_seconds: int = Field(default=3_600, ge=0, le=86_400)
    news_result_cache_seconds: int = Field(default=600, ge=0, le=86_400)
    image_result_cache_seconds: int = Field(default=600, ge=0, le=86_400)

    text_analysis_deadline_seconds: float = Field(default=30.0, ge=2.0, le=120.0)
    news_analysis_deadline_seconds: float = Field(default=35.0, ge=5.0, le=120.0)
    image_analysis_deadline_seconds: float = Field(default=55.0, ge=5.0, le=180.0)

    image_ocr_max_bytes: int = Field(default=10_000_000, ge=100_000, le=10_000_000)
    image_ocr_max_pixels: int = Field(default=6_000_000, ge=1_000_000, le=25_000_000)
    image_ocr_max_source_pixels: int = Field(default=80_000_000, ge=25_000_000, le=150_000_000)
    image_ocr_warmup: bool = False
    paddleocr_language: str = "en"
    ocr_medium_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    ocr_high_confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    gemini_api_keys: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    gemini_vision_model: str = "gemini-3.5-flash-lite"
    gemini_timeout_seconds: float = Field(default=30.0, ge=2.0, le=60.0)
    gemini_key_cooldown_seconds: int = Field(default=60, ge=5, le=3_600)

    text_model_path: Path = Path(r"C:\Users\dever\Downloads\xlmr-ai-human-best")
    text_model_device: Literal["auto", "cpu", "cuda"] = "auto"
    # Prefer model config label metadata. Set this only as an explicit override
    # for legacy exports whose labels are still documented externally.
    text_model_ai_label_id: int | None = Field(default=None, ge=0, le=1)
    text_model_max_length: int = Field(default=512, ge=32, le=512)
    text_model_stride: int = Field(default=64, ge=0, le=256)
    text_model_batch_size: int = Field(default=4, ge=1, le=32)
    text_model_max_concurrent_inferences: int = Field(default=2, ge=1, le=8)
    text_model_warmup: bool = False
    text_model_review_threshold: float = Field(default=0.65, gt=0.5, lt=1.0)

    google_search_api_key: SecretStr | None = None
    google_cse_id: str | None = None
    searchapi_api_key: SecretStr | None = None
    # AI Mode summaries are supplementary discovery aids. Their cited links,
    # not generated prose, are evaluated as evidence.
    searchapi_ai_mode_api_key: SecretStr | None = None
    searchapi_ai_mode_max_queries: int = Field(default=1, ge=1, le=3)
    serper_api_key: SecretStr | None = None
    serper_api_keys: SecretStr | None = None
    news_search_provider_order: str = "serper,searchapi,google"
    fact_check_domains: str = "verafiles.org,rappler.com,tsek.ph"
    quote_source_domains: str = "tribune.net.ph,smninewschannel.com"
    philippine_news_domains: str = (
        "abs-cbn.com,balita.net.ph,bilyonaryo.com,bomboradyo.com,brigadanews.ph,bulatlat.com,"
        "bulgaronline.com,businessmirror.com.ph,bworldonline.com,dailyguardian.com.ph,"
        "dailytribune.net.ph,davaotoday.com,dzrh.com.ph,gmanetwork.com,inquirer.net,"
        "journalnews.com.ph,malaya.com.ph,manilastandard.net,manilatimes.net,mb.com.ph,"
        "mindanews.com,news5.com.ph,onenews.ph,panaynews.net,philstar.com,pia.gov.ph,"
        "pna.gov.ph,pco.gov.ph,politiko.com.ph,rappler.com,remate.ph,smninewschannel.com,sunstar.com.ph,"
        "tribune.net.ph,tsek.ph,verafiles.org,"
        "ched.gov.ph,coa.gov.ph,comelec.gov.ph,dbm.gov.ph,deped.gov.ph,dilg.gov.ph,"
        "doe.gov.ph,doh.gov.ph,house.gov.ph,icc-cpi.int,officialgazette.gov.ph,ovp.gov.ph,"
        "pagasa.dost.gov.ph,phivolcs.dost.gov.ph,pnp.gov.ph,senate.gov.ph,dole.gov.ph,psa.gov.ph,bsp.gov.ph"
    )
    trusted_news_domains: str = "reuters.com,pna.gov.ph,pco.gov.ph,gmanetwork.com,abs-cbn.com,inquirer.net,verafiles.org,tsek.ph"
    news_tier_2_domains: str = (
        "rappler.com,philstar.com,mb.com.ph,news5.com.ph,sunstar.com.ph,tribune.net.ph,"
        "bomboradyo.com,bulgaronline.com,apnews.com,afp.com,bbc.com"
    )
    news_min_relevant_results: int = Field(default=3, ge=1, le=10)
    news_relevance_threshold: int = Field(default=40, ge=0, le=100)
    news_max_search_results: int = Field(default=20, ge=5, le=50)
    news_max_articles_to_scrape: int = Field(default=6, ge=1, le=10)
    news_max_concurrent_search_requests: int = Field(default=4, ge=1, le=20)
    news_max_concurrent_scrapes: int = Field(default=4, ge=1, le=20)
    image_max_concurrent_claims: int = Field(default=2, ge=1, le=3)
    news_max_evidence_items: int = Field(default=8, ge=1, le=20)
    news_max_related_evidence: int = Field(default=3, ge=0, le=10)
    news_search_timeout_seconds: float = Field(default=10.0, ge=2.0, le=30.0)
    news_scrape_timeout_seconds: float = Field(default=12.0, ge=2.0, le=30.0)
    news_max_article_bytes: int = Field(default=2_000_000, ge=100_000, le=5_000_000)
    news_max_redirects: int = Field(default=3, ge=0, le=5)
    news_old_story_days: int = Field(default=30, ge=1, le=3650)
    news_unrestricted_fallback: bool = True
    news_debug: bool = False

    gemini_adjudicator_model: str = "gemini-3.6-flash"
    gemini_adjudicator_timeout_seconds: float = Field(default=25.0, ge=5.0, le=60.0)
    news_use_llm_adjudicator: bool = True
    news_max_search_rounds: int = Field(default=3, ge=1, le=5)
    news_audit_log_enabled: bool = True
    news_audit_log_path: str = "logs/verification_audit.jsonl"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @field_validator("jwt_algorithm")
    @classmethod
    def restrict_jwt_algorithm(cls, value: str) -> str:
        if value not in {"HS256", "HS384", "HS512"}:
            raise ValueError("JWT_ALGORITHM must be an HMAC SHA-2 algorithm")
        return value

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.text_model_stride >= self.text_model_max_length - 2:
            raise ValueError("TEXT_MODEL_STRIDE must be smaller than the model window")
        if not self.is_production:
            return self
        if not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true in production")
        if "*" in self.allowed_origins or not self.allowed_origins:
            raise ValueError("CORS_ORIGINS must explicitly list trusted origins")
        if "*" in self.trusted_host_list or not self.trusted_host_list:
            raise ValueError("TRUSTED_HOSTS must explicitly list trusted hosts")
        if self.jwt_secret.get_secret_value().startswith("replace-"):
            raise ValueError("JWT_SECRET must be replaced in production")
        if len(set(self.jwt_secret.get_secret_value())) < 12:
            raise ValueError("JWT_SECRET does not have enough entropy")
        if self.data_encryption_key is None:
            raise ValueError("DATA_ENCRYPTION_KEY is required in production")
        try:
            Fernet(self.data_encryption_key.get_secret_value().encode())
        except (TypeError, ValueError) as exc:
            raise ValueError("DATA_ENCRYPTION_KEY must be a valid Fernet key") from exc
        if not self.rate_limit_storage_uri.startswith(("redis://", "rediss://")):
            raise ValueError("A Redis-backed rate-limit store is required in production")
        if not self.database_url_has_tls:
            raise ValueError("DATABASE_URL must require TLS in production")
        if not self.smtp_host or not self.smtp_from_address:
            raise ValueError("SMTP_HOST and SMTP_FROM_ADDRESS are required in production")
        if bool(self.smtp_username) != bool(self.smtp_password):
            raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be configured together")
        return self

    @property
    def allowed_origins(self) -> list[str]:
        return [
            origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()
        ]

    @property
    def trusted_host_list(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]

    @property
    def trusted_news_domain_list(self) -> list[str]:
        return self._csv_values(self.trusted_news_domains)

    @property
    def fact_check_domain_list(self) -> list[str]:
        return self._csv_values(self.fact_check_domains)

    @property
    def quote_source_domain_list(self) -> list[str]:
        return self._csv_values(self.quote_source_domains)

    @property
    def philippine_news_domain_list(self) -> list[str]:
        return self._csv_values(self.philippine_news_domains)

    @property
    def news_tier_2_domain_list(self) -> list[str]:
        return self._csv_values(self.news_tier_2_domains)

    @property
    def news_search_provider_list(self) -> list[str]:
        allowed = {"google", "searchapi", "searchapi_ai_mode", "serper"}
        return [
            provider
            for provider in self._csv_values(self.news_search_provider_order)
            if provider in allowed
        ]

    @property
    def gemini_api_key_list(self) -> list[str]:
        """Return the pooled Gemini keys without exposing them in settings reprs."""
        raw_values: list[str] = []
        if self.gemini_api_keys is not None:
            raw_values.append(self.gemini_api_keys.get_secret_value())
        if self.gemini_api_key is not None:
            raw_values.append(self.gemini_api_key.get_secret_value())
        keys = [
            key.strip()
            for value in raw_values
            for key in re.split(r"[,;\r\n]+", value)
            if key.strip()
        ]
        return list(dict.fromkeys(keys))

    @property
    def serper_api_key_list(self) -> list[str]:
        """Return the pooled Serper keys in fallback order without exposing them in settings reprs."""
        raw_values: list[str] = []
        if self.serper_api_key is not None:
            raw_values.append(self.serper_api_key.get_secret_value())
        if self.serper_api_keys is not None:
            raw_values.append(self.serper_api_keys.get_secret_value())
        keys = [
            key.strip()
            for value in raw_values
            for key in re.split(r"[,;\r\n]+", value)
            if key.strip()
        ]
        return list(dict.fromkeys(keys))

    @staticmethod
    def _csv_values(value: str) -> list[str]:
        return [item.strip().lower() for item in value.split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def effective_result_cache_url(self) -> str | None:
        if self.result_cache_url:
            return self.result_cache_url
        if self.rate_limit_storage_uri.startswith(("redis://", "rediss://")):
            return self.rate_limit_storage_uri
        return None

    @property
    def database_url_has_tls(self) -> bool:
        parsed = urlparse(self.database_url.replace("postgresql+psycopg://", "postgresql://"))
        query = parsed.query.lower()
        return "sslmode=require" in query or "sslmode=verify-full" in query


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
