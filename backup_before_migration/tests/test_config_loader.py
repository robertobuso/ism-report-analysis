import unittest
import os
import tempfile
import shutil
import json

# Import modules to test
from config_loader import ConfigLoader, ReportConfig

class TestConfigLoader(unittest.TestCase):
    """Test the configuration loader."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.config_dir = os.path.join(self.test_dir, 'config')
        os.makedirs(self.config_dir)
        
        # Create test config files
        self.mfg_config = {
            "indices": ["Manufacturing PMI", "New Orders"],
            "index_categories": {
                "New Orders": ["Growing", "Declining"]
            },
            "extraction_prompt": "Mfg extraction prompt",
            "correction_prompt": "Mfg correction prompt"
        }
        
        self.svc_config = {
            "indices": ["Services PMI", "Business Activity"],
            "index_categories": {
                "Business Activity": ["Growing", "Declining"]
            },
            "extraction_prompt": "Svc extraction prompt",
            "correction_prompt": "Svc correction prompt"
        }
        
        # Write config files
        with open(os.path.join(self.config_dir, 'manufacturing_config.json'), 'w') as f:
            json.dump(self.mfg_config, f)
        
        with open(os.path.join(self.config_dir, 'services_config.json'), 'w') as f:
            json.dump(self.svc_config, f)
        
        # Create an invalid config file
        with open(os.path.join(self.config_dir, 'invalid_config.json'), 'w') as f:
            f.write("{invalid json")
    
    def tearDown(self):
        """Clean up after the test."""
        shutil.rmtree(self.test_dir)
    
    def test_config_loading(self):
        """Test loading configurations."""
        loader = ConfigLoader(self.config_dir)
        
        # Check loaded configs
        self.assertIn('Manufacturing', loader.configs)
        self.assertIn('Services', loader.configs)
        
        # Check config types
        self.assertIsInstance(loader.configs['Manufacturing'], ReportConfig)
        self.assertIsInstance(loader.configs['Services'], ReportConfig)
    
    def test_get_config(self):
        """Test getting a specific configuration."""
        loader = ConfigLoader(self.config_dir)
        
        # Get Manufacturing config
        mfg_config = loader.get_config('Manufacturing')
        self.assertIsNotNone(mfg_config)
        self.assertEqual(mfg_config.indices, ["Manufacturing PMI", "New Orders"])
        
        # Get Services config
        svc_config = loader.get_config('Services')
        self.assertIsNotNone(svc_config)
        self.assertEqual(svc_config.indices, ["Services PMI", "Business Activity"])
        
        # Get non-existent config
        none_config = loader.get_config('NonExistent')
        self.assertIsNone(none_config)
    
    def test_get_indices(self):
        """Test getting indices for a report type."""
        loader = ConfigLoader(self.config_dir)
        
        # Get Manufacturing indices
        mfg_indices = loader.get_indices('Manufacturing')
        self.assertEqual(mfg_indices, ["Manufacturing PMI", "New Orders"])
        
        # Get Services indices
        svc_indices = loader.get_indices('Services')
        self.assertEqual(svc_indices, ["Services PMI", "Business Activity"])
        
        # Get indices for non-existent report type
        none_indices = loader.get_indices('NonExistent')
        self.assertEqual(none_indices, [])
    
    def test_get_index_categories(self):
        """Test getting categories for a specific index."""
        loader = ConfigLoader(self.config_dir)
        
        # Get categories for an index in the config
        new_orders_categories = loader.get_index_categories('Manufacturing', 'New Orders')
        self.assertEqual(new_orders_categories, ["Growing", "Declining"])
        
        # Get categories for an index not in the config
        supplier_deliveries_categories = loader.get_index_categories('Manufacturing', 'Supplier Deliveries')
        self.assertEqual(supplier_deliveries_categories, ["Slower", "Faster"])
        
        # Get categories for an index in a non-existent report type
        default_categories = loader.get_index_categories('NonExistent', 'Some Index')
        self.assertEqual(default_categories, ["Growing", "Declining"])
    
    def test_get_prompts(self):
        """Test getting prompts for a report type."""
        loader = ConfigLoader(self.config_dir)
        
        # Get Manufacturing prompts
        mfg_extraction = loader.get_extraction_prompt('Manufacturing')
        self.assertEqual(mfg_extraction, "Mfg extraction prompt")
        
        mfg_correction = loader.get_correction_prompt('Manufacturing')
        self.assertEqual(mfg_correction, "Mfg correction prompt")
        
        # Get Services prompts
        svc_extraction = loader.get_extraction_prompt('Services')
        self.assertEqual(svc_extraction, "Svc extraction prompt")
        
        svc_correction = loader.get_correction_prompt('Services')
        self.assertEqual(svc_correction, "Svc correction prompt")
        
        # Get prompts for non-existent report type
        none_extraction = loader.get_extraction_prompt('NonExistent')
        self.assertEqual(none_extraction, "Extract data from the report.")
        
        none_correction = loader.get_correction_prompt('NonExistent')
        self.assertEqual(none_correction, "Verify and correct the extracted data.")

if __name__ == '__main__':
    unittest.main()