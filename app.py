import streamlit as st
import pandas as pd
import os
from datetime import datetime

st.set_page_config(page_title="利润分析工具", layout="wide")

st.title("📊 利润分析工具 - 基础优化版")

# ========= 上传并保存文件 =========
upload_folder = "uploads"
os.makedirs(upload_folder, exist_ok=True)

uploaded_file = st.sidebar.file_uploader("上传价钱表", type=["xlsx", "xls", "csv"])
if uploaded_file:
    # 保存文件，带时间戳
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = os.path.join(upload_folder, f"{timestamp}_{uploaded_file.name}")
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    st.sidebar.success(f"已保存: {save_path}")

    # 永远保留 latest 文件
    latest_path = os.path.join(upload_folder, "latest.xlsx")
    with open(latest_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    # ========= 自动清理表头 =========
    if uploaded_file.name.endswith((".xlsx", ".xls")):
        raw_df = pd.read_excel(save_path, header=[0, 1])  # 读两行表头
        raw_df.columns = [
            " ".join([str(x) for x in col if "Unnamed" not in str(x)]).strip()
            for col in raw_df.columns.values
        ]
        df = raw_df
    else:
        df = pd.read_csv(save_path)

    st.subheader("📋 数据预览")
    st.dataframe(df.head())

    # ========= 选择列 =========
    product_col = st.sidebar.selectbox("选择产品名称列", df.columns)
    cost_col = st.sidebar.selectbox("选择普通成本列", df.columns)
    promo_col = st.sidebar.selectbox("选择促销价列 (可选)", [None] + list(df.columns))

    if product_col and cost_col:
        result_df = df.copy()

        # 使用促销价 > 否则用普通价
        if promo_col:
            result_df["最终售价"] = result_df[promo_col].fillna(result_df[cost_col])
        else:
            result_df["最终售价"] = result_df[cost_col]

        # 假设成本是 cost_col，售价是最终售价
        result_df["利润"] = result_df["最终售价"] - result_df[cost_col]
        result_df["利润率 %"] = result_df["利润"] / result_df[cost_col] * 100

        # ========= 数值格式化 =========
        num_cols = ["利润", "利润率 %", "最终售价"]
        for col in num_cols:
            if col in result_df.columns:
                result_df[col] = result_df[col].round(2)

        # ========= 表格高亮 =========
        def highlight_rows(row):
            if promo_col and pd.notna(row[promo_col]):
                return ['background-color: #fff3cd'] * len(row)  # 黄色（促销）
            elif row["利润"] < 0:
                return ['background-color: #f8d7da'] * len(row)  # 红色（亏损）
            elif row["利润"] > 50:  # 自己设定阈值
                return ['background-color: #d4edda'] * len(row)  # 绿色（高利润）
            else:
                return [''] * len(row)

        st.subheader("📊 利润计算结果")
        st.dataframe(result_df.style.apply(highlight_rows, axis=1))

        # ========= 下载结果 =========
        output_file = f"Profit_Report_{datetime.now().strftime('%Y%m%d')}.xlsx"
        result_df.to_excel(output_file, index=False)

        with open(output_file, "rb") as f:
            st.download_button("📥 下载结果 Excel", f, file_name=output_file)

else:
    st.info("请先上传一个价钱表文件。")
