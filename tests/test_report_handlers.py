import unittest
import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock

# Import modules to test
from report_handlers import (
    ReportTypeHandler,
    ManufacturingReportHandler,
    ServicesReportHandler,
    ReportTypeFactory
)

class TestReportHandlers(unittest.TestCase):
    """Test the report type handler classes."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.test_dir, 'test_config.json')
        
        # Create a test config file
        with open(self.test_file, 'w') as f:
            f.write('''{
                "indices": ["Test Index 1", "Test Index 2"],
                "index_categories": {
                    "Test Index 1": ["Category A", "Category B"],
                    "Test Index 2": ["Category C", "Category D"]
                },
                "extraction_prompt": "Test extraction prompt",
                "correction_prompt": "Test correction prompt"
            }''')
    
    def tearDown(self):
        """Clean up after the test."""
        shutil.rmtree(self.test_dir)
    
    def test_manufacturing_handler_defaults(self):
        """Test that ManufacturingReportHandler provides correct defaults."""
        handler = ManufacturingReportHandler()
        
        # Test indices
        indices = handler.get_indices()
        self.assertIn("Manufacturing PMI", indices)
        self.assertIn("New Orders", indices)
        self.assertIn("Production", indices)
        
        # Test categories
        new_orders_categories = handler.get_index_categories("New Orders")
        self.assertEqual(new_orders_categories, ["Growing", "Declining"])
        
        supplier_deliveries_categories = handler.get_index_categories("Supplier Deliveries")
        self.assertEqual(supplier_deliveries_categories, ["Slower", "Faster"])
        
        # Test prompts
        extraction_prompt = handler.get_extraction_prompt()
        self.assertIn("Manufacturing", extraction_prompt)
        
        correction_prompt = handler.get_correction_prompt()
        self.assertGreater(len(correction_prompt), 100)  # Should be a substantial prompt
    
    def test_services_handler_defaults(self):
        """Test that ServicesReportHandler provides correct defaults."""
        handler = ServicesReportHandler()
        
        # Test indices
        indices = handler.get_indices()
        self.assertIn("Services PMI", indices)
        self.assertIn("Business Activity", indices)
        self.assertIn("New Orders", indices)
        
        # Test categories
        business_activity_categories = handler.get_index_categories("Business Activity")
        self.assertEqual(business_activity_categories, ["Growing", "Declining"])
        
        inventory_sentiment_categories = handler.get_index_categories("Inventory Sentiment")
        self.assertEqual(inventory_sentiment_categories, ["Too High", "Too Low"])
        
        # Test prompts
        extraction_prompt = handler.get_extraction_prompt()
        self.assertIn("Services", extraction_prompt)
        
        correction_prompt = handler.get_correction_prompt()
        self.assertGreater(len(correction_prompt), 100)  # Should be a substantial prompt
    
    def test_config_loading(self):
        """Test loading from a config file."""
        handler = ManufacturingReportHandler(self.test_file)
        
        # Test loaded values
        indices = handler.get_indices()
        self.assertEqual(indices, ["Test Index 1", "Test Index 2"])
        
        categories = handler.get_index_categories("Test Index 1")
        self.assertEqual(categories, ["Category A", "Category B"])
        
        extraction_prompt = handler.get_extraction_prompt()
        self.assertEqual(extraction_prompt, "Test extraction prompt")
        
        correction_prompt = handler.get_correction_prompt()
        self.assertEqual(correction_prompt, "Test correction prompt")
    
    def test_factory_detection(self):
        """Test that ReportTypeFactory correctly detects report types."""
        # Mock PDF text for Manufacturing
        mfg_text = "MANUFACTURING PMI® registered 50.9 percent in January"
        
        # Mock PDF text for Services
        svc_text = "SERVICES PMI® registered 52.8 percent in January"
        
        # Mock extract_text_from_pdf
        with patch('report_handlers.extract_text_from_pdf') as mock_extract:
            # Test Manufacturing detection
            mock_extract.return_value = mfg_text
            report_type = ReportTypeFactory.detect_report_type("dummy_path.pdf")
            self.assertEqual(report_type, 'Manufacturing')
            
            # Test Services detection
            mock_extract.return_value = svc_text
            report_type = ReportTypeFactory.detect_report_type("dummy_path.pdf")
            self.assertEqual(report_type, 'Services')
            
            # Test default to Manufacturing
            mock_extract.return_value = "Some random text"
            report_type = ReportTypeFactory.detect_report_type("dummy_path.pdf")
            self.assertEqual(report_type, 'Manufacturing')
    
    def test_factory_creation(self):
        """Test that ReportTypeFactory creates correct handlers."""
        # Create Manufacturing handler
        handler = ReportTypeFactory.create_handler('Manufacturing')
        self.assertIsInstance(handler, ManufacturingReportHandler)
        
        # Create Services handler
        handler = ReportTypeFactory.create_handler('Services')
        self.assertIsInstance(handler, ServicesReportHandler)
        
        # Create handler based on PDF detection
        with patch('report_handlers.ReportTypeFactory.detect_report_type') as mock_detect:
            mock_detect.return_value = 'Services'
            handler = ReportTypeFactory.create_handler(pdf_path="dummy_path.pdf")
            self.assertIsInstance(handler, ServicesReportHandler)

if __name__ == '__main__':
    unittest.main()