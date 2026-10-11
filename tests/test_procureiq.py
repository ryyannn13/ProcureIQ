import sys
from pathlib import Path
import unittest
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from procureiq import detect_duplicate_transactions, supplier_normalization, spend_concentration, normalize_columns, clean_transactions, monthly_spend_analysis, maverick_spend_proxy

class ProcureIQTests(unittest.TestCase):
    def sample(self):
        return pd.DataFrame({
            "amount": [100., 100., 200., 400.],
            "supplier": ["Acme Pvt Ltd", "Acme Pvt Ltd", "Beta Corp", "Gamma Ltd"],
            "category": ["IT", "IT", "Office", "Office"],
            "date": pd.to_datetime(["2025-01-01", "2025-01-01", "2025-01-03", "2025-01-04"]),
            "item": ["Laptop", "Laptop", "Paper", "Chair"],
            "quantity": [1, 1, 2, 1], "unit_price": [100., 100., 100., 400.],
            "department": ["IT", "IT", "Ops", "Ops"],
            "po_number": [pd.NA] * 4, "contract_id": [pd.NA] * 4,
            "invoice_id": [pd.NA] * 4, "transaction_id": ["T1", "T2", "T3", "T4"],
        })
    def test_duplicate_transaction_detection(self):
        result = detect_duplicate_transactions(self.sample())
        self.assertEqual(len(result), 2)
    def test_supplier_normalization_preserves_source(self):
        result = supplier_normalization(self.sample())
        self.assertEqual(result.loc[0, "supplier"], "Acme Pvt Ltd")
        self.assertEqual(result.loc[0, "supplier_normalized"], result.loc[1, "supplier_normalized"])
    def test_spend_concentration(self):
        summary, scorecard = spend_concentration(self.sample())
        self.assertEqual(len(scorecard), 3)
        self.assertGreater(summary["top_2_share_pct"], 0)
    def test_invalid_amount_validation(self):
        raw = pd.DataFrame({"Total Cost": ["10", "bad", "-5"], "Supplier": ["A", "B", "C"]})
        mapped = normalize_columns(raw, {"amount": "Total Cost", "supplier": "Supplier"})
        cleaned, quality = clean_transactions(mapped)
        self.assertEqual(len(cleaned), 2)
        self.assertEqual(quality["invalid_amount_rows_removed"], 1)
        self.assertEqual(quality["non_positive_amount"], 1)


    def test_monthly_spend_analysis(self):
        frame = pd.DataFrame({
            "date": pd.to_datetime(["2025-01-05", "2025-01-20", "2025-03-02"]),
            "amount": [100.0, 50.0, 300.0],
        })
        result = monthly_spend_analysis(frame)
        self.assertEqual(len(result), 3)  # February is represented as zero spend.
        self.assertEqual(float(result.loc[0, "total_spend"]), 150.0)
        self.assertEqual(float(result.loc[1, "total_spend"]), 0.0)
        self.assertAlmostEqual(float(result.loc[2, "mom_change"]), 300.0)

    def test_maverick_proxy_is_category_specific_and_review_only(self):
        frame = pd.DataFrame({
            "amount": [10., 11., 12., 13., 1000.],
            "category": ["IT"] * 5,
            "supplier": ["A"] * 5,
            "date": pd.to_datetime(["2025-01-01"] * 5),
            "item": ["Laptop"] * 5,
            "quantity": [1] * 5,
            "unit_price": [10., 11., 12., 13., 1000.],
            "transaction_id": ["T1", "T2", "T3", "T4", "T5"],
        })
        result = maverick_spend_proxy(frame)
        self.assertGreaterEqual(len(result), 1)
        self.assertIn("not proof", result.iloc[0]["review_reason"])

if __name__ == "__main__":
    unittest.main()
