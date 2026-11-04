import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
import argparse
from typing import List, Dict
import pandas as pd

import config
from data.fetcher import MarketDataFetcher
from data.earnings_filter import EarningsSafetyFilter
from models import MomentumBreakoutModel, MeanReversionModel, QualityTrendModel
from tournament.leaderboard import TournamentEngine
from rl_agent.ppo_manager import RLPortfolioManager
from reporter.discord_bot import DiscordReporter
from portfolio.tracker import PortfolioTracker
import json
from pathlib import Path

def run_pipeline(
    tickers: List[str] = None,
    budget_usd: float = 1000.0,
    force_safe_regime: bool = False
):
    print("🚀 [1/6] 미국 주식 AI 코파일럿 시스템 시작...")

    # 0. Check Existing Portfolio & Continuous Learning Tracker
    tracker = PortfolioTracker()
    check_res = tracker.check_open_positions()
    active_pos = check_res.get('active', [])
    closed_today = check_res.get('closed_today', [])
    if active_pos:
        print(f"• 현재 보유 관리 중인 포지션: {len(active_pos)}개")
    if closed_today:
        print(f"• 오늘 청산/손익 확정된 포지션: {len(closed_today)}개 (AI 지속학습 피드백 반영 완료)")

    tickers = tickers or config.DEFAULT_TICKERS
    print(f"• 분석 대상 종목 수: {len(tickers)}개 우량주")
    print(f"• 설정 운용 자산: ${budget_usd:,.0f} 달러")

    # 1. Fetch Macro Data
    print("\n🌐 [2/6] 글로벌 매크로 및 위험 지표 수집 중...")
    fetcher = MarketDataFetcher()
    macro_state = fetcher.fetch_macro_state()
    if force_safe_regime:
        macro_state["regime"] = "SAFE"
    print(f"• 거시경제 체제: {macro_state['regime']} (VIX: {macro_state['vix']}, 10Y금리: {macro_state['tnx_10y_yield']}%)")

    # 2. Fetch Stock Historical Data
    print("\n📈 [3/6] 종목별 OHLCV 및 기술적 지표 계산 중...")
    stock_data: Dict[str, pd.DataFrame] = {}
    earnings_filter = EarningsSafetyFilter(blackout_days=config.RISK_CONFIG['earnings_blackout_days'])
    
    safe_tickers = []
    for ticker in tickers:
        # Check earnings blackout
        earnings_status = earnings_filter.check_earnings_risk(ticker)
        if not earnings_status['is_safe_to_buy']:
            print(f"  └ ⚠️ [어닝 제외] {ticker}: {earnings_status['days_until_earnings']}일 후 실적 발표 예정")
            continue
            
        df = fetcher.fetch_stock_history(ticker, period="1y")
        if df is not None:
            stock_data[ticker] = df
            safe_tickers.append(ticker)

    print(f"• 실적 필터 통과 및 데이터 준비 완료: {len(stock_data)}개 종목")

    # 3. Competing Models & Tournament
    print("\n🥊 [4/6] 모델 토너먼트 리그전 진행 중...")
    model_a = MomentumBreakoutModel()
    model_b = MeanReversionModel()
    model_c = QualityTrendModel()
    competing_models = [model_a, model_b, model_c]

    tournament = TournamentEngine(competing_models)
    tournament_result = tournament.run_tournament(stock_data)
    champion = tournament_result['champion']
    print(f"• 🏆 토너먼트 1위 챔피언: {champion['model_name']} (샤프: {champion['sharpe_ratio']}, 승률: {champion['win_rate']}%)")

    # Gather consensus and candidate picks
    consensus_res = tournament.aggregate_consensus(stock_data)
    unanimous_picks = consensus_res['consensus_picks']
    all_picks = consensus_res['all_picks']

    # Priority pool: Champion's picks + Unanimous picks
    champ_picks = champion['model_instance'].score_stocks(stock_data)
    combined_candidates = []
    seen = set()

    for p in unanimous_picks + champ_picks + all_picks:
        if p['ticker'] not in seen:
            seen.add(p['ticker'])
            combined_candidates.append(p)

    print(f"• 총 발굴된 매수 후보 종목: {len(combined_candidates)}개")

    # 4. RL Portfolio Allocator
    print("\n🧠 [5/6] 강화학습(RL) 펀드매니저 최적 비중 및 자금 배분 계산 중...")
    rl_manager = RLPortfolioManager(
        max_single_allocation=config.RISK_CONFIG['max_position_size_pct']
    )
    allocation_result = rl_manager.optimize_allocations(
        candidate_picks=combined_candidates,
        macro_state=macro_state,
        total_budget_usd=budget_usd
    )

    # Save cache for interactive selection
    cache_path = Path(__file__).resolve().parent / "data" / "latest_candidates.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(allocation_result, f, indent=2, ensure_ascii=False)

    # 5. Discord Delivery & Logging
    print("\n📢 [6/6] 디스코드 리포트 발송 중...")
    reporter = DiscordReporter(webhook_url=config.DISCORD_WEBHOOK_URL)
    reporter.send_report(
        macro_state=macro_state,
        tournament_result=tournament_result,
        rl_allocation=allocation_result,
        unanimous_picks=unanimous_picks,
        total_budget_usd=budget_usd
    )
    print("✅ 모든 파이프라인이 성공적으로 실행되었습니다!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Antigravity AI US Stock Copilot")
    parser.add_argument("--budget", type=float, default=1000.0, help="Total investment budget in USD")
    parser.add_argument("--test-safe", action="store_true", help="Force SAFE macro regime for testing")
    args = parser.parse_args()

    run_pipeline(budget_usd=args.budget, force_safe_regime=args.test_safe)
