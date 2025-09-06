# app.py
# -*- coding: utf-8 -*-

import streamlit as st
import pandas as pd
import numpy as np
import os, io, json, shutil, re
from datetime import datetime
from pathlib import Path

# ============== 页面基本设置 ==============
st.set_page_config(page_title="Profit Calculator — Multi-Country", layout="wide")
st.title("💰 多国家利润计算器（合并表头自动清理 + 历史费率管理 + 可视化）")

# ============== 文件与配置路径 ==============
BASE_DIR = Path(".")
UPLOAD_DIR = BASE_DIR / "uploads"
META_FILE = BASE_DIR / "file_metadata.csv"
CONFIG_FILE = BASE_DIR / "platform_fees.csv"
CONFIG_HISTORY_DIR = BASE_DIR / "config_history"
RATES_FILE = BASE_DIR / "exchange_rates.json"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
if not META_FILE.exists():
    pd.DataFrame(columns=["country", "filename", "filepath", "upload_date"]).to_csv(META_FILE, index=False)

# ============== 国家与汇率默认 ==============
COUNTRY_CURRENCY = {
    "Thailand": "THB",
    "Malaysia": "MYR",
    "Vietnam": "VND",
    "Philippines": "PHP",
    "Indonesia": "IDR",
}

DEFAULT_RATES = {"THB": 7.8, "MYR": 1.0, "VND": 5400.0, "PHP": 12.0, "IDR": 3400.0}

# ============== 平台费率配置初始化（示例文件） ==============
def ensure_config_file():
    if not CONFIG_FILE.exists():
        demo = pd.DataFrame([
            ["Thailand","Shopee","基础佣金",9,"示例"],
            ["Thailand","Lazada","Full（FS+LazCoin）",13,"示例"],
            ["Malaysia","Shopee","基础佣金",8,"示例"],
        ], columns=["country","platform","scenario","fee_pct","remark"])
        demo.to_csv(CONFIG_FILE, index=False)

ensure_config_file()

def load_fee_config():
    try:
        return pd.read_csv(CONFIG_FILE)
    except Exception:
        return pd.DataFrame(columns=["country","platform","scenario","fee_pct","remark"])

def save_fee_config(df: pd.DataFrame, keep_history=True):
    df.to_csv(CONFIG_FILE, index=False)
    if keep_history:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy(CONFIG_FILE, CONFIG_HISTORY_DIR / f"platform_fees_{ts}.csv")

fee_df_global = load_fee_config()

# ============== 辅助函数 ==============
def clean_column_names_from_multiindex(cols):
    new_cols = []
    for col in cols:
        if isinstance(col, tuple) or isinstance(col, list):
            parts = [str(x).strip() for x in col if x is not None and "Unnamed" not in str(x)]
            joined = " ".join([p for p in parts if p and p.lower() != 'nan']).strip()
            new_cols.append(joined if joined else None)
        else:
            c = str(col)
            new_cols.append(c if c and "Unnamed" not in c and c.lower() != 'nan' else None)
    ser = pd.Series(new_cols)
    if ser.isna().all():
        return [f"Column_{i}" for i in range(len(new_cols))]
    ser = ser.fillna(method="ffill").fillna(method="bfill")
    return ser.tolist()

def try_read_and_clean(path, header_idx):
    p = Path(path)
    df = None
    if p.suffix.lower() in [".xlsx", ".xls"]:
        try:
            df_try = pd.read_excel(path, header=header_idx)
            cols = [str(c) for c in df_try.columns]
            unnamed_count = sum(1 for c in cols if "Unnamed" in str(c) or str(c).strip() == "nan" or str(c).strip() == "")
            if unnamed_count <= 0.3 * len(cols):
                clean_cols = []
                for i, c in enumerate(df_try.columns):
                    if c is None or str(c).startswith("Unnamed") or str(c).strip() == "":
                        clean_cols.append(None)
                    else:
                        clean_cols.append(str(c).strip())
                clean_cols = pd.Series(clean_cols).fillna(method="ffill").fillna(method="bfill")
                df_try.columns = clean_cols
                return df_try
            else:
                try:
                    df2 = pd.read_excel(path, header=[0, header_idx])
                    new_cols = clean_column_names_from_multiindex(df2.columns.values)
                    df2.columns = new_cols
                    return df2
                except Exception:
                    cols = [c if not str(c).startswith("Unnamed") else None for c in df_try.columns]
                    cols = pd.Series(cols).fillna(method="ffill").fillna(method="bfill")
                    df_try.columns = cols
                    return df_try
        except Exception:
            df = pd.read_excel(path, header=None)
            df.columns = [f"Column_{i}" for i in range(len(df.columns))]
            return df
    else:
        try:
            df_try = pd.read_csv(path, header=header_idx)
            cols = [str(c) for c in df_try.columns]
            unnamed_count = sum(1 for c in cols if "Unnamed" in str(c) or str(c).strip() == "nan" or str(c).strip() == "")
            if unnamed_count <= 0.3 * len(cols):
                clean_cols = []
                for i, c in enumerate(df_try.columns):
                    if c is None or str(c).startswith("Unnamed") or str(c).strip() == "":
                        clean_cols.append(None)
                    else:
                        clean_cols.append(str(c).strip())
                clean_cols = pd.Series(clean_cols).fillna(method="ffill").fillna(method="bfill")
                df_try.columns = clean_cols
                return df_try
            else:
                df = pd.read_csv(path, header=None)
                df.columns = [f"Column_{i}" for i in range(len(df.columns))]
                return df
        except Exception:
            df = pd.read_csv(path, header=None)
            df.columns = [f"Column_{i}" for i in range(len(df.columns))]
            return df

def split_price_cell(v):
    if pd.isna(v):
        return []
    s = str(v)
    s = re.sub(r"[\/\|;，\s]+", ",", s)
    parts = [p.strip() for p in s.split(",") if p.strip() != "" and p.strip().lower() not in ["nan","none"]]
    out = []
    for p in parts:
        try:
            out.append(float(p))
        except:
            continue
    return out

def style_results(df_results):
    def row_style(row):
        if pd.isna(row["利润 (MYR)"]):
            return [""] * len(row)
        if row["利润 (MYR)"] < 0:
            return ["background-color:#ffd6d6"] * len(row)
        if row.get("来源", "") == "Promotion":
            return ["background-color:#e6ffe6"] * len(row)
        return [""] * len(row)

    sty = df_results.style.apply(lambda r: row_style(r), axis=1)
    if "利润 (MYR)" in df_results.columns:
        sty = sty.format({"利润 (MYR)": "RM {0:,.2f}", "个人抽成 (MYR)": "RM {0:,.2f}"}, na_rep="-")
    return sty

# ============== 侧边栏：国家选择 & 文件上传 ==============
# ... （中间内容完全保留，不改动） ...

            # 可视化利润对比
            st.subheader("📈 产品利润对比（MYR）")
            try:
                import altair as alt
                chart_data = display_df.groupby(["产品名称", "来源", f"卖价 ({COUNTRY_CURRENCY[country]})"])["利润 (MYR)"].sum().reset_index()
                chart = (
                    alt.Chart(chart_data)
                    .mark_bar()
                    .encode(
                        x=alt.X("产品名称:N", sort="-y"),
                        y=alt.Y("利润 (MYR):Q"),
                        color=alt.Color("来源:N"),
                        tooltip=list(chart_data.columns)
                    )
                    .properties(height=400)
                )
                st.altair_chart(chart, use_container_width=True)

                # 🔹 在这里加红/绿说明
                st.markdown(
                    """
                    <div style="margin-top:10px; font-size:14px;">
                        <span style="background-color:#ffd6d6; padding:3px 8px; border-radius:5px;">红色：亏损</span>
                        &nbsp;&nbsp;
                        <span style="background-color:#e6ffe6; padding:3px 8px; border-radius:5px;">绿色：促销</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            except Exception:
                st.bar_chart(display_df.set_index("产品名称")["利润 (MYR)"])

# ============== 结束 ==============
st.caption("说明：本工具只抓取公开信息（示范），不会登录任何平台。费率/汇率请按实际业务情况确认。")
