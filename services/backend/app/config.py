from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# A liquid, sector-diversified set of US large caps, mid caps, small caps and ETFs.
# Override with UNIVERSE="AAPL,MSFT,..." in .env to track your own watchlist. Size
# buckets (Mega/Large/Mid/Small) are assigned from live market caps, not from this list.
DEFAULT_UNIVERSE = [
    # Technology & communication
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AVGO", "ORCL", "CRM", "AMD", "ADBE",
    "CSCO", "QCOM", "TXN", "IBM", "INTC", "NFLX", "PLTR", "UBER", "T", "VZ", "DIS",
    # Consumer
    "AMZN", "TSLA", "WMT", "COST", "HD", "MCD", "NKE", "SBUX", "PG", "KO", "PEP",
    # Financials
    "BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS",
    # Healthcare
    "LLY", "UNH", "JNJ", "MRK", "ABBV", "PFE", "TMO", "ABT",
    # Industrials, energy, utilities
    "CAT", "DE", "GE", "HON", "RTX", "LMT", "UPS", "XOM", "CVX", "NEE",
    # Mid caps (roughly $2-15B)
    "ELF", "CELH", "FIVE", "WING", "CROX", "LSCC", "MTSI", "EXEL", "HALO", "SAIA", "TXRH",
    "AAON", "FN", "CVLT", "DUOL", "MEDP", "ONTO", "RMBS", "ENSG", "SFM", "CAVA", "BJ",
    # Small caps (roughly $0.3-2B+)
    "CALM", "SHAK", "BOOT", "PLMR", "CORT", "CPRX", "IDCC", "POWL", "STRL", "UFPT",
    "YELP", "ZETA", "HIMS", "OSCR", "UPST", "IONQ",
    # ETFs (broad / sector / gold)
    "QQQ", "IWM", "GLD", "XLK", "XLV", "XLF", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC",
]

# Sector names as Yahoo Finance reports them -> the SPDR ETF used as that sector's benchmark.
SECTOR_ETFS = {
    "Technology": "XLK", "Healthcare": "XLV", "Financial Services": "XLF", "Energy": "XLE",
    "Industrials": "XLI", "Consumer Cyclical": "XLY", "Consumer Defensive": "XLP", "Utilities": "XLU",
    "Basic Materials": "XLB", "Real Estate": "XLRE", "Communication Services": "XLC",
}


def cap_category(quote_type: str | None, market_cap: float | None) -> str | None:
    if quote_type == "ETF":
        return "ETF"
    if not market_cap:
        return None
    for floor, label in ((200e9, "Mega"), (10e9, "Large"), (2e9, "Mid"), (300e6, "Small")):
        if market_cap >= floor:
            return label
    return "Micro"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://invest:invest@localhost:5432/invest"
    analytics_url: str = "http://localhost:8001"
    agent_url: str = "http://localhost:8002"

    universe: str = ""
    benchmark: str = "SPY"
    volatility_index: str = "^VIX"
    fx_symbol: str = "USDINR=X"  # INR per USD
    fx_markup_pct: float = 1.0  # your broker/bank's FX spread, each way
    top_n: int = 10
    history_period: str = "2y"
    fundamentals_max_age_days: int = 7
    fetch_fundamentals: bool = True

    # Daily run after the US close (times in America/New_York).
    schedule_hour: int = 17
    schedule_minute: int = 0
    # Pre-market news brief (America/New_York; 07:30 ET is 17:00 / 18:00 IST).
    brief_hour: int = 7
    brief_minute: int = 30
    brief_candidates: int = 15
    run_on_startup: bool = True
    backfill_days_on_first_start: int = 60

    quote_cache_seconds: int = 60
    cors_origins: str = "http://localhost:5173,http://localhost:3000,https://manujmehrotra.github.io"

    @property
    def universe_list(self) -> list[str]:
        custom = [s.strip().upper() for s in self.universe.split(",") if s.strip()]
        return custom or list(DEFAULT_UNIVERSE)

    @property
    def all_symbols(self) -> list[str]:
        return list(dict.fromkeys([self.benchmark, self.volatility_index, self.fx_symbol, *SECTOR_ETFS.values(), *self.universe_list]))

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
