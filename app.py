from pathlib import Path
import sys
from datetime import datetime
from io import BytesIO
import re

import pandas as pd
import streamlit as st
import plotly.express as px

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from procureiq import (
    load_csv, suggest_mapping, normalize_columns, clean_transactions,
    build_kpis, spend_by, supplier_scorecard, category_scorecard,
    flag_opportunities, candidate_supplier_duplicates, supplier_normalization,
    detect_duplicate_transactions, spend_concentration, generate_insights,
    build_executive_report, monthly_spend_analysis, maverick_spend_proxy,
)


def _excel_bytes(sheets):
    """Build an Excel workbook in memory from named DataFrames."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            safe_name = re.sub(r"[\\[\\]:*?/\\\\]", "_", str(name))[:31] or "Sheet"
            export_frame = frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame(frame)
            if export_frame.empty and len(export_frame.columns) == 0:
                export_frame = pd.DataFrame({"info": ["No records available for this analysis."]})
            export_frame.to_excel(writer, sheet_name=safe_name, index=False)
    output.seek(0)
    return output.getvalue()


st.set_page_config(page_title="ProcureIQ | Spend Analytics", page_icon="📊", layout="wide")
st.title("ProcureIQ")
st.caption("Procurement Spend Analytics & Cost Optimization | Portfolio project")
st.markdown("Explore spend patterns, supplier concentration, data-quality issues and reviewable cost-optimization opportunities.")

with st.sidebar:
    st.header("Data")
    uploaded = st.file_uploader("Upload a CSV downloaded from Kaggle", type=["csv"])
    default_path = ROOT / "data" / "raw" / "company_purchasing_dataset.csv"
    if uploaded is not None:
        raw = load_csv(uploaded)
        source_label = uploaded.name
    elif default_path.exists():
        raw = load_csv(default_path)
        source_label = default_path.name
    else:
        st.info("No Kaggle CSV found. Using the included clearly labelled demo dataset.")
        raw = load_csv(ROOT / "data" / "demo_procurement.csv")
        source_label = "demo_procurement.csv (synthetic demo)"
    st.caption(f"Loaded: {source_label} · {len(raw):,} rows")

if raw.empty:
    st.error("The selected file is empty or could not be parsed as CSV. Please check the file and try again.")
    st.stop()

suggested = suggest_mapping(raw.columns)
with st.sidebar:
    st.header("Column mapping")
    st.caption("Check auto-detected fields and change any mapping that doesn't match your dataset.")
    cols = ["(not available)"] + list(raw.columns)
    def choose(label, key):
        guess = suggested.get(key)
        index = cols.index(guess) if guess in cols else 0
        selected = st.selectbox(label, cols, index=index, key=f"map_{key}")
        return None if selected == "(not available)" else selected
    mapping = {
        "amount": choose("Spend / total cost (required)", "amount"),
        "supplier": choose("Supplier / vendor", "supplier"),
        "category": choose("Category", "category"),
        "date": choose("Order / transaction date", "date"),
        "item": choose("Item / description", "item"),
        "quantity": choose("Quantity", "quantity"),
        "unit_price": choose("Unit price", "unit_price"),
        "department": choose("Department / buyer", "department"),
        "po_number": choose("PO number (optional)", "po_number"),
        "transaction_id": choose("Transaction ID (optional)", "transaction_id"),
    }

if not mapping["amount"]:
    st.error("Select the column containing total spend/cost in the sidebar.")
    st.stop()

df = normalize_columns(raw, mapping)
df, quality = clean_transactions(df)
if df.empty:
    st.error("No usable records remain after validation. Check the spend column mapping and source values.")
    st.stop()


# Preserve the full validated dataset; filters control the analytical view.
df_all = df.copy()
with st.sidebar:
    st.divider()
    st.header("Analysis filters")
    supplier_values = sorted(df_all["supplier"].dropna().astype(str).unique().tolist())
    category_values = sorted(df_all["category"].dropna().astype(str).unique().tolist())
    chosen_suppliers = st.multiselect("Supplier", supplier_values, default=supplier_values, key="filter_suppliers")
    chosen_categories = st.multiselect("Category", category_values, default=category_values, key="filter_categories")
    date_values = pd.to_datetime(df_all["date"], errors="coerce").dropna()
    selected_dates = None
    if not date_values.empty:
        min_date, max_date = date_values.min().date(), date_values.max().date()
        selected_dates = st.date_input(
            "Purchase date range", value=(min_date, max_date),
            min_value=min_date, max_value=max_date, key="filter_date_range"
        )

df = df_all.copy()
if df["supplier"].notna().any():
    df = df[df["supplier"].isna() | df["supplier"].astype(str).isin(chosen_suppliers)]
if df["category"].notna().any():
    df = df[df["category"].isna() | df["category"].astype(str).isin(chosen_categories)]
if selected_dates and isinstance(selected_dates, (tuple, list)) and len(selected_dates) == 2:
    start_date, end_date = selected_dates
    date_series = pd.to_datetime(df["date"], errors="coerce")
    df = df[date_series.isna() | ((date_series.dt.date >= start_date) & (date_series.dt.date <= end_date))]
if df.empty:
    st.warning("No transactions match the selected filters. Adjust the filters in the sidebar.")
    st.stop()

st.success(f"Analyzing {len(df):,} filtered records from {len(df_all):,} usable records. Spend values use the source dataset's currency; no currency conversion is performed.")
kpis = build_kpis(df)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total spend", f"{kpis['total_spend']:,.2f}")
c2.metric("Transactions", f"{kpis['transactions']:,}")
c3.metric("Average transaction", f"{kpis['average_transaction']:,.2f}")
c4.metric("Supplier count", f"{kpis['supplier_count']:,}" if kpis["supplier_count"] is not None else "Not mapped")

# Executive report is downloadable as a Markdown file, generated from the same data currently analyzed.
report = build_executive_report(df, quality, source_label)
with st.expander("Executive report", expanded=False):
    st.markdown("Download a management-ready summary of KPIs, concentration, category/supplier rankings, and review flags.")
    st.download_button(
        "Download executive report (.md)",
        data=report.encode("utf-8"),
        file_name=f"procureiq_executive_report_{datetime.now().strftime('%Y%m%d')}.md",
        mime="text/markdown",
        key="download_exec_report",
    )

    excel_suppliers = supplier_scorecard(df)
    excel_categories = category_scorecard(df)
    excel_monthly = monthly_spend_analysis(df)
    excel_maverick = maverick_spend_proxy(df)
    excel_opportunities = flag_opportunities(df)
    excel_dupes = detect_duplicate_transactions(df)
    excel_supplier_pairs = candidate_supplier_duplicates(df)
    quality_export = pd.DataFrame([{
        "rows_before_cleaning": quality.get("rows_before_cleaning", 0),
        "rows_after_cleaning": quality.get("rows_after_cleaning", 0),
        "exact_duplicate_rows_removed": quality.get("duplicate_rows_removed", 0),
        "missing_supplier": quality.get("missing_supplier", 0),
        "missing_category": quality.get("missing_category", 0),
        "non_positive_amount": quality.get("non_positive_amount", 0),
        "missing_date": quality.get("missing_date", 0),
        "invalid_amount_rows_removed": quality.get("invalid_amount_rows_removed", 0),
    }])
    summary_export = pd.DataFrame([{
        "data_source": source_label,
        "records_analyzed_after_filters": len(df),
        "total_spend": float(df["amount"].sum()),
        "average_transaction": float(df["amount"].mean()),
        "supplier_count": int(df["supplier"].nunique()) if df["supplier"].notna().any() else 0,
        "currency_note": "Source dataset currency; no conversion performed",
    }])
    excel_data = _excel_bytes({
        "Executive Summary": summary_export,
        "Transactions": df,
        "Supplier Scorecard": excel_suppliers,
        "Category Scorecard": excel_categories,
        "Monthly Trends": excel_monthly,
        "Data Quality": quality_export,
        "Opportunities": excel_opportunities,
        "Duplicate Review": excel_dupes,
        "Supplier Name Review": excel_supplier_pairs,
        "Maverick Spend Proxy": excel_maverick,
    })
    st.download_button(
        "Download Excel analysis pack (.xlsx)",
        data=excel_data,
        file_name=f"procureiq_analysis_pack_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_excel_pack",
    )


tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Overview", "Supplier analysis", "Category analysis", "Data quality",
    "Opportunities", "Duplicates & normalization"
])

with tab1:
    left, right = st.columns(2)
    if df["date"].notna().any():
        monthly = df.dropna(subset=["date"]).assign(month=lambda x: x["date"].dt.to_period("M").astype(str)).groupby("month", as_index=False)["amount"].sum()
        left.plotly_chart(px.line(monthly, x="month", y="amount", markers=True, title="Monthly spend trend"), use_container_width=True)
    else:
        left.info("Map a date column to enable monthly spend trends.")

    st.subheader("Month-over-month spend analysis")
    monthly_analysis = monthly_spend_analysis(df)
    if monthly_analysis.empty:
        st.info("Map a valid purchase date column to enable month-over-month analysis.")
    else:
        chart_monthly = monthly_analysis.copy()
        chart_monthly["month_label"] = pd.to_datetime(chart_monthly["month"]).dt.strftime("%Y-%m")
        st.plotly_chart(
            px.bar(chart_monthly, x="month_label", y="mom_change",
                   title="Month-over-month change in spend",
                   labels={"month_label": "Month", "mom_change": "Change vs previous month"}),
            use_container_width=True,
        )
        display_monthly = chart_monthly.copy()
        display_monthly["month"] = display_monthly["month_label"]
        display_monthly["mom_change_pct"] = display_monthly["mom_change_pct"].round(2)
        st.dataframe(display_monthly[["month", "total_spend", "previous_month_spend", "mom_change", "mom_change_pct"]],
                     use_container_width=True, hide_index=True)

    category = spend_by(df, "category")
    if not category.empty:
        right.plotly_chart(px.bar(category.head(12).sort_values("amount"), x="amount", y="category", orientation="h", title="Spend by category (top 12)"), use_container_width=True)
    else:
        right.info("Map a category column to enable category analysis.")
    st.subheader("Recent transactions")
    st.dataframe(df.head(100), use_container_width=True, hide_index=True)
    st.download_button("Download cleaned transactions", df.to_csv(index=False).encode("utf-8"), "cleaned_transactions.csv", "text/csv")

with tab2:
    suppliers = supplier_scorecard(df)
    if suppliers.empty:
        st.info("Map a supplier/vendor column to enable supplier analysis.")
    else:
        concentration, _ = spend_concentration(df)
        a, b = st.columns(2)
        a.plotly_chart(px.bar(suppliers.head(15).sort_values("total_spend"), x="total_spend", y="supplier", orientation="h", title="Top suppliers by spend"), use_container_width=True)
        b.plotly_chart(px.pie(suppliers.head(8), names="supplier", values="total_spend", title="Spend share: top suppliers"), use_container_width=True)
        m1, m2, m3 = st.columns(3)
        m1.metric("Top 2 supplier share", f"{concentration['top_2_share_pct']:.2f}%")
        m2.metric("Top 5 supplier share", f"{concentration['top_5_share_pct']:.2f}%")
        m3.metric("Supplier HHI", f"{concentration['hhi']:.1f}")
        st.caption(concentration["interpretation"])
        st.dataframe(suppliers, use_container_width=True, hide_index=True)
        st.download_button("Download supplier scorecard", suppliers.to_csv(index=False).encode(), "supplier_scorecard.csv", "text/csv")

with tab3:
    categories = category_scorecard(df)
    if categories.empty:
        st.info("Map a category column to enable category analysis.")
    else:
        st.plotly_chart(px.bar(categories.head(20).sort_values("total_spend"), x="total_spend", y="category", orientation="h", title="Category spend ranking"), use_container_width=True)
        st.dataframe(categories, use_container_width=True, hide_index=True)
        st.download_button("Download category scorecard", categories.to_csv(index=False).encode(), "category_scorecard.csv", "text/csv")

with tab4:
    st.subheader("Data quality checks")
    st.write("Checks are diagnostic flags, not automatic proof that a record is incorrect.")
    q1, q2, q3 = st.columns(3)
    q1.metric("Missing supplier", quality.get("missing_supplier", 0))
    q2.metric("Missing category", quality.get("missing_category", 0))
    q3.metric("Non-positive spend", quality.get("non_positive_amount", 0))
    q4, q5, q6 = st.columns(3)
    q4.metric("Exact duplicate rows removed", quality.get("duplicate_rows_removed", 0))
    q5.metric("Missing/unparseable date", quality.get("missing_date", 0))
    q6.metric("Invalid amount rows removed", quality.get("invalid_amount_rows_removed", 0))
    dupes = candidate_supplier_duplicates(df)
    st.subheader("Potential supplier name duplicates")
    if dupes.empty:
        st.info("No likely name variants found, or supplier column isn't mapped. Review normalized names manually.")
    else:
        st.dataframe(dupes, use_container_width=True, hide_index=True)
        st.download_button("Download supplier duplicate candidates", dupes.to_csv(index=False).encode(), "supplier_duplicate_candidates.csv", "text/csv")
    st.caption("Supplier name matching is heuristic. Review candidates before merging supplier records.")

with tab5:
    opps = flag_opportunities(df)
    if opps.empty:
        st.info("No rule-based opportunity flags were generated from the available fields.")
    else:
        st.dataframe(opps, use_container_width=True, hide_index=True)
        st.download_button("Download opportunity flags", opps.to_csv(index=False).encode(), "spend_opportunities.csv", "text/csv")
    st.subheader("Narrative summary")
    for insight in generate_insights(df):
        st.markdown(f"- {insight}")
    st.caption("Flags indicate areas to investigate, not confirmed savings, fraud, or policy violations.")

    st.divider()
    st.subheader("Maverick spend proxy: out-of-pattern transactions")
    st.caption("No contract or purchasing-policy fields are available, so this is not true maverick-spend detection. It flags positive transactions above a category-specific IQR threshold for analyst review.")
    proxy = maverick_spend_proxy(df)
    if proxy.empty:
        st.info("No category-level out-of-pattern transactions met the screening threshold, or categories have too few records.")
    else:
        st.warning(f"{len(proxy)} transactions flagged for review. These are statistical outliers, not confirmed policy violations.")
        st.dataframe(proxy, use_container_width=True, hide_index=True)
        st.download_button("Download maverick spend proxy review", proxy.to_csv(index=False).encode("utf-8"), "maverick_spend_proxy.csv", "text/csv")



with tab6:
    st.subheader("Potential duplicate transaction detection")
    st.caption("Because this dataset has no invoice ID or contract ID, this check compares supplier, amount and available item/date/quantity/unit-price fields. These are candidates for review, not confirmed duplicates.")
    transaction_dupes = detect_duplicate_transactions(df)
    if transaction_dupes.empty:
        st.success("No potential duplicate transaction groups detected using the available matching fields.")
    else:
        st.warning(f"{len(transaction_dupes)} rows belong to potential duplicate transaction groups. Review the records before taking action.")
        st.dataframe(transaction_dupes, use_container_width=True, hide_index=True)
        st.download_button("Download duplicate transaction review", transaction_dupes.to_csv(index=False).encode(), "duplicate_transaction_review.csv", "text/csv")

    st.divider()
    st.subheader("Supplier normalization")
    normalized = supplier_normalization(df)
    if mapping.get("supplier") is None:
        st.warning("Map a supplier/vendor column in the sidebar to enable normalization.")
    else:
        st.caption("The source supplier name is preserved. Normalized keys are for candidate matching only; never merge records automatically.")
        st.dataframe(normalized[["supplier", "supplier_normalized", "supplier_normalization_note"]].drop_duplicates().head(500), use_container_width=True, hide_index=True)
        st.download_button("Download normalized supplier list", normalized[["supplier", "supplier_normalized", "supplier_normalization_note"]].drop_duplicates().to_csv(index=False).encode(), "supplier_normalization_review.csv", "text/csv")
        supplier_pairs = candidate_supplier_duplicates(df)
        st.subheader("Potential duplicate supplier pairs")
        if supplier_pairs.empty:
            st.info("No supplier-name pairs exceeded the similarity threshold.")
        else:
            st.dataframe(supplier_pairs, use_container_width=True, hide_index=True)
            st.download_button("Download supplier pair review", supplier_pairs.to_csv(index=False).encode(), "supplier_pair_review.csv", "text/csv")

st.divider()
st.caption("Portfolio demonstration. Review heuristic flags before acting; results depend on the selected dataset and column mappings.")
