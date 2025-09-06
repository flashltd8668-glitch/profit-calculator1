import streamlit as st
import pandas as pd
import numpy as np
import io

st.set_page_config(page_title="Profit Calculator — Mobile/Desktop + Multi-Currency", layout="wide")

st.title("📊 Universal Profit Calculator — Ultimate Edition")

st.write("Upload your Excel/CSV file and map the columns. Compare multiple price columns, choose input/output currencies, and switch between Mobile/Desktop display modes.")

# File uploader
uploaded_file = st.file_uploader("Upload Excel/CSV file", type=["xlsx", "xls", "csv"])

if uploaded_file:
    try:
        if uploaded_file.name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(uploaded_file, header=1)  # Skip first row (merged header)
        else:
            df = pd.read_csv(uploaded_file)
    except Exception:
        try:
            df = pd.read_excel(uploaded_file)
        except Exception:
            df = pd.read_csv(uploaded_file, encoding_errors='ignore')

    st.subheader("Preview Data")
    st.dataframe(df.head())

    # Column mapping
    st.sidebar.header("Map Your Columns")
    cost_col = st.sidebar.selectbox("Select Cost Column", [None] + list(df.columns))
    price_cols = st.sidebar.multiselect("Select Price Columns", list(df.columns))
    qty_col = st.sidebar.selectbox("Select Quantity Column (optional)", [None] + list(df.columns))
    platform_col = st.sidebar.selectbox("Select Platform Column (optional)", [None] + list(df.columns))
    currency_col = st.sidebar.selectbox("Select Currency Column (optional)", [None] + list(df.columns))

    # Currency settings
    st.sidebar.header("Currency Settings")
    input_currency = st.sidebar.text_input("Input Currency (in your file)", "THB")
    output_currency = st.sidebar.text_input("Output Currency (for results)", "THB")
    conversion_rate = st.sidebar.number_input("Conversion Rate (1 {} = ? {})".format(input_currency, output_currency), value=1.0)

    # Fees & Commission
    st.sidebar.header("Fees & Commission")
    platform_fee_pct = st.sidebar.number_input("Platform Fee (%)", value=5.0)
    platform_fee_fixed = st.sidebar.number_input("Platform Fee (Fixed)", value=0.0)
    commission_pct = st.sidebar.number_input("Personal Commission (%)", value=0.0)

    # Display mode
    st.sidebar.header("Display Mode")
    display_mode = st.sidebar.radio("Choose Display Mode", ["Desktop (Full Columns)", "Mobile (Simplified)"])

    if cost_col and price_cols:
        df_calc = df.copy()

        # Quantity
        qty = pd.to_numeric(df_calc[qty_col], errors="coerce").fillna(1) if qty_col else pd.Series(1, index=df_calc.index)
        cost = pd.to_numeric(df_calc[cost_col], errors="coerce").fillna(0)

        comparison_records = []
        result_df = df_calc.copy()

        for pcol in price_cols:
            price = pd.to_numeric(df_calc[pcol], errors="coerce").fillna(0)
            revenue_in = price * qty
            total_cost_in = cost * qty
            platform_fee_in = (revenue_in * (platform_fee_pct / 100.0)) + platform_fee_fixed
            commission_in = revenue_in * (commission_pct / 100.0)
            profit_in = revenue_in - total_cost_in - platform_fee_in - commission_in
            margin = np.where(revenue_in > 0, (profit_in / revenue_in) * 100, np.nan)

            # Convert to output currency
            revenue = revenue_in / conversion_rate
            total_cost = total_cost_in / conversion_rate
            platform_fee = platform_fee_in / conversion_rate
            commission = commission_in / conversion_rate
            profit = profit_in / conversion_rate

            # Save per-row results
            result_df[f"Price__{pcol}"] = price
            result_df[f"Revenue__{pcol} ({output_currency})"] = revenue
            result_df[f"Cost__{pcol} ({output_currency})"] = total_cost
            result_df[f"PlatformFee__{pcol} ({output_currency})"] = platform_fee
            result_df[f"Commission__{pcol} ({output_currency})"] = commission
            result_df[f"Profit__{pcol} ({output_currency})"] = profit
            result_df[f"Margin%__{pcol}"] = margin

            comparison_records.append({
                "Price Column": pcol,
                f"Total Revenue ({output_currency})": float(revenue.sum()),
                f"Total Cost ({output_currency})": float(total_cost.sum()),
                f"Total Fees ({output_currency})": float(platform_fee.sum() + commission.sum()),
                f"Total Profit ({output_currency})": float(profit.sum()),
                "Average Margin %": float(np.nanmean(margin))
            })

        comp_df = pd.DataFrame(comparison_records).sort_values(by=f"Total Profit ({output_currency})", ascending=False)

        st.subheader("Comparison Summary")
        st.dataframe(comp_df.reset_index(drop=True))
        try:
            st.bar_chart(comp_df.set_index('Price Column')[f'Total Profit ({output_currency})'])
        except Exception:
            pass

        if display_mode == "Desktop (Full Columns)":
            st.subheader("Item-level Results (Full)")
            st.dataframe(result_df)
        else:
            st.subheader("Item-level Results (Mobile Simplified)")
            simplified_cols = [cost_col] + [f"Price__{p}" for p in price_cols] + [f"Profit__{p} ({output_currency})" for p in price_cols] + [f"Margin%__{p}" for p in price_cols]
            simplified_cols = [c for c in simplified_cols if c in result_df.columns]
            st.dataframe(result_df[simplified_cols])

        # Excel Export with Settings Sheet
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            # Write settings info
            settings_df = pd.DataFrame({
                "Setting": ["Input Currency", "Output Currency", "Conversion Rate", "Platform Fee %", "Platform Fee Fixed", "Commission %"],
                "Value": [input_currency, output_currency, conversion_rate, platform_fee_pct, platform_fee_fixed, commission_pct]
            })
            settings_df.to_excel(writer, index=False, sheet_name="Settings")

            # Write results
            result_df.to_excel(writer, index=False, sheet_name="ItemLevel")
            comp_df.to_excel(writer, index=False, sheet_name="ComparisonSummary")

        st.download_button(
            label="Download Full Results as Excel",
            data=buffer.getvalue(),
            file_name="profit_results_full.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("Please map at least Cost and one or more Price columns to proceed.")
