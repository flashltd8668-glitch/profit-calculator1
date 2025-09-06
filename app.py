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
                df2 = pd.read_excel(path, header=[0, header_idx])
                new_cols = clean_column_names_from_multiindex(df2.columns.values)
                df2.columns = new_cols
                return df2
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
st.sidebar.header("🌍 国家选择")
countries = list(COUNTRY_CURRENCY.keys())
country = st.sidebar.selectbox("选择国家", countries)
st.sidebar.header("📤 上传价钱表")
uploaded_file = st.sidebar.file_uploader(f"上传 {country} 的 Excel/CSV", type=["xlsx","xls","csv"])

if uploaded_file:
    save_dir = UPLOAD_DIR / country
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / uploaded_file.name
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    meta_df = pd.read_csv(META_FILE)
    new_record = pd.DataFrame([{
        "country": country,
        "filename": uploaded_file.name,
        "filepath": str(save_path),
        "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }])
    meta_df = pd.concat([meta_df, new_record], ignore_index=True)
    meta_df.to_csv(META_FILE, index=False)
    st.sidebar.success("✅ 文件已保存")

meta_df = pd.read_csv(META_FILE)
country_files = meta_df[meta_df["country"] == country].sort_values("upload_date", ascending=False)
selected_file = None
if not country_files.empty:
    st.sidebar.header("📁 已上传文件")
    selected_file = st.sidebar.selectbox("选择文件", country_files["filename"].tolist())

# ============== 汇率设置 ==============
st.sidebar.header("💱 汇率设置")
rates = {}
if RATES_FILE.exists():
    try:
        rates = json.loads(RATES_FILE.read_text(encoding="utf-8"))
    except:
        rates = DEFAULT_RATES.copy()
else:
    rates = DEFAULT_RATES.copy()
for cur in COUNTRY_CURRENCY.values():
    rates[cur] = st.sidebar.number_input(f"1 {cur} = ? MYR", value=float(rates.get(cur, DEFAULT_RATES.get(cur, 1.0))), step=0.01)
if st.sidebar.button("💾 保存汇率"):
    RATES_FILE.write_text(json.dumps(rates, ensure_ascii=False, indent=2), encoding="utf-8")
    st.sidebar.success("✅ 汇率已保存")

# ============== 读取文件并计算利润 ==============
df = None
if selected_file:
    sel_info = country_files[country_files["filename"] == selected_file].iloc[0]
    fpath = sel_info["filepath"]
    try:
        df = try_read_and_clean(fpath, 0)
    except Exception as e:
        st.error(f"读取文件失败：{e}")
        df = None

if df is not None:
    st.subheader("📋 数据预览")
    st.dataframe(df.head(), use_container_width=True)

    name_col = st.selectbox("选择产品名列", df.columns)
    cost_col = st.selectbox("选择成本列", df.columns)
    price_cols = st.multiselect("选择卖价列", df.columns)

    if name_col and cost_col and price_cols:
        records = []
        conv = float(rates[COUNTRY_CURRENCY[country]])
        for _, row in df.iterrows():
            product = str(row.get(name_col, ""))
            cost = float(pd.to_numeric(row.get(cost_col), errors="coerce") or 0)
            for col in price_cols:
                prices = split_price_cell(row.get(col))
                for price in prices:
                    platform_fee_local = price * 0.1
                    profit_local = price - cost - platform_fee_local
                    profit_myr = profit_local / conv
                    records.append({
                        "产品名称": product,
                        "利润 (MYR)": profit_myr,
                        "来源": "Normal"
                    })
        result_df = pd.DataFrame(records)
        st.subheader("📊 计算结果")
        st.write(style_results(result_df), unsafe_allow_html=True)

        # ============== 利润对比图 ==============
        st.subheader("📉 产品利润对比图（MYR）")
        try:
            import altair as alt
            chart_data = result_df.groupby(["产品名称"])["利润 (MYR)"].sum().reset_index()
            chart = (
                alt.Chart(chart_data)
                .mark_bar()
                .encode(
                    x=alt.X("产品名称:N", sort="-y"),
                    y=alt.Y("利润 (MYR):Q"),
                    tooltip=["产品名称", "利润 (MYR)"],
                )
                .properties(height=400)
            )
            st.altair_chart(chart, use_container_width=True)
        except Exception as e:
            st.bar_chart(result_df.set_index("产品名称")["利润 (MYR)"])

        # ============== 颜色说明 ==============
        st.markdown("### 🎨 颜色说明")
        st.markdown(
            """
            - 🟥 **红色背景** → 利润为负  
            - 🟩 **绿色背景** → 促销产品  
            """
        )

        # 导出 Excel
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            result_df.to_excel(writer, index=False, sheet_name="Results")
        st.download_button("⬇️ 下载结果 Excel", data=buffer.getvalue(), file_name=f"profit_results_{country}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
