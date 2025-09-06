import streamlit as st
import pandas as pd
import numpy as np
import os
import io
import shutil
from datetime import datetime

st.set_page_config(page_title="Profit Calculator (Multi-Country + Auto Promo)", layout="wide")
st.title("💰 多国家利润计算器 (自动促销优先 + 文件管理 + 汇率支持)")

# ========== 文件存放目录 & metadata ==========
UPLOAD_DIR = "uploads"
META_FILE = "file_metadata.csv"

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

if not os.path.exists(META_FILE):
    pd.DataFrame(columns=["country", "filename", "filepath", "upload_date"]).to_csv(META_FILE, index=False)

# 国家和对应货币
COUNTRY_CURRENCY = {
    "Thailand": "THB",
    "Malaysia": "MYR",
    "Vietnam": "VND",
    "Philippines": "PHP",
    "Indonesia": "IDR"
}

# ========== 国家选择 ==========
st.sidebar.header("国家选择")
countries = list(COUNTRY_CURRENCY.keys())
country = st.sidebar.selectbox("选择国家", countries)

# ========== 上传文件 ==========
uploaded_file = st.sidebar.file_uploader(f"上传 {country} 的 Excel/CSV 文件", type=["xlsx", "xls", "csv"])
if uploaded_file:
    save_dir = os.path.join(UPLOAD_DIR, country)
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, uploaded_file.name)

    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    # 更新 metadata
    meta_df = pd.read_csv(META_FILE)
    meta_df = meta_df[~((meta_df["country"] == country) & (meta_df["filename"] == uploaded_file.name))]
    new_record = pd.DataFrame([{
        "country": country,
        "filename": uploaded_file.name,
        "filepath": save_path,
        "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M")
    }])
    meta_df = pd.concat([meta_df, new_record], ignore_index=True)
    meta_df.to_csv(META_FILE, index=False)
    st.success(f"✅ 文件已保存到 {save_path}")

# ========== 历史文件选择 ==========
meta_df = pd.read_csv(META_FILE)
country_files = meta_df[meta_df["country"] == country]

df = None
file_choice = None

if not country_files.empty:
    st.sidebar.subheader(f"{country} 已上传的文件")
    file_choice = st.sidebar.selectbox(
        "选择文件",
        country_files.sort_values("upload_date", ascending=False)["filename"].tolist()
    )

# 如果 metadata 丢失，直接扫描 uploads/{country}
if not file_choice:
    country_dir = os.path.join(UPLOAD_DIR, country)
    if os.path.exists(country_dir):
        files = sorted(os.listdir(country_dir), key=lambda x: os.path.getmtime(os.path.join(country_dir, x)), reverse=True)
        if files:
            file_choice = files[0]

if file_choice:
    file_info = country_files[country_files["filename"] == file_choice].iloc[0] if not country_files.empty else {
        "filepath": os.path.join(UPLOAD_DIR, country, file_choice),
        "filename": file_choice,
        "upload_date": "未知"
    }
    st.info(f"📂 选择文件: {file_info['filename']} (上传日期: {file_info.get('upload_date', '未知')})")

    if str(file_choice).endswith((".xlsx", ".xls")):
        df = pd.read_excel(file_info["filepath"], header=1)
    else:
        df = pd.read_csv(file_info["filepath"])

# ========== 删除所有文件 ==========
st.sidebar.header("⚙️ 文件管理")
if st.sidebar.button("🗑️ 删除所有已上传文件"):
    if os.path.exists(UPLOAD_DIR):
        shutil.rmtree(UPLOAD_DIR)
        os.makedirs(UPLOAD_DIR, exist_ok=True)
    pd.DataFrame(columns=["country", "filename", "filepath", "upload_date"]).to_csv(META_FILE, index=False)
    st.sidebar.success("✅ 已删除所有上传文件和记录")
    st.stop()

# ========== 汇率设置 ==========
st.sidebar.header("🌍 汇率设置 (换算成 MYR)")
exchange_rates = {}
for c, cur in COUNTRY_CURRENCY.items():
    default_rate = 7.8 if cur == "THB" else 1.0
    rate = st.sidebar.number_input(f"1 {cur} = ? MYR", value=default_rate, step=0.01)
    exchange_rates[cur] = rate

# ========== 利润计算 ==========
if df is not None:
    st.subheader("📋 数据预览")
    st.dataframe(df.head())

    # 字段映射
    st.sidebar.header("映射字段")
    name_col = st.sidebar.selectbox("选择产品名称列", [None] + list(df.columns))
    cost_col = st.sidebar.selectbox("选择普通成本列", [None] + list(df.columns))
    promo_cost_col = st.sidebar.selectbox("选择促销成本列 (可选)", [None] + list(df.columns))
    promo_price_col = st.sidebar.selectbox("选择促销售价列 (可选)", [None] + list(df.columns))
    price_cols = st.sidebar.multiselect("选择普通卖价列（可多选）", list(df.columns))

    # 设置
    st.sidebar.header("计算设置")
    platform_fee_pct = st.sidebar.number_input("平台抽成 (%)", value=5.0)
    personal_commission_pct = st.sidebar.number_input("个人抽成 (%)", value=0.0)
    profit_threshold = st.sidebar.number_input("高利润阈值 (MYR)", value=50.0, step=1.0)

    if name_col and cost_col and price_cols:
        records = []
        local_currency = COUNTRY_CURRENCY[country]
        conversion_rate = exchange_rates[local_currency]

        for _, row in df.iterrows():
            product = row[name_col]

            if promo_cost_col and promo_price_col and pd.notna(row.get(promo_cost_col)) and pd.notna(row.get(promo_price_col)):
                base_cost = pd.to_numeric(row[promo_cost_col], errors="coerce") or 0
                prices = str(row[promo_price_col]).split("/")
                source = "Promotion"
            else:
                base_cost = pd.to_numeric(row[cost_col], errors="coerce") or 0
                prices = []
                for col in price_cols:
                    prices.extend(str(row[col]).split("/"))
                source = "Normal"

            for raw_p in prices:
                try:
                    price = float(raw_p)
                except:
                    continue

                platform_fee = price * (platform_fee_pct / 100.0)
                profit = price - base_cost - platform_fee
                margin = (profit / price) * 100 if price > 0 else np.nan
                commission = profit * (personal_commission_pct / 100.0)

                profit_myr = profit / conversion_rate
                commission_myr = commission / conversion_rate

                records.append({
                    "产品名称": product,
                    f"成本 ({local_currency})": round(base_cost, 2),
                    f"卖价 ({local_currency})": round(price, 2),
                    f"平台抽成 ({local_currency})": round(platform_fee, 2),
                    "利润 (MYR)": round(profit_myr, 2),
                    "利润率 %": round(margin, 2),
                    "个人抽成 (MYR)": round(commission_myr, 2),
                    "来源": source
                })

        result_df = pd.DataFrame(records)
        result_df = result_df.sort_values(by="利润 (MYR)", ascending=False).reset_index(drop=True)

        # ========== 筛选产品 ==========
        st.sidebar.header("产品筛选")
        all_products = sorted([str(p) for p in result_df["产品名称"].dropna().unique().tolist()])
        search_term = st.sidebar.text_input("🔍 搜索产品（支持模糊匹配）")

        filtered_products = [p for p in all_products if search_term.lower() in str(p).lower()] if search_term else all_products
        selected_products = st.sidebar.multiselect("选择要显示的产品", filtered_products, default=filtered_products)
        filtered_df = result_df[result_df["产品名称"].isin(selected_products)]

        # ========== 表格展示 ==========
        st.subheader("📊 计算结果（已按利润高低排序）")

        # 颜色说明
        st.markdown(f"""
        **颜色提示：**  
        🟨 黄色 → 使用促销价  
        🟥 红色 → 利润 < 0 (亏损)  
        🟩 绿色 → 利润 > {profit_threshold} (高利润)  
        """)

        def highlight_rows(row):
            if row["来源"] == "Promotion":
                return ["background-color: yellow"] * len(row)
            elif row["利润 (MYR)"] < 0:
                return ["background-color: red; color: white"] * len(row)
            elif row["利润 (MYR)"] > profit_threshold:
                return ["background-color: lightgreen"] * len(row)
            else:
                return [""] * len(row)

        if filtered_df.empty:
            st.warning("⚠️ 没有符合条件的产品数据")
        else:
            st.dataframe(filtered_df.style.apply(highlight_rows, axis=1), use_container_width=True)

        # ========== 平台费率汇总表（示例 DataFrame） ==========
        st.subheader("📊 平台费率汇总表")
        fee_show = pd.DataFrame({
            "country": ["Thailand", "Thailand", "Malaysia", "Vietnam"],
            "platform": ["Shopee", "Lazada", "Shopee", "Shopee"],
            "fee_pct": [5.0, 6.5, 4.0, 8.0]
        })

        sum_df = (
            fee_show.groupby(["country", "platform"])
            .agg(最低费率=("fee_pct", "min"),
                 最高费率=("fee_pct", "max"),
                 平均费率=("fee_pct", "mean"),
                 方案数量=("fee_pct", "count"))
            .reset_index()
        )

        st.dataframe(sum_df, use_container_width=True)

