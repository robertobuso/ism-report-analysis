import os
import json
import logging
import yaml
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, ValidationError # Keep ValidationError

# Configure logging
logger = logging.getLogger(__name__)

class IndexCategoryConfig(BaseModel): # This model seems unused directly, but keep if planned for future
    """Pydantic model for index category configuration."""
    categories: Dict[str, List[str]] = Field(default_factory=dict)

class ReportConfig(BaseModel):
    """Pydantic model for report configuration."""
    indices: List[str] = Field(...)
    index_categories: Dict[str, List[str]] = Field(...)
    extraction_prompt: str = Field(...)
    correction_prompt: str = Field(...)
    canonical_industries: List[str] = Field(default_factory=list) # Field for canonical industries

class ConfigLoader:
    """Loader for configuration files."""
    
    def __init__(self, config_dir: Optional[str] = None): # Added type hint for config_dir
        """
        Initialize the configuration loader.
        
        Args:
            config_dir: Directory containing configuration files. 
                        Defaults to a 'config' subdirectory relative to this file.
        """
        if config_dir is None:
            # Path relative to this file (config_loader.py)
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_dir = os.path.join(base_dir, 'config')
        
        self.config_dir = config_dir
        self.configs: Dict[str, ReportConfig] = {} # Type hint for clarity
        
        # Create config directory if it doesn't exist - good for initial setup
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            logger.info(f"Config directory set to: {self.config_dir}")
        except OSError as e:
            logger.error(f"Could not create or access config directory {self.config_dir}: {e}")
            # Depending on desired behavior, you might raise an error or proceed with empty configs
            # For now, we'll let _load_configs handle the case where the dir might still be problematic
        
        self._load_configs()
    
    def _load_configs(self):
        """Load all configuration files from the config directory."""
        try:
            if not os.path.exists(self.config_dir) or not os.path.isdir(self.config_dir):
                logger.warning(f"Config directory {self.config_dir} not found or is not a directory. No configs loaded.")
                return

            for filename in os.listdir(self.config_dir):
                if filename.endswith(('.json', '.yaml', '.yml')):
                    file_path = os.path.join(self.config_dir, filename)
                    config_name = os.path.splitext(filename)[0] # e.g., "manufacturing_config"
                    
                    if not config_name.lower().endswith('_config'):
                        logger.debug(f"Skipping file (does not end with '_config'): {filename}")
                        continue
                    
                    # Derive report_type: "manufacturing_config" -> "Manufacturing"
                    report_type_str = config_name.lower().replace('_config', '').capitalize()
                    if not report_type_str:
                        logger.warning(f"Could not determine report type from filename: {filename}")
                        continue
                        
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f: # Added encoding
                            config_data: Dict[Any, Any] # Type hint for loaded data
                            if filename.endswith('.json'):
                                config_data = json.load(f)
                            elif filename.endswith(('.yaml', '.yml')): # Handled both .yaml and .yml
                                config_data = yaml.safe_load(f)
                            else: # Should not be reached due to outer check
                                continue 
                                
                        # Validate config using Pydantic model
                        config = ReportConfig(**config_data)
                        self.configs[report_type_str] = config
                        logger.info(f"Successfully loaded and validated configuration for '{report_type_str}' from {filename}")
                    except (json.JSONDecodeError, yaml.YAMLError) as e_parse:
                        logger.error(f"Error parsing config file {file_path}: {e_parse}")
                    except ValidationError as e_validate:
                        logger.error(f"Configuration validation error in {file_path} for report type '{report_type_str}': {e_validate}")
                    except Exception as e_general: # Catch other potential errors
                        logger.error(f"Unexpected error processing config file {file_path}: {e_general}")
        except FileNotFoundError:
            logger.warning(f"Configuration directory '{self.config_dir}' was not found during scan. No configurations loaded.")
        except Exception as e: # Catch errors like permission issues with listdir
            logger.error(f"Error accessing or listing configuration directory '{self.config_dir}': {str(e)}")
    
    def get_config(self, report_type: str) -> Optional[ReportConfig]:
        """
        Get configuration for a specific report type.
        """
        return self.configs.get(report_type.capitalize()) # Standardize access key
    
    def get_indices(self, report_type: str) -> List[str]:
        """
        Get indices for a specific report type.
        """
        config = self.get_config(report_type)
        return config.indices if config else []
    
    def get_index_categories(self, report_type: str, index_name: str) -> List[str]:
        """
        Get categories for a specific index in a report type.
        """
        config = self.get_config(report_type)
        if config and index_name in config.index_categories:
            return config.index_categories[index_name]
        
        # Fallback default categories (as before)
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
        """
        config = self.get_config(report_type)
        return config.extraction_prompt if config else "Extract data from the report."
    
    def get_correction_prompt(self, report_type: str) -> str:
        """
        Get correction prompt for a specific report type.
        """
        config = self.get_config(report_type)
        return config.correction_prompt if config else "Verify and correct the extracted data."

    def get_canonical_industries(self, report_type: str) -> List[str]:
        """
        Get the list of canonical industries for a specific report type.
        Returns an empty list if not configured or report type not found.
        """
        config = self.get_config(report_type)
        if config and config.canonical_industries:
            return config.canonical_industries
        logger.warning(f"Canonical industries not configured or found for report type: {report_type}")
        return []

# Create singleton instance
# This will load configs when the module is imported.
config_loader = ConfigLoader()