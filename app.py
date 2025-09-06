import streamlit as st
import pandas as pd
import numpy as np
import io

st.set_page_config(page_title="Profit Calculator (MYR Edition)", layout="wide")

st.title("💰 简易利润计算器 (支持 THB → MYR)")

uploaded_file = st.file_uploader("上传 Excel/CSV 文件", type=["xlsx", "xls", "csv"])

if uploaded_file:
    try:
        if uploaded_file.name.endswith((".xlsx", ".xls")):
            # 跳过第一行（合并表头），第二行才是真正的字段名
            df = pd.read_excel(uploaded_file, header=1)
        else:
            df = pd.read_csv(uploaded_file)
    except Exception:
        df = pd.read_csv(uploaded_file, encoding_errors="ignore")


    st.subheader("预览数据")
    st.dataframe(df.head())

    # 映射
    st.sidebar.header("映射字段")
    name_col = st.sidebar.selectbox("选择产品名称列", [None] + list(df.columns))
    cost_col = st.sidebar.selectbox("选择成本列", [None] + list(df.columns))
    price_col = st.sidebar.selectbox("选择卖价列", [None] + list(df.columns))

    # 设置
    st.sidebar.header("设置")
    platform_fee_pct = st.sidebar.number_input("平台抽成 (%)", value=5.0)
    personal_commission_pct = st.sidebar.number_input("个人抽成 (%)", value=0.0)

    # 汇率设置
    st.sidebar.header("汇率设置")
    thb_to_myr = st.sidebar.number_input("THB → MYR 汇率", value=7.8)

    if name_col and cost_col and price_col:
        df_calc = df.copy()

        # 转换成数字
        cost = pd.to_numeric(df_calc[cost_col], errors="coerce").fillna(0)
        price = pd.to_numeric(df_calc[price_col], errors="coerce").fillna(0)

        # 平台抽成金额
        platform_fee = price * (platform_fee_pct / 100.0)

        # 利润 (不含个人抽成)
        profit = price - cost - platform_fee

        # 利润率
        margin = np.where(price > 0, (profit / price) * 100, np.nan)

        # 个人抽成 (基于利润)
        commission = profit * (personal_commission_pct / 100.0)

        # 换算成马币
        profit_myr = profit / thb_to_myr
        commission_myr = commission / thb_to_myr

        # 结果表
        result_df = pd.DataFrame({
            "产品名称": df_calc[name_col] if name_col else "",
            f"成本 (THB)": cost,
            f"卖价 (THB)": price,
            f"平台抽成 ({platform_fee_pct}%)": platform_fee,
            "利润 (THB)": profit,
            "利润率 %": margin,
            f"个人抽成 (MYR)": commission_myr.map(lambda x: f"RM {x:,.2f}"),
            f"利润 (MYR)": profit_myr.map(lambda x: f"RM {x:,.2f}"),
            "利润_MYR_数值": profit_myr  # 用于排序 & 绘图
        })

        # 按利润(MYR)从高到低排序
        result_df = result_df.sort_values(by="利润_MYR_数值", ascending=False)

        st.subheader("计算结果（已排序）")
        st.dataframe(result_df.drop(columns=["利润_MYR_数值"]), use_container_width=True)

        # 📊 图表：产品 vs 利润（MYR），按排序
        st.subheader("利润对比图 (MYR)")
        chart_df = result_df[["产品名称", "利润_MYR_数值"]]
        st.bar_chart(chart_df.set_index("产品名称"))

        # 导出 Excel
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            result_df.drop(columns=["利润_MYR_数值"]).to_excel(writer, index=False, sheet_name="Results")

        st.download_button(
            label="下载结果 Excel",
            data=buffer.getvalue(),
            file_name="profit_results_myr.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("请至少选择 产品名 / 成本 / 卖价 列")
