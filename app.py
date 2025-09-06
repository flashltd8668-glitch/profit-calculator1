# app.py
# -*- coding: utf-8 -*-

import streamlit as st
import pandas as pd
import numpy as np
import os, io, json, shutil, re
import requests
from datetime import datetime
from pathlib import Path

# ============== 基本设置 ==============
st.set_page_config(page_title="Profit Calculator — Multi-Country", layout="wide")
st.title("💰 多国家利润计算器（安全版｜自动促销优先｜费率配置管理）")

# 目录与文件
BASE_DIR = Path(".")
UPLOAD_DIR = BASE_DIR / "uploads"
META_FILE = BASE_DIR / "file_metadata.csv"
CONFIG_FILE = BASE_DIR / "platform_fees.csv"
CONFIG_HISTORY_DIR = BASE_DIR / "config_history"
RATES_FILE = BASE_DIR / "exchange_rates.json"

# 保证目录存在
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

# 初始化上传记录表
if not META_FILE.exists():
    pd.DataFrame(columns=["country", "filename", "filepath", "upload_date"]).to_csv(META_FILE, index=False)

# 国家与币种
COUNTRY_CURRENCY = {
    "Thailand": "THB",
    "Malaysia": "MYR",
    "Vietnam": "VND",
    "Philippines": "PHP",
    "Indonesia": "IDR",
}

# 默认汇率（1 本币 = ? MYR）
DEFAULT_RATES = {
    "THB": 7.8,
    "MYR": 1.0,
    "VND": 5400.0,   # 示例：1 MYR ≈ 5400 VND（这里只做占位，实际请按你需要）
    "PHP": 12.0,     # 示例占位
    "IDR": 3400.0,   # 示例占位
}

# 读取/初始化汇率文件
def load_exchange_rates():
    if RATES_FILE.exists():
        try:
            return json.loads(RATES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    # 初始化：以 DEFAULT_RATES 为主；保证所有币种都有值
    rates = {}
    for cur in COUNTRY_CURRENCY.values():
        rates[cur] = DEFAULT_RATES.get(cur, 1.0)
    RATES_FILE.write_text(json.dumps(rates, ensure_ascii=False, indent=2), encoding="utf-8")
    return rates

def save_exchange_rates(rates: dict):
    RATES_FILE.write_text(json.dumps(rates, ensure_ascii=False, indent=2), encoding="utf-8")

# 初始化/加载平台费率配置：如果没有就创建一个示例文件
def ensure_config_file():
    if not CONFIG_FILE.exists():
        demo = pd.DataFrame([
            # 你可以按需调整示例费率；后续也可上传CSV覆盖
            ["Thailand","Shopee","基础佣金",9,"未参加任何活动"],
            ["Thailand","Lazada","Full（FS+LazCoin）",13,"含 Free Shipping + LazCoin（示例）"],
            ["Thailand","Lazada","无 LazCoin（参加 FS）",11,"不含 LazCoin，含 Free Shipping（示例）"],
            ["Thailand","Lazada","无 Free Shipping（参加 LazCoin）",11,"不含 Free Shipping，含 LazCoin（示例）"],
            ["Thailand","Lazada","无活动",8,"只收佣金+支付手续费（示例）"],
            ["Malaysia","Shopee","基础佣金",8,"未参加任何活动（示例）"],
            ["Malaysia","Lazada","Full（FS+LazCoin）",14,"含 Free Shipping + LazCoin（示例）"],
            ["Vietnam","Lazada","Full（FS+LazCoin）",12,"示例"],
            ["Philippines","Lazada","Full（FS+LazCoin）",12,"示例"],
            ["Indonesia","Lazada","Full（FS+LazCoin）",12,"示例"],
        ], columns=["country","platform","scenario","fee_pct","remark"])
        demo.to_csv(CONFIG_FILE, index=False)

def load_fee_config() -> pd.DataFrame:
    ensure_config_file()
    return pd.read_csv(CONFIG_FILE)

def save_fee_config(df: pd.DataFrame, keep_history: bool = True):
    df.to_csv(CONFIG_FILE, index=False)
    if keep_history:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        hist = CONFIG_HISTORY_DIR / f"platform_fees_{ts}.csv"
        shutil.copy(CONFIG_FILE, hist)

fee_df_global = load_fee_config()
rates = load_exchange_rates()

# ============== 安全的公开页面同步（示范函数） ==============
# 仅抓取公开网页（不登录），解析失败则忽略，不覆盖现有配置
def fetch_public_fee_updates():
    """
    仅示范逻辑：
    - 访问公开公告页（这里放示例 URL；你可以替换成真实公开页面）
    - 尝试用正则提取“xx%”数字作为参考
    - 匹配平台关键词，更新到 dataframe（仅演示：不会破坏已有结构）
    """
    sources = [
        # 这里是示例公开页面，部署时请替换为你信任的官方公告/政策页面
        # "https://example.com/lazada/fees",
        # "https://example.com/shopee/fees",
    ]
    updates = []
    for url in sources:
        try:
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                text = r.text
                # 简单示范：抓取“xx%”这样的数字，真实环境你应该针对页面结构更精细解析
                found = re.findall(r"(\d+(?:\.\d+)?)\s*%", text)
                # 假装抓到一些数值：
                for pct in found[:3]:
                    updates.append({"source": url, "fee_pct": float(pct)})
        except Exception:
            # 静默失败，保证安全
            pass
    return updates  # 返回空列表则代表这次没有可用更新

def apply_public_updates_to_config(fee_df: pd.DataFrame, updates: list) -> pd.DataFrame:
    """
    演示把抓到的“公开百分比”应用到配置里：
    - 为了安全起见，这里不直接覆盖，只做一个示范：若抓到的值与现有差异很大，不自动更新
    - 你可以根据业务逻辑自行增强匹配规则（按国家/平台/场景等）
    """
    if not updates:
        return fee_df

    df = fee_df.copy()
    # 示例策略：把第一条抓到的 fee_pct（若合理）更新到某一条 Lazada Full（Thailand）上
    for u in updates:
        new_pct = u.get("fee_pct")
        if new_pct is None:
            continue
        # 判断合理区间（例如在 3%~25% 之间）
        if 3 <= new_pct <= 25:
            mask = (df["country"] == "Thailand") & (df["platform"] == "Lazada") & (df["scenario"].str.contains("Full", na=False))
            if mask.any():
                old_val = float(df.loc[mask, "fee_pct"].iloc[0])
                # 变化幅度不超过 50% 才更新（防止异常抓取）
                if abs(new_pct - old_val) / max(old_val, 1e-9) <= 0.5:
                    df.loc[mask, "fee_pct"] = new_pct
                    break
    return df

# ============== 定时任务（每天早上、下午各一次） ==============
# 说明：Streamlit 是“请求即运行”的模型，严格意义的后台常驻任务需要你把应用部署在能常驻的环境，
# 这里我们用 schedule-like 的轻量机制：每次有用户访问时，检查是否到点，若到点就执行一次。
# 若你部署在可长驻进程的环境，可替换为 APScheduler/cron。

def should_run_auto_update(now: datetime):
    # 设定两个时刻（本地时间） 09:00 与 15:00
    # 每个时刻只跑一次。用一个记录文件保存当天是否已跑过。
    flags_dir = BASE_DIR / "auto_flags"
    flags_dir.mkdir(exist_ok=True)
    datestr = now.strftime("%Y%m%d")
    h = now.hour
    mark_0900 = flags_dir / f"{datestr}_0900.done"
    mark_1500 = flags_dir / f"{datestr}_1500.done"
    if h >= 9 and not mark_0900.exists():
        return "0900", mark_0900
    if h >= 15 and not mark_1500.exists():
        return "1500", mark_1500
    return None, None

def auto_update_if_needed():
    now = datetime.now()
    slot, flag_path = should_run_auto_update(now)
    if slot:
        try:
            updates = fetch_public_fee_updates()
            if updates:
                df = load_fee_config()
                new_df = apply_public_updates_to_config(df, updates)
                # 只有实际变化时才保存
                if not new_df.equals(df):
                    save_fee_config(new_df, keep_history=True)
            flag_path.write_text("done", encoding="utf-8")
        except Exception:
            # 自动更新失败时静默，不影响主流程
            pass

# 尝试执行一次自动更新（只在需要的时段且当天未执行时触发）
auto_update_if_needed()

# ============== 侧边栏：国家选择与文件管理 ==============
st.sidebar.header("🌍 国家选择")
countries = list(COUNTRY_CURRENCY.keys())
country = st.sidebar.selectbox("选择国家", countries)
local_currency = COUNTRY_CURRENCY[country]

# 上传文件（按国家分目录保存，去重保最新）
st.sidebar.header("📤 上传价钱表")
uploaded_file = st.sidebar.file_uploader(f"上传 {country} 的 Excel/CSV（标题行在第2行）", type=["xlsx", "xls", "csv"])
if uploaded_file:
    save_dir = UPLOAD_DIR / country
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / uploaded_file.name
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    meta_df = pd.read_csv(META_FILE)
    # 删除同国家+同名旧记录
    meta_df = meta_df[~((meta_df["country"] == country) & (meta_df["filename"] == uploaded_file.name))]
    # 新记录
    new_record = pd.DataFrame([{
        "country": country,
        "filename": uploaded_file.name,
        "filepath": str(save_path),
        "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }])
    meta_df = pd.concat([meta_df, new_record], ignore_index=True)
    meta_df.to_csv(META_FILE, index=False)
    st.sidebar.success("✅ 文件已保存（同名文件保留最新记录）")

# 历史文件选择 + 删除
st.sidebar.header("📁 已上传文件")
meta_df_all = pd.read_csv(META_FILE)
country_files = meta_df_all[meta_df_all["country"] == country]
selected_file = None
if not country_files.empty:
    selected_file = st.sidebar.selectbox(
        "选择文件",
        country_files.sort_values("upload_date", ascending=False)["filename"].tolist()
    )
    if selected_file:
        info = country_files[country_files["filename"] == selected_file].iloc[0]
        st.sidebar.caption(f"最后上传：{info['upload_date']}")

        if st.sidebar.button(f"🗑️ 删除此文件: {selected_file}"):
            try:
                fp = Path(info["filepath"])
                if fp.exists():
                    fp.unlink()
                meta_df_all = meta_df_all.drop(
                    meta_df_all[(meta_df_all["country"] == country) & (meta_df_all["filename"] == selected_file)].index
                )
                meta_df_all.to_csv(META_FILE, index=False)
                st.sidebar.success("✅ 已删除，刷新页面后生效")
                st.stop()
            except Exception as e:
                st.sidebar.error(f"删除失败: {e}")

# 批量删除
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

# ============== 侧边栏：汇率管理（1 本币 = ? MYR） ==============
st.sidebar.header("💱 汇率设置（换算为 MYR）")
for cur in COUNTRY_CURRENCY.values():
    rates[cur] = st.sidebar.number_input(f"1 {cur} = ? MYR", value=float(rates.get(cur, DEFAULT_RATES.get(cur, 1.0))), step=0.01)
if st.sidebar.button("💾 保存汇率"):
    save_exchange_rates(rates)
    st.sidebar.success("✅ 汇率已保存到 exchange_rates.json")

# ============== 侧边栏：平台费率配置管理 ==============
st.sidebar.header("⚙️ 平台费率配置管理")
fee_df = load_fee_config()

# 上传新配置 CSV（校验必需列）
cfg_file = st.sidebar.file_uploader("上传新的 platform_fees.csv", type=["csv"], key="cfg_up")
if cfg_file is not None:
    try:
        new_cfg = pd.read_csv(cfg_file)
        required = {"country","platform","scenario","fee_pct","remark"}
        if not required.issubset(set(new_cfg.columns)):
            st.sidebar.error(f"❌ 配置缺少列，请包含：{required}")
        else:
            save_fee_config(new_cfg, keep_history=True)
            st.sidebar.success("✅ 配置已更新并保存历史版本（config_history/）")
            fee_df = load_fee_config()
    except Exception as e:
        st.sidebar.error(f"上传失败：{e}")

# 历史版本回滚
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

# 手动下载当前配置
st.sidebar.download_button(
    label="⬇️ 下载当前 platform_fees.csv",
    data=CONFIG_FILE.read_bytes(),
    file_name="platform_fees.csv",
    mime="text/csv",
)

# 手动触发一次公开公告同步（安全，不登录）
if st.sidebar.button("🔁 从公开公告尝试同步（安全）"):
    try:
        up = fetch_public_fee_updates()
        new_df = apply_public_updates_to_config(fee_df, up)
        if not new_df.equals(fee_df):
            save_fee_config(new_df, keep_history=True)
            st.sidebar.success("✅ 已基于公开信息更新（示范），并保存历史版本")
            fee_df = load_fee_config()
        else:
            st.sidebar.info("ℹ️ 本次没有找到可应用的公开更新或差异不大")
    except Exception as e:
        st.sidebar.error(f"同步失败：{e}")

with st.expander("📄 当前费率配置预览"):
    st.dataframe(fee_df, use_container_width=True)

# 费率图表 + 过滤器
st.subheader("🌍 各国家平台费率对比（可筛选）")
c1, c2, c3 = st.columns([1,1,1])
with c1:
    country_filter = st.multiselect("筛选国家", sorted(fee_df["country"].unique().tolist()))
with c2:
    platform_filter = st.multiselect("筛选平台", sorted(fee_df["platform"].unique().tolist()))
with c3:
    scenario_query = st.text_input("按方案关键词搜索（如“无活动”/“Free Shipping”）")

fee_show = fee_df.copy()
if country_filter:
    fee_show = fee_show[fee_show["country"].isin(country_filter)]
if platform_filter:
    fee_show = fee_show[fee_show["platform"].isin(platform_filter)]
if scenario_query:
    fee_show = fee_show[fee_show["scenario"].str.contains(scenario_query, case=False, na=False)]

# 汇总表
sum_df = (
    fee_show.groupby(["country","platform"])
    .agg(min_pct=("fee_pct","min"), max_pct=("fee_pct","max"), avg_pct=("fee_pct","mean"), count=("fee_pct","count"))
    .reset_index()
)
st.dataframe(sum_df, use_container_width=True)

# 可视化（使用 Altair）
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
    sel_info = country_files[country_files["filename"] == selected_file].iloc[0]
    fpath = Path(sel_info["filepath"])
    if fpath.suffix.lower() in [".xlsx",".xls"]:
        # 你的表格第二行是表头（header=1）
        df = pd.read_excel(fpath, header=1)
    else:
        df = pd.read_csv(fpath)

if df is not None and not df.empty:
    st.subheader("📋 数据预览")
    st.dataframe(df.head(), use_container_width=True)

    # ===== 字段映射（根据你Excel固定模板） =====
orig_cols = list(df.columns)

# 默认映射规则（确保有 fallback）
default_name_col = "DESCRIPTION" if "DESCRIPTION" in orig_cols else orig_cols[0]
default_cost_col = "COST" if "COST" in orig_cols else None
default_promo_cost_col = "PROMOTION" if "PROMOTION" in orig_cols else None

# 卖价列完全手动选择（不给默认值）
price_candidates = []


# 在侧边栏显示（可手动调整）
st.sidebar.header("🧩 字段映射")
name_col = st.sidebar.selectbox("产品名称列", orig_cols, index=orig_cols.index(default_name_col))
cost_col = st.sidebar.selectbox("普通成本列（Cost）", [None] + orig_cols,
                                index=(orig_cols.index(default_cost_col) + 1 if default_cost_col else 0))
promo_cost_col = st.sidebar.selectbox("促销成本列（Promotion，可选）", [None] + orig_cols,
                                      index=(orig_cols.index(default_promo_cost_col) + 1 if default_promo_cost_col else 0))
promo_price_col = st.sidebar.selectbox("促销售价列（Promo Selling Price，可选）", [None] + orig_cols)

price_cols = st.sidebar.multiselect("普通卖价列（可多选，支持 199/299 用 '/' 分隔）",
                                    orig_cols, default=price_candidates)


    # ===== 平台抽成（来自配置 + 可手调） =====
    st.sidebar.header("🏷️ 平台抽成设置")
    fee_country = fee_df[fee_df["country"] == country]
    if fee_country.empty:
        st.sidebar.warning("当前国家暂无费率方案，请先在『平台费率配置管理』里添加/上传")
        platform_choice = "自定义"
        default_fee_pct = 0.0
    else:
        # 合成展示名：Platform — Scenario（Remark）
        fee_country = fee_country.copy()
        fee_country["display"] = fee_country["platform"] + " — " + fee_country["scenario"] + "（" + fee_country["remark"].fillna("") + "）"
        platform_choice = st.sidebar.selectbox("选择平台/活动方案", fee_country["display"].tolist())
        default_fee_pct = float(fee_country.loc[fee_country["display"] == platform_choice, "fee_pct"].iloc[0])

    platform_fee_pct = st.sidebar.number_input("平台费率（%）", value=default_fee_pct, step=0.1)

    # 个人抽成（MYR）
    personal_commission_pct = st.sidebar.number_input("个人抽成（%）", value=0.0, step=0.1)

    # ===== 计算 =====
    if name_col and (promo_price_col or price_cols) and (promo_cost_col or cost_col):
        records = []
        conv = float(rates[local_currency]) if float(rates[local_currency]) > 0 else 1.0

        for _, row in df.iterrows():
            product = row.get(name_col, "")

            # 优先：促销成本 + 促销售价
            use_promo = False
            base_cost = None
            prices = []

            if promo_cost_col and promo_price_col and pd.notna(row.get(promo_cost_col)) and pd.notna(row.get(promo_price_col)):
                base_cost = pd.to_numeric(row.get(promo_cost_col), errors="coerce")
                prices = str(row.get(promo_price_col)).split("/")
                use_promo = True
            else:
                base_cost = pd.to_numeric(row.get(cost_col), errors="coerce") if cost_col else np.nan
                prices = []
                for col in price_cols:
                    if col in df.columns:
                        prices.extend(str(row.get(col)).split("/"))
                use_promo = False

            if pd.isna(base_cost):
                base_cost = 0.0

            for raw_p in prices:
                try:
                    price = float(str(raw_p).strip())
                except Exception:
                    continue

                # 平台抽成（按价格 * 费率）
                platform_fee_local = price * (platform_fee_pct / 100.0)
                profit_local = price - base_cost - platform_fee_local
                margin_pct = (profit_local / price * 100.0) if price > 0 else np.nan

                # 个人抽成基于利润
                personal_comm_local = profit_local * (personal_commission_pct / 100.0)

                # 换 MYR
                profit_myr = profit_local / conv
                personal_comm_myr = personal_comm_local / conv

                records.append({
                    "产品名称": product,
                    f"成本 ({local_currency})": base_cost,
                    f"卖价 ({local_currency})": price,
                    f"平台抽成 ({local_currency})": platform_fee_local,
                    "利润 (MYR)": profit_myr,
                    "利润率 %": margin_pct,
                    "个人抽成 (MYR)": personal_comm_myr,
                    "来源": "Promotion" if use_promo else "Normal",
                    "平台方案": platform_choice,
                })

        result_df = pd.DataFrame(records)
        if not result_df.empty:
            result_df = result_df.sort_values(by="利润 (MYR)", ascending=False).reset_index(drop=True)

            # ===== 搜索/筛选 =====
            st.sidebar.header("🔎 产品筛选")
            all_products = sorted(result_df["产品名称"].dropna().unique().tolist())
            keyword = st.sidebar.text_input("搜索关键词（模糊匹配）")
            if keyword:
                filtered_names = [p for p in all_products if keyword.lower() in str(p).lower()]
            else:
                filtered_names = all_products
            selected = st.sidebar.multiselect("选择要显示的产品", filtered_names, default=filtered_names)

            filtered_df = result_df[result_df["产品名称"].isin(selected)]

            # ===== 表格展示（MYR 金额带符号） =====
            st.subheader("📊 计算结果（按利润从高到低）")
            if filtered_df.empty:
                st.warning("没有符合条件的数据")
            else:
                disp = filtered_df.copy()
                disp["利润 (MYR)"] = disp["利润 (MYR)"].map(lambda x: f"RM {x:,.2f}")
                disp["个人抽成 (MYR)"] = disp["个人抽成 (MYR)"].map(lambda x: f"RM {x:,.2f}")
                st.dataframe(disp, use_container_width=True)

                # ===== 图表：产品利润对比 =====
                st.subheader("📈 产品利润对比（MYR）")
                try:
                    import altair as alt
                    chart_data = filtered_df.groupby(["产品名称", "来源", f"卖价 ({local_currency})"])["利润 (MYR)"].sum().reset_index()
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

                # ===== 导出 Excel =====
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                    # Settings
                    settings_df = pd.DataFrame({
                        "Setting": [
                            "Country","Local Currency",
                            "Exchange (1 Local = ? MYR)",
                            "Platform Scheme","Platform Fee %",
                            "Personal Commission %",
                            "Selected File","Generated At"
                        ],
                        "Value": [
                            country, local_currency,
                            rates[local_currency],
                            platform_choice, platform_fee_pct,
                            personal_commission_pct,
                            selected_file, datetime.now().strftime("%Y-%m-%d %H:%M")
                        ]
                    })
                    settings_df.to_excel(writer, index=False, sheet_name="Settings")
                    result_df.to_excel(writer, index=False, sheet_name="All_Results")
                    filtered_df.to_excel(writer, index=False, sheet_name="Filtered_Results")

                st.download_button(
                    label="⬇️ 下载结果 Excel",
                    data=buffer.getvalue(),
                    file_name=f"profit_results_{country}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.info("未解析到有效的价格。请检查列映射或价格格式（支持 '199/299' 用 '/' 分隔）。")
    else:
        st.warning("请至少映射：产品名、成本（普通或促销）、卖价（促销或普通价列）")
else:
    st.info("左侧选择一个已上传文件开始计算。")
