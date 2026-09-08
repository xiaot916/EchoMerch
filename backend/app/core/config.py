import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _load_dotenv() -> None:
    """Load the local .env as a development fallback without adding a dependency."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and name not in os.environ:
            os.environ[name] = value


_load_dotenv()


def _csv_env(name: str, default: str) -> list[str]:
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


def _csv_int_env(name: str, default: str) -> list[int]:
    return [int(value) for value in _csv_env(name, default)]


def _optional_int_env(name: str) -> int | None:
    value = os.getenv(name)
    return int(value) if value and value.strip() else None


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _project_path_env(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path.resolve())


@dataclass(frozen=True)
class Settings:
    legacy_database_url: str | None
    cors_origins: list[str]
    local_database_path: str
    default_store_id: int | None
    capture_database_path: str
    capture_source_directory: str
    contract_report_path: str
    daily_dry_run_directory: str
    auth_enabled: bool
    auth_session_days: int
    auth_cookie_secure: bool
    tmall_session_source: str
    tmall_browser_port: int
    tmall_cookie_env: str
    ai_base_url: str
    ai_api_path: str
    ai_api_key: str | None
    ai_model: str
    ai_timeout_seconds: float
    ai_credentials_path: str
    jackyun_token_url: str | None
    jackyun_inventory_url: str | None
    jackyun_package_url: str | None
    jackyun_package_detail_url: str | None
    jackyun_goods_url: str | None
    jackyun_credentials_path: str
    jackyun_token_cache_path: str | None
    jackyun_warehouse_ids: list[str]
    jackyun_cookie: str | None
    jackyun_appkey: str
    jackyun_ati: str
    jackyun_signature_secret: str | None
    jackyun_token: str | None
    jackyun_client_id: str | None
    jackyun_client_secret: str | None
    jackyun_username: str | None
    jackyun_password: str | None
    jackyun_store_ids: list[int]
    jackyun_token_ttl_seconds: int
    jackyun_inventory_refresh_minutes: int

    @property
    def jackyun_configured(self) -> bool:
        if not self.jackyun_inventory_url:
            return False
        if self.jackyun_token:
            return True
        candidate_paths = []
        if self.jackyun_credentials_path:
            candidate_paths.append(Path(self.jackyun_credentials_path).expanduser())
        if self.jackyun_token_cache_path:
            candidate_paths.append(Path(self.jackyun_token_cache_path).expanduser())
        project_root = Path(__file__).resolve().parents[3]
        candidate_paths.append(project_root.parent / "Arachne" / "JackyunV5" / "token_cache.json")
        return bool(self.jackyun_token_url and any(path.exists() for path in candidate_paths))


settings = Settings(
    legacy_database_url=os.getenv("LEGACY_DATABASE_URL"),
    cors_origins=_csv_env(
        "ECHO_CORS_ORIGINS",
        "http://localhost:9568,http://127.0.0.1:9568",
    ),
    local_database_path=_project_path_env(
        "ECHO_LOCAL_DATABASE_PATH",
        "artifacts/local/echomerch_local.sqlite3",
    ),
    default_store_id=_optional_int_env("ECHO_DEFAULT_STORE_ID"),
    capture_database_path=_project_path_env(
        "ECHO_CAPTURE_DATABASE_PATH",
        "artifacts/local/reqable_capture.sqlite3",
    ),
    capture_source_directory=os.getenv(
        "ECHO_CAPTURE_SOURCE_DIRECTORY",
        r"C:\Users\Moli\AppData\Roaming\Reqable\capture",
    ),
    contract_report_path=_project_path_env(
        "ECHO_CONTRACT_REPORT_PATH",
        "artifacts/local/reqable_api_request_pairs.json",
    ),
    daily_dry_run_directory=_project_path_env(
        "ECHO_DAILY_DRY_RUN_DIRECTORY",
        "artifacts/local",
    ),
    # Authentication is enabled by default. It can still be disabled
    # explicitly for isolated tests or one-off local diagnostics.
    auth_enabled=_bool_env("ECHO_AUTH_ENABLED", True),
    auth_session_days=int(os.getenv("ECHO_AUTH_SESSION_DAYS", "12")),
    auth_cookie_secure=_bool_env("ECHO_AUTH_COOKIE_SECURE", False),
    # Collection uses the dedicated logged-in browser by default. Environment
    # cookies remain available as an explicit deployment override.
    tmall_session_source=os.getenv("ECHO_TMALL_SESSION_SOURCE", "drissionpage").strip() or "drissionpage",
    tmall_browser_port=int(os.getenv("ECHO_TMALL_BROWSER_PORT", "9222")),
    tmall_cookie_env=os.getenv("ECHO_TMALL_COOKIE_ENV", "SYCM_COOKIE").strip() or "SYCM_COOKIE",
    ai_base_url=os.getenv("ECHO_AI_BASE_URL", "https://apihub.agnes-ai.com").strip().rstrip("/"),
    ai_api_path=os.getenv("ECHO_AI_API_PATH", "/v1/chat/completions").strip() or "/v1/chat/completions",
    ai_api_key=os.getenv("ECHO_AI_API_KEY") or None,
    ai_model=os.getenv("ECHO_AI_MODEL", "agnes-2.0-flash").strip() or "agnes-2.0-flash",
    ai_timeout_seconds=float(os.getenv("ECHO_AI_TIMEOUT_SECONDS", "45")),
    ai_credentials_path=_project_path_env(
        "ECHO_AI_CREDENTIALS_PATH",
        "artifacts/runtime/ai_credentials.bin",
    ),
    jackyun_token_url=os.getenv("ECHO_JACKYUN_TOKEN_URL", "https://web.jackyun.com/auth/refresh").strip() or None,
    jackyun_inventory_url=os.getenv("ECHO_JACKYUN_INVENTORY_URL", "https://web.jackyun.com/jkyun/erp-stock/warehouseStock/stockSkuList").strip() or None,
    jackyun_package_url=os.getenv(
        "ECHO_JACKYUN_PACKAGE_URL",
        "https://web.jackyun.com/jkyun/erp-goods/search/getskulistbycondition",
    ).strip() or None,
    jackyun_package_detail_url=os.getenv(
        "ECHO_JACKYUN_PACKAGE_DETAIL_URL",
        "https://web.jackyun.com/jkyun/erp-goods/package/getPackageId",
    ).strip() or None,
    jackyun_goods_url=os.getenv(
        "ECHO_JACKYUN_GOODS_URL",
        "https://web.jackyun.com/jkyun/erp-goods/search/getgoodsinfoandbaseunit",
    ).strip() or None,
    jackyun_credentials_path=_project_path_env(
        "ECHO_JACKYUN_CREDENTIALS_PATH",
        "artifacts/runtime/jackyun_credentials.bin",
    ),
    jackyun_token_cache_path=os.getenv("ECHO_JACKYUN_TOKEN_CACHE_PATH", "").strip() or None,
    jackyun_warehouse_ids=_csv_env("ECHO_JACKYUN_WAREHOUSE_IDS", ""),
    jackyun_cookie=os.getenv("ECHO_JACKYUN_COOKIE", "").strip() or None,
    jackyun_appkey=os.getenv("ECHO_JACKYUN_APPKEY", "jackyun_web_browser_2024").strip() or "jackyun_web_browser_2024",
    jackyun_ati=os.getenv("ECHO_JACKYUN_ATI", "8592270430974").strip() or "8592270430974",
    jackyun_signature_secret=os.getenv("ECHO_JACKYUN_SIGNATURE_SECRET", "").strip() or None,
    jackyun_token=os.getenv("ECHO_JACKYUN_TOKEN", "").strip() or None,
    jackyun_client_id=os.getenv("ECHO_JACKYUN_CLIENT_ID", "").strip() or None,
    jackyun_client_secret=os.getenv("ECHO_JACKYUN_CLIENT_SECRET", "").strip() or None,
    jackyun_username=os.getenv("ECHO_JACKYUN_USERNAME", "").strip() or None,
    jackyun_password=os.getenv("ECHO_JACKYUN_PASSWORD", "").strip() or None,
    jackyun_store_ids=_csv_int_env("ECHO_JACKYUN_STORE_IDS", ""),
    jackyun_token_ttl_seconds=max(60, int(os.getenv("ECHO_JACKYUN_TOKEN_TTL_SECONDS", "3600"))),
    jackyun_inventory_refresh_minutes=max(5, int(os.getenv("ECHO_JACKYUN_INVENTORY_REFRESH_MINUTES", "60"))),
)
