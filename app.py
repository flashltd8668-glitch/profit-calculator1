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
st.sidebar.header("⚙️ 设置")

country = st.sidebar.selectbox("选择国家", list(COUNTRY_CURRENCY.keys()))
currency = COUNTRY_CURRENCY[country]

uploaded_file = st.sidebar.file_uploader("上传 Excel/CSV 文件", type=["xlsx", "xls", "csv"])

if uploaded_file is not None:
    # 保存上传的文件
    save_path = UPLOAD_DIR / uploaded_file.name
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    # 更新元数据
    meta = pd.read_csv(META_FILE)
    new_row = {
        "country": country,
        "filename": uploaded_file.name,
        "filepath": str(save_path),
        "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    meta = pd.concat([meta, pd.DataFrame([new_row])], ignore_index=True)
    meta.to_csv(META_FILE, index=False)

    st.sidebar.success(f"文件已保存: {uploaded_file.name}")

# 历史文件列表
st.sidebar.subheader("📂 历史文件")
meta = pd.read_csv(META_FILE)
meta_country = meta[meta["country"] == country]
if not meta_country.empty:
    selected_file = st.sidebar.selectbox("选择已上传文件", meta_country["filename"].tolist()[::-1])
    if selected_file:
        file_record = meta_country[meta_country["filename"] == selected_file].iloc[0]
        file_path = file_record["filepath"]

        st.write(f"已选择文件: **{selected_file}** （上传于 {file_record['upload_date']}）")

        # 尝试读取
        try:
            df_preview = try_read_and_clean(file_path, header_idx=0)
            st.write("数据预览：", df_preview.head())
        except Exception as e:
            st.error(f"文件读取失败: {e}")

# ============== 汇率设置 ==============
st.sidebar.subheader("💱 汇率设置")
rates = DEFAULT_RATES.copy()
if RATES_FILE.exists():
    try:
        with open(RATES_FILE, "r", encoding="utf-8") as f:
            rates.update(json.load(f))
    except Exception:
        pass

for cur in COUNTRY_CURRENCY.values():
    rates[cur] = st.sidebar.number_input(
        f"1 {cur} = ? MYR", value=float(rates.get(cur, 1.0)), step=0.01
    )

if st.sidebar.button("保存汇率"):
    with open(RATES_FILE, "w", encoding="utf-8") as f:
        json.dump(rates, f, ensure_ascii=False, indent=2)
    st.sidebar.success("汇率已保存 ✅")

# ============== 利润计算逻辑 ==============
if uploaded_file or ("selected_file" in locals() and selected_file):
    if uploaded_file:
        file_path = save_path
    else:
        file_record = meta_country[meta_country["filename"] == selected_file].iloc[0]
        file_path = file_record["filepath"]

    try:
        df = try_read_and_clean(file_path, header_idx=0)
    except Exception as e:
        st.error(f"读取失败: {e}")
        df = None

    if df is not None:
        st.subheader("📊 字段映射")
        st.write("清理后列名：", list(df.columns))

        name_col = st.selectbox("产品名称列", df.columns)
        cost_col = st.selectbox("成本列", df.columns)
        price_col = st.selectbox("卖价列", df.columns)

        platform_fee_pct = st.number_input("平台费率 (%)", value=10.0, step=0.1)
        personal_pct = st.number_input("个人抽成 (%)", value=0.0, step=0.1)

        if st.button("开始计算"):
            records = []
            conv = float(rates[currency]) if rates[currency] > 0 else 1.0

            for _, row in df.iterrows():
                try:
                    product = str(row[name_col])
                    cost = float(row[cost_col])
                    price = float(row[price_col])
                except Exception:
                    continue

                platform_fee = price * platform_fee_pct / 100.0
                profit_local = price - cost - platform_fee
                profit_myr = profit_local / conv
                margin_pct = profit_local / price * 100 if price > 0 else np.nan
                personal_comm = profit_local * personal_pct / 100.0 / conv

                records.append({
                    "产品名称": product,
                    f"成本 ({currency})": cost,
                    f"卖价 ({currency})": price,
                    "平台抽成": platform_fee,
                    "利润 (MYR)": profit_myr,
                    "利润率 %": margin_pct,
                    "个人抽成 (MYR)": personal_comm,
                })

            result_df = pd.DataFrame(records)
            result_df = result_df.sort_values("利润 (MYR)", ascending=False)

            st.subheader("📈 计算结果")
            sty = style_results(result_df)
            st.write(sty, unsafe_allow_html=True)

            # 导出
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
                result_df.to_excel(writer, index=False)
            st.download_button(
                "下载结果 Excel",
                buf.getvalue(),
                file_name="profit_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

# ============== 利润对比图 ==============
if "result_df" in locals() and not result_df.empty:
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
        st.warning(f"绘制 Altair 图表失败，使用默认图表: {e}")
        st.bar_chart(result_df.set_index("产品名称")["利润 (MYR)"])

    # ============== 颜色说明 ==============
    st.markdown("### 🎨 颜色说明")
    st.markdown(
        """
        - 🟥 **红色背景** → 利润为负  
        - 🟩 **绿色背景** → 促销产品（利润为正）  
        """
    )
