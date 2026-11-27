"""
strategy.py - 策略信号模块

职责：基于均线交叉生成每日交易信号。

借鉴点说明：
  - "指标公式单独写函数"：MA5 / MA20 各自封装为独立函数，注明计算方式；
  - 信号的生成只依赖历史数据（shift 取昨日值），不含未来函数。

信号约定：
  1 = 买入, -1 = 卖出, 0 = 持有/空仓
"""

import pandas as pd


def ma5(close: pd.Series) -> pd.Series:
    """
    5 日均线 MA5。

    计算方式：MA5[t] = (close[t-4] + close[t-3] + close[t-2] + close[t-1] + close[t]) / 5
    即最近 5 个交易日收盘价的算术平均；前 4 个交易日因数据不足结果为 NaN。
    用 pandas rolling(5).mean() 实现。
    """
    return close.rolling(window=5, min_periods=5).mean()


def ma20(close: pd.Series) -> pd.Series:
    """
    20 日均线 MA20。

    计算方式：MA20[t] = (close[t-19] + ... + close[t]) / 20
    即最近 20 个交易日收盘价的算术平均；前 19 个交易日结果为 NaN。
    用 pandas rolling(20).mean() 实现。
    该均线同时充当"20 日预热期"的信号来源——MA20 首次有值恰好在第 20 个交易日。
    """
    return close.rolling(window=20, min_periods=20).mean()


def generate_signals(df: pd.DataFrame) -> pd.Series:
    """
    生成每日交易信号（返回与 df 等长、索引一致的 Series，名为 signal）。

    买入条件（signal = 1）：
      1) MA5 上穿 MA20：昨日 MA5 <= MA20 且 今日 MA5 > MA20
      2) 且今日 MA20 > 昨日 MA20（趋势向上过滤）

    卖出条件（signal = -1）：
      MA5 下穿 MA20：昨日 MA5 >= MA20 且 今日 MA5 < MA20

    其余情况 signal = 0（持有/空仓观望）。

    参数:
      df: 至少包含 'close' 列的日线 DataFrame
    返回:
      Series, 值为 1 / -1 / 0
    """
    close = df["close"]
    m5 = ma5(close)
    m20 = ma20(close)

    # 上穿：今日金叉 且 昨日不在金叉状态
    cross_up = (m5 > m20) & (m5.shift(1) <= m20.shift(1))
    # 下穿：今日死叉 且 昨日不在死叉状态
    cross_down = (m5 < m20) & (m5.shift(1) >= m20.shift(1))

    # 趋势过滤：MA20 今日严格大于昨日
    ma20_rising = m20 > m20.shift(1)

    signals = pd.Series(0, index=df.index, dtype=int, name="signal")
    signals[cross_up & ma20_rising] = 1
    signals[cross_down] = -1

    return signals


if __name__ == "__main__":
    from data_loader import load_510300

    df = load_510300()
    sig = generate_signals(df)
    print(f"总交易日: {len(df)}")
    print(f"买入信号: {(sig == 1).sum()} 次, 卖出信号: {(sig == -1).sum()} 次")
    print(sig[sig != 0].head(10).to_string())
