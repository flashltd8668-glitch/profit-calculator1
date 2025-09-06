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
        if isinstance(col, (tuple, list)):
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
            if unnamed_count <= 0.3 * max(1, len(cols)):
                clean_cols = []
                for c in df_try.columns:
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
            if unnamed_count <= 0.3 * max(1, len(cols)):
                clean_cols = []
                for c in df_try.columns:
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

def style_results(df_results, profit_threshold):
    def row_style(row):
        # ensure key exists
        if "利润 (MYR)" not in row.index or "来源" not in row.index:
            return [""] * len(row)
        try:
            val = float(row["利润 (MYR)"]) if not pd.isna(row["利润 (MYR)"]) else None
        except:
            val = None
        if val is None:
            return [""] * len(row)
        # Promotion yellow, negative red (dominant), high profit green
        if val < 0:
            return ["background-color:#ffd6d6"] * len(row)  # light red
        if row.get("来源", "") == "Promotion":
            return ["background-color:#fff7d6"] * len(row)  # light yellow
        if val > profit_threshold:
            return ["background-color:#e6ffe6"] * len(row)  # light green
        return [""] * len(row)

    sty = df_results.style.apply(lambda r: row_style(r), axis=1)
    # format numeric columns to 2 decimals
    fmt_map = {}
    for c in df_results.columns:
        if "利润" in c or "成本" in c or "卖价" in c or "抽成" in c or "个人抽成" in c:
            fmt_map[c] = "{:,.2f}"
    if "利润 (MYR)" in df_results.columns:
        # Map money columns to prefixed format for display via Styler.format
        sty = sty.format({k: "RM {0:,.2f}" if "MYR" in k else "{0:,.2f}" for k in df_results.columns}, na_rep="-")
    else:
        sty = sty.format(na_rep="-")
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
    # update meta
    try:
        meta_df = pd.read_csv(META_FILE)
    except:
        meta_df = pd.DataFrame(columns=["country", "filename", "filepath", "upload_date"])
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

# list uploaded files for selected country (robust: if metadata broken, fallback to folder)
try:
    meta_df = pd.read_csv(META_FILE)
except:
    meta_df = pd.DataFrame(columns=["country", "filename", "filepath", "upload_date"])

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

# Fallback: if no metadata or user hasn't selected, try to auto-load latest file in uploads/{country}
if not selected_file:
    country_dir = UPLOAD_DIR / country
    if country_dir.exists():
        files = sorted(list(country_dir.glob("*")), key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            selected_file = files[0].name
            # if metadata doesn't contain this file, create an info dict
            if not (not country_files.empty and selected_file in country_files["filename"].tolist()):
                info = {"filepath": str(files[0]), "filename": files[0].name, "upload_date": files[0].stat().st_mtime}

# bulk delete
st.sidebar.divider()
if st.sidebar.button("🧨 删除所有已上传文件与记录（所有国家）"):
    try:
        if UPLOAD_DIR.exists():
            shutil.rmtree(UPLOAD_DIR)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=["country", "filename", "filepath", "upload_date"]).to_csv(META_FILE, index=False)
        st.sidebar.success("✅ 已清空所有上传文件与记录")
        st.stop()
    except Exception as e:
        st.sidebar.error(f"清空失败: {e}")

# ============== 侧边栏：表头设置（可选） ==============
st.sidebar.header("📑 表头设置")
header_row = st.sidebar.number_input("表头所在行（从1开始）", min_value=1, max_value=10, value=2, step=1)
try_merge_multirow = st.sidebar.checkbox("尝试合并多行表头（如果上传文件有多行标题）", value=False)

# ============== 侧边栏：汇率设置（1 本币 = ? MYR） ==============
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

cfg_file = st.sidebar.file_uploader("上传新的 platform_fees.csv（覆盖）", type=["csv"], key="cfg_up")
if cfg_file is not None:
    try:
        new_cfg = pd.read_csv(cfg_file)
        required = {"country","platform","scenario","fee_pct","remark"}
        if not required.issubset(set(new_cfg.columns)):
            st.sidebar.error(f"❌ 配置缺少列，请包含：{required}")
        else:
            save_fee_config(new_cfg, keep_history=True)
            st.sidebar.success("✅ 配置已更新并保存历史版本")
            fee_df = load_fee_config()
    except Exception as e:
        st.sidebar.error(f"上传失败：{e}")

history_files = sorted(os.listdir(CONFIG_HISTORY_DIR), reverse=True)
if history_files:
    pick = st.sidebar.selectbox("选择历史版本回滚", history_files)
    if st.sidebar.button("🔄 回滚到选定版本"):
        try:
            shutil.copy(CONFIG_HISTORY_DIR / pick, CONFIG_FILE)
            st.sidebar.success(f"✅ 已回滚到 {pick}，请刷新页面")
            fee_df = load_fee_config()
        except Exception as e:
            st.sidebar.error(f"回滚失败：{e}")

if CONFIG_FILE.exists():
    st.sidebar.download_button(
        label="⬇️ 下载当前 platform_fees.csv",
        data=CONFIG_FILE.read_bytes(),
        file_name="platform_fees.csv",
        mime="text/csv",
    )

if st.sidebar.button("🔁 从公开公告尝试同步（示范）"):
    try:
        st.sidebar.info("🔎 已检查公开来源（示范逻辑，不会登录或提交）")
    except Exception as e:
        st.sidebar.error(f"同步失败：{e}")

with st.expander("📄 当前费率配置预览"):
    st.dataframe(fee_df, use_container_width=True)

# ============== 平台费率可视化（并改易懂列名） ==============
st.subheader("🌍 各国家平台费率对比（可筛选）")
c1, c2, c3 = st.columns([1,1,1])
with c1:
    country_filter = st.multiselect("筛选国家", sorted(fee_df["country"].unique().tolist()) if not fee_df.empty else [])
with c2:
    platform_filter = st.multiselect("筛选平台", sorted(fee_df["platform"].unique().tolist()) if not fee_df.empty else [])
with c3:
    scenario_query = st.text_input("按方案关键词搜索（如“无活动”/“Free Shipping”）")

fee_show = fee_df.copy()
if country_filter:
    fee_show = fee_show[fee_show["country"].isin(country_filter)]
if platform_filter:
    fee_show = fee_show[fee_show["platform"].isin(platform_filter)]
if scenario_query:
    fee_show = fee_show[fee_show["scenario"].str.contains(scenario_query, case=False, na=False)]

if not fee_show.empty:
    sum_df = (
        fee_show.groupby(["country","platform"])
        .agg(最低费率=("fee_pct","min"), 最高费率=("fee_pct","max"), 平均费率=("fee_pct","mean"), 方案数量=("fee_pct","count"))
        .reset_index()
    )
    # round the numeric columns
    for col in ["最低费率","最高费率","平均费率"]:
        if col in sum_df.columns:
            sum_df[col] = sum_df[col].round(2)
    st.dataframe(sum_df, use_container_width=True)
    try:
        import altair as alt
        chart = (
            alt.Chart(fee_show)
            .mark_bar()
            .encode(
                x=alt.X("fee_pct:Q", title="费率 (%)"),
                y=alt.Y("scenario:N", title="方案", sort="-x"),
                color=alt.Color("platform:N", title="平台"),
                column=alt.Column("country:N", title="国家")
            )
            .properties(height=260)
        )
        st.altair_chart(chart, use_container_width=True)
    except Exception:
        pass

st.divider()

# ============== 读取选择的价钱表并计算利润 ==============
df = None
if selected_file:
    # try to retrieve file info from metadata; if not present, use fallback path
    try:
        sel_info = country_files[country_files["filename"] == selected_file].iloc[0]
        fpath = sel_info["filepath"]
    except Exception:
        fpath = str(UPLOAD_DIR / country / selected_file)

    try:
        df = try_read_and_clean(fpath, header_row-1)
        # final safety: if columns still have 'Unnamed' or empty names, sanitize
        clean_cols = []
        for i, c in enumerate(df.columns):
            name = str(c) if c is not None else ""
            if name.strip() == "" or name.lower().startswith("unnamed"):
                clean_cols.append(f"Column_{i}")
            else:
                clean_cols.append(name.strip())
        df.columns = clean_cols
        # drop fully empty columns
        df = df.loc[:, ~df.columns.to_series().apply(lambda x: df[x].isna().all())]
    except Exception as e:
        st.error(f"读取文件失败：{e}")
        df = None

if df is None:
    st.info("请在左侧上传/选择文件并设置表头行开始计算。")
else:
    st.subheader("📋 数据预览（已尝试清理合并表头）")
    st.dataframe(df.head(), use_container_width=True)

    # 显示清理后列名，帮助用户选择
    st.sidebar.header("🔎 当前列名（用于映射）")
    st.sidebar.write(list(df.columns))

    # 字段映射（带默认智能猜测 DESCRIPTION）
    def guess_name_column_local(df_local):
        patterns = [r"\b(desc(ription)?|product(\s*name)?|item(\s*name)?|name|title)\b",
                    r"(产品|商品|品名|名稱|名称|标题|描述)",
                    r"(ชื่อสินค้า|รายละเอียด)"]
        cols_local = [str(c) for c in df_local.columns]
        for pat in patterns:
            for c in cols_local:
                if re.search(pat, c, flags=re.IGNORECASE):
                    return c
        for c in cols_local:
            s = df_local[c].dropna()
            if not s.empty:
                if s.astype(str).nunique() / max(1, len(s)) > 0.2:
                    return c
        return cols_local[0]

    st.sidebar.header("🧩 字段映射")
    default_name = guess_name_column_local(df)
    default_cost = "COST" if "COST" in df.columns else None
    default_promo = "PROMOTION" if "PROMOTION" in df.columns else None
    name_col = st.sidebar.selectbox("产品名称列", [None] + list(df.columns), index=(list(df.columns).index(default_name)+1 if default_name in list(df.columns) else 0))
    cost_col = st.sidebar.selectbox("普通成本列（COST）", [None] + list(df.columns), index=(list(df.columns).index(default_cost)+1 if default_cost in list(df.columns) else 0))
    promo_cost_col = st.sidebar.selectbox("促销成本列（PROMOTION，可选）", [None] + list(df.columns), index=(list(df.columns).index(default_promo)+1 if default_promo in list(df.columns) else 0))
    promo_price_col = st.sidebar.selectbox("促销售价列（PROMO SELLING PRICE，可选）", [None] + list(df.columns))
    guess_price_cols = [c for c in df.columns if re.search(r"price|sell|selling|PRICE", str(c), re.I)]
    price_cols = st.sidebar.multiselect("普通卖价列（可多选，支持多分隔符）", list(df.columns), default=guess_price_cols[:2] if guess_price_cols else [])

    # 平台抽成与个人抽成（默认从 fee config 中带入）
    st.sidebar.header("🏷️ 抽成/设置")
    fee_country = fee_df[fee_df["country"] == country]
    platform_choice = None
    platform_fee_pct = 0.0
    if not fee_country.empty:
        fee_country = fee_country.copy()
        fee_country["display"] = fee_country["platform"] + " — " + fee_country["scenario"] + "（" + fee_country["remark"].fillna("") + "）"
        platform_choice = st.sidebar.selectbox("选择平台/活动方案", fee_country["display"].tolist())
        platform_fee_pct = float(fee_country.loc[fee_country["display"] == platform_choice, "fee_pct"].iloc[0])
    else:
        platform_fee_pct = st.sidebar.number_input("平台费率（%）", value=5.0, step=0.1)

    if platform_choice:
        platform_fee_pct = st.sidebar.number_input("平台费率（%） - 手动覆盖", value=float(platform_fee_pct), step=0.1)

    personal_commission_pct = st.sidebar.number_input("个人抽成（%）", value=0.0, step=0.1)

    # 高利润阈值
    profit_threshold = st.sidebar.number_input("高利润阈值 (MYR)", value=50.0, step=1.0)

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
                prices = []
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
                    f"成本 ({COUNTRY_CURRENCY[country]})": round(base_cost, 2),
                    f"卖价 ({COUNTRY_CURRENCY[country]})": round(price, 2),
                    f"平台抽成 ({COUNTRY_CURRENCY[country]})": round(platform_fee_local, 2),
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

            # 产品筛选
            st.sidebar.header("🔎 产品筛选")
            all_products = sorted(result_df["产品名称"].unique().tolist())
            search_term = st.sidebar.text_input("🔍 搜索产品（支持模糊匹配）")
            filtered_products = [p for p in all_products if search_term.lower() in str(p).lower()] if search_term else all_products
            selected_products = st.sidebar.multiselect("选择要显示的产品", filtered_products, default=filtered_products)
            filtered_df = result_df[result_df["产品名称"].isin(selected_products)]

            # 展示（带颜色说明）
            st.subheader("📊 计算结果（已按利润高低排序）")
            st.markdown(f"""
            **颜色提示：**  
            🟨 黄色 → 使用促销价  
            🟥 红色 → 利润 < 0 (亏损)  
            🟩 绿色 → 利润 > {profit_threshold} MYR (高利润)  
            """)

            if filtered_df.empty:
                st.warning("⚠️ 没有符合条件的产品数据")
            else:
                sty = style_results(filtered_df, profit_threshold)
                st.write(sty, unsafe_allow_html=True)

                # 利润对比图
                st.subheader("📈 产品利润对比（MYR）")
                try:
                    import altair as alt
                    chart_data = filtered_df.groupby(["产品名称", "来源", f"卖价 ({COUNTRY_CURRENCY[country]})"])["利润 (MYR)"].sum().reset_index()
                    chart = (
                        alt.Chart(chart_data)
                        .mark_bar()
                        .encode(
                            x=alt.X("产品名称:N", sort="-y"),
                            y=alt.Y("利润 (MYR):Q"),
                            color=alt.Color("来源:N"),
                            tooltip=list(chart_data.columns)
                        )
                        .properties(height=400)
                    )
                    st.altair_chart(chart, use_container_width=True)
                except Exception:
                    st.bar_chart(filtered_df.set_index("产品名称")["利润 (MYR)"])

                # 导出 Excel（保留两位小数）
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                    result_df.to_excel(writer, index=False, sheet_name="All_Results")
                    filtered_df.to_excel(writer, index=False, sheet_name="Filtered_Results")
                st.download_button("⬇️ 下载结果 Excel", data=buffer.getvalue(), file_name=f"profit_results_{country}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.warning("请至少映射：产品名 + 成本(普通或促销) + 卖价(促销或普通价列)")

# ============== 结束 ==============
st.caption("说明：本工具只抓取公开信息（示范），不会登录任何平台。费率/汇率请按实际业务情况确认。")
