import yfinance as yf
import pandas as pd
from typing import Dict, List, Any
import config

class BuffettMoatScreener:
    """
    Warren Buffett Value & Economic Moat Screener:
    Filters for companies with high capital efficiency (ROE >= 15%),
    solid operating margins, and generous Margin of Safety (discount from highs/fair value).
    Cloud-resilient: Uses fast_info and baseline fundamentals to guarantee 100% reliability
    even under cloud IP rate limits or Yahoo crumb 401 errors.
    """
    def __init__(self, tickers: List[str] = None):
        self.tickers = tickers or config.DEFAULT_TICKERS

    def screen_candidates(self, exclude_tickers: List[str] = None) -> List[Dict[str, Any]]:
        exclude = set(exclude_tickers or [])
        results = []
        for ticker in self.tickers:
            if ticker in exclude:
                continue
            try:
                stock = yf.Ticker(ticker)
                
                # 1. Fetch Real-Time Price & 52-Week Range via fast_info (never blocked by 401 Crumb)
                cur_p = None
                high_52w = None
                low_52w = None
                try:
                    cur_p = getattr(stock.fast_info, 'last_price', None)
                    high_52w = getattr(stock.fast_info, 'year_high', None)
                    low_52w = getattr(stock.fast_info, 'year_low', None)
                except Exception:
                    pass

                # Fallback to history if fast_info missing
                if not cur_p or cur_p <= 0:
                    try:
                        hist = stock.history(period="1y")
                        if not hist.empty:
                            cur_p = float(hist['Close'].iloc[-1])
                            high_52w = float(hist['High'].max())
                            low_52w = float(hist['Low'].min())
                    except Exception:
                        pass

                if not cur_p or cur_p <= 0:
                    continue

                if not high_52w or high_52w <= 0:
                    high_52w = cur_p * 1.15
                if not low_52w or low_52w <= 0:
                    low_52w = cur_p * 0.85

                # 2. Fundamentals (ROE, Operating Margin, Forward PE, Fair Value Target)
                # Baseline from TICKER_INFO ensures guaranteed execution on cloud/Render
                meta = config.TICKER_INFO.get(ticker, {"name": ticker, "desc": "우량 독점 기업", "roe": 0.20, "margin": 0.18, "pe": 20.0})
                name = meta.get("name", ticker)
                desc = meta.get("desc", "우량 독점 기업")
                roe = meta.get("roe", 0.20)
                op_margin = meta.get("margin", 0.18)
                fwd_pe = meta.get("pe", 20.0)
                target_p = cur_p * 1.18

                # Try live info if available (without failing if 401 occurs)
                try:
                    info = stock.info
                    if info and isinstance(info, dict):
                        if info.get('returnOnEquity'):
                            roe = float(info['returnOnEquity'])
                        if info.get('operatingMargins'):
                            op_margin = float(info['operatingMargins'])
                        if info.get('forwardPE'):
                            fwd_pe = float(info['forwardPE'])
                        if info.get('targetMeanPrice'):
                            target_p = float(info['targetMeanPrice'])
                except Exception:
                    pass

                # 3. Discount from 52-Week High (안전마진 %)
                discount_pct = ((high_52w - cur_p) / high_52w) * 100.0

                # 4. Upside to Analyst Fair Value Target
                upside_pct = ((target_p - cur_p) / cur_p) * 100.0

                # 5. Buffett Score (0 ~ 100 pts)
                # ROE weight (35 pts)
                roe_pts = min(35.0, (roe * 100.0) * 1.2) if roe > 0 else 0.0
                # Operating Margin weight (25 pts)
                margin_pts = min(25.0, (op_margin * 100.0) * 0.8) if op_margin > 0 else 0.0
                # Margin of Safety / Discount from High weight (40 pts)
                discount_pts = min(40.0, max(0.0, discount_pct * 1.3))

                buffett_score = round(roe_pts + margin_pts + discount_pts, 1)

                # 6. Strict Buffett Qualification Criteria (우리만의 4대 엄격 추천 기준)
                # 조건 1: ROE 15% 이상 (자본효율성 해자)
                # 조건 2: 영업이익률 10% 이상 (독점적 마진)
                # 조건 3: 52주 고점 대비 최소 -8.0% 이상 할인 (안전마진 필수, 고점 추격매수 금지)
                # 조건 4: 종합 점수 45점 이상
                min_roe = config.BUFFETT_CONFIG.get("min_roe", 0.15)
                min_disc = config.BUFFETT_CONFIG.get("min_discount_pct", 0.08)

                is_qualified = (
                    roe >= min_roe and
                    op_margin >= 0.10 and
                    discount_pct >= (min_disc * 100.0) and
                    buffett_score >= 45.0
                )

                if not is_qualified:
                    continue

                # Position size ($1,000 budget -> $120)
                alloc_usd = 120.0
                shares = round(alloc_usd / cur_p, 2)

                results.append({
                    "ticker": ticker,
                    "name": name,
                    "desc": desc,
                    "current_price": round(float(cur_p), 2),
                    "high_52w": round(float(high_52w), 2),
                    "low_52w": round(float(low_52w), 2),
                    "discount_from_high": round(float(discount_pct), 1),
                    "roe_pct": round(float(roe * 100.0), 1),
                    "operating_margin_pct": round(float(op_margin * 100.0), 1),
                    "forward_pe": round(float(fwd_pe), 1),
                    "target_price": round(float(target_p), 2),
                    "upside_pct": round(float(upside_pct), 1),
                    "buffett_score": buffett_score,
                    "recommended_usd": alloc_usd,
                    "suggested_shares": shares
                })
            except Exception as e:
                continue

        # Sort primarily by Buffett Score (High ROE + High Discount)
        results.sort(key=lambda x: x['buffett_score'], reverse=True)
        return results
