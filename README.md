# ProcureIQ — Procurement Spend Analytics & Cost Optimization

**A Python + Streamlit portfolio project for spend analysis, supplier intelligence, and procurement data quality.**

ProcureIQ turns purchasing transaction data into an interactive analytical workspace. It helps an analyst explore where money is being spent, identify supplier and category concentration, investigate unusual transactions, and export findings for review.

> **Data note:** This is a portfolio project using the [Company Purchasing Dataset on Kaggle](https://www.kaggle.com/datasets/shahriarkabir/company-purchasing-dataset). Results depend on the CSV uploaded and the columns mapped in the app. The app does not represent a real company's confidential procurement data.

## Highlights

- **Interactive analysis filters** — filter by supplier, category, and purchase-date range; dashboard analysis uses the selected view.
- **Spend overview** — total spend, transaction count, average transaction, supplier count, monthly trend, and spend by category.
- **Supplier analysis** — rank suppliers by spend, compare transaction volumes and averages, and examine supplier spend share and cumulative concentration.
- **Category analysis** — compare categories by total spend, transaction count, average transaction, and share of overall spend.
- **Month-over-month analysis** — compare monthly totals with the previous calendar month, including absolute and percentage changes.
- **Data-quality checks** — review missing supplier/category/date values, invalid or non-positive amounts, and exact duplicate rows.
- **Potential duplicate transaction review** — compare supplier, amount, and available item/date/quantity/unit-price fields.
- **Supplier normalization** — standardize supplier names into matching keys and surface candidate names for manual review.
- **Spend concentration analysis** — quantify supplier concentration, including top-supplier shares and HHI where available.
- **Opportunity flags** — identify high-value transactions and other patterns that warrant further investigation.
- **Maverick-spend proxy** — flag category-level statistical outliers for review when contract or purchasing-policy data is unavailable.
- **Executive report and Excel analysis pack** — export a concise report and a multi-sheet workbook with summary KPIs, transactions, supplier/category scorecards, monthly trends, data-quality findings, duplicate review, supplier-name review, opportunities, and outlier flags.

## Why this project matters

Spend analysts need more than charts. They must validate source data, understand supplier and category patterns, spot records that deserve review, and communicate findings clearly. ProcureIQ brings these activities into one workflow:

1. Load a purchasing CSV and map its columns.
2. Review data quality and confirm the usable analytical records.
3. Filter the data by supplier, category, or date.
4. Investigate supplier/category spend and changes over time.
5. Review potential duplicate transactions and out-of-pattern purchases.
6. Export analysis for further review and stakeholder reporting.

## Technology

- **Python**
- **Pandas / NumPy** for data preparation and analysis
- **Streamlit** for the interactive app
- **Plotly** for interactive charts
- **SQL** for complementary analytical queries
- **openpyxl** for Excel workbook export
- **unittest** for core logic tests

## Dataset

Primary source: [Company Purchasing Dataset — Kaggle](https://www.kaggle.com/datasets/shahriarkabir/company-purchasing-dataset)

The dataset used during development contains fields such as:

`TransactionID`, `ItemName`, `Category`, `Quantity`, `UnitPrice`, `TotalCost`, `PurchaseDate`, `Supplier`, and `Buyer`.

The current dataset does **not** provide invoice ID or contract ID fields. Therefore:

- ProcureIQ detects **potential duplicate transactions**, not confirmed duplicate invoices.
- The app does not claim to identify confirmed contract or policy violations.
- The maverick-spend proxy flags statistical outliers for investigation only.
- Currency values are not converted; spend is shown in the source dataset's currency.
- Similar supplier names are suggestions only and should be manually verified before any merge.

Check Kaggle's current dataset license and terms before redistributing the CSV. Avoid committing raw data unless its license permits redistribution.

## Run locally

### 1. Requirements

- Python 3.10 or newer
- Git (optional, for version control)

### 2. Create and activate a virtual environment

**Windows PowerShell:**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

If the environment already exists, activate it instead of recreating it.

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Add the Kaggle CSV

Place the downloaded CSV at:

```text
data/raw/company_purchasing_dataset.csv
```

Alternatively, upload the CSV through the application's sidebar. Use the column-mapping controls to confirm which source fields correspond to spend, supplier, category, date, quantity, and item.

### 5. Start the app

```powershell
streamlit run app.py
```

Open the local URL printed in the terminal, usually `http://localhost:8501`.

## Repository structure

```text
procureiq_spend_analytics/
├── app.py
├── requirements.txt
├── README.md
├── data/
│   ├── raw/                 # Local source CSV; do not commit unless permitted
│   ├── processed/
│   └── demo_procurement.csv # Synthetic demo data, if included
├── outputs/                 # Generated exports
├── sql/
│   └── analysis_queries.sql
├── src/
│   └── procureiq.py
└── tests/
    └── test_procureiq.py
```

Folder contents may vary slightly by project version.

## Metric definitions and interpretation

- **Total spend:** sum of usable numeric transaction amounts.
- **Spend share:** supplier or category spend divided by total spend in the current analytical view.
- **Month-over-month change:** current month's spend minus the previous calendar month's spend.
- **Month-over-month percentage:** absolute change divided by previous month's spend; undefined when previous-month spend is zero.
- **High-value/outlier flags:** heuristic screening results, not proof of waste, fraud, or policy violations.
- **Supplier normalization:** a standardized text key for matching; it does not automatically merge supplier records.
- **Spend concentration / HHI:** measures how much spend is distributed across suppliers; interpret it in the context of the dataset and category.
- **Potential savings:** ProcureIQ does not claim realized savings. Any savings estimate needs explicit assumptions and business validation.
est discover -s tests -v

