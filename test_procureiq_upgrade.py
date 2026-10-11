import sys
from pathlib import Path
import unittest
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from procureiq import detect_duplicate_invoices, supplier_normalization, spend_concentration, normalize_columns, clean_transactions

class UpgradeTests(unittest.TestCase):
    def sample(self):
        return pd.DataFrame({'amount':[100.,200.,100.,400.], 'supplier':['Acme Pvt Ltd','ACME','Beta Corp','Gamma Ltd'], 'category':['IT','IT','Office','Office'], 'date':pd.to_datetime(['2025-01-01','2025-01-02','2025-01-03','2025-01-04']), 'item':['x','y','z','q'], 'quantity':[1,1,2,1], 'unit_price':[100.,200.,50.,400.], 'department':['IT','IT','Ops','Ops'], 'po_number':['PO1','PO2','PO3','PO4'], 'contract_id':['C1','C1','C2','C3'], 'invoice_id':['INV-1',' inv-1 ','INV-3',None]})
    def test_duplicate_invoice_detection(self):
        self.assertEqual(len(detect_duplicate_invoices(self.sample())), 2)
    def test_supplier_normalization_preserves_original(self):
        result=supplier_normalization(self.sample())
        self.assertEqual(result.loc[0,'supplier'],'Acme Pvt Ltd')
        self.assertEqual(result.loc[0,'supplier_normalized'],result.loc[1,'supplier_normalized'])
    def test_spend_concentration(self):
        summary, scorecard=spend_concentration(self.sample())
        self.assertAlmostEqual(summary['top_2_share_pct'],75.0,places=1)
        self.assertEqual(len(scorecard),4)
    def test_invalid_amount_validation(self):
        raw=pd.DataFrame({'Total Cost':['10','bad','-5'],'Supplier':['A','B','C']})
        mapped=normalize_columns(raw, {'amount':'Total Cost','supplier':'Supplier'})
        cleaned, quality=clean_transactions(mapped)
        self.assertEqual(len(cleaned),2)
        self.assertEqual(quality['invalid_amount_rows_removed'],1)
        self.assertEqual(quality['non_positive_amount'],1)

if __name__=='__main__': unittest.main()
