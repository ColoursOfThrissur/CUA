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
            name="save_portfolio",
            description="Save portfolio holdings persistently so morning notes and reports work without re-entering tickers.",
            parameters=[
                Parameter("holdings", ParameterType.DICT, "Dict of ticker→shares e.g. {'AAPL': 10, 'NVDA': 5}", required=True),
                Parameter("name", ParameterType.STRING, "Portfolio name e.g. 'main'", required=False, default="main"),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=[]
        ), self._handle_save_portfolio)

        self.add_capability(ToolCapability(
            name="generate_morning_note",
            description="Generate a morning market brief: macro snapshot, per-holding price+technicals+sentiment, risk flags, today's actions. Uses saved portfolio if no holdings passed.",
            parameters=[
                Parameter("holdings", ParameterType.DICT, "Dict of ticker→shares. Omit to use saved portfolio.", required=False, default={}),
                Parameter("portfolio_name", ParameterType.STRING, "Saved portfolio name to load", required=False, default="main"),
                Parameter("include_macro", ParameterType.BOOLEAN, "Include VIX, DXY, 10Y yield snapshot", required=False, default=True),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=["yfinance", "pandas"]
        ), self._handle_generate_morning_note)

        self.add_capability(ToolCapability(
            name="generate_full_report",
            description="Generate a comprehensive investment report: executive summary, per-holding deep analysis, peer comparison, DCF estimate, risk-adjusted metrics, benchmark comparison, and full outlook narrative.",
            parameters=[
                Parameter("holdings", ParameterType.DICT, "Dict of ticker→shares. Omit to use saved portfolio.", required=False, default={}),
                Parameter("portfolio_name", ParameterType.STRING, "Saved portfolio name to load", required=False, default="main"),
                Parameter("benchmark", ParameterType.STRING, "Benchmark ticker for comparison e.g. '^GSPC'", required=False, default="^GSPC"),
                Parameter("period", ParameterType.STRING, "Analysis period", required=False, default="1y"),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=["yfinance", "pandas"]
        ), self._handle_generate_full_report)

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

        self.add_capability(ToolCapability(
            name="search_mutual_funds",
            description="Search Indian mutual funds by name. Returns scheme codes and details for use in other operations.",
            parameters=[
                Parameter("query", ParameterType.STRING, "Fund name to search e.g. 'HDFC Top 100' or 'Axis Bluechip'", required=True),
                Parameter("limit", ParameterType.INTEGER, "Max results to return", required=False, default=10),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=[]
        ), self._handle_search_mutual_funds)

        self.add_capability(ToolCapability(
            name="get_mutual_fund_details",
            description="Get detailed NAV history and metadata for a mutual fund scheme. Includes full historical data for analysis.",
            parameters=[
                Parameter("scheme_code", ParameterType.STRING, "MF scheme code e.g. '119551'", required=True),
                Parameter("period", ParameterType.STRING, "History period: 1mo, 3mo, 6mo, 1y, 2y, max", required=False, default="1y"),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=[]
        ), self._handle_get_mutual_fund_details)

        self.add_capability(ToolCapability(
            name="list_mutual_fund_categories",
            description="List all mutual fund categories with fund counts. Useful for browsing funds by type.",
            parameters=[],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=[]
        ), self._handle_list_mutual_fund_categories)

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
                    # Fallback to MFApi for Indian mutual funds
                    mf_data = self._fetch_mf_data(ticker)
                    if mf_data:
                        result[ticker] = mf_data
                        continue
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
                # Fallback to MFApi for Indian mutual funds
                mf_data = self._fetch_mf_data(ticker)
                if mf_data:
                    result[ticker] = mf_data
                else:
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
            values = {t: latest[t] * float(holdings.get(t, 0)) for t in price_df.columns}
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

    def _handle_save_portfolio(self, **kwargs) -> dict:
        holdings = kwargs.get("holdings", {})
        name = kwargs.get("name", "main")
        if not holdings:
            return {"success": False, "error": "holdings dict is required"}
        holdings = {_normalize_ticker(k): v for k, v in holdings.items()}
        self.services.storage.save(f"portfolio_{name}", {"holdings": holdings, "saved_at": datetime.now(timezone.utc).isoformat()})
        return {"success": True, "portfolio_name": name, "tickers": list(holdings.keys()), "message": f"Portfolio '{name}' saved with {len(holdings)} holdings"}

    def _load_portfolio(self, holdings: dict, portfolio_name: str) -> dict:
        """Return holdings — from arg if provided, else from file-based storage."""
        if holdings:
            return {_normalize_ticker(k): v for k, v in holdings.items()}
        # Try file-based storage first (portfolio saved via save_portfolio.py)
        try:
            from pathlib import Path
            file_path = Path("data/financialanalysis") / f"portfolio_{portfolio_name}.json"
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                if saved.get("holdings"):
                    return saved["holdings"]
        except Exception:
            pass
        # Fallback to services storage
        try:
            saved = self.services.storage.get(f"portfolio_{portfolio_name}")
            if saved and saved.get("holdings"):
                return saved["holdings"]
        except Exception:
            pass
        return {}

    def _get_macro_snapshot(self) -> dict:
        """Fetch VIX, DXY, 10Y yield as macro context."""
        try:
            import yfinance as yf
            macro_tickers = {"VIX": "^VIX", "DXY": "DX-Y.NYB", "10Y_Yield": "^TNX"}
            result = {}
            for label, sym in macro_tickers.items():
                try:
                    hist = yf.Ticker(sym).history(period="5d")
                    if not hist.empty:
                        prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else None
                        curr = float(round(hist["Close"].iloc[-1], 2))
                        result[label] = {
                            "value": curr,
                            "change": round(curr - prev, 2) if prev else None,
                            "change_pct": round((curr / prev - 1) * 100, 2) if prev else None,
                        }
                except Exception:
                    pass
            return result
        except Exception:
            return {}

    def _get_earnings_flags(self, tickers: list) -> dict:
        """Check if any ticker has earnings in the next 7 days."""
        try:
            import yfinance as yf
            from datetime import timedelta
            flags = {}
            today = datetime.now(timezone.utc).date()
            for ticker in tickers:
                try:
                    cal = yf.Ticker(ticker).calendar
                    if cal is not None and not cal.empty:
                        earnings_date = cal.iloc[0].get("Earnings Date") if hasattr(cal.iloc[0], 'get') else None
                        if earnings_date:
                            from pandas import Timestamp
                            ed = Timestamp(earnings_date).date() if not isinstance(earnings_date, type(today)) else earnings_date
                            days_away = (ed - today).days
                            if 0 <= days_away <= 7:
                                flags[ticker] = {"earnings_date": str(ed), "days_away": days_away}
                except Exception:
                    pass
            return flags
        except Exception:
            return {}

    def _handle_generate_morning_note(self, **kwargs) -> dict:
        holdings = self._load_portfolio(kwargs.get("holdings") or {}, kwargs.get("portfolio_name", "main"))
        include_macro = kwargs.get("include_macro", True)
        if not holdings:
            return {"success": False, "error": "No holdings provided and no saved portfolio found. Use save_portfolio first or pass holdings."}

        tickers = list(holdings.keys())
        today_str = datetime.now(timezone.utc).strftime("%A, %d %B %Y")

        # Fetch all layers
        price_data = self._handle_get_price_data(tickers=tickers, period="5d")
        technicals = {t: self._handle_get_technicals(ticker=t, period="3mo") for t in tickers}
        sentiment = self._handle_get_sentiment(tickers=tickers)
        macro = self._get_macro_snapshot() if include_macro else {}
        earnings_flags = self._get_earnings_flags(tickers)

        # Build per-holding summaries for LLM
        holding_lines = []
        for t in tickers:
            pd_ = (price_data.get("data") or {}).get(t, {})
            tech = technicals.get(t, {})
            sent = (sentiment.get("data") or {}).get(t, {})
            shares = float(holdings.get(t, 0))
            current_price = pd_.get("current_price", 0)
            value = round(current_price * shares, 2) if shares and current_price else None
            line = f"{t}: price={current_price} change={pd_.get('price_change_pct')}%"
            if value:
                line += f" value=₹{value:,.0f}"
            line += f" | RSI={tech.get('rsi')} trend={tech.get('trend')} macd={tech.get('macd_crossover')}"
            line += f" | sentiment={sent.get('sentiment')} score={sent.get('score')}"
            if t in earnings_flags:
                line += f" | ⚠ EARNINGS in {earnings_flags[t]['days_away']} days"
            holding_lines.append(line)

        macro_lines = [f"{k}: {v['value']} ({'+' if v.get('change_pct', 0) >= 0 else ''}{v.get('change_pct')}%)"
                       for k, v in macro.items() if v.get('value')]

        prompt = (
            f"You are a professional portfolio manager writing a morning market brief for {today_str}.\n"
            f"Write a concise, actionable morning note covering:\n"
            f"1. Market mood (1-2 sentences using macro data)\n"
            f"2. Portfolio snapshot (key movers, risks)\n"
            f"3. Today's watchlist (what to monitor)\n"
            f"4. Specific actions for today (buy/trim/hold with reasoning)\n\n"
            + (f"MACRO:\n" + "\n".join(macro_lines) + "\n\n" if macro_lines else "")
            + f"HOLDINGS:\n" + "\n".join(holding_lines)
            + (f"\n\nEARNINGS THIS WEEK: {list(earnings_flags.keys())}" if earnings_flags else "")
            + "\n\nReply with JSON: {\"date\": \"...\", \"market_mood\": \"...\", \"portfolio_snapshot\": \"...\", "
              "\"watchlist\": [...], \"actions\": [...], \"risk_flags\": [...], \"one_liner\": \"...\"}\n"
            "Keep actions specific: ticker, direction, reason."
        )

        try:
            raw = self.services.llm.generate(prompt, temperature=0.3, max_tokens=1200)
            parsed = self._parse_json(raw) or {}
            # Fallback: if LLM didn't return proper JSON, build minimal response from raw data
            if not parsed.get("market_mood") and not parsed.get("actions"):
                parsed = {
                    "date": today_str,
                    "one_liner": f"Portfolio update for {today_str}",
                    "market_mood": "Market data fetched. See details below.",
                    "portfolio_snapshot": "\n".join(holding_lines),
                    "watchlist": tickers,
                    "actions": ["Review holdings based on technical indicators in details section."],
                    "risk_flags": [],
                }
            return {
                "success": True,
                "date": today_str,
                "one_liner": parsed.get("one_liner", ""),
                "market_mood": parsed.get("market_mood", ""),
                "portfolio_snapshot": parsed.get("portfolio_snapshot", ""),
                "watchlist": parsed.get("watchlist", []),
                "actions": parsed.get("actions", []),
                "risk_flags": parsed.get("risk_flags", []),
                "earnings_this_week": earnings_flags,
                "layers": {
                    "macro": macro,
                    "price_data": price_data.get("data"),
                    "technicals": {t: {k: v for k, v in d.items() if k != "success"} for t, d in technicals.items() if d.get("success")},
                    "sentiment": sentiment.get("data"),
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_generate_full_report(self, **kwargs) -> dict:
        holdings = self._load_portfolio(kwargs.get("holdings") or {}, kwargs.get("portfolio_name", "main"))
        # Sanitize benchmark — reject LLM hallucinations, default to Nifty50 for Indian portfolio
        raw_benchmark = kwargs.get("benchmark", "^NSEI")
        _VALID_BENCHMARKS = {"^GSPC", "^NSEI", "^BSESN", "^DJI", "^IXIC", "^NSEBANK", "SPY", "QQQ"}
        benchmark = raw_benchmark if raw_benchmark in _VALID_BENCHMARKS else "^NSEI"
        period = _normalize_period(kwargs.get("period", "1y"), default="1y")
        if not holdings:
            return {"success": False, "error": "No holdings provided and no saved portfolio found."}

        tickers = list(holdings.keys())
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # All layers
        price_data = self._handle_get_price_data(tickers=tickers, period=period)
        technicals = {t: self._handle_get_technicals(ticker=t, period=period) for t in tickers}
        sentiment = self._handle_get_sentiment(tickers=tickers)
        portfolio = self._handle_get_portfolio_analysis(holdings=holdings, period=period)
        macro = self._get_macro_snapshot()
        earnings_flags = self._get_earnings_flags(tickers)

        # Benchmark comparison
        benchmark_data = self._handle_get_price_data(tickers=[benchmark], period=period)
        benchmark_return = None
        try:
            bd = (benchmark_data.get("data") or {}).get(benchmark, {})
            benchmark_return = bd.get("price_change_pct")
        except Exception:
            pass

        # Peer comparison — fetch sector peers via yfinance info
        peer_data = {}
        try:
            import yfinance as yf
            for t in tickers[:3]:  # limit to 3 to avoid timeout
                info = yf.Ticker(t).info or {}
                peers = info.get("recommendationKey", "")
                sector = info.get("sector", "")
                peer_data[t] = {
                    "sector": sector,
                    "recommendation": peers,
                    "target_price": info.get("targetMeanPrice"),
                    "analyst_count": info.get("numberOfAnalystOpinions"),
                    "forward_pe": info.get("forwardPE"),
                    "peg_ratio": info.get("pegRatio"),
                    "price_to_book": info.get("priceToBook"),
                    "debt_to_equity": info.get("debtToEquity"),
                    "roe": info.get("returnOnEquity"),
                    "revenue_growth": info.get("revenueGrowth"),
                }
        except Exception:
            pass

        # Build full context for LLM
        pd_summary = json.dumps(price_data.get("data", {}), indent=2)[:1500]
        tech_summary = {t: {k: v for k, v in d.items() if k != "success"} for t, d in technicals.items() if d.get("success")}
        port_summary = {k: v for k, v in (portfolio or {}).items() if k != "success"}

        prompt = (
            f"You are a senior investment analyst writing a comprehensive portfolio report dated {today_str}.\n"
            f"Benchmark: {benchmark} ({benchmark_return}% over {period})\n\n"
            f"PRICE DATA:\n{pd_summary}\n\n"
            f"TECHNICALS:\n{json.dumps(tech_summary, indent=2)[:800]}\n\n"
            f"PORTFOLIO METRICS:\n{json.dumps(port_summary, indent=2)[:600]}\n\n"
            f"SENTIMENT:\n{json.dumps(sentiment.get('data', {}), indent=2)[:600]}\n\n"
            f"PEER/ANALYST DATA:\n{json.dumps(peer_data, indent=2)[:600]}\n\n"
            + (f"EARNINGS FLAGS: {json.dumps(earnings_flags)}\n\n" if earnings_flags else "")
            + "Write a full investment report with these sections:\n"
            "1. Executive Summary (3-4 sentences)\n"
            "2. Portfolio Performance vs Benchmark\n"
            "3. Per-Holding Analysis (each ticker: trend, valuation, recommendation)\n"
            "4. Risk Assessment (concentration, correlation, macro risks)\n"
            "5. Strategic Recommendations (specific actions with rationale)\n"
            "6. Outlook (30-day view)\n\n"
            "Reply with JSON: {\"executive_summary\": \"...\", \"performance_vs_benchmark\": \"...\", "
            "\"holding_analysis\": {\"TICKER\": {\"trend\": \"\", \"valuation\": \"\", \"recommendation\": \"\"}}, "
            "\"risk_assessment\": \"...\", \"recommendations\": [...], \"outlook\": \"...\", "
            "\"rating\": \"bullish|neutral|bearish\"}"
        )

        try:
            raw = self.services.llm.generate(prompt, temperature=0.2, max_tokens=1500)
            parsed = self._parse_json(raw) or {}

            # Build markdown report
            md_lines = [
                f"# Investment Report — {today_str}",
                f"**Benchmark:** {benchmark} | **Period:** {period}",
                "",
                f"## Executive Summary",
                parsed.get("executive_summary", ""),
                "",
                f"## Performance vs Benchmark",
                parsed.get("performance_vs_benchmark", ""),
                "",
                f"## Holding Analysis",
            ]
            for ticker, analysis in (parsed.get("holding_analysis") or {}).items():
                if isinstance(analysis, dict):
                    md_lines.append(f"### {ticker}")
                    md_lines.append(f"- Trend: {analysis.get('trend', '')}")
                    md_lines.append(f"- Valuation: {analysis.get('valuation', '')}")
                    md_lines.append(f"- Recommendation: {analysis.get('recommendation', '')}")
            md_lines += [
                "",
                "## Risk Assessment",
                parsed.get("risk_assessment", ""),
                "",
                "## Strategic Recommendations",
            ]
            for rec in (parsed.get("recommendations") or []):
                md_lines.append(f"- {rec}")
            md_lines += [
                "",
                "## Outlook",
                parsed.get("outlook", ""),
            ]

            return {
                "success": True,
                "date": today_str,
                "rating": parsed.get("rating", "neutral"),
                "executive_summary": parsed.get("executive_summary", ""),
                "performance_vs_benchmark": parsed.get("performance_vs_benchmark", ""),
                "holding_analysis": parsed.get("holding_analysis", {}),
                "risk_assessment": parsed.get("risk_assessment", ""),
                "recommendations": parsed.get("recommendations", []),
                "outlook": parsed.get("outlook", ""),
                "markdown_report": "\n".join(md_lines),
                "layers": {
                    "price_data": price_data.get("data"),
                    "technicals": tech_summary,
                    "sentiment": sentiment.get("data"),
                    "portfolio": port_summary,
                    "macro": macro,
                    "peer_data": peer_data,
                    "benchmark": {"ticker": benchmark, "return_pct": benchmark_return, "period": period},
                    "earnings_flags": earnings_flags,
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


    def _fetch_mf_data(self, scheme_code: str, period: str = "3mo") -> dict:
        """Fetch mutual fund data from MFApi (Indian MFs). Returns None if not a valid MF scheme."""
        try:
            import requests
            from datetime import datetime, timedelta
            # MFApi expects numeric scheme codes, skip if ticker is not numeric
            if not scheme_code.isdigit():
                return None
            
            url = f"https://api.mfapi.in/mf/{scheme_code}"
            resp = requests.get(url, timeout=5)
            if resp.status_code != 200:
                return None
            
            data = resp.json()
            if not data.get("data") or not data.get("meta"):
                return None
            
            nav_history = data["data"]
            latest = nav_history[0]
            
            # Filter by period
            period_days = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "5y": 1825, "max": 99999}
            days = period_days.get(period, 90)
            cutoff_date = datetime.now().date() - timedelta(days=days)
            
            filtered_history = []
            for entry in nav_history:
                try:
                    entry_date = datetime.strptime(entry["date"], "%d-%m-%Y").date()
                    if entry_date >= cutoff_date:
                        filtered_history.append(entry)
                except Exception:
                    continue
            
            if not filtered_history:
                filtered_history = nav_history[:min(len(nav_history), 90)]  # fallback to 90 entries
            
            oldest = filtered_history[-1] if len(filtered_history) > 1 else latest
            current_nav = float(latest["nav"])
            old_nav = float(oldest["nav"])
            change_pct = round((current_nav / old_nav - 1) * 100, 2) if old_nav > 0 else 0.0
            
            return {
                "type": "mutual_fund",
                "scheme_name": data["meta"].get("scheme_name", ""),
                "fund_house": data["meta"].get("fund_house", ""),
                "scheme_category": data["meta"].get("scheme_category", ""),
                "current_price": current_nav,
                "nav_date": latest["date"],
                "price_change_pct": change_pct,
                "data_points": len(filtered_history),
                "sector": "Mutual Fund",
                "nav_history": filtered_history,  # Include full history for technicals
            }
        except Exception:
            return None

    def _handle_search_mutual_funds(self, **kwargs) -> dict:
        """Search mutual funds by name using MFApi."""
        query = kwargs.get("query", "").strip().lower()
        limit = kwargs.get("limit", 10)
        if not query:
            return {"success": False, "error": "query parameter is required"}
        
        try:
            import requests
            url = "https://api.mfapi.in/mf"
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                return {"success": False, "error": f"MFApi returned status {resp.status_code}"}
            
            all_schemes = resp.json()
            if not isinstance(all_schemes, list):
                return {"success": False, "error": "Unexpected API response format"}
            
            # Fuzzy search by name
            matches = []
            for scheme in all_schemes:
                scheme_name = scheme.get("schemeName", "").lower()
                if query in scheme_name:
                    matches.append({
                        "scheme_code": scheme.get("schemeCode"),
                        "scheme_name": scheme.get("schemeName"),
                    })
                    if len(matches) >= limit:
                        break
            
            return {
                "success": True,
                "query": query,
                "results": matches,
                "count": len(matches),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_get_mutual_fund_details(self, **kwargs) -> dict:
        """Get detailed NAV history and metadata for a mutual fund."""
        scheme_code = kwargs.get("scheme_code", "").strip()
        period = _normalize_period(kwargs.get("period", "1y"), default="1y")
        if not scheme_code:
            return {"success": False, "error": "scheme_code is required"}
        
        mf_data = self._fetch_mf_data(scheme_code, period=period)
        if not mf_data:
            return {"success": False, "error": f"No data found for scheme code {scheme_code}"}
        
        # Calculate technicals from NAV history
        nav_history = mf_data.get("nav_history", [])
        technicals = self._calculate_mf_technicals(nav_history)
        
        return {
            "success": True,
            "scheme_code": scheme_code,
            "scheme_name": mf_data.get("scheme_name"),
            "fund_house": mf_data.get("fund_house"),
            "scheme_category": mf_data.get("scheme_category"),
            "current_nav": mf_data.get("current_price"),
            "nav_date": mf_data.get("nav_date"),
            "change_pct": mf_data.get("price_change_pct"),
            "period": period,
            "data_points": len(nav_history),
            "technicals": technicals,
            "nav_history_sample": nav_history[:10],  # First 10 for display
        }

    def _handle_list_mutual_fund_categories(self, **kwargs) -> dict:
        """List all mutual fund categories with counts."""
        try:
            import requests
            url = "https://api.mfapi.in/mf"
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                return {"success": False, "error": f"MFApi returned status {resp.status_code}"}
            
            all_schemes = resp.json()
            if not isinstance(all_schemes, list):
                return {"success": False, "error": "Unexpected API response format"}
            
            # Group by category (extract from scheme name)
            categories = {}
            for scheme in all_schemes:
                name = scheme.get("schemeName", "")
                # Extract category from name (e.g., "HDFC Top 100 Fund - Direct Plan - Growth")
                # Categories usually contain: Equity, Debt, Hybrid, Liquid, etc.
                category = "Other"
                if "equity" in name.lower():
                    category = "Equity"
                elif "debt" in name.lower():
                    category = "Debt"
                elif "hybrid" in name.lower():
                    category = "Hybrid"
                elif "liquid" in name.lower():
                    category = "Liquid"
                elif "elss" in name.lower():
                    category = "ELSS (Tax Saving)"
                elif "index" in name.lower():
                    category = "Index"
                elif "fof" in name.lower() or "fund of fund" in name.lower():
                    category = "Fund of Funds"
                
                categories[category] = categories.get(category, 0) + 1
            
            # Sort by count
            sorted_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)
            
            return {
                "success": True,
                "categories": {cat: count for cat, count in sorted_categories},
                "total_schemes": len(all_schemes),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _calculate_mf_technicals(self, nav_history: list) -> dict:
        """Calculate technical indicators from NAV history."""
        if not nav_history or len(nav_history) < 20:
            return {}
        
        try:
            import pandas as pd
            from datetime import datetime
            
            # Convert to pandas Series
            navs = [float(entry["nav"]) for entry in reversed(nav_history)]  # oldest to newest
            dates = [datetime.strptime(entry["date"], "%d-%m-%Y") for entry in reversed(nav_history)]
            
            series = pd.Series(navs, index=dates)
            
            # Moving averages
            ma20 = float(round(series.rolling(20).mean().iloc[-1], 2)) if len(series) >= 20 else None
            ma50 = float(round(series.rolling(50).mean().iloc[-1], 2)) if len(series) >= 50 else None
            
            current = float(round(series.iloc[-1], 2))
            trend = "bullish" if (ma20 and current > ma20) else "bearish"
            
            # Rolling returns
            returns = {}
            if len(series) >= 21:
                returns["1M"] = round((series.iloc[-1] / series.iloc[-21] - 1) * 100, 2)
            if len(series) >= 63:
                returns["3M"] = round((series.iloc[-1] / series.iloc[-63] - 1) * 100, 2)
            if len(series) >= 126:
                returns["6M"] = round((series.iloc[-1] / series.iloc[-126] - 1) * 100, 2)
            if len(series) >= 252:
                returns["1Y"] = round((series.iloc[-1] / series.iloc[-252] - 1) * 100, 2)
            
            # Volatility (annualized)
            daily_returns = series.pct_change().dropna()
            volatility = float(round(daily_returns.std() * (252 ** 0.5) * 100, 2)) if len(daily_returns) > 0 else None
            
            return {
                "current_nav": current,
                "ma20": ma20,
                "ma50": ma50,
                "trend": trend,
                "rolling_returns": returns,
                "volatility_annual_pct": volatility,
            }
        except Exception:
            return {}

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
