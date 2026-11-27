"""
report.py - 结果输出与可视化模块

职责：
  1) 绘制策略与基准的归一化净值曲线（均从 1.0 起算）
  2) 在曲线上标注买入/卖点
  3) 输出指标表（策略 vs 基准）

不引入 backtrader 的绘图体系，直接用 matplotlib。
"""

import os
import matplotlib
matplotlib.use("Agg")  # 无 GUI 环境下也能出图
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# 中文字体设置（Windows 用微软雅黑；其他系统可按需调整）
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def normalize(nav: pd.Series) -> pd.Series:
    """归一化净值：除以首个值，使曲线从 1.0 起算。"""
    return nav / nav.iloc[0]


def benchmark_nav(bench_df: pd.DataFrame, init_cash: float = 1e6) -> pd.Series:
    """
    基准净值：买入并持有沪深300指数。
    计算方式：份额 = init_cash / 首日收盘价，每日净值 = 份额 × 当日收盘价。
    这样基准与策略使用相同初始资金、可比。
    """
    shares = init_cash / bench_df["close"].iloc[0]
    nav = bench_df["close"] * shares
    nav.index = bench_df["date"]
    nav.name = "benchmark"
    return nav


def plot_nav(strategy_nav, bench_nav, trades, save_path=None):
    """
    绘制归一化净值曲线并标注买卖点。

    参数:
      strategy_nav: 策略每日净值 Series（index 为 date）
      bench_nav:    基准每日净值 Series
      trades:       成交记录 list[dict]，含 date / side / price
      save_path:    图片保存路径；None 则显示
    """
    s = normalize(strategy_nav)
    b = normalize(bench_nav)

    fig, ax = plt.subplots(figsize=(13, 6))
    ax.plot(s.index, s.values, label="策略（MA5/MA20）", color="#d62728", linewidth=1.8, zorder=3)
    ax.plot(b.index, b.values, label="基准（沪深300）", color="#1f77b4", linewidth=1.5, alpha=0.85, zorder=2)

    # 按成交记录标注买卖点：买入用红三角向上，卖出用绿三角向下
    buys = [t for t in trades if t["side"] == "BUY"]
    sells = [t for t in trades if t["side"] == "SELL"]
    if buys:
        bx = [t["date"] for t in buys]
        by = [s.loc[d] for d in bx]
        ax.scatter(bx, by, marker="^", color="#d62728", s=90, zorder=5,
                   edgecolors="white", linewidths=0.6, label=f"买入点 ({len(buys)})")
    if sells:
        sx = [t["date"] for t in sells]
        sy = [s.loc[d] for d in sx]
        ax.scatter(sx, sy, marker="v", color="#2ca02c", s=90, zorder=5,
                   edgecolors="white", linewidths=0.6, label=f"卖出点 ({len(sells)})")

    ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
    ax.set_title("策略 vs 基准 归一化净值曲线（起点 = 1.0）", fontsize=14)
    ax.set_xlabel("日期")
    ax.set_ylabel("归一化净值")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.25)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate()
    fig.tight_layout()

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        fig.savefig(save_path, dpi=150)
        print(f"净值曲线已保存: {save_path}")
    else:
        plt.show()
    plt.close(fig)


def build_metrics_table(strategy_metrics, bench_metrics):
    """
    构造策略与基准的指标对比表。
    注：夏普比率对买入持有基准同样按日收益计算，口径与策略一致。
    """
    rows = []
    for name in ["cumulative_return", "annual_return", "max_drawdown", "sharpe_ratio"]:
        rows.append({
            "指标": name,
            "策略": strategy_metrics.get(name),
            "基准": bench_metrics.get(name),
        })
    return pd.DataFrame(rows).set_index("指标")


# CSV 展示格式：中文指标名 + 百分比（4 位小数）
CN_METRIC_NAME = {
    "cumulative_return": "累计收益率",
    "annual_return": "年化收益率",
    "max_drawdown": "最大回撤",
    "sharpe_ratio": "夏普比率",
}
PCT_METRICS = {"累计收益率", "年化收益率", "最大回撤"}


def format_table_for_csv(table: pd.DataFrame) -> pd.DataFrame:
    """
    将内部指标表转换为交付用的展示格式：
      1) 英文指标名替换为中文
      2) 收益率类指标乘 100 并加 '%'，所有数值统一保留 4 位小数
    仅用于写 CSV，不影响控制台打印与绘图。
    """
    cn_index = [CN_METRIC_NAME.get(i, i) for i in table.index]
    # 用字符串重新构造，避免 pandas 3.x 不允许把 str 写入 float 列
    rows = []
    for pos, (_, row) in enumerate(table.iterrows()):
        cn = cn_index[pos]
        rows.append([
            f"{row[col] * 100:.4f}%" if cn in PCT_METRICS else f"{row[col]:.4f}"
            for col in table.columns
        ])
    result = pd.DataFrame(rows, index=cn_index, columns=table.columns)
    result.index.name = table.index.name  # 保留"指标"列名，维持原表头结构
    return result


def print_report(table: pd.DataFrame, trades, title="回测绩效对比"):
    """在控制台打印指标表与交易概览。"""
    cn_name = {
        "cumulative_return": "累计收益率",
        "annual_return": "年化收益率",
        "max_drawdown": "最大回撤",
        "sharpe_ratio": "夏普比率",
    }
    print("\n" + "=" * 60)
    print(f"{title:^50}")
    print("=" * 60)
    print(f"{'指标':<16}{'策略':>14}{'基准':>14}")
    print("-" * 60)
    for idx, row in table.iterrows():
        print(f"{cn_name.get(idx, idx):<14}{row['策略']:>14.4f}{row['基准']:>14.4f}")
    print("-" * 60)
    print(f"成交笔数: {len(trades)}")
    if trades:
        print(f"首笔: {trades[0]['date'].date()} {trades[0]['side']} @ {trades[0]['price']:.4f}")
        print(f"末笔: {trades[-1]['date'].date()} {trades[-1]['side']} @ {trades[-1]['price']:.4f}")
    print("=" * 60)


def slice_signals_by_date(full_signals, full_dates, segment_dates):
    """
    从【全样本一次性算好】的信号中，按日期切片出某一段的信号。

    为什么不在每段内重新 generate_signals？
      因为 MA5/MA20 是滚动指标，段首的值依赖段前 19 根 K 线。若段内重算，
      段首会出现 20 根 NaN（二次预热），白白丢掉段初真实交易。
      全样本算一次再切片，才能让样本外起点继承完整的历史均线。
    """
    start, end = segment_dates.iloc[0], segment_dates.iloc[-1]
    mask = (full_dates >= start) & (full_dates <= end)
    return full_signals[mask].reset_index(drop=True)


def analyze_period(etf, bench, label, signals, warmup):
    """
    对给定区间做回测并返回结果。
    每段净值均从 1.0 起算，指标口径与全样本一致、可直接对比。

    参数:
      signals: 已在全样本上预计算并按本段日期切片的信号
      warmup:  预热期长度。全样本/样本内用 20；样本外用 0
               （段首均线已由全样本历史算好，无需二次预热）
    """
    from backtest import run_backtest, compute_metrics

    result = run_backtest(etf, signals, warmup=warmup)
    bench_nav = benchmark_nav(bench)
    bench_metrics = compute_metrics(bench_nav, [], bench)
    table = build_metrics_table(result["metrics"], bench_metrics)
    print_report(table, result["trades"], title=label)
    return result, bench_nav, table


if __name__ == "__main__":
    from data_loader import load_all
    from strategy import generate_signals
    from backtest import WARMUP

    etf, bench = load_all()
    # 关键：信号只在完整历史上计算一次，分段时按日期切片，避免二次预热
    full_signals = generate_signals(etf)

    # ---- 1) 全样本 ----
    result, bench_nav, table = analyze_period(
        etf, bench, "全样本回测绩效对比 2018-01-01 ~ 2026-10-31",
        full_signals, warmup=WARMUP,
    )

    # ---- 2) 样本内 / 样本外 分段 ----
    in_start, in_end = "2018-01-01", "2022-12-31"
    out_start, out_end = "2023-01-01", "2026-10-31"

    etf_in = etf[(etf["date"] >= in_start) & (etf["date"] <= in_end)].reset_index(drop=True)
    bench_in = bench[(bench["date"] >= in_start) & (bench["date"] <= in_end)].reset_index(drop=True)
    sig_in = slice_signals_by_date(full_signals, etf["date"], etf_in["date"])
    res_in, _, table_in = analyze_period(
        etf_in, bench_in, f"样本内  {in_start} ~ {in_end}", sig_in, warmup=WARMUP,
    )

    etf_out = etf[(etf["date"] >= out_start) & (etf["date"] <= out_end)].reset_index(drop=True)
    bench_out = bench[(bench["date"] >= out_start) & (etf["date"] <= out_end)].reset_index(drop=True)
    sig_out = slice_signals_by_date(full_signals, etf["date"], etf_out["date"])
    # 样本外段首均线已含 2022 年历史，warmup=0，不再二次预热
    res_out, _, table_out = analyze_period(
        etf_out, bench_out, f"样本外  {out_start} ~ {out_end}", sig_out, warmup=0,
    )

    # ---- 2b) 成交笔数一致性校验：全样本 == 样本内 + 样本外 ----
    n_all, n_in, n_out = len(result["trades"]), len(res_in["trades"]), len(res_out["trades"])
    print("\n" + "-" * 60)
    print(f"成交笔数一致性校验: 全样本 {n_all} = 样本内 {n_in} + 样本外 {n_out} -> "
          f"{'通过' if n_all == n_in + n_out else '不通过'}")
    print("-" * 60)

    # ---- 3) 输出 ----
    save_path = os.path.join(OUTPUT_DIR, "nav_curve.png")
    plot_nav(result["nav"], bench_nav, result["trades"], save_path=save_path)
    format_table_for_csv(table).to_csv(
        os.path.join(OUTPUT_DIR, "metrics.csv"), encoding="utf-8-sig"
    )

    # 分段时间表单独落盘，便于报告引用（同样转为展示格式）
    segments = pd.concat(
        {
            "样本内": format_table_for_csv(table_in),
            "样本外": format_table_for_csv(table_out),
        },
        axis=1,
    )
    segments.to_csv(os.path.join(OUTPUT_DIR, "metrics_segments.csv"), encoding="utf-8-sig")
