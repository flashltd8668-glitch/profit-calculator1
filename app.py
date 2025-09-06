import streamlit as st
import pandas as pd
import numpy as np
import os
from datetime import datetime

st.set_page_config(page_title="利润计算助手", layout="wide")

# ========== 自动清理表头 ==========
def clean_headers(df):
    df = df.rename(columns=lambda x: str(x).replace("Unnamed: ", "").strip())
    df.columns = [c if c.strip() != "" else f"col_{i}" for i, c in enumerate(df.columns)]
    return df

# ========== 高亮规则 ==========
def highlight_rows(row, threshold):
    styles = []
    if row["来源"] == "Promotion":
        styles.append("background-color: yellow")
    elif row["利润 (MYR)"] < 0:
        styles.append("background-color: red; color: white")
    elif row["利润 (MYR)"] > threshold:
        styles.append("background-color: lightgreen")
    else:
        styles.append("")
    return styles * len(row)

# ========== 读取价钱表 ==========
st.sidebar.header("上传文件")
uploaded_file = st.sidebar.file_uploader("上传价钱表 (Excel)", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    df = clean_headers(df)

    # ========== 选择列 ==========
    st.sidebar.subheader("选择对应列")
    product_col = st.sidebar.selectbox("产品名称列", df.columns)
    cost_col = st.sidebar.selectbox("普通成本列", df.columns)
    promo_cost_col = st.sidebar.selectbox("促销成本列", [None] + list(df.columns))
    price_col = st.sidebar.selectbox("售价列", df.columns)
    promo_price_col = st.sidebar.selectbox("促销售价列", [None] + list(df.columns))

    # ========== 参数设置 ==========
    st.sidebar.header("计算设置")
    platform_fee_pct = st.sidebar.number_input("平台抽成 (%)", value=5.0)
    personal_commission_pct = st.sidebar.number_input("个人抽成 (%)", value=0.0)
    high_profit_threshold = st.sidebar.number_input("高利润阈值 (MYR)", value=50.0, step=1.0)

    if product_col and cost_col and price_col:
        records = []
        for _, row in df.iterrows():
            product = row[product_col]
            base_cost = row[cost_col]

            # 促销成本优先
            cost = row[promo_cost_col] if promo_cost_col and not pd.isna(row[promo_cost_col]) else base_cost
            price = row[promo_price_col] if promo_price_col and not pd.isna(row[promo_price_col]) else row[price_col]

            source = "Promotion" if promo_price_col and not pd.isna(row.get(promo_price_col)) else "Normal"

            if pd.isna(cost) or pd.isna(price):
                continue

            platform_fee = price * platform_fee_pct / 100
            personal_fee = price * personal_commission_pct / 100
            profit = price - cost - platform_fee - personal_fee
            profit_rate = profit / price if price > 0 else 0

            records.append({
                "产品": product,
                "来源": source,
                "成本 (MYR)": round(cost, 2),
                "售价 (MYR)": round(price, 2),
                "平台费 (MYR)": round(platform_fee, 2),
                "个人抽成 (MYR)": round(personal_fee, 2),
                "利润 (MYR)": round(profit, 2),
                "利润率 (%)": round(profit_rate * 100, 2)
            })

        result_df = pd.DataFrame(records)

        # ========== 显示结果 ==========
        st.subheader("💰 产品利润计算结果")
        st.markdown(f"""
        **颜色提示：**  
        🟨 黄色 → 使用促销价  
        🟥 红色 → 利润 < 0 (亏损)  
        🟩 绿色 → 利润 > {high_profit_threshold} MYR (高利润)  
        """)

        st.dataframe(result_df.style.apply(
            lambda row: highlight_rows(row, high_profit_threshold), axis=1
        ))

        # ========== 汇总表 (模拟平台费率配置) ==========
        st.subheader("📊 平台费率汇总表")
        fee_data = pd.DataFrame({
            "country": ["Thailand", "Thailand", "Malaysia", "Malaysia", "Vietnam"],
            "platform": ["Shopee", "Lazada", "Shopee", "Lazada", "Shopee"],
            "fee_pct": [5, 6, 5.5, 7, 6.2]
        })

        fee_show = fee_data.copy()
        sum_df = (
            fee_show.groupby(["country", "platform"])
            .agg(最低费率=("fee_pct", "min"),
                 最高费率=("fee_pct", "max"),
                 平均费率=("fee_pct", "mean"),
                 方案数量=("fee_pct", "count"))
            .reset_index()
        )

        st.dataframe(sum_df)
