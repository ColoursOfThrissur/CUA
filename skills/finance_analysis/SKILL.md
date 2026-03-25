# finance_analysis skill

Routes financial questions to `FinancialAnalysisTool` for multi-layer analysis.

## What it handles

- Stock price data, OHLCV history, fundamentals (P/E, EPS, beta, revenue)
- Technical indicators: RSI, MACD, moving averages (20/50), Bollinger Bands
- News sentiment: fetches recent headlines, LLM scores bullish/bearish/neutral
- Portfolio analysis: sector exposure, concentration risk (HHI), Sharpe ratio, max drawdown, correlation
- Advisor insight: all layers combined → LLM risk manager gives actionable recommendations

## Example queries

- "How is my portfolio doing?" → `get_advisor_insight`
- "Analyse AAPL" → `get_price_data` + `get_technicals` + `get_sentiment`
- "Is NVDA overbought?" → `get_technicals`
- "What's the sector exposure in my portfolio?" → `get_portfolio_analysis`
- "Should I trim my MSFT position?" → `get_advisor_insight`

## Tool operations

| Operation | Description |
|-----------|-------------|
| `get_price_data` | OHLCV + fundamentals for one or more tickers |
| `get_technicals` | RSI, MACD, MAs, Bollinger Bands for a single ticker |
| `get_sentiment` | News headlines + LLM sentiment score per ticker |
| `get_portfolio_analysis` | Sector exposure, Sharpe, drawdown, correlation |
| `get_advisor_insight` | Full committee analysis + LLM advisor recommendations |

## Dependencies

Requires `yfinance` and `pandas`:
```bash
pip install yfinance pandas
```
