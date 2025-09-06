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
st.title("💰 多国家利润计算器（合并表头清理 + 历史费率管理 + 可视化）")

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

# ============== 平台费率配置初始化 ==============
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
    ser = ser.fillna(method="ffill").fillna(method="bfill")
    return ser.tolist()

def try_read_and_clean(path, header_idx):
    p = Path(path)
    if p.suffix.lower() in [".xlsx", ".xls"]:
        try:
            df_try = pd.read_excel(path, header=header_idx)
        except:
            df_try = pd.read_excel(path, header=None)
            df_try.columns = [f"Column_{i}" for i in range(len(df_try.columns))]
            return df_try
    else:
        try:
            df_try = pd.read_csv(path, header=header_idx)
        except:
            df_try = pd.read_csv(path, header=None)
            df_try.columns = [f"Column_{i}" for i in range(len(df_try.columns))]
            return df_try
    # 兜底清理 Unnamed
    df_try.columns = [str(c).strip() for c in df_try.columns]
    df_try = df_try.loc[:, ~df_try.columns.str.contains("^Unnamed", case=False)]
    return df_try

def split_price_cell(v):
    if pd.isna(v): return []
    s = str(v)
    s = re.sub(r"[\/\|;，\s]+", ",", s)
    parts = [p.strip() for p in s.split(",") if p.strip() != ""]
    out = []
    for p in parts:
        try: out.append(float(p))
        except: continue
    return out

def style_results(df_results, high_profit_threshold):
    def row_style(row):
        if pd.isna(row["利润 (MYR)"]):
            return [""] * len(row)
        if row["利润 (MYR)"] < 0:
            return ["background-color:#ffd6d6"] * len(row)  # 红
        if row["利润 (MYR)"] >= high_profit_threshold:
            return ["background-color:#fff7cc"] * len(row)  # 黄
        if row.get("来源", "") == "Promotion":
            return ["background-color:#e6ffe6"] * len(row)  # 绿
        return [""] * len(row)

    sty = df_results.style.apply(lambda r: row_style(r), axis=1)
    sty = sty.format(precision=2, na_rep="-")
    return sty

# ============== 侧边栏：国家选择 & 上传 ==============
st.sidebar.header("🌍 国家选择")
countries = list(COUNTRY_CURRENCY.keys())
country = st.sidebar.selectbox("选择国家", countries)

st.sidebar.header("📤 上传价钱表")
uploaded_file = st.sidebar.file_uploader(f"上传 {country} 的 Excel/CSV", type=["xlsx","xls","csv"])
if uploaded_file:
    save_dir = UPLOAD_DIR / country
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / uploaded_file.name
    with open(save_path, "wb") as f: f.write(uploaded_file.getbuffer())

    meta_df = pd.read_csv(META_FILE)
    meta_df = meta_df[~((meta_df["country"] == country) & (meta_df["filename"] == uploaded_file.name))]
    new_record = pd.DataFrame([{
        "country": country,"filename": uploaded_file.name,
        "filepath": str(save_path),"upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }])
    meta_df = pd.concat([meta_df,new_record], ignore_index=True)
    meta_df.to_csv(META_FILE, index=False)
    st.sidebar.success("✅ 文件已保存")

meta_df = pd.read_csv(META_FILE)
country_files = meta_df[meta_df["country"] == country].sort_values("upload_date", ascending=False)

selected_file = None
if not country_files.empty:
    st.sidebar.header("📁 已上传文件")
    selected_file = st.sidebar.selectbox("选择文件", country_files["filename"].tolist())

# ============== 侧边栏：表头 & 汇率 & 阈值 ==============
st.sidebar.header("📑 表头设置")
header_row = st.sidebar.number_input("表头所在行（从1开始）", min_value=1, max_value=10, value=2)

st.sidebar.header("💱 汇率设置")
rates = json.loads(RATES_FILE.read_text()) if RATES_FILE.exists() else DEFAULT_RATES
for cur in COUNTRY_CURRENCY.values():
    rates[cur] = st.sidebar.number_input(f"1 {cur} = ? MYR", value=float(rates.get(cur, DEFAULT_RATES[cur])), step=0.01)
if st.sidebar.button("💾 保存汇率"):
    RATES_FILE.write_text(json.dumps(rates, ensure_ascii=False, indent=2))
    st.sidebar.success("✅ 汇率已保存")

st.sidebar.header("🎯 高利润阈值设置")
high_profit_threshold = st.sidebar.number_input("高利润阈值 (MYR)", value=50.0, step=1.0)

# ============== 平台费率对比 ==============
st.subheader("🌍 各国家平台费率对比（可筛选）")
fee_df = load_fee_config()
if not fee_df.empty:
    sum_df = (
        fee_df.groupby(["country","platform"])
        .agg(最低费率=("fee_pct","min"),
             最高费率=("fee_pct","max"),
             平均费率=("fee_pct","mean"),
             方案数量=("fee_pct","count"))
        .reset_index()
    )
    sum_df = sum_df.round(2)
    st.dataframe(sum_df, use_container_width=True)

# ============== 读取文件并计算利润 ==============
if selected_file:
    fpath = country_files[country_files["filename"] == selected_file].iloc[0]["filepath"]
    df = try_read_and_clean(fpath, header_row-1)
    st.subheader("📋 数据预览")
    st.dataframe(df.head(), use_container_width=True)

    # 映射
    st.sidebar.header("🧩 字段映射")
    name_col = st.sidebar.selectbox("产品名称列", list(df.columns))
    cost_col = st.sidebar.selectbox("成本列", list(df.columns))
    price_cols = st.sidebar.multiselect("卖价列", list(df.columns))

    # 平台费率
    st.sidebar.header("🏷️ 抽成设置")
    platform_fee_pct = st.sidebar.number_input("平台费率（%）", value=5.0, step=0.1)
    personal_commission_pct = st.sidebar.number_input("个人抽成（%）", value=0.0, step=0.1)

    # 计算
    records = []
    conv = float(rates[COUNTRY_CURRENCY[country]])
    for _, row in df.iterrows():
        product = str(row.get(name_col, "")).strip()
        cost = pd.to_numeric(row.get(cost_col), errors="coerce")
        if pd.isna(cost): continue
        for col in price_cols:
            for price in split_price_cell(row.get(col)):
                fee = price * (platform_fee_pct/100)
                profit_local = price - cost - fee
                profit_myr = profit_local / conv
                records.append({
                    "产品名称": product,
                    "利润 (MYR)": round(profit_myr,2),
                    "利润率 %": round((profit_local/price*100) if price>0 else 0,2),
                })
    result_df = pd.DataFrame(records)

    st.subheader("📊 计算结果")
    sty = style_results(result_df, high_profit_threshold)
    st.write(sty, unsafe_allow_html=True)

    st.markdown("**颜色说明：** 🟥 亏损 / 🟩 Promotion / 🟨 高利润")

