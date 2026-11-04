import matplotlib
matplotlib.use('Agg') # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from pathlib import Path
from typing import Optional
import platform

# Set Korean Font for Windows / Linux Cloud Containers
if platform.system() == 'Windows':
    plt.rcParams['font.family'] = 'Malgun Gothic'
else:
    plt.rcParams['font.family'] = 'NanumGothic'
plt.rcParams['axes.unicode_minus'] = False

def generate_stock_chart(
    df: pd.DataFrame,
    ticker: str,
    name: str,
    stop_loss: float = 0.0,
    target_profit: float = 0.0,
    output_path: str = "assets/latest_chart.png"
) -> Optional[str]:
    """
    Generates a 3-timeframe comprehensive minimalist stock chart:
    [Panel 1 - Top]: Recent 3-Month Detail (60 days) + Trading Volume (Short-term Timing)
    [Panel 2 - Middle]: Recent 1-Year Range (252 days) (Mid-term Margin of Safety)
    [Panel 3 - Bottom]: 5-Year Long-Term Moat Growth Trajectory (Long-term Foundation)
    """
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        if df is None or len(df) < 10:
            return None

        fig = plt.figure(figsize=(11, 10.5), facecolor='#0f172a') # Sleek dark slate
        gs = fig.add_gridspec(4, 1, height_ratios=[2.5, 0.9, 2.0, 2.2], hspace=0.32)

        ax1 = fig.add_subplot(gs[0])
        ax1_v = fig.add_subplot(gs[1], sharex=ax1)
        ax2 = fig.add_subplot(gs[2])
        ax3 = fig.add_subplot(gs[3])

        for ax in [ax1, ax1_v, ax2, ax3]:
            ax.set_facecolor('#0f172a')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_color('#334155')
            ax.spines['bottom'].set_color('#334155')
            ax.tick_params(colors='#94a3b8', labelsize=8)

        latest_p = float(df['Close'].iloc[-1])

        # ==========================================
        # 1. Top Panel: 3-Month Detail & Volume (60 days)
        # ==========================================
        df_3m = df.iloc[-60:].copy() if len(df) >= 60 else df.copy()
        d3 = df_3m.index
        c3 = df_3m['Close']
        h3, l3 = c3.max(), c3.min()

        ax1.plot(d3, c3, color='#00f2fe', linewidth=2.0) # Bright neon cyan
        ax1.fill_between(d3, c3, c3.min() * 0.99, color='#00f2fe', alpha=0.10)
        ax1.scatter([d3[-1]], [latest_p], color='#00f2fe', s=50, zorder=5)
        ax1.text(
            d3[-1], latest_p, f" ${latest_p:.2f}",
            color='#f8fafc', fontsize=10, fontweight='bold', va='center'
        )
        ax1.set_title(
            f"[{ticker}] {name}  │  ① 최근 3개월 단기 흐름 & 매수세 (3M: \\${l3:.2f} ~ \\${h3:.2f})",
            color='#f8fafc', fontsize=11, fontweight='bold', pad=8, loc='left'
        )
        ax1.grid(True, color='#334155', linestyle=':', alpha=0.4)

        # 3M Volume Bars
        v_colors = ['#ef4444' if df_3m['Close'].iloc[i] < df_3m['Open'].iloc[i] else '#10b981' for i in range(len(df_3m))]
        ax1_v.bar(d3, df_3m['Volume'], color=v_colors, alpha=0.7, width=0.8)
        ax1_v.set_ylabel('Volume', color='#94a3b8', fontsize=8)
        ax1_v.grid(True, color='#334155', linestyle=':', alpha=0.3)
        ax1_v.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))

        # ==========================================
        # 2. Middle Panel: 1-Year Range (252 days)
        # ==========================================
        df_1y = df.iloc[-252:].copy() if len(df) >= 252 else df.copy()
        d1 = df_1y.index
        c1 = df_1y['Close']
        h1, l1 = c1.max(), c1.min()

        ax2.plot(d1, c1, color='#38bdf8', linewidth=2.0) # Sky blue
        ax2.fill_between(d1, c1, c1.min() * 0.99, color='#38bdf8', alpha=0.10)
        ax2.scatter([d1[-1]], [latest_p], color='#38bdf8', s=50, zorder=5)
        ax2.set_title(
            f"② 최근 1년 중기 안전마진 추세 (52주 고점: \\${h1:.2f} │ 저점: \\${l1:.2f})",
            color='#f8fafc', fontsize=11, fontweight='bold', pad=8, loc='left'
        )
        ax2.grid(True, color='#334155', linestyle=':', alpha=0.4)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%y/%m'))

        # ==========================================
        # 3. Bottom Panel: 5-Year Moat Growth Curve
        # ==========================================
        df_5y = df.iloc[-1260:].copy() if len(df) >= 1260 else df.copy()
        d5 = df_5y.index
        c5 = df_5y['Close']
        h5, l5 = c5.max(), c5.min()

        ax3.plot(d5, c5, color='#a78bfa', linewidth=2.0) # Violet-purple long-term line
        ax3.fill_between(d5, c5, c5.min() * 0.99, color='#a78bfa', alpha=0.10)
        ax3.scatter([d5[-1]], [latest_p], color='#a78bfa', s=50, zorder=5)
        ax3.set_title(
            f"③ 5년 장기 경제적 해자 성장 궤적 (5-Year: \\${l5:.2f} ~ \\${h5:.2f})",
            color='#f8fafc', fontsize=11, fontweight='bold', pad=8, loc='left'
        )
        ax3.grid(True, color='#334155', linestyle=':', alpha=0.4)
        ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y/%m'))

        fig.savefig(output_path, dpi=120, bbox_inches='tight', facecolor='#0f172a')
        plt.close(fig)
        return output_path
    except Exception as e:
        print(f"[Chart Error] {e}")
        return None
