import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
import json
from pathlib import Path
import requests

import config
from data.fetcher import MarketDataFetcher
from data.earnings_filter import EarningsSafetyFilter
from models import MomentumBreakoutModel, MeanReversionModel, QualityTrendModel
from tournament.leaderboard import TournamentEngine
from rl_agent.ppo_manager import RLPortfolioManager
from portfolio.tracker import PortfolioTracker

CANDIDATES_CACHE_FILE = Path(__file__).resolve().parent / "data" / "latest_candidates.json"

def get_candidates(budget_usd=1000.0):
    fetcher = MarketDataFetcher()
    macro_state = fetcher.fetch_macro_state()
    earnings_filter = EarningsSafetyFilter()

    stock_data = {}
    for ticker in config.DEFAULT_TICKERS:
        if earnings_filter.check_earnings_risk(ticker)['is_safe_to_buy']:
            df = fetcher.fetch_stock_history(ticker, period="6mo")
            if df is not None:
                stock_data[ticker] = df

    models = [MomentumBreakoutModel(), MeanReversionModel(), QualityTrendModel()]
    tournament = TournamentEngine(models)
    tournament_result = tournament.run_tournament(stock_data)
    champion = tournament_result['champion']
    consensus_res = tournament.aggregate_consensus(stock_data)

    champ_picks = champion['model_instance'].score_stocks(stock_data)
    combined = []
    seen = set()
    for p in consensus_res['consensus_picks'] + champ_picks + consensus_res['all_picks']:
        if p['ticker'] not in seen:
            seen.add(p['ticker'])
            combined.append(p)

    rl_manager = RLPortfolioManager()
    allocation = rl_manager.optimize_allocations(combined, macro_state, budget_usd)
    
    with open(CANDIDATES_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(allocation, f, indent=2, ensure_ascii=False)

    return allocation

def interactive_selection():
    print("=" * 70)
    print("🎯 [투자자 포트폴리오 직접 선택 & 자금 결정 프로그램]")
    print("=" * 70)

    tracker = PortfolioTracker()
    current_data = tracker.load()
    cash_avail = current_data.get("cash_usd", 1000.0)
    print(f"• 현재 계좌 가용 현금: ${cash_avail:,.0f} 달러\n")

    if CANDIDATES_CACHE_FILE.exists():
        with open(CANDIDATES_CACHE_FILE, "r", encoding="utf-8") as f:
            allocation = json.load(f)
    else:
        print("최신 AI 추천 후보를 분석하는 중입니다...")
        allocation = get_candidates(cash_avail)

    stocks = allocation.get("allocated_stocks", [])[:10]
    if not stocks:
        print("현재 매수 추천 후보가 없습니다.")
        return

    print("📊 [오늘의 AI 추천 후보 목록 (기업 한글명 & 핵심 사업 포함)]")
    print("-" * 70)
    for idx, s in enumerate(stocks, start=1):
        ticker = s['ticker']
        info = config.TICKER_INFO.get(ticker, {"name": ticker, "desc": "우량주"})
        name = info["name"]
        desc = info["desc"]

        cur_p = s['current_price']
        sl_p = s['stop_loss_price']
        pct = s['recommended_pct']
        usd = s['recommended_usd']
        shares = round(usd / cur_p, 1) if cur_p > 0 else 0.0

        print(f"[{idx:>2}] {ticker} · {name} ({desc})")
        print(f"     현재가: ${cur_p:.2f} ──▶ 손절선: ${sl_p:.2f} (-2.5%)")
        print(f"     AI 추천액: ${usd:.0f} ({shares:.1f}주, {pct:.1f}%)\n")
    print("-" * 70)

    print("💡 [선택 방법 가이드]")
    print("1) 번호와 직접 투자할 금액 입력: 1 150, 3 100  (1번에 $150, 3번에 $100)")
    print("2) AI 추천금액 그대로 선택: 1, 3  (1번, 3번을 AI 추천금액으로 매수)")
    print("3) 'all' 입력 시: 상위 5개 종목을 AI 추천금액으로 일괄 매수")
    print("4) 'q' 입력 시: 취소하고 나가기\n")

    user_input = input("선택을 입력하세요 > ").strip()
    if not user_input or user_input.lower() == 'q':
        print("매수를 취소했습니다.")
        return

    selected_trades = []
    if user_input.lower() == 'all':
        for s in stocks[:5]:
            selected_trades.append({
                "ticker": s['ticker'],
                "entry_price": s['current_price'],
                "stop_loss_price": s['stop_loss_price'],
                "target_price": s.get('target_price', s['current_price'] * 1.08),
                "amount_usd": s['recommended_usd'],
                "models": [s.get('model', 'AI')]
            })
    else:
        tokens = [t.strip() for t in user_input.split(',')]
        for token in tokens:
            parts = token.split()
            if not parts:
                continue
            try:
                stock_idx = int(parts[0]) - 1
                if 0 <= stock_idx < len(stocks):
                    stock_item = stocks[stock_idx]
                    if len(parts) >= 2:
                        custom_amount = float(parts[1])
                    else:
                        custom_amount = stock_item['recommended_usd']

                    selected_trades.append({
                        "ticker": stock_item['ticker'],
                        "entry_price": stock_item['current_price'],
                        "stop_loss_price": stock_item['stop_loss_price'],
                        "target_price": stock_item.get('target_price', stock_item['current_price'] * 1.08),
                        "amount_usd": custom_amount,
                        "models": [stock_item.get('model', 'AI')]
                    })
            except ValueError:
                print(f"입력 형식 오류: '{token}' 건너뜁니다.")

    if not selected_trades:
        print("선택된 종목이 없습니다.")
        return

    total_spend = sum(t['amount_usd'] for t in selected_trades)
    print(f"\n총 {len(selected_trades)}개 종목, 총 ${total_spend:,.0f} 달러 매수 등록 중...")
    
    tracker.add_positions(selected_trades)
    print("포트폴리오 기록 및 지속적 사후 학습 추적기에 저장되었습니다!")

    send_discord_confirmation(selected_trades, total_spend)

def send_discord_confirmation(selected_trades, total_spend):
    blocks = []
    for t in selected_trades:
        ticker = t['ticker']
        info = config.TICKER_INFO.get(ticker, {"name": ticker, "desc": ""})
        name = info["name"]
        cur_p = t['entry_price']
        sl_p = t['stop_loss_price']
        usd = t['amount_usd']
        shares = round(usd / cur_p, 1) if cur_p > 0 else 0.0

        blocks.append(
            f"• {ticker} · {name}\n"
            f"  진입가: ${cur_p:.2f} ──▶ 손절선: ${sl_p:.2f} (-2.5%)\n"
            f"  투자금액: ${usd:.0f} (약 {shares:.1f}주)"
        )

    block_text = "\n----------------------------------------\n".join(blocks)

    embed = {
        "title": "투자자 포트폴리오 매수 확정 알림",
        "color": 0x27ae60,
        "description": (
            f"### [투자자 선택 주문 완료]\n"
            f"```text\n"
            f"{block_text}\n"
            f"```\n"
            f"• **총 투자 집행액**: `${total_spend:,.0f}`\n"
            f"• **사후 추적**: 손절선(-2.5%) 또는 목표가(+8%) 도달 시 자동 알림 및 AI 모델 학습 피드백이 기록됩니다."
        )
    }

    if config.DISCORD_WEBHOOK_URL:
        try:
            requests.post(config.DISCORD_WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)
            print("[Discord] 투자자 포트폴리오 확정 알림이 디스코드에 발송되었습니다!")
        except Exception:
            pass

if __name__ == "__main__":
    interactive_selection()
