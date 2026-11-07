import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import yfinance as yf
import config

BASE_DIR = Path(__file__).resolve().parent

class FriendsTournamentManager:
    """
    AI Autonomous Investment Friends & Tournament Manager:
    Manages 4 distinct AI trader personas with $1,000 initial capital,
    weekly $50 allowance, autonomous buying/selling, and persistent trade diaries.
    """
    def __init__(self, storage_path: str = "friends_portfolio.json"):
        self.storage_path = BASE_DIR / storage_path
        self.alt_storage_path = BASE_DIR / "data" / storage_path
        self._ensure_storage()

    def _ensure_storage(self):
        target = self.storage_path
        if not target.exists() and self.alt_storage_path.exists():
            target = self.alt_storage_path

        if not target.exists():
            initial_data = {
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "last_deposit_date": datetime.now().strftime("%Y-%m-%d"),
                "models": {
                    "buffett": {
                        "id": "buffett",
                        "name": "버핏 AI (가치/해자)",
                        "icon": "🏛️",
                        "philosophy": "워런 버핏의 경제적 해자(ROE 15%+)와 바겐세일 안전마진 중점",
                        "cash": 1000.0,
                        "total_deposited": 1000.0,
                        "positions": [],
                        "history": [],
                        "take_profit_pct": 15.0,
                        "stop_loss_pct": -20.0
                    },
                    "momentum": {
                        "id": "momentum",
                        "name": "모멘텀 AI (추세돌파)",
                        "icon": "🚀",
                        "philosophy": "제시 리버모어 스타일의 52주 신고가 근접 및 강한 추세추종",
                        "cash": 1000.0,
                        "total_deposited": 1000.0,
                        "positions": [],
                        "history": [],
                        "take_profit_pct": 10.0,
                        "stop_loss_pct": -5.0
                    },
                    "reversion": {
                        "id": "reversion",
                        "name": "역발상 AI (바닥낚시)",
                        "icon": "🎣",
                        "philosophy": "피터 린치 스타일의 우량주 단기 과매도/바닥권 바겐세일 반등 매수",
                        "cash": 1000.0,
                        "total_deposited": 1000.0,
                        "positions": [],
                        "history": [],
                        "take_profit_pct": 12.0,
                        "stop_loss_pct": -7.0
                    },
                    "dividend": {
                        "id": "dividend",
                        "name": "배당귀족 AI (배당복리)",
                        "icon": "👑",
                        "philosophy": "존 네프 스타일의 고배당 및 수십년 연속 배당성장주 현금흐름 재투자",
                        "cash": 1000.0,
                        "total_deposited": 1000.0,
                        "positions": [],
                        "history": [],
                        "take_profit_pct": 8.0,
                        "stop_loss_pct": -8.0
                    }
                }
            }
            self.save(initial_data)

    def load(self) -> Dict[str, Any]:
        target = self.storage_path
        if not target.exists() and self.alt_storage_path.exists():
            target = self.alt_storage_path

        try:
            with open(target, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            self._ensure_storage()
            with open(self.storage_path, "r", encoding="utf-8") as f:
                return json.load(f)

    def save(self, data: Dict[str, Any]):
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        try:
            os.makedirs(self.alt_storage_path.parent, exist_ok=True)
            with open(self.alt_storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def check_and_process_weekly_allowance(self, weekly_amount: float = 50.0) -> bool:
        """
        Adds weekly allowance ($50) to all models in sync with the user.
        """
        data = self.load()
        last_dep_str = data.get("last_deposit_date", "2000-01-01")
        try:
            last_date = datetime.strptime(last_dep_str, "%Y-%m-%d")
        except Exception:
            last_date = datetime.now() - timedelta(days=8)

        now = datetime.now()
        days_passed = (now - last_date).days

        if days_passed >= 7:
            now_date_str = now.strftime("%Y-%m-%d")
            data["last_deposit_date"] = now_date_str
            for m_id, model in data.get("models", {}).items():
                model["cash"] += weekly_amount
                model["total_deposited"] += weekly_amount
                model.setdefault("history", []).append({
                    "type": "DEPOSIT",
                    "ticker": "USD",
                    "name": "주간 용돈 입금",
                    "amount_usd": weekly_amount,
                    "date": now.strftime("%Y-%m-%d %H:%M"),
                    "note": f"매주 공통 지원금 +${weekly_amount:.0f} 적립 완료"
                })
            self.save(data)
            return True
        return False

    def evaluate_and_trade(self) -> List[Dict[str, Any]]:
        """
        Autonomous trading cycle for all 4 AI friends:
        1. Process Weekly Allowance
        2. Evaluate Open Positions (Take-Profit & Stop-Loss execution)
        3. Scan and Buy new opportunities using each persona's investment philosophy
        """
        self.check_and_process_weekly_allowance(50.0)
        data = self.load()
        executed_events = []
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        # ----------------------------------------------------
        # Step 1: Manage Open Positions (Sell rules)
        # ----------------------------------------------------
        for m_id, model in data.get("models", {}).items():
            positions = model.get("positions", [])
            rem_positions = []

            for pos in positions:
                ticker = pos["ticker"]
                name = pos.get("name", ticker)
                entry_p = float(pos["entry_price"])
                shares = float(pos["shares"])
                orig_usd = float(pos["amount_usd"])

                # Fetch real-time price
                cur_p = entry_p
                try:
                    s = yf.Ticker(ticker)
                    cur_p = float(getattr(s.fast_info, "last_price", entry_p))
                except Exception:
                    pass

                cur_val = cur_p * shares
                gain_pct = ((cur_p - entry_p) / entry_p) * 100.0
                pnl_usd = cur_val - orig_usd

                tp = model.get("take_profit_pct", 15.0)
                sl = model.get("stop_loss_pct", -10.0)

                is_tp = gain_pct >= tp
                is_sl = gain_pct <= sl

                if is_tp or is_sl:
                    action_type = "TAKE_PROFIT" if is_tp else "STOP_LOSS"
                    reason_label = f"목표 익절가(+{tp:.1f}%) 도달" if is_tp else f"손절선({sl:.1f}%) 터치 (리스크 방어)"
                    
                    # Credit cash
                    model["cash"] += cur_val
                    record = {
                        "type": "SELL",
                        "action": action_type,
                        "ticker": ticker,
                        "name": name,
                        "entry_price": round(entry_p, 2),
                        "sell_price": round(cur_p, 2),
                        "shares": round(shares, 2),
                        "amount_usd": round(cur_val, 2),
                        "pnl_usd": round(pnl_usd, 2),
                        "pnl_pct": round(gain_pct, 1),
                        "date": now_str,
                        "reason": reason_label
                    }
                    model.setdefault("history", []).append(record)
                    executed_events.append({
                        "model_name": model["name"],
                        "icon": model.get("icon", "🤖"),
                        "action": "매도",
                        "ticker": ticker,
                        "name": name,
                        "pnl_pct": round(gain_pct, 1),
                        "pnl_usd": round(pnl_usd, 2),
                        "reason": reason_label
                    })
                else:
                    rem_positions.append(pos)

            model["positions"] = rem_positions

        # ----------------------------------------------------
        # Step 2: Scan & Buy for each model if cash >= $100
        # ----------------------------------------------------
        # Pre-fetch ticker market metrics
        market_stats = self._fetch_universe_metrics()

        for m_id, model in data.get("models", {}).items():
            if model["cash"] < 100.0:
                continue

            held_tickers = {p["ticker"] for p in model.get("positions", [])}
            candidates = self._screen_for_model(m_id, market_stats, held_tickers)

            if candidates:
                best = candidates[0]
                ticker = best["ticker"]
                name = best["name"]
                cur_p = best["price"]
                reason = best["reason"]

                # Buy $110 allocation
                buy_usd = min(110.0, model["cash"])
                shares = round(buy_usd / cur_p, 2)
                if shares <= 0:
                    continue

                model["cash"] -= buy_usd
                pos_record = {
                    "ticker": ticker,
                    "name": name,
                    "entry_price": round(cur_p, 2),
                    "shares": shares,
                    "amount_usd": round(buy_usd, 2),
                    "entry_date": now_str,
                    "reason": reason
                }
                model.setdefault("positions", []).append(pos_record)
                model.setdefault("history", []).append({
                    "type": "BUY",
                    "ticker": ticker,
                    "name": name,
                    "entry_price": round(cur_p, 2),
                    "shares": shares,
                    "amount_usd": round(buy_usd, 2),
                    "date": now_str,
                    "reason": reason
                })
                executed_events.append({
                    "model_name": model["name"],
                    "icon": model.get("icon", "🤖"),
                    "action": "매수",
                    "ticker": ticker,
                    "name": name,
                    "price": round(cur_p, 2),
                    "shares": shares,
                    "amount_usd": round(buy_usd, 2),
                    "reason": reason
                })

        self.save(data)
        return executed_events

    def _fetch_universe_metrics(self) -> Dict[str, Dict[str, Any]]:
        """
        Fast scan of universe tickers using fast_info and baseline fundamentals.
        """
        stats = {}
        for ticker in config.DEFAULT_TICKERS:
            try:
                s = yf.Ticker(ticker)
                last_p = getattr(s.fast_info, "last_price", None)
                high_52 = getattr(s.fast_info, "year_high", None)
                low_52 = getattr(s.fast_info, "year_low", None)

                if not last_p or last_p <= 0:
                    continue
                if not high_52: high_52 = last_p * 1.15
                if not low_52: low_52 = last_p * 0.85

                disc_pct = ((high_52 - last_p) / high_52) * 100.0
                bounce_pct = ((last_p - low_52) / low_52) * 100.0

                meta = config.TICKER_INFO.get(ticker, {})
                stats[ticker] = {
                    "ticker": ticker,
                    "name": meta.get("name", ticker),
                    "price": float(last_p),
                    "high_52w": float(high_52),
                    "low_52w": float(low_52),
                    "discount_pct": float(disc_pct),
                    "bounce_pct": float(bounce_pct),
                    "roe": meta.get("roe", 0.20),
                    "margin": meta.get("margin", 0.18),
                    "pe": meta.get("pe", 20.0)
                }
            except Exception:
                pass
        return stats

    def _screen_for_model(self, model_id: str, market_stats: Dict[str, Dict[str, Any]], held_tickers: set) -> List[Dict[str, Any]]:
        candidates = []
        for ticker, item in market_stats.items():
            if ticker in held_tickers:
                continue

            disc = item["discount_pct"]
            roe = item["roe"]
            p = item["price"]

            # 1. 버핏 AI: ROE 15% 이상 & 52주 고점 대비 -8% 이상 할인 (안전마진 가치주)
            if model_id == "buffett":
                if roe >= 0.15 and disc >= 8.0:
                    score = (roe * 100 * 1.2) + (disc * 1.3)
                    candidates.append({
                        "ticker": ticker,
                        "name": item["name"],
                        "price": p,
                        "score": score,
                        "reason": f"ROE {roe*100:.1f}% 해자 & 52주 고점 대비 -{disc:.1f}% 안전마진 할인"
                    })

            # 2. 모멘텀 AI: 52주 신고가 근접(할인율 6% 이하) & 강한 상승 추세돌파
            elif model_id == "momentum":
                if disc <= 6.0 and item["bounce_pct"] >= 15.0:
                    score = (100.0 - disc) + item["bounce_pct"]
                    candidates.append({
                        "ticker": ticker,
                        "name": item["name"],
                        "price": p,
                        "score": score,
                        "reason": f"52주 신고가권(-{disc:.1f}%) 돌파 임박 및 저점 대비 +{item['bounce_pct']:.1f}% 강한 모멘텀"
                    })

            # 3. 역발상 AI: 52주 고점 대비 -18% 이상 깊은 과매도 바닥 우량주 낚시
            elif model_id == "reversion":
                if disc >= 18.0 and roe >= 0.10:
                    score = disc * 1.5 + (roe * 50)
                    candidates.append({
                        "ticker": ticker,
                        "name": item["name"],
                        "price": p,
                        "score": score,
                        "reason": f"52주 고점 대비 -{disc:.1f}% 극단적 과매도 도달 (바닥권 기술적 반등 기대)"
                    })

            # 4. 배당귀족 AI: 방어형 전통 소비재 및 에너지 고배당주
            elif model_id == "dividend":
                dividend_aristocrats = {"KO", "PEP", "PG", "JNJ", "CVX", "XOM", "MCD", "CAT"}
                if ticker in dividend_aristocrats and roe >= 0.15:
                    score = (roe * 100) + disc
                    candidates.append({
                        "ticker": ticker,
                        "name": item["name"],
                        "price": p,
                        "score": score,
                        "reason": f"30년+ 배당증액 배당귀족주 및 안정적 현금흐름 (ROE {roe*100:.1f}%)"
                    })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates

    def get_leaderboard(self, user_portfolio_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Builds a comprehensive leaderboard comparing the User vs all 4 AI friends.
        """
        data = self.load()
        rows = []

        # 1. User Stats
        u_cash = float(user_portfolio_data.get("cash_usd", 1000.0))
        u_open = user_portfolio_data.get("open_positions", [])
        u_stock_val = 0.0
        for p in u_open:
            ticker = p["ticker"]
            shares = float(p.get("shares", 0.0))
            try:
                s = yf.Ticker(ticker)
                cur_p = float(getattr(s.fast_info, "last_price", p["entry_price"]))
            except Exception:
                cur_p = float(p["entry_price"])
            u_stock_val += (cur_p * shares)

        u_total = u_cash + u_stock_val
        u_deposit = 1000.0 + len(user_portfolio_data.get("deposit_history", [])) * 50.0
        u_roi = ((u_total - u_deposit) / u_deposit) * 100.0
        u_history = user_portfolio_data.get("closed_trades", [])
        u_wins = len([t for t in u_history if float(t.get("profit_loss_pct", 0.0)) > 0])
        u_total_closed = len(u_history)
        u_win_rate = (u_wins / u_total_closed * 100.0) if u_total_closed > 0 else 0.0

        rows.append({
            "id": "user",
            "name": "나 (User)",
            "icon": "👤",
            "is_user": True,
            "total_asset": round(u_total, 2),
            "cash": round(u_cash, 2),
            "stock_val": round(u_stock_val, 2),
            "deposited": round(u_deposit, 2),
            "roi_pct": round(u_roi, 2),
            "holdings_count": len(u_open),
            "holdings_summary": ", ".join([p["ticker"] for p in u_open]) if u_open else "현금 100%",
            "trades_count": u_total_closed,
            "win_rate": round(u_win_rate, 1)
        })

        # 2. AI Models Stats
        for m_id, model in data.get("models", {}).items():
            m_cash = float(model.get("cash", 1000.0))
            m_deposit = float(model.get("total_deposited", 1000.0))
            m_open = model.get("positions", [])
            m_stock_val = 0.0

            for p in m_open:
                ticker = p["ticker"]
                shares = float(p.get("shares", 0.0))
                try:
                    s = yf.Ticker(ticker)
                    cur_p = float(getattr(s.fast_info, "last_price", p["entry_price"]))
                except Exception:
                    cur_p = float(p["entry_price"])
                m_stock_val += (cur_p * shares)

            m_total = m_cash + m_stock_val
            m_roi = ((m_total - m_deposit) / m_deposit) * 100.0
            m_history = [t for t in model.get("history", []) if t.get("type") == "SELL"]
            m_wins = len([t for t in m_history if float(t.get("pnl_pct", 0.0)) > 0])
            m_total_closed = len(m_history)
            m_win_rate = (m_wins / m_total_closed * 100.0) if m_total_closed > 0 else 0.0

            rows.append({
                "id": m_id,
                "name": model["name"],
                "icon": model.get("icon", "🤖"),
                "is_user": False,
                "total_asset": round(m_total, 2),
                "cash": round(m_cash, 2),
                "stock_val": round(m_stock_val, 2),
                "deposited": round(m_deposit, 2),
                "roi_pct": round(m_roi, 2),
                "holdings_count": len(m_open),
                "holdings_summary": ", ".join([p["ticker"] for p in m_open]) if m_open else "현금 100%",
                "trades_count": m_total_closed,
                "win_rate": round(m_win_rate, 1)
            })

        # Rank primarily by ROI % descending
        rows.sort(key=lambda x: x["roi_pct"], reverse=True)
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for idx, row in enumerate(rows):
            row["rank"] = idx + 1
            row["medal"] = medals[idx] if idx < len(medals) else f"{idx+1}위"

        return rows

    def get_diary(self, model_query: str) -> Optional[Dict[str, Any]]:
        """
        Returns full trading diary and portfolio details for a specific model or user.
        """
        data = self.load()
        q = model_query.lower().strip()

        target_model = None
        for m_id, m in data.get("models", {}).items():
            if q in m_id or q in m["name"].lower() or (q == "버핏" and "버핏" in m["name"]) or (q == "모멘텀" and "모멘텀" in m["name"]) or (q == "역발상" and "역발상" in m["name"]) or (q == "배당" and "배당" in m["name"]):
                target_model = m
                break

        if not target_model:
            return None

        # Build detailed holding info
        positions_detail = []
        total_eval_stock = 0.0
        for p in target_model.get("positions", []):
            ticker = p["ticker"]
            name = p.get("name", ticker)
            entry_p = float(p["entry_price"])
            shares = float(p["shares"])
            try:
                s = yf.Ticker(ticker)
                cur_p = float(getattr(s.fast_info, "last_price", entry_p))
            except Exception:
                cur_p = entry_p

            cur_val = cur_p * shares
            total_eval_stock += cur_val
            gain_pct = ((cur_p - entry_p) / entry_p) * 100.0
            positions_detail.append({
                "ticker": ticker,
                "name": name,
                "entry_price": entry_p,
                "current_price": round(cur_p, 2),
                "shares": shares,
                "market_value": round(cur_val, 2),
                "gain_pct": round(gain_pct, 1),
                "entry_date": p.get("entry_date", "-"),
                "reason": p.get("reason", "전략 매수")
            })

        total_asset = target_model["cash"] + total_eval_stock
        roi_pct = ((total_asset - target_model["total_deposited"]) / target_model["total_deposited"]) * 100.0

        return {
            "name": target_model["name"],
            "icon": target_model.get("icon", "🤖"),
            "philosophy": target_model.get("philosophy", ""),
            "cash": round(target_model["cash"], 2),
            "stock_value": round(total_eval_stock, 2),
            "total_asset": round(total_asset, 2),
            "total_deposited": round(target_model["total_deposited"], 2),
            "roi_pct": round(roi_pct, 2),
            "positions": positions_detail,
            "history": target_model.get("history", [])[-8:],  # last 8 events
            "take_profit_pct": target_model.get("take_profit_pct", 10.0),
            "stop_loss_pct": target_model.get("stop_loss_pct", -5.0)
        }
