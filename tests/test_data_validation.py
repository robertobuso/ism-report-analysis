# test_data_validation.py
import unittest
from data_validation import PMIValue, IndustryCategory, ISMReport, DataTransformationPipeline

class TestDataValidation(unittest.TestCase):
    def test_pmi_value_validation(self):
        # Test numerical value
        pmi = PMIValue(value=52.8, direction="Growing")
        self.assertEqual(pmi.value, 52.8)
        self.assertEqual(pmi.direction, "Growing")
        
        # Test string value with number
        pmi = PMIValue(value="54.2", direction="growing")
        self.assertEqual(pmi.value, 54.2)
        self.assertEqual(pmi.direction, "Growing")
        
        # Test direction standardization
        pmi = PMIValue(value=48.5, direction="contracting")
        self.assertEqual(pmi.direction, "Contracting")
    
    def test_industry_category_validation(self):
        # Test with valid industries
        cat = IndustryCategory(industries=["Chemical Products", "Fabricated Metal Products"])
        self.assertEqual(len(cat.industries), 2)
        
        # Test with duplicates
        cat = IndustryCategory(industries=["Chemical Products", "chemical products", "Fabricated Metal Products"])
        self.assertEqual(len(cat.industries), 2)
        
        # Test with invalid entries
        cat = IndustryCategory(industries=["Chemical Products", "", "are:", "in order", "Fabricated Metal Products"])
        self.assertEqual(len(cat.industries), 2)
    
    def test_ism_report_validation(self):
        # Test basic report
        report = ISMReport(
            month_year="January 2025",
            report_type="Manufacturing",
            indices={
                "Manufacturing PMI": {"value": 52.8, "direction": "Growing"},
                "New Orders": {"value": 55.4, "direction": "Growing"}
            },
            industry_data={
                "New Orders": {
                    "Growing": ["Chemical Products", "Fabricated Metal Products"],
                    "Declining": ["Textile Mills", "Machinery"]
                }
            }
        )
        
        self.assertEqual(report.month_year, "January 2025")
        self.assertEqual(report.report_type, "Manufacturing")
        self.assertEqual(report.indices["Manufacturing PMI"].value, 52.8)
        self.assertEqual(len(report.industry_data["New Orders"]["Growing"]), 2)
    
    def test_data_transformation_pipeline(self):
        # Test full pipeline
        raw_data = {
            "month_year": "Jan 2025",
            "indices": {
                "Manufacturing PMI": {"value": "52.8%", "direction": "growing"},
                "New Orders": {"value": 55.4, "direction": "Growing"}
            },
            "industry_data": {
                "New Orders": {
                    "Growing": ["Chemical", "Chemical", "Fabricated Metal", "are:"],
                    "Declining": ["Textile", "Machinery", ""]
                }
            },
            "index_summaries": {
                "New Orders": "New Orders registered 55.4 percent in January..."
            }
        }
        
        result = DataTransformationPipeline.process(raw_data, "Manufacturing")
        
        self.assertEqual(result["month_year"], "January 2025")
        self.assertEqual(result["report_type"], "Manufacturing")
        self.assertEqual(result["indices"]["Manufacturing PMI"]["value"], 52.8)
        self.assertEqual(len(result["industry_data"]["New Orders"]["Growing"]), 2)
        self.assertEqual(len(result["industry_data"]["New Orders"]["Declining"]), 2)

if __name__ == '__main__':
    unittest.main()