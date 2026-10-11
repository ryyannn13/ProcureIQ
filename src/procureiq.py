"""Reusable cleaning and analytics functions for ProcureIQ."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

import pandas as pd
import numpy as np

CANONICAL = [
    "amount", "supplier", "category", "date", "item", "quantity", "unit_price",
    "department", "po_number", "contract_id", "invoice_id", "transaction_id",
]

ALIASES = {
    "amount": ["amount", "total cost", "total_cost", "spend", "purchase amount", "purchase_amount",
               "total amount", "total_amount", "line total", "line_total", "cost", "extended price",
               "extended_price", "value", "net amount", "net_amount", "total spend", "total_spend"],
    "supplier": ["supplier", "supplier name", "supplier_name", "vendor", "vendor name", "vendor_name",
                 "supplier_name_clean", "seller", "company"],
    "category": ["category", "spend category", "spend_category", "product category", "product_category",
                 "item category", "item_category", "material group", "material_group", "type"],
    "date": ["date", "order date", "order_date", "purchase date", "purchase_date", "po date", "po_date",
             "transaction date", "transaction_date", "created date", "created_date", "invoice date"],
    "item": ["item", "item name", "item_name", "description", "item description", "item_description",
             "product", "product name", "product_name", "material", "material description"],
    "quantity": ["quantity", "qty", "units", "order quantity", "order_quantity"],
    "unit_price": ["unit price", "unit_price", "price per unit", "price_per_unit", "price", "unit cost", "unit_cost"],
    "department": ["department", "buyer", "business unit", "business_unit", "cost centre", "cost_center", "requester"],
    "po_number": ["po number", "po_number", "purchase order", "purchase_order", "purchase order id", "po id", "transaction id"],
    "contract_id": ["contract id", "contract_id", "contract", "contract number", "contract_number"],
    "invoice_id": ["invoice id", "invoice_id", "invoice number", "invoice_number", "invoice"],
    "transaction_id": ["transaction id", "transaction_id", "transactionid", "record id", "record_id"],
}

def _norm(value: Any) -> str:
    """Lowercase and collapse punctuation/spacing for matching."""
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()

def suggest_mapping(columns):
    normalized = {_norm(c): c for c in columns}
    result = {}
    for target, aliases in ALIASES.items():
        match = None
        for alias in aliases:
            if _norm(alias) in normalized:
                match = normalized[_norm(alias)]
                break
        if match is None:
            for col in columns:
                name = _norm(col)
                scores = [SequenceMatcher(None, name, _norm(a)).ratio() for a in aliases]
                if scores and max(scores) >= 0.91:
                    match = col
                    break
        result[target] = match
    return result

def load_csv(source):
    """Read a CSV with common encodings; return an empty frame for unreadable files."""
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            try:
                source.seek(0)
            except Exception:
                pass
            return pd.read_csv(source, encoding=encoding, sep=None, engine="python", on_bad_lines="warn")
        except (UnicodeDecodeError, pd.errors.ParserError, ValueError, OSError):
            continue
    return pd.DataFrame()

def normalize_columns(raw, mapping):
    """Map source columns to the project's stable schema and validate values."""
    out = pd.DataFrame(index=raw.index)
    for target in CANONICAL:
        source = mapping.get(target)
        out[target] = raw[source] if source and source in raw.columns else pd.NA

    amount_text = (
        out["amount"].astype("string").str.strip()
        .str.replace(r"[₹$€£,\s]", "", regex=True)
        .str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    )
    out["amount"] = pd.to_numeric(amount_text, errors="coerce")
    for col in ["quantity", "unit_price"]:
        cleaned = out[col].astype("string").str.strip().str.replace(",", "", regex=False)
        out[col] = pd.to_numeric(cleaned, errors="coerce")

    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for col in ["supplier", "category", "item", "department", "po_number", "contract_id", "invoice_id", "transaction_id"]:
        out[col] = out[col].astype("string").str.strip()
        out[col] = out[col].replace({"": pd.NA, "nan": pd.NA, "None": pd.NA, "NA": pd.NA, "NaN": pd.NA})
    return out

def clean_transactions(df):
    """Remove exact duplicates and rows with unusable amounts; return quality diagnostics."""
    df = df.copy()
    before = len(df)
    duplicate_mask = df.duplicated()
    removed = int(duplicate_mask.sum())
    df = df.loc[~duplicate_mask].copy()
    nonpositive = int((df["amount"].notna() & (df["amount"] <= 0)).sum())
    invalid_amount = int(df["amount"].isna().sum())
    df = df.dropna(subset=["amount"])
    quality = {
        "duplicate_rows_removed": removed,
        "missing_supplier": int(df["supplier"].isna().sum()),
        "missing_category": int(df["category"].isna().sum()),
        "non_positive_amount": nonpositive,
        "missing_date": int(df["date"].isna().sum()),
        "invalid_amount_rows_removed": invalid_amount,
        "rows_before_cleaning": before,
        "rows_after_cleaning": len(df),
    }
    return df.reset_index(drop=True), quality

def build_kpis(df):
    supplier_count = int(df["supplier"].nunique()) if df["supplier"].notna().any() else None
    return {
        "total_spend": float(df["amount"].sum()),
        "transactions": int(len(df)),
        "average_transaction": float(df["amount"].mean()) if len(df) else 0.0,
        "supplier_count": supplier_count,
    }

def spend_by(df, col):
    if col not in df or df[col].isna().all():
        return pd.DataFrame(columns=[col, "amount"])
    result = df.dropna(subset=[col]).groupby(col, as_index=False)["amount"].sum()
    return result.sort_values("amount", ascending=False)

def supplier_scorecard(df):
    if df["supplier"].isna().all():
        return pd.DataFrame()
    work = df.dropna(subset=["supplier"])
    result = work.groupby("supplier", as_index=False).agg(
        total_spend=("amount", "sum"),
        transaction_count=("amount", "size"),
        average_transaction=("amount", "mean"),
    ).sort_values("total_spend", ascending=False)
    total = max(float(df["amount"].sum()), 1e-9)
    result["spend_share_pct"] = (result["total_spend"] / total * 100).round(2)
    result["cumulative_spend_share_pct"] = result["spend_share_pct"].cumsum().round(2)
    return result

def category_scorecard(df):
    if df["category"].isna().all():
        return pd.DataFrame()
    work = df.dropna(subset=["category"])
    result = work.groupby("category", as_index=False).agg(
        total_spend=("amount", "sum"),
        transaction_count=("amount", "size"),
        average_transaction=("amount", "mean"),
    ).sort_values("total_spend", ascending=False)
    total = max(float(df["amount"].sum()), 1e-9)
    result["spend_share_pct"] = (result["total_spend"] / total * 100).round(2)
    return result

def _supplier_key(value):
    text = _norm(value)
    # Remove common legal suffixes only as a candidate-generation heuristic.
    text = re.sub(r"\b(private limited|pvt ltd|pvt limited|limited|ltd|llp|incorporated|inc|corp|corporation|company|co)\b", "", text)
    return re.sub(r"\s+", " ", text).strip()

def supplier_normalization(df):
    """Return row-level normalized supplier keys without overwriting source names."""
    out = df.copy()
    out["supplier_normalized"] = out["supplier"].map(
        lambda x: _supplier_key(x) if pd.notna(x) and str(x).strip() else pd.NA
    ).astype("string")
    out["supplier_normalization_note"] = out.apply(
        lambda row: "Missing supplier" if pd.isna(row["supplier"]) else
        ("Name standardized for matching; verify before merging" if row["supplier_normalized"] != _norm(row["supplier"]) else "No obvious formatting change"),
        axis=1
    )
    return out

def candidate_supplier_duplicates(df, threshold=0.86, max_names=1000):
    """Suggest similar supplier-name pairs; suggestions require human verification."""
    if "supplier" not in df or df["supplier"].isna().all():
        return pd.DataFrame(columns=["supplier_a", "supplier_b", "normalized_a", "normalized_b", "similarity", "review_note"])
    names = sorted(df["supplier"].dropna().astype(str).str.strip().unique())
    names = [name for name in names if name]
    truncated = len(names) > max_names
    names = names[:max_names]
    keys = {name: _supplier_key(name) for name in names}
    rows = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ka, kb = keys[a], keys[b]
            score = 1.0 if ka and ka == kb else SequenceMatcher(None, ka, kb).ratio()
            if score >= threshold:
                rows.append({
                    "supplier_a": a, "supplier_b": b, "normalized_a": ka, "normalized_b": kb,
                    "similarity": round(float(score), 3),
                    "review_note": "Potential duplicate; manually verify legal identity before merging",
                })
    result = pd.DataFrame(rows, columns=["supplier_a", "supplier_b", "normalized_a", "normalized_b", "similarity", "review_note"])
    if not result.empty:
        result = result.sort_values(["similarity", "supplier_a"], ascending=[False, True]).reset_index(drop=True)
    result.attrs["names_truncated"] = truncated
    return result


def detect_duplicate_transactions(df, date_window_days=0):
    """Flag potential duplicate transactions using available transaction fields.

    Required matching context: supplier plus amount. Item/date/quantity/unit price
    improve the evidence when available. Results are candidates for manual review,
    not confirmed duplicate purchases or duplicate payments.
    """
    output_cols = [
        "transaction_id", "supplier", "item", "date", "quantity", "unit_price",
        "amount", "duplicate_group_size", "match_fields", "review_reason",
    ]
    if df.empty or df["supplier"].isna().all() or df["amount"].isna().all():
        return pd.DataFrame(columns=output_cols)

    work = df.copy()
    # Normalize matching strings while preserving original display fields.
    work["_supplier_key"] = work["supplier"].map(
        lambda x: _supplier_key(x) if pd.notna(x) and str(x).strip() else pd.NA
    )
    work["_item_key"] = work["item"].map(
        lambda x: _norm(x) if pd.notna(x) and str(x).strip() else pd.NA
    )
    work["_amount_key"] = pd.to_numeric(work["amount"], errors="coerce").round(2)
    work["_quantity_key"] = pd.to_numeric(work["quantity"], errors="coerce").round(4)
    work["_unit_price_key"] = pd.to_numeric(work["unit_price"], errors="coerce").round(4)
    work["_date_key"] = pd.to_datetime(work["date"], errors="coerce").dt.normalize()

    # Prefer a transaction ID as display-only context; do not use it as a match key.
    if "transaction_id" not in work:
        work["transaction_id"] = pd.NA

    # Build exact duplicate signatures using the most informative available fields.
    match_fields = ["supplier", "amount"]
    key_cols = ["_supplier_key", "_amount_key"]
    if work["_item_key"].notna().any():
        match_fields.append("item")
        key_cols.append("_item_key")
    if work["_date_key"].notna().any():
        match_fields.append("date")
        key_cols.append("_date_key")
    if work["_quantity_key"].notna().any():
        match_fields.append("quantity")
        key_cols.append("_quantity_key")
    if work["_unit_price_key"].notna().any():
        match_fields.append("unit_price")
        key_cols.append("_unit_price_key")

    valid = work["_supplier_key"].notna() & work["_amount_key"].notna()
    candidates = work.loc[valid].copy()
    if candidates.empty:
        return pd.DataFrame(columns=output_cols)

    # Include only optional keys that are present on a given row, allowing partial
    # data to remain usable. pandas groupby(dropna=False) keeps missing optional keys together.
    grouped = candidates.groupby(key_cols, dropna=False, sort=False)
    candidates["_duplicate_group_size"] = grouped["_amount_key"].transform("size")
    dupes = candidates[candidates["_duplicate_group_size"] > 1].copy()
    if dupes.empty:
        return pd.DataFrame(columns=output_cols)

    dupes["duplicate_group_size"] = dupes["_duplicate_group_size"].astype(int)
    dupes["match_fields"] = ", ".join(match_fields)
    dupes["review_reason"] = (
        "Matching supplier, amount and available item/date/quantity/price fields; "
        "confirm source records before treating as duplicate"
    )
    # The optional date window parameter is reserved for future fuzzy-date matching;
    # exact signatures are intentionally conservative for this version.
    result = dupes.copy()
    for col in output_cols:
        if col not in result.columns:
            result[col] = pd.NA
    return result[output_cols].sort_values(
        ["supplier", "date", "amount"], na_position="last"
    ).reset_index(drop=True)

def spend_concentration(df):
    """Summarize supplier concentration using sorted supplier spend shares."""
    suppliers = supplier_scorecard(df)
    if suppliers.empty:
        return {
            "supplier_count": 0, "top_2_share_pct": None, "top_5_share_pct": None,
            "hhi": None, "interpretation": "Supplier data is unavailable."
        }, suppliers
    shares = suppliers["spend_share_pct"].astype(float)
    hhi = float(((shares / 100) ** 2).sum() * 10000)
    top2 = float(shares.head(2).sum())
    top5 = float(shares.head(5).sum())
    if hhi < 1500:
        interpretation = "Relatively dispersed supplier spend under a common HHI screening convention; investigate business context."
    elif hhi < 2500:
        interpretation = "Moderate supplier concentration under a common HHI screening convention; review critical categories and alternatives."
    else:
        interpretation = "High supplier concentration under a common HHI screening convention; assess dependency, switching costs and continuity risk."
    summary = {
        "supplier_count": int(len(suppliers)),
        "top_2_share_pct": round(top2, 2),
        "top_5_share_pct": round(top5, 2),
        "hhi": round(hhi, 1),
        "interpretation": interpretation,
    }
    return summary, suppliers

def flag_opportunities(df):
    rows = []
    # Non-contract rule is only used when a contract field is actually populated.
    if df["contract_id"].notna().any():
        no_contract = df["contract_id"].astype("string").str.strip().str.lower().str.fullmatch(
            r"(no[- _]?contract|none|nan|na|n/?a|)", na=False
        )
        for _, row in df[no_contract & df["amount"].gt(0)].iterrows():
            rows.append({"opportunity_type": "Possible non-contract spend", "supplier": row["supplier"],
                         "category": row["category"], "amount": row["amount"],
                         "reason": "Contract field appears blank or indicates no contract; verify policy and context"})
    # IQR threshold is a review heuristic, not fraud detection.
    amounts = df["amount"].dropna()
    if len(amounts) >= 4:
        q1, q3 = amounts.quantile([0.25, 0.75])
        cutoff = q3 + 1.5 * (q3 - q1)
        unusual = df[df["amount"] > cutoff]
        for _, row in unusual.head(250).iterrows():
            rows.append({"opportunity_type": "High-value transaction review", "supplier": row["supplier"],
                         "category": row["category"], "amount": row["amount"],
                         "reason": f"Amount exceeds IQR review threshold ({cutoff:,.2f}); inspect business context"})
    # Supplier concentration is a review signal, not automatically a risk.
    score = supplier_scorecard(df)
    if not score.empty:
        for _, row in score.head(10).iterrows():
            if row["spend_share_pct"] >= 20:
                rows.append({"opportunity_type": "Supplier concentration review", "supplier": row["supplier"],
                             "category": pd.NA, "amount": row["total_spend"],
                             "reason": f"Supplier accounts for {row['spend_share_pct']:.1f}% of total spend; assess dependency and alternatives"})
    return pd.DataFrame(rows, columns=["opportunity_type", "supplier", "category", "amount", "reason"])


def monthly_spend_analysis(df):
    """Monthly spend totals with adjacent-calendar-month absolute and percentage changes."""
    cols = ["month", "total_spend", "previous_month_spend", "mom_change", "mom_change_pct"]
    if df.empty or "date" not in df or df["date"].isna().all():
        return pd.DataFrame(columns=cols)
    work = df.dropna(subset=["date", "amount"]).copy()
    if work.empty:
        return pd.DataFrame(columns=cols)
    work["month"] = pd.to_datetime(work["date"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    work = work.dropna(subset=["month"])
    if work.empty:
        return pd.DataFrame(columns=cols)
    monthly = work.groupby("month", as_index=False)["amount"].sum().rename(columns={"amount": "total_spend"})
    monthly = monthly.set_index("month").asfreq("MS", fill_value=0).rename_axis("month").reset_index()
    monthly["previous_month_spend"] = monthly["total_spend"].shift(1)
    monthly["mom_change"] = monthly["total_spend"] - monthly["previous_month_spend"]
    denominator = monthly["previous_month_spend"].where(monthly["previous_month_spend"].ne(0))
    monthly["mom_change_pct"] = (monthly["mom_change"] / denominator * 100).replace([np.inf, -np.inf], np.nan)
    return monthly[cols]


def maverick_spend_proxy(df, min_category_records=4):
    """Flag unusual positive amounts within a category; not a true policy-violation detector."""
    cols = ["transaction_id", "supplier", "category", "date", "item", "quantity",
            "unit_price", "amount", "category_q3", "review_threshold", "review_reason"]
    if df.empty or "category" not in df or df["category"].isna().all():
        return pd.DataFrame(columns=cols)
    work = df.copy()
    work["_amount_numeric"] = pd.to_numeric(work["amount"], errors="coerce")
    work = work.dropna(subset=["category", "_amount_numeric"])
    work = work[work["_amount_numeric"] > 0]
    flagged = []
    for category, group in work.groupby("category", dropna=True):
        if len(group) < int(min_category_records):
            continue
        q1 = float(group["_amount_numeric"].quantile(0.25))
        q3 = float(group["_amount_numeric"].quantile(0.75))
        threshold = q3 + 1.5 * (q3 - q1)
        for _, row in group[group["_amount_numeric"] > threshold].iterrows():
            flagged.append({
                "transaction_id": row.get("transaction_id", pd.NA),
                "supplier": row.get("supplier", pd.NA),
                "category": category,
                "date": row.get("date", pd.NaT),
                "item": row.get("item", pd.NA),
                "quantity": row.get("quantity", pd.NA),
                "unit_price": row.get("unit_price", pd.NA),
                "amount": float(row["_amount_numeric"]),
                "category_q3": q3,
                "review_threshold": threshold,
                "review_reason": "Amount exceeds category-specific IQR threshold; review context. This is not proof of policy violation.",
            })
    result = pd.DataFrame(flagged, columns=cols)
    if not result.empty:
        result = result.sort_values("amount", ascending=False).reset_index(drop=True)
    return result


def generate_insights(df):
    insights = []
    total = float(df["amount"].sum())
    insights.append(f"Total spend across {len(df):,} usable transactions is {total:,.2f} in the source dataset's currency.")
    suppliers = supplier_scorecard(df)
    if not suppliers.empty:
        top = suppliers.iloc[0]
        insights.append(f"Highest-spend supplier is {top['supplier']} at {top['total_spend']:,.2f} ({top['spend_share_pct']:.1f}% of spend).")
        concentration, _ = spend_concentration(df)
        if concentration["top_2_share_pct"] is not None:
            insights.append(f"Top 2 suppliers account for {concentration['top_2_share_pct']:.1f}% of spend.")
    cats = category_scorecard(df)
    if not cats.empty:
        topc = cats.iloc[0]
        insights.append(f"Highest-spend category is {topc['category']} at {topc['total_spend']:,.2f} ({topc['spend_share_pct']:.1f}% of spend).")
    dated = df.dropna(subset=["date"])
    if not dated.empty:
        monthly = dated.assign(month=dated["date"].dt.to_period("M").astype(str)).groupby("month")["amount"].sum()
        if len(monthly) >= 2:
            insights.append(f"Highest-spend month in the available data is {monthly.idxmax()} ({monthly.max():,.2f}).")
    return insights

def build_executive_report(df, quality, source_label="dataset"):
    """Build a concise Markdown executive report from the current filtered dataset."""
    kpis = build_kpis(df)
    concentration, suppliers = spend_concentration(df)
    categories = category_scorecard(df)
    duplicates = detect_duplicate_transactions(df)
    supplier_dupes = candidate_supplier_duplicates(df)
    opportunities = flag_opportunities(df)

    lines = [
        "# ProcureIQ — Executive Spend Report",
        "",
        f"**Data source:** {source_label}",
        f"**Records analyzed:** {len(df):,}",
        "**Currency:** As reported in the source dataset; no conversion performed.",
        "",
        "## Executive summary",
        f"- Total spend: **{kpis['total_spend']:,.2f}**",
        f"- Transactions analyzed: **{kpis['transactions']:,}**",
        f"- Average transaction: **{kpis['average_transaction']:,.2f}**",
        f"- Distinct suppliers: **{kpis['supplier_count'] if kpis['supplier_count'] is not None else 'Unavailable'}**",
        f"- Top 2 supplier spend share: **{concentration['top_2_share_pct'] if concentration['top_2_share_pct'] is not None else 'Unavailable'}%**",
        f"- Top 5 supplier spend share: **{concentration['top_5_share_pct'] if concentration['top_5_share_pct'] is not None else 'Unavailable'}%**",
        f"- Supplier HHI (screening metric): **{concentration['hhi'] if concentration['hhi'] is not None else 'Unavailable'}**",
        "",
        "## Largest suppliers",
    ]
    if suppliers.empty:
        lines.append("- Supplier information was not mapped.")
    else:
        for _, row in suppliers.head(5).iterrows():
            lines.append(f"- {row['supplier']}: {row['total_spend']:,.2f} ({row['spend_share_pct']:.2f}%)")
    lines += ["", "## Largest categories"]
    if categories.empty:
        lines.append("- Category information was not mapped.")
    else:
        for _, row in categories.head(5).iterrows():
            lines.append(f"- {row['category']}: {row['total_spend']:,.2f} ({row['spend_share_pct']:.2f}%)")
    lines += [
        "",
        "## Data quality diagnostics",
        f"- Exact duplicate rows removed: {quality.get('duplicate_rows_removed', 0)}",
        f"- Rows with missing supplier: {quality.get('missing_supplier', 0)}",
        f"- Rows with missing category: {quality.get('missing_category', 0)}",
        f"- Rows with non-positive spend: {quality.get('non_positive_amount', 0)}",
        f"- Rows with missing/unparseable date: {quality.get('missing_date', 0)}",
        f"- Rows removed due to invalid/missing spend: {quality.get('invalid_amount_rows_removed', 0)}",
        "",
        "## Items for review",
        f"- Potential duplicate transaction rows flagged: {len(duplicates)}",
        f"- Potential supplier-name pairs flagged: {len(supplier_dupes)}",
        f"- Rule-based opportunity flags: {len(opportunities)}",
        "",
        "## Interpretation and limitations",
        f"- {concentration['interpretation']}",
        "- Potential duplicate transactions and supplier-name matches are review candidates, not confirmed errors.",
        "- High-value transaction flags are statistical review prompts, not evidence of fraud or waste.",
        "- Any savings estimate requires validated baseline prices, volumes, contractual terms and stakeholder review.",
        "- Findings describe this dataset only and should not be generalized to a real company without validation.",
        "",
    ]
    return "\n".join(lines)
