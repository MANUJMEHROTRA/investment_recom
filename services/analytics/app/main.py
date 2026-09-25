"""Analytics service: stateless number-crunching. It never touches the database or the
internet - the backend sends it price data and stores whatever it returns."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from . import context, performance, scoring, strategy
from .indicators import macd, rsi, sma
from .schemas import AnalyzeRequest, AnalyzeResponse, IndicatorRequest, PerformanceRequest

app = FastAPI(title="Investment Analytics Service", version=scoring.MODEL_VERSION)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model_version": scoring.MODEL_VERSION}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    try:
        return scoring.analyze(req)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/indicators")
def indicators(req: IndicatorRequest) -> dict:
    df = scoring.to_frame(req.series)
    close = df["close"]
    m = macd(close)
    out = {
        "dates": [d.date().isoformat() for d in df.index],
        "close": close,
        "sma50": sma(close, 50),
        "sma200": sma(close, 200),
        "rsi14": rsi(close),
        "macd_hist": m["hist"],
    }
    return {k: (v if k == "dates" else [None if x != x else round(float(x), 4) for x in v]) for k, v in out.items()}


@app.post("/performance")
def perf(req: PerformanceRequest) -> dict:
    return performance.evaluate(req)


@app.post("/sectors")
def sectors(req: context.SectorRequest) -> list[dict]:
    return context.sector_rotation(req)


@app.post("/exits")
def exits(req: context.ExitRequest) -> list[dict]:
    return context.exit_signals(req)


@app.post("/fx")
def fx(req: context.FxRequest) -> dict:
    return context.fx_stats(req)


@app.post("/strategy")
def strategy_sim(req: strategy.StrategyRequest) -> dict:
    return strategy.simulate(req)


@app.get("/methodology")
def methodology() -> dict:
    return {
        "model_version": scoring.MODEL_VERSION,
        "weights": scoring.WEIGHTS,
        "rating_thresholds": [{"min_score": t, "rating": r} for t, r in scoring.RATING_THRESHOLDS],
        "components": {
            "trend": "Price above its 20/50/200-day moving averages, 50-day above 200-day, and a rising 50-day average.",
            "momentum": "Percentile rank vs the universe of 12-1 month, 6-month and 3-month returns. Stocks that have been going up tend to keep going up over 3-12 month horizons (the momentum effect).",
            "relative_strength": "Percentile rank of 6-month and 3-month return minus the S&P 500's return. Favours leaders over laggards.",
            "timing": "Short-term entry quality: RSI in a healthy 45-65 zone (overbought >75 is penalised), MACD above its signal line, fresh bullish crossovers, and proximity to the 52-week high.",
            "risk": "Percentile rank of low 3-month volatility (50%), shallow 1-year max drawdown (30%) and high 1-year Sharpe ratio (20%).",
            "fundamentals": "Forward P/E, revenue growth, profit margin and debt/equity from Yahoo Finance. Missing data is scored neutral (50).",
        },
        "rules": [
            "Stocks in a confirmed downtrend (price and 50-day both below the 200-day) are capped at Hold.",
            "In a Risk-Off market Strong Buy is downgraded to Buy, and suggested equity exposure drops to 30%.",
            "Position weights for the top picks are inverse-volatility weighted and scaled by the regime's equity exposure; the rest stays in cash.",
            "Suggested stop-loss is 2x the 14-day Average True Range below the latest close.",
        ],
        "regime": "Risk-On / Neutral / Risk-Off from S&P 500 vs its 200-day average, VIX level, and breadth (share of tracked stocks above their 200-day average). Exposure 100% / 60% / 30%.",
    }
