"""
backtest.py - 精简回测内核

只保留三个借鉴自 backtrader 的设计点：
  1) T+1 开盘成交：T 日信号暂存为 pending，T+1 日以开盘价撮合（杜绝未来函数）；
  2) 20 日预热期：前 20 个交易日不交易，对齐 MA20 的最小周期（backtrader 的 minperiod/prenext）；
  3) 可插拔指标字典输出：指标函数以注册表形式插拔，结果以 dict 返回（借鉴 analyzer 架构）。

其余 backtrader 特性（订单类型、佣金滑点、多数据源、元类、观察者、analyzer 体系等）一律不实现。

返回结构：{"nav": pd.Series, "trades": list[dict], "metrics": dict}
"""

import numpy as np
import pandas as pd

# 借鉴点 2：预热期长度，与 MA20 的最小周期一致
WARMUP = 20

# 年化系数：A 股一年约 252 个交易日
TRADING_DAYS = 252


# ---------------------------------------------------------------------------
# 借鉴点 3：可插拔指标注册表
# ---------------------------------------------------------------------------
# 每个指标函数签名统一为 func(nav, trades, df) -> float，用装饰器注册进字典。
# 需要新增指标时，只需再写一个函数并加 @register_metric("名字") 即可，无需改动内核。
METRIC_REGISTRY = {}


def register_metric(name):
    """把指标函数注册进 METRIC_REGISTRY 的装饰器工厂。"""
    def deco(func):
        METRIC_REGISTRY[name] = func
        return func
    return deco


@register_metric("cumulative_return")
def _cumulative_return(nav, trades, df):
    """累计收益率 = 期末净值 / 期初净值 - 1"""
    return nav.iloc[-1] / nav.iloc[0] - 1.0


@register_metric("annual_return")
def _annual_return(nav, trades, df):
    """年化收益率 = (期末净值 / 期初净值)^(252 / 总交易日数) - 1"""
    n = len(nav)
    return (nav.iloc[-1] / nav.iloc[0]) ** (TRADING_DAYS / n) - 1.0


@register_metric("max_drawdown")
def _max_drawdown(nav, trades, df):
    """最大回撤 = max[(历史峰值 - 当前净值) / 历史峰值]，返回正数表示回撤幅度。"""
    peak = nav.cummax()
    drawdown = (peak - nav) / peak
    return drawdown.max()


@register_metric("sharpe_ratio")
def _sharpe_ratio(nav, trades, df):
    """夏普比率 = 日均收益 / 日收益标准差 × sqrt(252)，无风险利率按 0 处理。"""
    rets = nav.pct_change().dropna()
    std = rets.std()
    if std == 0 or np.isnan(std):
        return 0.0
    return rets.mean() / std * np.sqrt(TRADING_DAYS)


def compute_metrics(nav, trades, df):
    """遍历注册表计算全部指标，返回 {指标名: 数值} 字典。"""
    return {name: func(nav, trades, df) for name, func in METRIC_REGISTRY.items()}


# ---------------------------------------------------------------------------
# 回测内核
# ---------------------------------------------------------------------------
def run_backtest(df, signals, init_cash=1e6, warmup=WARMUP):
    """
    逐日回测。

    参数:
      df:       含 date / open / close 列的日线 DataFrame
      signals:  与 df 等长的每日信号 Series（1 买入 / -1 卖出 / 0 持有）
      init_cash: 初始资金，默认 100 万
      warmup:    预热期长度，默认 WARMUP=20。

                 注意：预热期的语义是“MA20 数据不足时不交易”。当 signals 是在
                 完整历史上预计算后再按区间切片（如样本外回测）时，段首的 MA20
                 早已有效，此时应传 warmup=0，否则会对同一段历史“二次预热”，
                 白白吃掉段首若干笔真实交易，导致分段成交笔数与全样本对不上。

    返回:
      {
        "nav":     pd.Series, 每日收盘净值（绝对值）
        "trades":  list[dict], 每笔成交记录
        "metrics": dict, 可插拔指标字典
      }
    """
    dates = df["date"].reset_index(drop=True)
    opens = df["open"].reset_index(drop=True)
    closes = df["close"].reset_index(drop=True)
    sig = signals.reset_index(drop=True)
    n = len(df)

    cash = float(init_cash)   # 可用现金
    position = 0.0            # 持有份额（全仓/空仓二态）
    pending = 0               # 借鉴点 1：T 日信号暂存，供 T+1 成交
    trades = []
    nav_values = []

    for i in range(n):
        # 阶段 A：撮合昨日挂单 —— 用【今日开盘价】成交，这是 T+1 的核心
        if pending != 0 and i >= warmup:
            price = opens.iloc[i]
            if pending == 1 and position == 0.0 and price > 0:
                # 买入：现金全部换成份额（简化：不取整手、不计佣金）
                shares = cash / price
                position = shares
                cash = 0.0
                trades.append({
                    "date": dates.iloc[i],
                    "side": "BUY",
                    "price": price,
                    "shares": shares,
                    "cash_after": cash,
                })
            elif pending == -1 and position > 0.0:
                # 卖出：份额全部换回现金；shares 记为负数表示卖出方向
                sold_shares = position
                cash = position * price
                position = 0.0
                trades.append({
                    "date": dates.iloc[i],
                    "side": "SELL",
                    "price": price,
                    "shares": -sold_shares,
                    "cash_after": cash,
                })
            pending = 0

        # 阶段 B：读取今日信号，记为 pending 供【明日】成交
        # 借鉴点 2：i < warmup 时完全不产生交易意图
        if i >= warmup:
            s = int(sig.iloc[i])
            if s in (1, -1):
                pending = s

        # 阶段 C：按今日收盘价估值
        nav_values.append(cash + position * closes.iloc[i])

    nav = pd.Series(nav_values, index=dates, name="nav")
    metrics = compute_metrics(nav, trades, df)

    return {"nav": nav, "trades": trades, "metrics": metrics}


if __name__ == "__main__":
    from data_loader import load_510300
    from strategy import generate_signals

    df = load_510300()
    signals = generate_signals(df)
    result = run_backtest(df, signals)
    print("指标：")
    for k, v in result["metrics"].items():
        print(f"  {k}: {v:.4f}")
    print(f"成交笔数: {len(result['trades'])}")
