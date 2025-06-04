# test_report_detection.py
import unittest
import os
from report_detection import EnhancedReportTypeDetector

class TestReportDetection(unittest.TestCase):
    def test_detect_manufacturing_report(self):
        # Create a mock text with manufacturing indicators
        text = """
        MANUFACTURING AT A GLANCE
        JANUARY 2025
        
        Manufacturing PMI® at 52.8%
        New Orders, Production Growing
        Employment, Supplier Deliveries Contracting
        
        The Manufacturing PMI® registered 52.8 percent in January, up 1.1 percentage points
        from the December reading of 51.7 percent.
        
        MANUFACTURING INDEX SUMMARIES
        
        Manufacturing industries reporting growth: Chemical Products, Fabricated Metal
        """
        
        # Create a temporary file
        with open("temp_manufacturing.txt", "w") as f:
            f.write(text)
        
        # Test detection
        try:
            result = EnhancedReportTypeDetector.detect_report_type("temp_manufacturing.txt")
            self.assertEqual(result, "Manufacturing")
        finally:
            # Clean up
            os.remove("temp_manufacturing.txt")
    
    def test_detect_services_report(self):
        # Create a mock text with services indicators
        text = """
        SERVICES AT A GLANCE
        JANUARY 2025
        
        Services PMI® at 54.2%
        Business Activity, New Orders Growing
        Employment, Supplier Deliveries Contracting
        
        The Services PMI® registered 54.2 percent in January, up 0.8 percentage points
        from the December reading of 53.4 percent.
        
        SERVICES INDEX SUMMARIES
        
        Services industries reporting growth: Finance & Insurance, Health Care
        """
        
        # Create a temporary file
        with open("temp_services.txt", "w") as f:
            f.write(text)
        
        # Test detection
        try:
            result = EnhancedReportTypeDetector.detect_report_type("temp_services.txt")
            self.assertEqual(result, "Services")
        finally:
            # Clean up
            os.remove("temp_services.txt")

if __name__ == '__main__':
    unittest.main()