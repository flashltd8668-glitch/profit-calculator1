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

# ✅ 样式：按条件上色（阈值可调）
def style_results(df_results, threshold=50.0):
    def row_style(row):
        styles = [""] * len(row)
        if pd.isna(row["利润 (MYR)"]):
            return styles
        if row["利润 (MYR)"] < 0:
            styles = ["background-color:#ffcccc"] * len(row)  # 🟥 红色
        elif row.get("来源", "") == "Promotion":
            styles = ["background-color:#fff2cc"] * len(row)  # 🟨 黄色
        elif row["利润 (MYR)"] >= threshold:
            styles = ["background-color:#d9ead3"] * len(row)  # 🟩 绿色
        return styles

    sty = df_results.style.apply(lambda r: row_style(r), axis=1)
    sty = sty.format({
        "利润 (MYR)": "RM {0:,.2f}", 
        "个人抽成 (MYR)": "RM {0:,.2f}", 
        "利润率 %": "{0:.2f}%"
    }, na_rep="-")
    return sty

# ============== 侧边栏：国家选择 & 文件上传 ==============
st.sidebar.header("🌍 国家选择")
countries = list(COUNTRY_CURRENCY.keys())
country = st.sidebar.selectbox("选择国家", countries)

st.sidebar.header("📤 上传价钱表")
uploaded_file = st.sidebar.file_uploader(f"上传 {country} 的 Excel/CSV（表头可调整）", type=["xlsx","xls","csv"])
if uploaded_file:
    save_dir = UPLOAD_DIR / country
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / uploaded_file.name
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    meta_df = pd.read_csv(META_FILE)
    meta_df = meta_df[~((meta_df["country"] == country) & (meta_df["filename"] == uploaded_file.name))]
    new_record = pd.DataFrame([{
        "country": country,
        "filename": uploaded_file.name,
        "filepath": str(save_path),
        "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }])
    meta_df = pd.concat([meta_df, new_record], ignore_index=True)
    meta_df.to_csv(META_FILE, index=False)
    st.sidebar.success("✅ 文件已保存（同名保留最新）")

# list uploaded files
meta_df = pd.read_csv(META_FILE)
country_files = meta_df[meta_df["country"] == country].sort_values("upload_date", ascending=False)

selected_file = None
if not country_files.empty:
    st.sidebar.header("📁 已上传文件")
    selected_file = st.sidebar.selectbox("选择文件", country_files["filename"].tolist())
    if selected_file:
        info = country_files[country_files["filename"] == selected_file].iloc[0]
        st.sidebar.caption(f"最后上传：{info['upload_date']}")
        if st.sidebar.button(f"🗑️ 删除此文件: {selected_file}"):
            try:
                p = Path(info["filepath"])
                if p.exists():
                    p.unlink()
                meta_df = meta_df.drop(meta_df[(meta_df["country"] == country) & (meta_df["filename"] == selected_file)].index)
                meta_df.to_csv(META_FILE, index=False)
                st.sidebar.success("✅ 已删除，刷新页面后生效")
                st.stop()
            except Exception as e:
                st.sidebar.error(f"删除失败: {e}")

# ============== 侧边栏：表头设置 ==============
st.sidebar.header("📑 表头设置")
header_row = st.sidebar.number_input("表头所在行（从1开始）", min_value=1, max_value=10, value=2, step=1)

# ============== 侧边栏：汇率设置 ==============
st.sidebar.header("💱 汇率设置（换算为 MYR）")
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

# ============== 侧边栏：平台费率配置管理 ==============
st.sidebar.header("⚙️ 平台费率配置管理")
fee_df = load_fee_config()

# ...（平台费率管理部分保持不变）...

with st.expander("📄 当前费率配置预览"):
    st.dataframe(fee_df, use_container_width=True)

st.divider()

# ============== 读取文件并计算利润 ==============
df = None
if selected_file:
    sel_info = country_files[country_files["filename"] == selected_file].iloc[0]
    fpath = sel_info["filepath"]
    try:
        df = try_read_and_clean(fpath, header_row-1)
    except Exception as e:
        st.error(f"读取文件失败：{e}")
        df = None

if df is None:
    st.info("请在左侧上传/选择文件并设置表头行开始计算。")
else:
    st.subheader("📋 数据预览（已清理表头）")
    st.dataframe(df.head(), use_container_width=True)

    # ...（字段映射部分保持不变）...

    # 计算
    if name_col and (price_cols or promo_price_col) and (cost_col or promo_cost_col):
        records = []
        conv = float(rates[COUNTRY_CURRENCY[country]]) if float(rates[COUNTRY_CURRENCY[country]]) > 0 else 1.0

        for _, row in df.iterrows():
            product = str(row.get(name_col, "")).strip()
            use_promo = False
            base_cost = np.nan
            prices = []

            if promo_cost_col and promo_price_col and pd.notna(row.get(promo_cost_col)) and pd.notna(row.get(promo_price_col)):
                base_cost = pd.to_numeric(row.get(promo_cost_col), errors="coerce")
                base_cost = 0.0 if pd.isna(base_cost) else float(base_cost)
                prices = split_price_cell(row.get(promo_price_col))
                use_promo = True
            else:
                base_cost = pd.to_numeric(row.get(cost_col), errors="coerce") if cost_col else np.nan
                base_cost = 0.0 if pd.isna(base_cost) else float(base_cost)
                for col in price_cols:
                    prices += split_price_cell(row.get(col))
                use_promo = False

            if not prices:
                continue

            for price in prices:
                platform_fee_local = price * (platform_fee_pct / 100.0)
                profit_local = price - base_cost - platform_fee_local
                margin_pct = (profit_local / price * 100.0) if price > 0 else np.nan
                personal_comm_local = profit_local * (personal_commission_pct / 100.0)

                profit_myr = profit_local / conv
                personal_comm_myr = personal_comm_local / conv

                records.append({
                    "产品名称": product,
                    f"成本 ({COUNTRY_CURRENCY[country]})": base_cost,
                    f"卖价 ({COUNTRY_CURRENCY[country]})": price,
                    f"平台抽成 ({COUNTRY_CURRENCY[country]})": platform_fee_local,
                    "利润 (MYR)": round(profit_myr, 2),
                    "利润率 %": round(margin_pct, 2),
                    "个人抽成 (MYR)": round(personal_comm_myr, 2),
                    "来源": "Promotion" if use_promo else "Normal",
                    "平台方案": platform_choice or "自定义"
                })

        result_df = pd.DataFrame(records)
        if result_df.empty:
            st.info("未解析到有效价格（请检查映射与价格格式）")
        else:
            result_df["产品名称"] = result_df["产品名称"].astype(str)
            result_df = result_df.sort_values(by="利润 (MYR)", ascending=False).reset_index(drop=True)

            # ✅ 用户阈值
            threshold = st.sidebar.number_input("利润阈值 (MYR)", value=50.0, step=1.0)

            # 显示并样式化
            st.subheader("📊 计算结果（按利润排序）")
            sty = style_results(result_df, threshold=threshold)
            st.write(sty, unsafe_allow_html=True)

            # ✅ 图表
            st.subheader("📈 产品利润对比（MYR）")
            chart_data = result_df.copy()
            chart_data["颜色标识"] = chart_data.apply(
                lambda r: "🟥 利润 < 0" if r["利润 (MYR)"] < 0
                else ("🟨 用促销价" if r["来源"] == "Promotion"
                      else ("🟩 高利润 (≥阈值)" if r["利润 (MYR)"] >= threshold else "其它")),
                axis=1
            )

            import altair as alt
            chart = (
                alt.Chart(chart_data)
                .mark_bar()
                .encode(
                    x=alt.X("产品名称:N", sort="-y"),
                    y=alt.Y("利润 (MYR):Q"),
                    color=alt.Color("颜色标识:N", legend=alt.Legend(title="颜色说明", orient="top")),
                    tooltip=list(chart_data.columns)
                )
                .properties(height=400)
            )
            st.altair_chart(chart, use_container_width=True)

            # 导出 Excel
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                result_df.to_excel(writer, index=False, sheet_name="All_Results")
            st.download_button("⬇️ 下载结果 Excel", data=buffer.getvalue(), file_name=f"profit_results_{country}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ============== 结束 ==============
st.caption("说明：本工具只抓取公开信息（示范），不会登录任何平台。费率/汇率请按实际业务情况确认。")
