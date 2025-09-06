import streamlit as st
import pandas as pd
import numpy as np
import io

st.set_page_config(page_title="Profit Calculator (Auto Promo Edition)", layout="wide")

st.title("💰 自动促销优先的多卖价利润计算器 (THB → MYR)")

uploaded_file = st.file_uploader("上传 Excel/CSV 文件", type=["xlsx", "xls", "csv"])

if uploaded_file:
    try:
        if uploaded_file.name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(uploaded_file, header=1)  # 跳过第一行（合并表头）
        else:
            df = pd.read_csv(uploaded_file)
    except Exception:
        df = pd.read_csv(uploaded_file, encoding_errors="ignore")

    st.subheader("📋 数据预览")
    st.dataframe(df.head())

    # === 映射字段 ===
    st.sidebar.header("映射字段")
    name_col = st.sidebar.selectbox("选择产品名称列", [None] + list(df.columns))
    cost_col = st.sidebar.selectbox("选择普通成本列", [None] + list(df.columns))
    promo_cost_col = st.sidebar.selectbox("选择促销成本列 (可选)", [None] + list(df.columns))
    promo_price_col = st.sidebar.selectbox("选择促销售价列 (可选)", [None] + list(df.columns))
    price_cols = st.sidebar.multiselect("选择普通卖价列（可多选）", list(df.columns))

    # === 设置 ===
    st.sidebar.header("计算设置")
    platform_fee_pct = st.sidebar.number_input("平台抽成 (%)", value=5.0)
    personal_commission_pct = st.sidebar.number_input("个人抽成 (%)", value=0.0)

    # === 汇率设置 ===
    st.sidebar.header("汇率设置")
    thb_to_myr = st.sidebar.number_input("THB → MYR 汇率", value=7.8)

    if name_col and cost_col and price_cols:
        records = []

        for _, row in df.iterrows():
            product = row[name_col]

            # 如果有促销数据 → 优先
            if promo_cost_col and promo_price_col and pd.notna(row[promo_cost_col]) and pd.notna(row[promo_price_col]):
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

                # 平台抽成
                platform_fee = price * (platform_fee_pct / 100.0)

                # 利润
                profit = price - base_cost - platform_fee
                margin = (profit / price) * 100 if price > 0 else np.nan

                # 个人抽成
                commission = profit * (personal_commission_pct / 100.0)

                # 转 MYR
                profit_myr = profit / thb_to_myr
                commission_myr = commission / thb_to_myr

                records.append({
                    "产品名称": product,
                    "成本 (THB)": base_cost,
                    "卖价 (THB)": price,
                    "平台抽成 (THB)": platform_fee,
                    "利润 (MYR)": profit_myr,
                    "利润率 %": margin,
                    "个人抽成 (MYR)": commission_myr,
                    "来源": source
                })

        result_df = pd.DataFrame(records)

        # 排序：按利润 (MYR) 从高到低
        result_df = result_df.sort_values(by="利润 (MYR)", ascending=False).reset_index(drop=True)

        st.subheader("📊 计算结果（已按利润高低排序）")
        # 格式化显示
        display_df = result_df.copy()
        display_df["利润 (MYR)"] = display_df["利润 (MYR)"].map(lambda x: f"RM {x:,.2f}")
        display_df["个人抽成 (MYR)"] = display_df["个人抽成 (MYR)"].map(lambda x: f"RM {x:,.2f}")
        st.dataframe(display_df, use_container_width=True)

        # 利润对比图
        st.subheader("📈 利润对比图 (MYR)")
        chart_df = result_df.groupby(["产品名称", "来源", "卖价 (THB)"])["利润 (MYR)"].sum().reset_index()
        st.bar_chart(chart_df.set_index("产品名称").pivot(columns="卖价 (THB)", values="利润 (MYR)"))

        # === 导出 Excel ===
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            result_df.to_excel(writer, index=False, sheet_name="Results")
            chart_df.to_excel(writer, index=False, sheet_name="ChartData")

        st.download_button(
            label="下载结果 Excel",
            data=buffer.getvalue(),
            file_name="profit_results_auto_promo.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("⚠️ 请至少选择 产品名 / 成本 / 卖价 列")
