"""
data_loader.py - 数据接入模块

职责：用 akshare 拉取 510300（沪深300ETF）与 000300（沪深300指数）的日线数据，
      统一字段命名后缓存为 CSV，避免每次运行重复联网拉取。

数据区间：2018-01-01 ~ 2026-10-31
输出文件：data/510300.csv、data/000300.csv
"""

import os
import akshare as ak
import pandas as pd

# ---------- 全局配置 ----------
START_DATE = "20180101"          # akshare 接口要求 YYYYMMDD 格式
END_DATE = "20261031"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# akshare 返回的中文列名 -> 统一英文列名
COLUMN_MAP = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
}


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """
    统一数据格式：
      1. 重命名列名为英文
      2. date 转为 datetime 类型
      3. 按日期升序排列、重置索引
      4. 只保留回测需要的列
    """
    df = df.rename(columns=COLUMN_MAP).copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    keep = ["date", "open", "high", "low", "close", "volume"]
    return df[[c for c in keep if c in df.columns]]


def load_510300(force: bool = False) -> pd.DataFrame:
    """
    拉取 510300 沪深300ETF 日线（前复权）。

    akshare 接口：fund_etf_hist_em
      字段：日期 开盘 收盘 最高 最低 成交量 成交额 振幅 涨跌幅 涨跌额 换手率
    参数 adjust="qfq" 表示前复权，消除分红/拆分造成的价格跳变。

    若本地 CSV 已存在且 force=False，直接读缓存。
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    cache_path = os.path.join(DATA_DIR, "510300.csv")

    if os.path.exists(cache_path) and not force:
        return pd.read_csv(cache_path, parse_dates=["date"])

    try:
        raw = ak.fund_etf_hist_em(
            symbol="510300",
            period="daily",
            start_date=START_DATE,
            end_date=END_DATE,
            adjust="qfq",
        )
        df = _normalize(raw)
    except Exception:
        # 备用源：新浪 ETF 日线（不复权，仅作限流时的降级方案）
        raw = ak.fund_etf_hist_sina(symbol="sh510300")
        df = _normalize(raw)
        df = df[(df["date"] >= "2018-01-01") & (df["date"] <= "2026-10-31")].reset_index(drop=True)
    df.to_csv(cache_path, index=False, encoding="utf-8-sig")
    return df


def load_000300(force: bool = False) -> pd.DataFrame:
    """
    拉取 000300 沪深300指数 日线（作为基准）。

    akshare 接口：东方财富指数行情。
      注意：该接口在 akshare 1.20.44 由 index_zh_a_hist 更名为 index_zh_hist_em，
      这里做版本兼容——优先用新名，旧版本自动回退；字段与 ETF 接口一致，指数不涉及复权。

    若本地 CSV 已存在且 force=False，直接读缓存。
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    cache_path = os.path.join(DATA_DIR, "000300.csv")

    if os.path.exists(cache_path) and not force:
        return pd.read_csv(cache_path, parse_dates=["date"])

    # 主源：东方财富。但该源偶发限流，失败时回退到新浪源。
    raw = None
    try:
        kwargs = dict(symbol="000300", period="daily",
                      start_date=START_DATE, end_date=END_DATE)
        if hasattr(ak, "index_zh_hist_em"):
            raw = ak.index_zh_hist_em(**kwargs)      # akshare >= 1.20.44
        else:
            raw = ak.index_zh_a_hist(**kwargs)       # 旧版本
        df = _normalize(raw)
    except Exception:
        # 备用源：新浪（返回全历史，需自行按日期区间裁剪）
        raw = ak.index_zh_daily_sina(symbol="sh000300")
        df = _normalize(raw)
        df = df[(df["date"] >= "2018-01-01") & (df["date"] <= "2026-10-31")].reset_index(drop=True)

    df.to_csv(cache_path, index=False, encoding="utf-8-sig")
    return df


def load_all(force: bool = False):
    """一次性返回 (策略标的 ETF 数据, 基准指数数据)。"""
    return load_510300(force), load_000300(force)


if __name__ == "__main__":
    etf, bench = load_all(force=True)
    print(f"510300: {len(etf)} 行, {etf['date'].min().date()} ~ {etf['date'].max().date()}")
    print(f"000300: {len(bench)} 行, {bench['date'].min().date()} ~ {bench['date'].max().date()}")
    print("510300 前 3 行：")
    print(etf.head(3).to_string(index=False))
