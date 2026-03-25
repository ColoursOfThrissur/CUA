"""
FinancialAnalysisTool — multi-layer financial analysis using yfinance + LLM advisor.
Layers: price data → technicals → sentiment → portfolio → advisor insight.
"""
import json
from datetime import datetime, timezone
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel


# Common name → Yahoo Finance symbol
_TICKER_MAP = {
    # Indian indices
    "nifty50": "^NSEI", "nifty 50": "^NSEI", "nifty": "^NSEI",
    "sensex": "^BSESN", "bse sensex": "^BSESN",
    "banknifty": "^NSEBANK", "bank nifty": "^NSEBANK",
    # US indices
    "sp500": "^GSPC", "s&p500": "^GSPC", "s&p 500": "^GSPC",
    "dow": "^DJI", "dow jones": "^DJI", "djia": "^DJI",
    "nasdaq": "^IXIC", "nasdaq composite": "^IXIC",
    "vix": "^VIX",
    # Crypto
    "bitcoin": "BTC-USD", "btc": "BTC-USD",
    "ethereum": "ETH-USD", "eth": "ETH-USD",
}


def _normalize_ticker(ticker: str) -> str:
    """Map common names to correct Yahoo Finance symbols."""
    key = ticker.strip().lower()
    return _TICKER_MAP.get(key, ticker.strip().upper())


_VALID_PERIODS = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}
_PERIOD_MAP = {
    "day": "1d", "today": "1d", "1day": "1d", "daily": "1d",
    "week": "5d", "1week": "5d",
    "month": "1mo", "1month": "1mo", "monthly": "1mo",
    "3months": "3mo", "quarter": "3mo",
    "6months": "6mo", "halfyear": "6mo",
    "year": "1y", "1year": "1y", "yearly": "1y", "annual": "1y",
    "2years": "2y", "5years": "5y",
}


def _normalize_period(period: str, default: str = "3mo") -> str:
    """Map LLM-generated period strings to valid yfinance period values."""
    p = (period or "").strip().lower().replace(" ", "")
    if p in _VALID_PERIODS:
        return p
    return _PERIOD_MAP.get(p, default)


class FinancialAnalysisTool(BaseTool):
    """Multi-layer financial analysis: data → technicals → sentiment → portfolio → LLM advisor."""

    def __init__(self, orchestrator=None):
        self.description = "Financial analysis tool with price data, technicals, sentiment, portfolio analysis, and LLM advisor insights."
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        # Fix yfinance TzCache Windows path conflict
        try:
            import yfinance as yf
            from pathlib import Path
            cache_dir = Path.home() / ".cache" / "yfinance"
            cache_dir.mkdir(parents=True, exist_ok=True)
            yf.set_tz_cache_location(str(cache_dir))
        except Exception:
            pass
        super().__init__()

    def register_capabilities(self):
        self.add_capability(ToolCapability(
            name="get_price_data",
            description="Fetch OHLCV price history and fundamentals (P/E, EPS, beta, revenue) for one or more tickers.",
            parameters=[
                Parameter("tickers", ParameterType.LIST, "List of ticker symbols e.g. ['AAPL','NVDA']", required=True),
                Parameter("period", ParameterType.STRING, "History period: 1mo, 3mo, 6mo, 1y, 2y", required=False, default="3mo"),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=["yfinance"]
        ), self._handle_get_price_data)

        self.add_capability(ToolCapability(
            name="get_technicals",
            description="Compute RSI, MACD, moving averages (20/50), and Bollinger Bands for a ticker.",
            parameters=[
                Parameter("ticker", ParameterType.STRING, "Single ticker symbol", required=True),
                Parameter("period", ParameterType.STRING, "History period for calculation", required=False, default="6mo"),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=["yfinance", "pandas"]
        ), self._handle_get_technicals)

        self.add_capability(ToolCapability(
            name="get_sentiment",
            description="Fetch recent news headlines for tickers and score them bullish/bearish/neutral via LLM.",
            parameters=[
                Parameter("tickers", ParameterType.LIST, "List of ticker symbols", required=True),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=["yfinance"]
        ), self._handle_get_sentiment)

        self.add_capability(ToolCapability(
            name="get_portfolio_analysis",
            description="Analyse a portfolio: sector exposure, concentration risk, Sharpe ratio, max drawdown, correlation.",
            parameters=[
                Parameter("holdings", ParameterType.DICT, "Dict of ticker→shares e.g. {'AAPL': 10, 'NVDA': 5}", required=True),
                Parameter("period", ParameterType.STRING, "History period for metrics", required=False, default="1y"),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=["yfinance", "pandas"]
        ), self._handle_get_portfolio_analysis)

        self.add_capability(ToolCapability(
            name="get_advisor_insight",
            description="Full advisor analysis: runs all layers then asks LLM to act as risk manager giving actionable insights.",
            parameters=[
                Parameter("holdings", ParameterType.DICT, "Dict of ticker→shares. Use {} for single-stock queries.", required=True),
                Parameter("question", ParameterType.STRING, "User question e.g. 'how am I doing?' or 'should I trim NVDA?'", required=False, default=""),
                Parameter("period", ParameterType.STRING, "History period", required=False, default="3mo"),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=["yfinance", "pandas"]
        ), self._handle_get_advisor_insight)

    # ── execute routing ──────────────────────────────────────────────────────

    def execute(self, operation: str, **kwargs) -> ToolResult:
        return self.execute_capability(operation, **kwargs)

    # ── handlers ─────────────────────────────────────────────────────────────

    def _handle_get_price_data(self, **kwargs) -> dict:
        tickers = kwargs.get("tickers", [])
        period = _normalize_period(kwargs.get("period", "3mo"), default="3mo")
        if not tickers:
            return {"success": False, "error": "tickers list is required"}
        tickers = [_normalize_ticker(t) for t in tickers]
        try:
            import yfinance as yf
        except ImportError:
            return {"success": False, "error": "yfinance not installed. Run: pip install yfinance"}

        result = {}
        for ticker in tickers:
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period=period)
                if hist.empty:
                    result[ticker] = {"error": "no data returned"}
                    continue
                info = t.info or {}
                result[ticker] = {
                    "current_price": round(float(hist["Close"].iloc[-1]), 2),
                    "price_change_pct": round(float((hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100), 2),
                    "high_52w": round(float(info.get("fiftyTwoWeekHigh") or hist["High"].max()), 2),
                    "low_52w": round(float(info.get("fiftyTwoWeekLow") or hist["Low"].min()), 2),
                    "avg_volume": int(hist["Volume"].mean()),
                    "pe_ratio": info.get("trailingPE"),
                    "eps": info.get("trailingEps"),
                    "beta": info.get("beta"),
                    "revenue": info.get("totalRevenue"),
                    "market_cap": info.get("marketCap"),
                    "sector": info.get("sector", "Unknown"),
                    "ohlcv_tail": hist[["Open", "High", "Low", "Close", "Volume"]].tail(5).round(2).to_dict(orient="records"),
                }
            except Exception as e:
                result[ticker] = {"error": str(e)}
        return {"success": True, "data": result, "period": period}

    def _handle_get_technicals(self, **kwargs) -> dict:
        ticker = kwargs.get("ticker", "")
        period = _normalize_period(kwargs.get("period", "6mo"), default="6mo")
        if not ticker:
            return {"success": False, "error": "ticker is required"}
        ticker = _normalize_ticker(ticker)
        try:
            import yfinance as yf
            import pandas as pd
        except ImportError as e:
            return {"success": False, "error": f"Missing dependency: {e}"}

        try:
            hist = yf.Ticker(ticker).history(period=period)
            if hist.empty:
                return {"success": False, "error": f"No data for {ticker}"}

            close = hist["Close"]

            # RSI (14)
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain / loss.replace(0, float("nan"))
            rsi = float(round((100 - 100 / (1 + rs)).iloc[-1], 2))

            # MACD (12/26/9)
            ema12 = close.ewm(span=12).mean()
            ema26 = close.ewm(span=26).mean()
            macd_line = ema12 - ema26
            signal_line = macd_line.ewm(span=9).mean()
            macd_val = float(round(macd_line.iloc[-1], 4))
            signal_val = float(round(signal_line.iloc[-1], 4))

            # Moving averages
            ma20 = float(round(close.rolling(20).mean().iloc[-1], 2)) if len(close) >= 20 else None
            ma50 = float(round(close.rolling(50).mean().iloc[-1], 2)) if len(close) >= 50 else None

            # Bollinger Bands (20, 2σ)
            bb_mid = close.rolling(20).mean()
            bb_std = close.rolling(20).std()
            bb_upper = float(round((bb_mid + 2 * bb_std).iloc[-1], 2))
            bb_lower = float(round((bb_mid - 2 * bb_std).iloc[-1], 2))

            current = float(round(close.iloc[-1], 2))
            trend = "bullish" if (ma20 and current > ma20) else "bearish"
            rsi_signal = "overbought" if rsi > 70 else ("oversold" if rsi < 30 else "neutral")

            return {
                "success": True,
                "ticker": ticker,
                "current_price": current,
                "rsi": rsi,
                "rsi_signal": rsi_signal,
                "macd": macd_val,
                "macd_signal": signal_val,
                "macd_crossover": "bullish" if macd_val > signal_val else "bearish",
                "ma20": ma20,
                "ma50": ma50,
                "trend": trend,
                "bollinger_upper": bb_upper,
                "bollinger_lower": bb_lower,
                "bollinger_position": "above_upper" if current > bb_upper else ("below_lower" if current < bb_lower else "within_bands"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_get_sentiment(self, **kwargs) -> dict:
        tickers = kwargs.get("tickers", [])
        if not tickers:
            return {"success": False, "error": "tickers list is required"}
        tickers = [_normalize_ticker(t) for t in tickers]
        try:
            import yfinance as yf
        except ImportError:
            return {"success": False, "error": "yfinance not installed"}

        result = {}
        for ticker in tickers:
            try:
                news_items = yf.Ticker(ticker).news or []
                headlines = [n.get("content", {}).get("title", "") or n.get("title", "") for n in news_items[:8]]
                headlines = [h for h in headlines if h]
                if not headlines:
                    result[ticker] = {"sentiment": "neutral", "headlines": [], "reason": "no news found"}
                    continue

                prompt = (
                    f"Rate the overall market sentiment for {ticker} based on these headlines.\n"
                    f"Headlines:\n" + "\n".join(f"- {h}" for h in headlines) +
                    "\n\nReply with JSON only: {\"sentiment\": \"bullish|bearish|neutral\", \"score\": -1.0 to 1.0, \"summary\": \"one sentence\"}"
                )
                raw = self.services.llm.generate(prompt, temperature=0.1, max_tokens=120)
                parsed = self._parse_json(raw) or {}
                result[ticker] = {
                    "sentiment": parsed.get("sentiment", "neutral"),
                    "score": parsed.get("score", 0.0),
                    "summary": parsed.get("summary", ""),
                    "headlines": headlines,
                }
            except Exception as e:
                result[ticker] = {"sentiment": "neutral", "error": str(e)}
        return {"success": True, "data": result}

    def _handle_get_portfolio_analysis(self, **kwargs) -> dict:
        holdings = kwargs.get("holdings", {})
        period = _normalize_period(kwargs.get("period", "1y"), default="1y")
        if not holdings:
            return {"success": False, "error": "holdings dict is required"}
        holdings = {_normalize_ticker(k): v for k, v in holdings.items()}
        try:
            import yfinance as yf
            import pandas as pd
        except ImportError as e:
            return {"success": False, "error": f"Missing dependency: {e}"}

        try:
            tickers = list(holdings.keys())
            prices = {}
            sectors = {}
            for ticker in tickers:
                t = yf.Ticker(ticker)
                hist = t.history(period=period)
                if not hist.empty:
                    prices[ticker] = hist["Close"]
                info = t.info or {}
                sectors[ticker] = info.get("sector", "Unknown")

            if not prices:
                return {"success": False, "error": "Could not fetch price data for any ticker"}

            price_df = pd.DataFrame(prices).dropna()
            returns = price_df.pct_change().dropna()

            # Portfolio value and weights
            latest = {t: float(price_df[t].iloc[-1]) for t in price_df.columns}
            values = {t: latest[t] * holdings.get(t, 0) for t in price_df.columns}
            total_value = sum(values.values())
            weights = {t: round(v / total_value * 100, 1) for t, v in values.items()} if total_value > 0 else {}

            # Sector exposure
            sector_exposure = {}
            for t, w in weights.items():
                s = sectors.get(t, "Unknown")
                sector_exposure[s] = round(sector_exposure.get(s, 0) + w, 1)

            # Concentration risk (HHI)
            hhi = sum((w / 100) ** 2 for w in weights.values())
            concentration = "high" if hhi > 0.25 else ("medium" if hhi > 0.15 else "low")

            # Portfolio returns (weighted)
            w_series = pd.Series({t: holdings.get(t, 0) * latest.get(t, 0) for t in returns.columns})
            w_series = w_series / w_series.sum()
            port_returns = returns.dot(w_series)

            # Sharpe ratio (annualised, assume 0% risk-free)
            sharpe = float(round((port_returns.mean() / port_returns.std()) * (252 ** 0.5), 2)) if port_returns.std() > 0 else 0.0

            # Max drawdown
            cum = (1 + port_returns).cumprod()
            drawdown = float(round(((cum / cum.cummax()) - 1).min() * 100, 2))

            # Correlation matrix (top pairs)
            corr = returns.corr().round(2)
            high_corr_pairs = []
            cols = list(corr.columns)
            for i in range(len(cols)):
                for j in range(i + 1, len(cols)):
                    v = float(corr.iloc[i, j])
                    if abs(v) > 0.7:
                        high_corr_pairs.append({"pair": f"{cols[i]}/{cols[j]}", "correlation": v})

            return {
                "success": True,
                "total_value": round(total_value, 2),
                "weights_pct": weights,
                "sector_exposure_pct": sector_exposure,
                "concentration_risk": concentration,
                "hhi": round(hhi, 3),
                "sharpe_ratio": sharpe,
                "max_drawdown_pct": drawdown,
                "high_correlation_pairs": high_corr_pairs,
                "period": period,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_get_advisor_insight(self, **kwargs) -> dict:
        holdings = kwargs.get("holdings", {})
        question = kwargs.get("question", "")
        period = _normalize_period(kwargs.get("period", "3mo"), default="3mo")

        tickers = [_normalize_ticker(t) for t in holdings.keys()] if holdings else []
        holdings = {_normalize_ticker(k): v for k, v in holdings.items()} if holdings else {}
        if not tickers:
            return {"success": False, "error": "holdings dict with at least one ticker is required"}

        # Layer 1: price data
        price_data = self._handle_get_price_data(tickers=tickers, period=period)

        # Layer 2: technicals (per ticker)
        technicals = {}
        for t in tickers:
            technicals[t] = self._handle_get_technicals(ticker=t, period="6mo")

        # Layer 3: sentiment
        sentiment = self._handle_get_sentiment(tickers=tickers)

        # Layer 4: portfolio (only if multi-ticker with shares)
        portfolio = None
        if len(tickers) > 1 and any(v > 0 for v in holdings.values()):
            portfolio = self._handle_get_portfolio_analysis(holdings=holdings, period="1y")

        # Layer 5: LLM advisor
        context_parts = [f"DATE: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"]

        if price_data.get("success"):
            context_parts.append("PRICE DATA:\n" + json.dumps(price_data["data"], indent=2))

        tech_summary = {t: {k: v for k, v in d.items() if k != "success"} for t, d in technicals.items() if d.get("success")}
        if tech_summary:
            context_parts.append("TECHNICALS:\n" + json.dumps(tech_summary, indent=2))

        if sentiment.get("success"):
            context_parts.append("SENTIMENT:\n" + json.dumps(sentiment["data"], indent=2))

        if portfolio and portfolio.get("success"):
            context_parts.append("PORTFOLIO METRICS:\n" + json.dumps({k: v for k, v in portfolio.items() if k != "success"}, indent=2))

        user_q = question.strip() or "Give me a full portfolio review with actionable recommendations."

        prompt = (
            "You are a professional risk manager and financial advisor. "
            "Analyse the data below and give specific, actionable insights. "
            "Think at portfolio level — sector concentration, momentum, risk. "
            "Give concrete actions (e.g. 'trim NVDA by 10%, rotate into XOM'). "
            "Be direct and concise.\n\n"
            + "\n\n".join(context_parts)
            + f"\n\nUSER QUESTION: {user_q}\n\n"
            "Reply with JSON: {\"summary\": \"2-3 sentence overview\", \"insights\": [\"insight1\", ...], \"actions\": [\"action1\", ...], \"risks\": [\"risk1\", ...]}"
        )

        try:
            raw = self.services.llm.generate(prompt, temperature=0.3, max_tokens=800)
            parsed = self._parse_json(raw) or {}
            return {
                "success": True,
                "summary": parsed.get("summary", raw[:300] if raw else ""),
                "insights": parsed.get("insights", []),
                "actions": parsed.get("actions", []),
                "risks": parsed.get("risks", []),
                "layers": {
                    "price_data": price_data.get("data"),
                    "technicals": tech_summary,
                    "sentiment": sentiment.get("data"),
                    "portfolio": {k: v for k, v in (portfolio or {}).items() if k != "success"},
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── helpers ───────────────────────────────────────────────────────────────

    def _parse_json(self, text: str) -> dict:
        """Extract first JSON object from LLM response."""
        if not text:
            return {}
        try:
            import re
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception:
            pass
        return {}
