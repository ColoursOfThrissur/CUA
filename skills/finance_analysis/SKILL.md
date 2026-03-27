# finance_analysis skill

Routes financial questions to `FinancialAnalysisTool` for multi-layer analysis of stocks, mutual funds, and portfolios.

## What it handles

- Stock price data, OHLCV history, fundamentals (P/E, EPS, beta, revenue)
- Technical indicators: RSI, MACD, moving averages (20/50), Bollinger Bands
- News sentiment: fetches recent headlines, LLM scores bullish/bearish/neutral
- Portfolio analysis: sector exposure, concentration risk (HHI), Sharpe ratio, max drawdown, correlation
- Advisor insight: all layers combined → LLM risk manager gives actionable recommendations
- Morning note: macro snapshot + per-holding brief + today's actions + risk flags
- Full report: executive summary, holding analysis, peer comparison, benchmark, outlook
- **Indian mutual funds**: search by name, NAV history, technicals (MA, trend, rolling returns), category browsing

## Example queries

### Stocks & Portfolio
- "How is my portfolio doing?" → `get_advisor_insight`
- "Analyse AAPL" → `get_price_data` + `get_technicals` + `get_sentiment`
- "Is NVDA overbought?" → `get_technicals`
- "What's the sector exposure in my portfolio?" → `get_portfolio_analysis`
- "Should I trim my MSFT position?" → `get_advisor_insight`
- "Generate my morning note" → `generate_morning_note`
- "Generate a full report" → `generate_full_report`
- "Save my portfolio" → `save_portfolio`
- "How is Nifty doing today?" → `get_advisor_insight`

### Mutual Funds (Indian)
- "Search for HDFC Top 100 fund" → `search_mutual_funds`
- "Show me details for scheme code 119551" → `get_mutual_fund_details`
- "List all mutual fund categories" → `list_mutual_fund_categories`
- "Find Axis Bluechip fund" → `search_mutual_funds`
- "What are the technicals for scheme 119551?" → `get_mutual_fund_details`

## Tool operations

| Operation | Description |
|-----------|-------------|
| `get_price_data` | OHLCV + fundamentals for stocks OR NAV for mutual funds (auto-fallback) |
| `get_technicals` | RSI, MACD, MAs, Bollinger Bands for stocks |
| `get_sentiment` | News headlines + LLM sentiment score per ticker |
| `get_portfolio_analysis` | Sector exposure, Sharpe, drawdown, correlation |
| `get_advisor_insight` | Full committee analysis + LLM advisor recommendations |
| `generate_morning_note` | Daily market brief: macro + holdings + actions + risk flags |
| `generate_full_report` | Comprehensive report: executive summary, peer comparison, outlook |
| `save_portfolio` | Persist holdings so morning notes work without re-entering tickers |
| `search_mutual_funds` | Search Indian MFs by name, returns scheme codes |
| `get_mutual_fund_details` | Full NAV history + technicals (MA, trend, rolling returns, volatility) |
| `list_mutual_fund_categories` | Browse all MF categories (Equity, Debt, Hybrid, ELSS, etc.) |

## Dependencies

Requires `yfinance`, `pandas`, and `requests`:
```bash
pip install yfinance pandas requests
```

## Data sources

- **Stocks (US/Global)**: Yahoo Finance via `yfinance`
- **Indian indices**: Yahoo Finance (^NSEI, ^BSESN, ^NSEBANK)
- **Indian mutual funds**: MFApi (https://api.mfapi.in) — free, no API key required
