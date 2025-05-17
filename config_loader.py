import os
import json
import logging
import yaml
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, ValidationError

# Configure logging
logger = logging.getLogger(__name__)

class IndexCategoryConfig(BaseModel):
    """Pydantic model for index category configuration."""
    categories: Dict[str, List[str]] = Field(default_factory=dict)

class ReportConfig(BaseModel):
    """Pydantic model for report configuration."""
    indices: List[str] = Field(...)
    index_categories: Dict[str, List[str]] = Field(...)
    extraction_prompt: str = Field(...)
    correction_prompt: str = Field(...)

class ConfigLoader:
    """Loader for configuration files."""
    
    def __init__(self, config_dir=None):
        """
        Initialize the configuration loader.
        
        Args:
            config_dir: Directory containing configuration files
        """
        if config_dir is None:
            config_dir = os.path.join(os.path.dirname(__file__), 'config')
        
        self.config_dir = config_dir
        self.configs = {}
        
        # Create config directory if it doesn't exist
        os.makedirs(self.config_dir, exist_ok=True)
        
        # Load configurations
        self._load_configs()
    
    def _load_configs(self):
        """Load all configuration files from the config directory."""
        try:
            for filename in os.listdir(self.config_dir):
                if filename.endswith(('.json', '.yaml', '.yml')):
                    file_path = os.path.join(self.config_dir, filename)
                    config_name = os.path.splitext(filename)[0]
                    
                    # Skip if not a report config
                    if not config_name.endswith('_config'):
                        continue
                    
                    # Get report type from filename
                    report_type = config_name.split('_')[0].capitalize()
                    
                    try:
                        with open(file_path, 'r') as f:
                            if filename.endswith('.json'):
                                config_data = json.load(f)
                            elif filename.endswith(('.yaml', '.yml')):
                                config_data = yaml.safe_load(f)
                                
                            # Validate config
                            config = ReportConfig(**config_data)
                            self.configs[report_type] = config
                            logger.info(f"Loaded configuration for {report_type} from {filename}")
                    except (json.JSONDecodeError, yaml.YAMLError) as e:
                        logger.error(f"Error parsing {file_path}: {str(e)}")
                    except ValidationError as e:
                        logger.error(f"Invalid configuration in {file_path}: {str(e)}")
        except Exception as e:
            logger.error(f"Error loading configurations: {str(e)}")
    
    def get_config(self, report_type: str) -> Optional[ReportConfig]:
        """
        Get configuration for a specific report type.
        
        Args:
            report_type: Report type (e.g., 'Manufacturing', 'Services')
            
        Returns:
            ReportConfig or None if not found
        """
        return self.configs.get(report_type)
    
    def get_indices(self, report_type: str) -> List[str]:
        """
        Get indices for a specific report type.
        
        Args:
            report_type: Report type (e.g., 'Manufacturing', 'Services')
            
        Returns:
            List of indices
        """
        config = self.get_config(report_type)
        if config:
            return config.indices
        return []
    
    def get_index_categories(self, report_type: str, index_name: str) -> List[str]:
        """
        Get categories for a specific index in a report type.
        
        Args:
            report_type: Report type (e.g., 'Manufacturing', 'Services')
            index_name: Name of the index
            
        Returns:
            List of categories
        """
        config = self.get_config(report_type)
        if config and index_name in config.index_categories:
            return config.index_categories[index_name]
        
        # Default categories if not found
        if index_name == "Supplier Deliveries":
            return ["Slower", "Faster"]
        elif index_name == "Inventories":
            return ["Higher", "Lower"]
        elif index_name in ["Customers' Inventories", "Inventory Sentiment"]:
            return ["Too High", "Too Low"]
        elif index_name == "Prices":
            return ["Increasing", "Decreasing"]
        else:
            return ["Growing", "Declining"]
    
    def get_extraction_prompt(self, report_type: str) -> str:
        """
        Get extraction prompt for a specific report type.
        
        Args:
            report_type: Report type (e.g., 'Manufacturing', 'Services')
            
        Returns:
            Extraction prompt string
        """
        config = self.get_config(report_type)
        if config:
            return config.extraction_prompt
        return "Extract data from the report."
    
    def get_correction_prompt(self, report_type: str) -> str:
        """
        Get correction prompt for a specific report type.
        
        Args:
            report_type: Report type (e.g., 'Manufacturing', 'Services')
            
        Returns:
            Correction prompt string
        """
        config = self.get_config(report_type)
        if config:
            return config.correction_prompt
        return "Verify and correct the extracted data."

# Create singleton instance
config_loader = ConfigLoader()