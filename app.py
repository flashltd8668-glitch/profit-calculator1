# app.py
# -*- coding: utf-8 -*-

import streamlit as st
import pandas as pd
import numpy as np
import os, io, json, shutil, re
from datetime import datetime
from pathlib import Path

# ============== 基本设置 ==============
st.set_page_config(page_title="Profit Calculator — Multi-Country", layout="wide")
st.title("💰 多国家利润计算器（安全版｜自动促销优先｜费率配置管理）")

# ============== 文件/目录初始化 ==============
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

COUNTRY_CURRENCY = {
    "Thailand": "THB",
    "Malaysia": "MYR",
    "Vietnam": "VND",
    "Philippines": "PHP",
    "Indonesia": "IDR",
}

DEFAULT_RATES = {"THB": 7.8,"MYR": 1.0,"VND": 5400.0,"PHP": 12.0,"IDR": 3400.0}

# ============== 上传文件（侧边栏） ==============
st.sidebar.header("📂 上传价钱表")
uploaded_file = st.sidebar.file_uploader("选择Excel/CSV文件", type=["xlsx","xls","csv"])
country = st.sidebar.selectbox("选择国家", list(COUNTRY_CURRENCY.keys()))

if uploaded_file:
    save_path = UPLOAD_DIR / uploaded_file.name
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    meta = pd.read_csv(META_FILE)
    new_entry = {
        "country": country,
        "filename": uploaded_file.name,
        "filepath": str(save_path),
        "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    meta = pd.concat([meta, pd.DataFrame([new_entry])], ignore_index=True)
    meta.to_csv(META_FILE, index=False)
    st.sidebar.success("上传成功 ✅")

# 读取上传记录
country_files = pd.read_csv(META_FILE) if META_FILE.exists() else pd.DataFrame()
selected_file = None
if not country_files.empty:
    st.sidebar.header("📑 已上传文件")
    selected_file = st.sidebar.selectbox("选择文件计算", country_files["filename"].unique())

# ============== 读取文件 ==============
df = None
if selected_file:
    sel_info = country_files[country_files["filename"] == selected_file].iloc[0]
    fpath = Path(sel_info["filepath"])

    # ✅ 修改点 1：表头所在行选择
    st.sidebar.header("📑 表头设置")
    header_row = st.sidebar.number_input("表头所在行（从1开始）", min_value=1, max_value=20, value=2, step=1)
    header_idx = header_row - 1

    if fpath.suffix.lower() in [".xlsx",".xls"]:
        df = pd.read_excel(fpath, header=header_idx)
    else:
        df = pd.read_csv(fpath, header=header_idx)

# ============== 数据预览 & 字段映射 ==============
if df is not None and not df.empty:
    st.subheader("📋 数据预览")
    st.dataframe(df.head(), use_container_width=True)

    # ✅ 修改点 2：智能猜测产品名称列 + 预览
    def guess_name_column(df: pd.DataFrame) -> str | None:
        patterns = [
            r"\b(desc(ription)?|product(\s*name)?|item(\s*name)?|name|title)\b",
            r"(产品|商品|品名|名稱|名称|标题|描述)",
            r"(ชื่อสินค้า|รายละเอียด)",
        ]
        cols = [str(c) for c in df.columns]
        for pat in patterns:
            for c in cols:
                if re.search(pat, c, flags=re.IGNORECASE):
                    return c
        best, best_score = None, -1
        for c in cols:
            s = df[c].dropna()
            if s.empty: continue
            str_ratio = (s.apply(lambda x: isinstance(x,str)).sum()) / len(s)
            uniq_ratio = s.astype(str).nunique() / len(s)
            score = str_ratio*0.6 + uniq_ratio*0.4
            if score > best_score:
                best, best_score = c, score
        return best

    st.sidebar.header("🧩 字段映射")
    name_options = [str(c) for c in df.columns]
    default_name = guess_name_column(df)
    default_idx = name_options.index(default_name) if default_name in name_options else 0
    name_col = st.sidebar.selectbox("产品名称列", name_options, index=default_idx)

    with st.sidebar.expander("🔎 名称列样例预览", expanded=False):
        st.write(df[name_col].head(10))

    # 其它字段
    cost_col = st.sidebar.selectbox("普通成本列（COST）", [None] + list(df.columns),
                                    index=(list(df.columns).index("COST") if "COST" in df.columns else 0))
    promo_cost_col = st.sidebar.selectbox("促销成本列（PROMOTION）", [None] + list(df.columns),
                                          index=(list(df.columns).index("PROMOTION") if "PROMOTION" in df.columns else 0))
    promo_price_col = st.sidebar.selectbox("促销售价列（PROMO SELLING PRICE）", [None] + list(df.columns),
                                           index=(list(df.columns).index("PROMO SELLING PRICE") if "PROMO SELLING PRICE" in df.columns else 0))
    guess_price_cols = [c for c in df.columns if re.search(r"price", str(c), re.I)]
    price_cols = st.sidebar.multiselect("普通卖价列（可多选，支持'199/299'）",
                                        guess_price_cols or list(df.columns),
                                        default=guess_price_cols[:2] if guess_price_cols else [])

    # ============== 计算利润 ==============
    results = []
    for _, row in df.iterrows():
        # ✅ 修改点 3：产品名转字符串
        product = str(row.get(name_col, "")).strip()
        base_cost = row.get(cost_col, np.nan) if cost_col else np.nan
        promo_cost = row.get(promo_cost_col, np.nan) if promo_cost_col else np.nan
        cost = promo_cost if pd.notna(promo_cost) else base_cost

        for pcol in price_cols:
            selling_val = row.get(pcol, np.nan)
            if pd.isna(selling_val): continue

            try:
                options = str(selling_val).replace("，",",").replace("/",",").split(",")
                prices = [float(x) for x in options if str(x).strip() != ""]
            except:
                prices = []
            for price in prices:
                profit = np.nan
                if pd.notna(cost):
                    profit = price - cost
                results.append({
                    "产品": product,
                    "卖价列": pcol,
                    "售价": price,
                    "成本": cost,
                    "利润": profit
                })

    if results:
        res_df = pd.DataFrame(results)
        st.subheader("📊 计算结果")
        st.dataframe(res_df, use_container_width=True)
