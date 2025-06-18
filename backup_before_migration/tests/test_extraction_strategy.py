# test_extraction_strategy.py
import unittest
from extraction_strategy import DateExtractionStrategy, TableExtractionStrategy, IndustryExtractionStrategy, StrategyRegistry

class TestExtractionStrategies(unittest.TestCase):
    def test_date_extraction(self):
        text = "January 2025 MANUFACTURING INDEX"
        strategy = DateExtractionStrategy()
        result = strategy.extract(text)
        self.assertEqual(result["month_year"], "January 2025")
    
    def test_table_extraction(self):
        text = """
        MANUFACTURING AT A GLANCE
        JANUARY 2025
        
        Manufacturing PMI® at 52.8 percent, Growing
        New Orders at 55.4 percent, Growing
        Production at 54.2 percent, Growing
        """
        
        strategy = TableExtractionStrategy()
        result = strategy.extract(text)
        
        self.assertIn("indices", result)
        self.assertIn("Manufacturing PMI", result["indices"])
        self.assertEqual(result["indices"]["Manufacturing PMI"]["value"], "52.8")
        self.assertEqual(result["indices"]["Manufacturing PMI"]["direction"], "Growing")
    
    def test_industry_extraction(self):
        text = """
        NEW ORDERS
        ISM®'s New Orders Index registered 55.4 percent in January, up 5.5 percentage points
        compared to the 49.9 percent reported for December. This indicates that new orders
        grew after contracting for two consecutive months. "The New Orders Index signaled
        expansion for the first time in three months," says Fiore. "Four of the six largest
        manufacturing industries — Transportation Equipment; Food, Beverage & Tobacco Products; 
        Chemical Products; and Fabricated Metal Products — expanded. The index returned to 
        expansion because of panelists' clear enthusiasm regarding demand, but the same number 
        of industries reported new orders growth and contraction in January."
        
        The five manufacturing industries reporting growth in new orders in January are:
        Transportation Equipment; Food, Beverage & Tobacco Products; Chemical Products; 
        Fabricated Metal Products; and Plastics & Rubber Products.
        
        The seven industries reporting a decline in new orders in January — in order of
        percentage decline — are: Furniture & Related Products; Textile Mills; Paper Products;
        Machinery; Primary Metals; Nonmetallic Mineral Products; and Miscellaneous Manufacturing.
        """
        
        strategy = IndustryExtractionStrategy()
        result = strategy.extract(text)
        
        self.assertIn("industry_data", result)
        self.assertIn("New Orders", result["industry_data"])
        self.assertIn("Growing", result["industry_data"]["New Orders"])
        self.assertIn("Declining", result["industry_data"]["New Orders"])
        
        growing = result["industry_data"]["New Orders"]["Growing"]
        declining = result["industry_data"]["New Orders"]["Declining"]
        
        self.assertIn("Chemical Products", growing)
        self.assertIn("Transportation Equipment", growing)
        self.assertIn("Textile Mills", declining)
        self.assertIn("Machinery", declining)
    
    def test_strategy_registry(self):
        # Test registry functionality
        strategies = StrategyRegistry.get_strategies_for_report_type("Manufacturing")
        self.assertTrue(len(strategies) > 0)
        
        # Test getting strategies by section type
        date_strategies = StrategyRegistry.get_strategies_for_report_type("Manufacturing", "date")
        self.assertEqual(len(date_strategies), 1)
        self.assertEqual(date_strategies[0].__name__, "DateExtractionStrategy")

if __name__ == '__main__':
    unittest.main()