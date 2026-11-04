import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
import os
import json
import asyncio
from pathlib import Path
from datetime import datetime

import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, TextInput
import yfinance as yf
from aiohttp import web

import config
try:
    from data.fetcher import MarketDataFetcher
    from data.buffett_screener import BuffettMoatScreener
    from data.chart_generator import generate_stock_chart
except ModuleNotFoundError:
    from fetcher import MarketDataFetcher
    from buffett_screener import BuffettMoatScreener
    from chart_generator import generate_stock_chart

try:
    from portfolio.tracker import PortfolioTracker
    from portfolio.auto_seller import AutoSellerEngine
except ModuleNotFoundError:
    from tracker import PortfolioTracker
    from auto_seller import AutoSellerEngine

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
tracker = PortfolioTracker()
auto_seller = AutoSellerEngine()

class CustomBuyModal(Modal):
    """
    Modal allowing user to set custom price and amount for Buffett Moat stocks.
    """
    def __init__(self, stock_item):
        ticker = stock_item['ticker']
        name = stock_item.get('name', ticker)
        super().__init__(title=f"{name} ({ticker}) 매수 주문 설정")
        self.stock_item = stock_item

        rec_usd = int(stock_item.get('recommended_usd', 120))
        cur_price = stock_item.get('current_price', 100.0)

        self.amount_input = TextInput(
            label="투자 금액 (USD $)",
            placeholder="투자할 달러 금액을 입력하세요",
            default=str(rec_usd),
            min_length=1,
            max_length=6,
            required=True
        )
        self.add_item(self.amount_input)

        self.price_input = TextInput(
            label="진입 희망가 (USD $)",
            placeholder="원하는 매수 가격 (기본값: 현재가)",
            default=f"{cur_price:.2f}",
            min_length=1,
            max_length=10,
            required=True
        )
        self.add_item(self.price_input)

    async def on_submit(self, interaction: discord.Interaction):
        ticker = self.stock_item['ticker']
        name = self.stock_item.get('name', ticker)
        
        try:
            custom_amount = float(self.amount_input.value.strip())
            custom_price = float(self.price_input.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ 숫자 형식으로 올바르게 입력해 주세요.", ephemeral=True)
            return

        # Target price: +15% intrinsic fair value take profit
        target_profit = round(custom_price * (1.0 + config.BUFFETT_CONFIG['auto_take_profit_pct']), 2)
        # In Buffett value investing, no mechanical -2.5% stop loss; stop price acts as fundamental alert level
        stop_alert_price = round(custom_price * 0.80, 2) # -20% deep dip alert for additional buying
        shares = round(custom_amount / custom_price, 2) if custom_price > 0 else 0.0

        trade = [{
            "ticker": ticker,
            "entry_price": custom_price,
            "stop_loss_price": stop_alert_price,
            "target_price": target_profit,
            "amount_usd": custom_amount,
            "shares": shares,
            "models": ["버핏가치투자"]
        }]
        tracker.add_positions(trade)

        embed = discord.Embed(
            title=f"✅ {name} ({ticker}) 매수 등록 완료!",
            color=0x2ecc71,
            description=(
                f"```text\n"
                f"종목명     : {ticker} · {name}\n"
                f"매수가격   : ${custom_price:.2f}\n"
                f"목표익절선 : ${target_profit:.2f} (+15.0% 고평가 도달 시 AI 자동매도)\n"
                f"투자금액   : ${custom_amount:,.0f} (약 {shares:.2f}주)\n"
                f"```\n"
                f"• **AI 자동 매도 전담**: 목표가 도달 시 AI가 고점에서 자동으로 매도하여 차익을 실현합니다.\n"
                f"• 편안하게 보유하시고, 매도는 AI에게 맡겨두시면 됩니다."
            )
        )
        await interaction.response.send_message(embed=embed)

class SingleStockBuyView(View):
    def __init__(self, stock_item):
        super().__init__(timeout=None)
        self.stock_item = stock_item
        name = stock_item.get('name', stock_item['ticker'])

        button = Button(
            label=f"🟢 {name} 매수하기 (금액/가격 설정)",
            style=discord.ButtonStyle.success,
            custom_id=f"buffett_buy_{stock_item['ticker']}"
        )
        button.callback = self.button_callback
        self.add_item(button)

    async def button_callback(self, interaction: discord.Interaction):
        modal = CustomBuyModal(self.stock_item)
        await interaction.response.send_modal(modal)

class StockSelectionBuyView(View):
    def __init__(self, candidates):
        super().__init__(timeout=None)
        for idx, s in enumerate(candidates[:5], start=1):
            ticker = s['ticker']
            name = s.get('name', ticker)
            btn = Button(
                label=f"[{idx}] {name} 매수",
                style=discord.ButtonStyle.success,
                custom_id=f"b_quick_buy_{ticker}"
            )
            btn.callback = self.create_callback(s)
            self.add_item(btn)

    def create_callback(self, stock_item):
        async def cb(interaction: discord.Interaction):
            modal = CustomBuyModal(stock_item)
            await interaction.response.send_modal(modal)
        return cb

class StockSelectionChartView(View):
    def __init__(self, candidates):
        super().__init__(timeout=None)
        for idx, s in enumerate(candidates[:5], start=1):
            ticker = s['ticker']
            name = s.get('name', ticker)
            btn = Button(
                label=f"[{idx}] {name} 차트",
                style=discord.ButtonStyle.primary,
                custom_id=f"b_quick_chart_{ticker}"
            )
            btn.callback = self.create_callback(s)
            self.add_item(btn)

    def create_callback(self, stock_item):
        async def cb(interaction: discord.Interaction):
            ticker = stock_item['ticker']
            name = stock_item.get('name', ticker)
            await interaction.response.send_message(f"📈 [{ticker}] {name} 차트 생성 중...", ephemeral=True)
            
            fetcher = MarketDataFetcher()
            df = fetcher.fetch_stock_history(ticker, period="5y")
            if df is not None:
                c_path = generate_stock_chart(df, ticker, name, output_path=f"assets/chart_{ticker}.png")
                if c_path and os.path.exists(c_path):
                    embed = discord.Embed(
                        title=f"📊 [{ticker}] {name} 3개월 / 1년 / 5년 멀티 종합 차트",
                        color=0x3498db
                    )
                    file = discord.File(c_path, filename=f"chart_{ticker}.png")
                    embed.set_image(url=f"attachment://chart_{ticker}.png")
                    await interaction.followup.send(embed=embed, file=file)
        return cb

last_active_channel_id = None
notified_dca_keys = set()

def build_dca_embed(c: dict) -> discord.Embed:
    ticker = c['ticker']
    name = c['name']
    entry_p = c['entry_price']
    cur_p = c['current_price']
    drop_pct = c['drop_pct']
    roe_pct = c['roe_pct']
    add_usd = c['add_amount_usd']
    new_avg = c['new_avg_price']
    new_shares = c['new_shares']
    scale_count = c.get('scale_in_count', 0)

    embed = discord.Embed(
        title=f"🚨 [바겐세일 추가 매수 기회 감지!] {ticker} · {name}",
        color=0xe67e22,
        description=(
            f"```text\n"
            f"종목      : {ticker} · {name}\n"
            f"현재 상황 : 진입가(${entry_p:.2f}) 대비 -{drop_pct:.1f}% 하락 (일시적 시장 조정)\n"
            f"AI 기업진단: ROE {roe_pct:.1f}% 로 본업 경쟁력 압도적 정상!\n"
            f"평단가 인하: 지금 ${add_usd:,.0f} 추가 매수 시 평단가가\n"
            f"           ${entry_p:.2f} ──▶ ${new_avg:.2f} 로 대폭 인하됩니다.\n"
            f"추가 수량 : 약 {new_shares:.2f}주 추가 (현재 {scale_count}/2회차)\n"
            f"```\n"
            f"💡 **워런 버핏의 해자 투자 원칙**:\n"
            f"본업 해자가 튼튼한 우량 기업이 시장 공포로 하락할 때는 두려워할 때가 아니라 평단가를 낮출 절호의 기회입니다.\n"
            f"👇 **아래 버튼을 눌러 승인하시면 즉시 평단가 낮추기가 집행됩니다.**"
        )
    )
    return embed

class DCAPromptView(View):
    def __init__(self, candidate: dict):
        super().__init__(timeout=None)
        self.candidate = candidate
        ticker = candidate['ticker']
        add_usd = candidate['add_amount_usd']

        buy_btn = Button(
            label=f"🟢 ${add_usd:.0f} 추가 매수 집행",
            style=discord.ButtonStyle.success,
            custom_id=f"dca_exec_{ticker}"
        )
        buy_btn.callback = self.execute_callback
        self.add_item(buy_btn)

        skip_btn = Button(
            label="❌ 건너뛰기",
            style=discord.ButtonStyle.secondary,
            custom_id=f"dca_skip_{ticker}"
        )
        skip_btn.callback = self.skip_callback
        self.add_item(skip_btn)

    async def execute_callback(self, interaction: discord.Interaction):
        ticker = self.candidate['ticker']
        name = self.candidate['name']
        add_usd = self.candidate['add_amount_usd']
        
        res = auto_seller.execute_dca(ticker, add_usd)
        if res.get("success"):
            for child in self.children:
                child.disabled = True
            
            embed = discord.Embed(
                title=f"✅ {name} ({ticker}) 스마트 추가 매수(물타기) 완료!",
                color=0x2ecc71,
                description=(
                    f"```text\n"
                    f"종목       : {ticker} · {name}\n"
                    f"추가 매수액 : ${add_usd:,.0f} 달러 (현재 체결가: ${res['cur_price']:.2f})\n"
                    f"평단가 변화 : ${res['old_entry']:.2f} ──▶ ${res['new_avg']:.2f} (대폭 인하!)\n"
                    f"총 보유 수량: {res['total_shares']:.2f}주 (추가 매수 {res['scale_in_count']}/2회)\n"
                    f"새 AI목표가 : ${round(res['new_avg']*(1.0 + config.BUFFETT_CONFIG['auto_take_profit_pct']), 2):.2f} (+15.0% 도달 시 자동 익절)\n"
                    f"```\n"
                    f"• 버핏의 원칙대로 좋은 기업의 일시적 조정을 이용해 평단가를 성공적으로 낮췄습니다.\n"
                    f"• 목표가(+15%) 도달 시 AI가 전량 자동 익절합니다."
                )
            )
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("❌ 추가 매수 집행 중 오류가 발생했거나 가용 현금이 부족합니다.", ephemeral=True)

    async def skip_callback(self, interaction: discord.Interaction):
        ticker = self.candidate['ticker']
        name = self.candidate['name']
        for child in self.children:
            child.disabled = True
        
        embed = discord.Embed(
            title=f"⏸️ {name} ({ticker}) 추가 매수 건너뛰기",
            color=0x95a5a6,
            description=f"이번 {name}의 추가 매수 제안은 집행하지 않고 기존 포지션을 유지합니다."
        )
        await interaction.response.edit_message(embed=embed, view=self)

def get_active_channel():
    global last_active_channel_id
    if last_active_channel_id:
        ch = bot.get_channel(last_active_channel_id)
        if ch:
            return ch
    for guild in bot.guilds:
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                return ch
    return None

# Background auto-seller & auto-DCA task that checks positions every 30 minutes
@tasks.loop(minutes=30)
async def auto_sell_check_loop():
    global last_active_channel_id
    try:
        channel = get_active_channel()

        # 1. Process weekly deposit ($50)
        dep = tracker.check_and_process_weekly_deposit(config.BUFFETT_CONFIG.get("weekly_deposit_usd", 50.0))
        if dep.get("deposited") and channel:
            dep_embed = discord.Embed(
                title="💰 [주간 적립식 투자금 자동 충전]",
                color=0x2ecc71,
                description=(
                    f"```text\n"
                    f"충전 일자   : {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                    f"충전 금액   : +${dep['amount_usd']:.2f} 달러\n"
                    f"가용 현금   : ${dep['new_cash']:,.2f} 달러 (총알 보충 완료)\n"
                    f"총 계좌 자산: ${dep['total_balance']:,.2f} 달러\n"
                    f"```\n"
                    f"• 매주 $50씩 현금이 자동 충전되어 깊은 바겐세일 물타기 및 신규 우량주 매수에 쓰입니다."
                )
            )
            await channel.send(embed=dep_embed)

        # 2. Check auto sell (+15% take profit or fundamental cut)
        auto_seller.check_and_execute_sells()

        # 3. Check and execute automated DCA (Option B: -10%, -18% with Guardrails)
        executed_dca = auto_seller.check_and_execute_auto_dca()
        if executed_dca and channel:
            for item in executed_dca:
                dca_embed = discord.Embed(
                    title=f"🚨 [AI 스마트 추가 매수 자동 집행 완료] {item['ticker']} · {item['name']}",
                    color=0xe67e22,
                    description=(
                        f"```text\n"
                        f"종목       : {item['ticker']} · {item['name']}\n"
                        f"집행 조건   : 진입가 대비 -{item['drop_pct']:.1f}% 하락 (B안 바겐세일 진입)\n"
                        f"AI 기업진단 : ROE {item['roe_pct']:.1f}% 로 본업 경쟁력 정상 확인\n"
                        f"추가 매수액 : ${item['add_usd']:,.0f} 달러 (현재 체결가: ${item['cur_price']:.2f})\n"
                        f"평단가 변화 : ${item['old_entry']:.2f} ──▶ ${item['new_avg']:.2f} (대폭 인하!)\n"
                        f"새 AI목표가 : ${item['target_profit_p']:.2f} (+15.0% 도달 시 전량 자동 익절)\n"
                        f"방지책 현황 : {item['stage']}/{item['max_count']}회차 집행 (남은 총알: {item['max_count']-item['stage']}회)\n"
                        f"남은 가용현금: ${item['remaining_cash']:,.2f} 달러\n"
                        f"```\n"
                        f"💡 **안전 가드레일 자동 준수**:\n"
                        f"• 번거로운 버튼 확인 없이 가장 유리한 저점에서 AI가 100% 자동 집행했습니다.\n"
                        f"• 종목당 최대 2회 캡 및 $250 투자 상한선 원칙이 엄격히 적용됩니다."
                    )
                )
                await channel.send(embed=dca_embed)
                await asyncio.sleep(1.0)
    except Exception as e:
        print(f"[AutoSeller/DCA Error] {e}")

@bot.before_invoke
async def before_any_command(ctx):
    global last_active_channel_id
    last_active_channel_id = ctx.channel.id

async def handle_ping(request):
    return web.Response(text="🏛️ [Buffett AI Quant Bot] 24/7 Live and Running on Render!")

async def start_render_web_server():
    try:
        app = web.Application()
        app.router.add_get('/', handle_ping)
        app.router.add_get('/health', handle_ping)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.environ.get("PORT", 10000))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        print(f"🌐 [Render Health Server] 0.0.0.0:{port} 정상 가동 완료 (24시간 무중단 포트 바인딩)")
    except Exception as e:
        print(f"[Render Server Info] {e}")

@bot.event
async def on_ready():
    print(f"🏛️ [Buffett AI Bot] {bot.user} 워런 버핏 퀀트 가치투자 봇 가동 완료!")
    await start_render_web_server()
    if not auto_sell_check_loop.is_running():
        auto_sell_check_loop.start()

@bot.command(name="추천")
async def cmd_recommend(ctx):
    status_msg = await ctx.send("🔍 버핏 30대 해자 기업의 [재무제표 ROE + 안전마진 할인율 + 차트]를 전수 분석 중입니다... (약 15초 소요)")
    
    curr_data = tracker.load()
    cash_avail = curr_data.get("cash_usd", 1000.0)
    open_pos = curr_data.get("open_positions", [])
    held_tickers = [p['ticker'] for p in open_pos]
    held_names = [f"{p['ticker']}({config.TICKER_INFO.get(p['ticker'], {}).get('name', p['ticker'])})" for p in open_pos]

    screener = BuffettMoatScreener()
    candidates = screener.screen_candidates(exclude_tickers=held_tickers)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    held_info_str = f"보유 제외 종목 : {', '.join(held_names)} (이미 보유 중으로 추천 제외)\n" if held_names else ""

    # Check if any stock qualified under strict Buffett criteria
    if not candidates:
        empty_embed = discord.Embed(
            title=f"🛡️ [추천 보류] 현재 버핏 엄격 기준 부합 종목 없음 ({now_str})",
            color=0xf39c12,
            description=(
                f"```text\n"
                f"진단 결과: 현재 버핏 30대 기업 중 '엄격한 안전마진'에 들어온 종목이 없습니다.\n"
                f"가용 현금: ${cash_avail:,.0f} 달러 (100% 현금 보존 권장)\n"
                f"{held_info_str}"
                f"```\n"
                f"💡 **우리만의 4대 엄격 추천 기준**:\n"
                f"1. **ROE 15% 이상** (압도적인 본업 자본효율성)\n"
                f"2. **영업이익률 10% 이상** (독점적 가격결정력 해자)\n"
                f"3. **52주 최고점 대비 최소 -8.0% 이상 할인** (고점 추격매수 절대 금지)\n"
                f"4. **버핏 종합점수 45점 이상** (펀더멘털 + 밸류에이션 복합 통과)\n\n"
                f"• **워런 버핏의 원칙**:\n"
                f"  *\"투자에서는 마음에 드는 완벽한 공이 스트라이크존에 들어올 때까지 방망이를 휘두르지 않고 지켜보는 것이 진정한 지혜입니다.\"*\n\n"
                f"• 무리하게 매수하지 않고, **진짜 바겐세일 기회가 포착될 때까지 현금을 소중히 지키며 대기**합니다."
            )
        )
        await ctx.send(embed=empty_embed)
        await status_msg.delete()
        return

    # 1. Header Overview Card
    header_embed = discord.Embed(
        title=f"🏛️ 워런 버핏 스타일 해자 가치주 추천 ({now_str})",
        color=0x27ae60,
        description=(
            f"```text\n"
            f"투자 철학       : 경제적 해자(ROE 15%+) + 안전마진(-8% 이상 할인)\n"
            f"현재 가용 현금   : ${cash_avail:,.0f} 달러\n"
            f"{held_info_str}"
            f"분할 매수 권장액 : 종목당 $100 ~ $150\n"
            f"매도 전략       : 목표가(+15%) 도달 시 AI 기계적 자동익절\n"
            f"```\n"
            f"👇 **아래 엄격 기준을 통과한 우량 가치주의 [재무 건전성 + 3M/1Y/5Y 멀티 종합 차트]를 확인하세요.**"
        )
    )
    await ctx.send(embed=header_embed)
    await status_msg.delete()

    fetcher = MarketDataFetcher()
    for idx, s in enumerate(candidates[:3], start=1):
        ticker = s['ticker']
        name = s['name']
        desc = s['desc']
        cur_p = s['current_price']
        high_p = s['high_52w']
        disc = s['discount_from_high']
        roe = s['roe_pct']
        margin = s['operating_margin_pct']
        target_p = round(cur_p * (1.0 + config.BUFFETT_CONFIG['auto_take_profit_pct']), 2)
        rec_usd = s['recommended_usd']
        shares = s['suggested_shares']

        stock_embed = discord.Embed(
            title=f"[{idx}위 추천] {ticker} · {name} ({desc})",
            color=0x16a085,
            description=(
                f"```text\n"
                f"현재 가격 : ${cur_p:.2f} ──▶ 52주 고점 대비: -{disc:.1f}% 할인 (바겐세일)\n"
                f"재무 해자 : ROE {roe:.1f}% │ 영업이익률 {margin:.1f}% (탁월한 수익성)\n"
                f"권장 배정 : ${rec_usd:.0f} (약 {shares:.2f}주) ──▶ AI목표가: ${target_p:.2f} (+15%)\n"
                f"버핏 점수 : {s['buffett_score']}점 (우량 펀더멘털 + 안전마진 우수)\n"
                f"```"
            )
        )

        df = fetcher.fetch_stock_history(ticker, period="5y")
        chart_file = None
        if df is not None:
            c_res = generate_stock_chart(df, ticker, name, output_path=f"assets/chart_{ticker}.png")
            if c_res and os.path.exists(c_res):
                chart_file = discord.File(c_res, filename=f"chart_{ticker}.png")
                stock_embed.set_image(url=f"attachment://chart_{ticker}.png")

        view = SingleStockBuyView(s)
        if chart_file:
            await ctx.send(embed=stock_embed, file=chart_file, view=view)
        else:
            await ctx.send(embed=stock_embed, view=view)

        await asyncio.sleep(1.0)

@bot.command(name="매수")
async def cmd_buy(ctx, ticker: str = None, amount_usd: float = None, custom_price: float = None):
    curr_data = tracker.load()
    open_pos = curr_data.get("open_positions", [])
    held_tickers = {p['ticker'] for p in open_pos}

    screener = BuffettMoatScreener()
    candidates = screener.screen_candidates(exclude_tickers=list(held_tickers))

    if not ticker:
        embed = discord.Embed(
            title="🎯 매수할 버핏 가치주 선택 (보유 종목 제외)",
            color=0x2ecc71,
            description=(
                "👇 **아래 버튼에서 매수하고 싶은 신규 우량 해자 기업을 선택해 주세요.**\n"
                "*(이미 보유 중인 종목은 중복 매수 방지를 위해 추천 목록에서 제외되었습니다)*\n\n"
                "버튼을 누르면 **투자 금액($)과 희망 가격($)**을 직접 설정할 수 있는 팝업창이 뜹니다."
            )
        )
        view = StockSelectionBuyView(candidates)
        await ctx.send(embed=embed, view=view)
        return

    ticker = ticker.upper()
    if ticker in held_tickers:
        await ctx.send(
            f"⚠️ **[{ticker}]** 종목은 이미 포트폴리오에 보유 중입니다!\n"
            f"• 중복 매수 대신 `!물타기`를 통해 -10% 이상 하락 시 자동 평단가 낮추기가 진행됩니다."
        )
        return

    info = config.TICKER_INFO.get(ticker, {"name": ticker, "desc": "우량 가치주"})
    name = info["name"]

    fetcher = MarketDataFetcher()
    df = fetcher.fetch_stock_history(ticker, period="5d")
    if df is None:
        await ctx.send(f"❌ {ticker} 종목의 시세 정보를 찾을 수 없습니다.")
        return

    entry_price = custom_price if custom_price else float(df['Close'].iloc[-1])
    target_profit = round(entry_price * (1.0 + config.BUFFETT_CONFIG['auto_take_profit_pct']), 2)
    amount_usd = amount_usd if amount_usd else 120.0
    shares = round(amount_usd / entry_price, 2) if entry_price > 0 else 0.0

    trade = [{
        "ticker": ticker,
        "entry_price": entry_price,
        "stop_loss_price": round(entry_price * 0.80, 2),
        "target_price": target_profit,
        "amount_usd": amount_usd,
        "shares": shares,
        "models": ["버핏가치투자"]
    }]
    tracker.add_positions(trade)

    embed = discord.Embed(
        title=f"✅ {name} ({ticker}) 매수 주문 등록 완료!",
        color=0x2ecc71,
        description=(
            f"```text\n"
            f"종목명     : {ticker} · {name}\n"
            f"진입 가격 : ${entry_price:.2f}\n"
            f"AI목표익절: ${target_profit:.2f} (+15.0% 도달 시 AI 자동매도)\n"
            f"투자금액   : ${amount_usd:,.0f} (약 {shares:.2f}주)\n"
            f"```\n"
            f"• 매수는 내가 완료했습니다. 이제 **매도는 AI가 알아서 기계적으로 집행**합니다."
        )
    )
    await ctx.send(embed=embed)

@bot.command(name="차트")
async def cmd_chart(ctx, ticker: str = None):
    screener = BuffettMoatScreener()
    candidates = screener.screen_candidates()

    if not ticker:
        embed = discord.Embed(
            title="📈 차트 조회할 종목 선택",
            color=0x3498db,
            description="👇 **아래 버튼에서 차트를 확인하고 싶은 종목을 선택해 주세요.**"
        )
        view = StockSelectionChartView(candidates)
        await ctx.send(embed=embed, view=view)
        return

    ticker = ticker.upper()
    info = config.TICKER_INFO.get(ticker, {"name": ticker, "desc": "우량 가치주"})
    name = info["name"]
    await ctx.send(f"📈 [{ticker}] {name}의 [3개월 단기 + 1년 안전마진 + 5년 장기 해자 3단 종합 차트]를 생성 중입니다...")

    fetcher = MarketDataFetcher()
    df = fetcher.fetch_stock_history(ticker, period="5y")
    if df is None:
        await ctx.send(f"❌ {ticker} 종목의 차트 데이터를 불러올 수 없습니다.")
        return

    cur_p = df['Close'].iloc[-1]
    c_path = generate_stock_chart(df, ticker, name, output_path=f"assets/chart_{ticker}.png")

    if c_path and os.path.exists(c_path):
        embed = discord.Embed(
            title=f"📊 [{ticker}] {name} 3개월 / 1년 / 5년 멀티 종합 차트",
            color=0x3498db,
            description=f"```text\n현재 가격: ${cur_p:.2f}\n```"
        )
        file = discord.File(c_path, filename=f"chart_{ticker}.png")
        embed.set_image(url=f"attachment://chart_{ticker}.png")
        await ctx.send(embed=embed, file=file)
    else:
        await ctx.send("차트 이미지 생성 중 오류가 발생했습니다.")

@bot.command(name="잔고", aliases=["포트폴리오"])
async def cmd_balance(ctx):
    # Trigger auto seller check first
    sold = auto_seller.check_and_execute_sells()
    
    data = tracker.load()
    cash = data.get("cash_usd", 1000.0)
    open_pos = data.get("open_positions", [])

    if not open_pos:
        embed = discord.Embed(
            title="📊 내 계좌 잔고 및 보유 주식",
            color=0x3498db,
            description=(
                f"```text\n"
                f"보유 종목 수 : 0개\n"
                f"가용 현금   : ${cash:,.0f} 달러\n"
                f"총 계좌 자산: ${cash:,.0f} 달러\n"
                f"```\n"
                f"👉 `!추천` 또는 `!매수` 명령어로 버핏 가치주를 담아보세요."
            )
        )
        await ctx.send(embed=embed)
        return

    pos_blocks = []
    total_val = cash
    now_live_str = datetime.now().strftime("%H:%M:%S")

    # Fetch live real-time prices for all open positions
    for p in open_pos:
        t = p['ticker']
        name = config.TICKER_INFO.get(t, {}).get("name", t)
        entry_p = p['entry_price']
        usd = p['amount_usd']
        shares = p.get('shares', round(usd / entry_p, 2))
        
        # Real-time price query
        try:
            live_price = float(yf.Ticker(t).fast_info.last_price)
            if live_price > 0:
                cur_p = live_price
            else:
                cur_p = p.get('current_price', entry_p)
        except Exception:
            cur_p = p.get('current_price', entry_p)

        # Calculate exact live PnL
        pnl_pct = ((cur_p - entry_p) / entry_p) * 100.0
        pnl_usd = (cur_p - entry_p) * shares
        cur_val = usd + pnl_usd
        total_val += cur_val

        # Update position record
        p['current_price'] = round(cur_p, 2)
        p['unrealized_pnl_pct'] = round(pnl_pct, 2)
        p['unrealized_pnl_usd'] = round(pnl_usd, 2)

        pnl_sign = "+" if pnl_pct >= 0 else ""
        usd_sign = "+" if pnl_usd >= 0 else ""
        target_p = p.get('target_price', entry_p * (1.0 + config.BUFFETT_CONFIG['auto_take_profit_pct']))

        pos_blocks.append(
            f"• {t} · {name}\n"
            f"  진입가: ${entry_p:.2f} ──▶ 실시간: ${cur_p:.2f} ({pnl_sign}{pnl_pct:.2f}%)\n"
            f"  평가액: ${cur_val:.2f} ({usd_sign}${pnl_usd:.2f}) │ AI익절가: ${target_p:.2f} (+15%)"
        )

    # Save fresh live prices into tracker
    tracker.save(data)

    blocks_str = "\n----------------------------------------\n".join(pos_blocks)
    total_pnl_pct = ((total_val - 1000.0) / 1000.0) * 100.0
    tot_sign = "+" if total_pnl_pct >= 0 else ""

    embed = discord.Embed(
        title=f"📊 내 계좌 실시간 포트폴리오 ({now_live_str} 기준)",
        color=0x2ecc71 if total_val >= 1000.0 else 0xe74c3c,
        description=(
            f"```text\n"
            f"{blocks_str}\n"
            f"```\n"
            f"```text\n"
            f"가용 현금   : ${cash:,.2f} 달러\n"
            f"총 계좌 자산: ${total_val:,.2f} 달러 ({tot_sign}{total_pnl_pct:.2f}%)\n"
            f"```\n"
            f"💡 **실시간 시세 반영**: 방금 미국 증시 실시간 체결가를 반영하여 손익을 갱신했습니다."
        )
    )
    await ctx.send(embed=embed)

@bot.command(name="초기화")
async def cmd_reset(ctx):
    initial_data = {
        "balance_usd": 1000.0,
        "cash_usd": 1000.0,
        "open_positions": [],
        "closed_positions": []
    }
    tracker.save(initial_data)
    embed = discord.Embed(
        title="🔄 계좌 초기화 완료",
        color=0xf39c12,
        description=(
            f"```text\n"
            f"설정 상태   : 초기화 완료\n"
            f"가용 현금   : $1,000 달러 (100% 현금)\n"
            f"보유 종목   : 0개\n"
            f"```\n"
            f"버핏 가치주로 새 출발합니다. `!추천`을 입력해 보세요."
        )
    )
    await ctx.send(embed=embed)

@bot.command(name="물타기", aliases=["추가매수", "dca", "평단가"])
async def cmd_dca(ctx):
    global last_active_channel_id
    last_active_channel_id = ctx.channel.id

    data = tracker.load()
    cash = data.get("cash_usd", 1000.0)
    open_pos = data.get("open_positions", [])

    cfg = config.BUFFETT_CONFIG
    status_lines = []

    for p in open_pos:
        t = p['ticker']
        name = config.TICKER_INFO.get(t, {}).get("name", t)
        entry_p = p['entry_price']
        scale_count = p.get('scale_in_count', 0)

        roe = 0.20
        try:
            stock = yf.Ticker(t)
            cur_p = float(stock.fast_info.last_price)
            roe = stock.info.get('returnOnEquity', 0.20) or 0.20
        except Exception:
            cur_p = p.get('current_price', entry_p)

        gain_pct = ((cur_p - entry_p) / entry_p) * 100.0
        pnl_sign = "+" if gain_pct >= 0 else ""
        
        target_drop = cfg.get("dca_stage1_drop_pct", -10.0) if scale_count == 0 else cfg.get("dca_stage2_drop_pct", -18.0)
        gap = gain_pct - target_drop

        # Check 3-day cooldown
        last_action_str = p.get('last_dca_date') or p.get('entry_date')
        cooldown_tag = ""
        if last_action_str:
            try:
                last_dt = datetime.strptime(last_action_str[:10], "%Y-%m-%d").date()
                passed = (datetime.now().date() - last_dt).days
                if passed < cfg.get("dca_cooldown_days", 3):
                    cooldown_tag = f" │ 쿨다운 D-{3-passed}일"
                else:
                    cooldown_tag = " │ 쿨다운 해제(바닥확인)"
            except Exception:
                pass

        roe_str = f"ROE {roe*100:.1f}%(해자정상)" if roe >= 0.15 else f"ROE {roe*100:.1f}%(⚠️해자경고)"

        if scale_count >= cfg.get("dca_max_count", 2):
            stage_str = "완료 (2회 캡 도달)"
            cond_str = "추가 매수 한도 종료 (안전 캡)"
        elif gap <= 0:
            stage_str = f"{scale_count+1}차 도달! (자동 집행 대상)"
            cond_str = f"목표 낙폭({target_drop:.1f}%) 돌파! {cooldown_tag}"
        else:
            stage_str = f"{scale_count+1}차 대기 중"
            cond_str = f"목표선({target_drop:.1f}%)까지 {gap:.1f}% 추가 하락 시 자동 집행{cooldown_tag}"

        status_lines.append(
            f"• {t} · {name} ({stage_str})\n"
            f"  진입가: ${entry_p:.2f} ──▶ 현재: ${cur_p:.2f} ({pnl_sign}{gain_pct:.1f}%) │ {roe_str}\n"
            f"  상황: {cond_str}"
        )

    block_text = "\n----------------------------------------\n".join(status_lines) if status_lines else "현재 보유 중인 종목이 없습니다."

    embed = discord.Embed(
        title="🛡️ 스마트 물타기 (B안: -10% / -18% 자동화) 현황",
        color=0x3498db,
        description=(
            f"```text\n"
            f"{block_text}\n"
            f"```\n"
            f"```text\n"
            f"가용 현금 : ${cash:,.2f} 달러 (최소 보존 버퍼: $100)\n"
            f"주간 충전 : 매주 $50.00 자동 적립 예정\n"
            f"```\n"
            f"💡 **AI 추가 매수 5대 안전 방지책**:\n"
            f"1. **B안 낙폭 기준**: 1차 -10% / 2차 -18% (잔파도 무시, 진짜 바겐세일만)\n"
            f"2. **종목당 최대 2회 캡**: 2회 초과 물타기 원천 차단\n"
            f"3. **종목당 투자 한도**: 총 $250(계좌 25%) 초과 투입 금지\n"
            f"4. **비상 현금 보존**: 가용 현금 $100 이하시 집행 중단\n"
            f"5. **3일 쿨다운**: 동일 종목 연속 추가 매수 방지 (바닥 확인)\n\n"
            f"조건 충족 시 **AI가 번거로운 승인 대기 없이 가장 유리한 저점에 즉시 자동 매수**하고 결과를 알려드립니다!"
        )
    )
    await ctx.send(embed=embed)

@bot.command(name="적립", aliases=["입금", "주간적립", "deposit"])
async def cmd_deposit(ctx, amount: float = None):
    global last_active_channel_id
    last_active_channel_id = ctx.channel.id

    data = tracker.load()
    today = datetime.now().date()
    last_date_str = data.get("last_weekly_deposit_date", today.strftime("%Y-%m-%d"))

    try:
        last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
    except Exception:
        last_date = today

    days_passed = (today - last_date).days
    days_left = max(0, 7 - days_passed)

    if amount and amount > 0:
        data["cash_usd"] = round(data.get("cash_usd", 1000.0) + amount, 2)
        data["balance_usd"] = round(data.get("balance_usd", 1000.0) + amount, 2)
        tracker.save(data)
        embed = discord.Embed(
            title="💰 계좌 추가 입금(적립) 완료",
            color=0x2ecc71,
            description=(
                f"```text\n"
                f"입금 금액   : +${amount:,.2f} 달러\n"
                f"현재 가용현금: ${data['cash_usd']:,.2f} 달러\n"
                f"총 계좌 자산: ${data['balance_usd']:,.2f} 달러\n"
                f"```\n"
                f"• 추가된 현금은 바겐세일 스마트 물타기 및 신규 가치주 매수에 즉시 투입 가능합니다."
            )
        )
        await ctx.send(embed=embed)
        return

    embed = discord.Embed(
        title="💰 주간 적립식 투자 현황",
        color=0x2ecc71,
        description=(
            f"```text\n"
            f"자동 적립 주기 : 매주 1회 ($50.00 달러)\n"
            f"최근 적립 일자 : {last_date_str}\n"
            f"다음 적립까지   : D-{days_left}일 남음\n"
            f"현재 가용 현금 : ${data.get('cash_usd', 1000.0):,.2f} 달러\n"
            f"```\n"
            f"• 매주 $50씩 현금이 자동 충전되어 현금 고갈 없이 꾸준히 버핏 투자를 이어갈 수 있습니다.\n"
            f"• 직접 추가 입금하시려면 `!적립 [금액]` (예: `!적립 50`)을 입력하세요."
        )
    )
    await ctx.send(embed=embed)

@bot.command(name="명령어", aliases=["도움말", "help", "commands"])
async def cmd_help(ctx):
    embed = discord.Embed(
        title="🏛️ 워런 버핏 가치투자 봇 명령어 가이드",
        color=0x9b59b6,
        description=(
            f"```text\n"
            f"【 분석 및 추천 】\n"
            f"• !추천  : 버핏 30대 기업 ROE/할인율 분석 + 1년 차트 + 매수 버튼\n"
            f"• !차트  : 버튼을 탭해 원하는 가치주 1년 차트 즉시 확인\n"
            f"\n"
            f"【 주문 및 계좌 관리 】\n"
            f"• !매수  : 버튼을 탭해 원하는 가치주 매수 팝업 설정\n"
            f"• !물타기: B안(-10%, -18%) 자동 평단가 인하 & 5대 방지책 현황\n"
            f"• !적립  : 매주 $50 자동 충전 일정 확인 및 수동 추가 입금\n"
            f"• !잔고  : 현재 보유 주식, 실시간 수익률, AI목표익절가 확인\n"
            f"• !초기화: 계좌를 $1,000 초기 현금 상태로 리셋\n"
            f"• !명령어: 이 도움말 안내창 다시 보기\n"
            f"```\n"
            f"💡 **완성된 3단계 역할 분담**:\n"
            f"1. **신규 매수**: 내가 `!추천` 보고 버튼을 눌러 최종 결정\n"
            f"2. **물타기**: B안(-10%, -18%) + 5대 안전방지책 하에 **AI가 100% 자동 분할 매수 + 디스코드 알림**\n"
            f"3. **매도**: 목표가(+15%) 도달 시 **AI가 100% 기계적 전량 자동 익절**"
        )
    )
    await ctx.send(embed=embed)

if __name__ == "__main__":
    token = os.getenv("DISCORD_BOT_TOKEN", "")
    if not token:
        print("[Error] DISCORD_BOT_TOKEN 이 .env 파일에 설정되어 있지 않습니다.")
    else:
        bot.run(token)
