import os
import logging
import json
import traceback
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union
import re
from extraction_strategy import StrategyRegistry

# Configure logging
logger = logging.getLogger(__name__)

class ReportTypeHandler(ABC):
    """
    Abstract base class for different report type handlers.
    This defines the interface that all concrete report type handlers must implement.
    """
    
    def __init__(self, config_path=None):
        """
        Initialize the report type handler.
        
        Args:
            config_path: Path to the configuration file for this report type
        """
        self.config = self._load_config(config_path)
        
    def _load_config(self, config_path):
        """Load configuration from file if available."""
        if not config_path or not os.path.exists(config_path):
            return {}
            
        try:
            with open(config_path, 'r') as f:
                if config_path.endswith('.json'):
                    return json.load(f)
                elif config_path.endswith('.yaml') or config_path.endswith('.yml'):
                    import yaml
                    return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error loading config from {config_path}: {str(e)}")
            return {}
    
    def extract_data_from_text(self, text: str, pdf_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract data from report text using appropriate strategies.
        If the extraction_strategy module is available, use it; otherwise fall back to simpler extraction.
        
        Args:
            text: The extracted text from the report
            pdf_path: Optional path to the original PDF
            
        Returns:
            Dictionary containing all extracted data
        """
        try:
            # Try to import and use the strategy registry
            from extraction_strategy import StrategyRegistry
            
            result = {}
            
            # Get all applicable strategies for this report type
            report_type = self.__class__.__name__.replace('ReportHandler', '')
            strategies = StrategyRegistry.get_strategies_for_report_type(report_type)
            
            # Apply each strategy
            for strategy_class in strategies:
                try:
                    strategy = strategy_class()
                    strategy_result = strategy.extract(text, pdf_path)
                    
                    # Merge with existing result
                    for key, value in strategy_result.items():
                        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                            # Merge dictionaries
                            result[key].update(value)
                        else:
                            # Replace or add the value
                            result[key] = value
                except Exception as e:
                    logger.error(f"Error applying strategy {strategy_class.__name__}: {str(e)}")
            
            return result
        except ImportError:
            # Fall back to basic extraction
            logger.warning("Extraction strategy module not available, falling back to basic extraction")
            
            result = {
                "month_year": self.parse_report_month_year(text) or "Unknown",
                "industry_data": self.extract_industry_data(text, {}),
                "index_summaries": {},
                "indices": {}
            }
            
            return result
    
    @abstractmethod
    def get_indices(self) -> List[str]:
        """Get the list of indices for this report type."""
        pass
        
    @abstractmethod
    def get_index_categories(self, index_name: str) -> List[str]:
        """
        Get the categories for a specific index.
        
        Args:
            index_name: Name of the index
            
        Returns:
            List of category names
        """
        pass
    
    @abstractmethod
    def get_extraction_prompt(self) -> str:
        """Get the extraction prompt for this report type."""
        pass
        
    @abstractmethod
    def get_correction_prompt(self) -> str:
        """Get the correction prompt for this report type."""
        pass
        
    @abstractmethod
    def parse_report_month_year(self, text: str) -> Optional[str]:
        """
        Parse the month and year from the report text.
        
        Args:
            text: The extracted text from the report
            
        Returns:
            Month and year as a string (e.g., "January 2025") or None if parsing fails
        """
        pass
        
    @abstractmethod
    def extract_industry_data(self, text: str, index_summaries: Dict[str, str]) -> Dict[str, Dict[str, List[str]]]:
        """
        Extract industry data from the report text and index summaries.
        
        Args:
            text: The extracted text from the report
            index_summaries: Dictionary mapping index names to their summaries
            
        Returns:
            Dictionary mapping indices to categories to lists of industries
        """
        pass
        
    @abstractmethod
    def extract_pmi_values(self, text: str, index_summaries: Dict[str, str]) -> Dict[str, Dict[str, Union[str, float]]]:
        """
        Extract PMI values from the report text and index summaries.
        
        Args:
            text: The extracted text from the report
            index_summaries: Dictionary mapping index names to their summaries
            
        Returns:
            Dictionary mapping indices to dictionaries with value and direction
        """
        pass
    
    def clean_industry_name(self, industry: str) -> Optional[str]:
        """
        Clean industry name to remove common artifacts.
        
        Args:
            industry: Raw industry name string
            
        Returns:
            Cleaned industry name or None if invalid
        """
        if not industry or not isinstance(industry, str):
            return None

        # Remove leading/trailing whitespace
        industry = industry.strip()

        # Skip parsing artifacts
        artifacts = [
            "following order",
            "are:",
            "in order",
            "listed in order",
            "in the following order",
            "reporting",
            "categories"
        ]

        industry_lower = industry.lower()
        for artifact in artifacts:
            if artifact in industry_lower:
                return None

        # Remove common prefixes and suffixes
        industry = re.sub(r"^(the\s+|and\s+|order\s+)", "", industry, flags=re.IGNORECASE)
        industry = re.sub(r"(\s+products)$", "", industry, flags=re.IGNORECASE)
        
        # Normalize whitespace
        industry = re.sub(r'\s+', ' ', industry).strip()

        # Remove any parsing leftovers at the beginning
        industry = re.sub(r"^[s]\s+", "", industry, flags=re.IGNORECASE)
        industry = re.sub(r"^[-—]\s+", "", industry, flags=re.IGNORECASE)
        industry = re.sub(r"^[a-z]\s+", "", industry, flags=re.IGNORECASE)
        
        # Skip if starts with punctuation
        if re.match(r'^[,;:.]+', industry):
            return None

        # Skip if too short
        if len(industry) < 3:
            return None
        
        return industry


class ManufacturingReportHandler(ReportTypeHandler):
    """Handler for Manufacturing PMI reports."""
    
    def __init__(self, config_path=None):
        """Initialize with optional custom config path."""
        if not config_path:
            from config_loader import config_loader
            self.config_loader = config_loader
            super().__init__(None)  # No direct config file, using config_loader instead
        else:
            self.config_loader = None
            super().__init__(config_path)
        
        # Default indices if not in config
        self._default_indices = [
            "Manufacturing PMI",
            "New Orders", 
            "Production", 
            "Employment", 
            "Supplier Deliveries",
            "Inventories", 
            "Customers' Inventories", 
            "Prices", 
            "Backlog of Orders",
            "New Export Orders", 
            "Imports"
        ]
        
        # Default index categories if not in config
        self._default_index_categories = {
            "New Orders": ["Growing", "Declining"],
            "Production": ["Growing", "Declining"],
            "Employment": ["Growing", "Declining"],
            "Supplier Deliveries": ["Slower", "Faster"],
            "Inventories": ["Higher", "Lower"],
            "Customers' Inventories": ["Too High", "Too Low"],
            "Prices": ["Increasing", "Decreasing"],
            "Backlog of Orders": ["Growing", "Declining"],
            "New Export Orders": ["Growing", "Declining"],
            "Imports": ["Growing", "Declining"]
        }
    
    def get_indices(self) -> List[str]:
        """Get the list of indices for Manufacturing reports."""
        if self.config_loader:
            return self.config_loader.get_indices("Manufacturing")
        return self.config.get('indices', self._default_indices)
        
    def get_index_categories(self, index_name: str) -> List[str]:
        """Get the categories for a specific Manufacturing index."""
        if self.config_loader:
            return self.config_loader.get_index_categories("Manufacturing", index_name)
        
        # Rest of the method remains the same if using direct config
        if 'index_categories' in self.config and index_name in self.config['index_categories']:
            return self.config['index_categories'][index_name]
        return self._default_index_categories.get(index_name, ["Growing", "Declining"])
    
    def get_extraction_prompt(self) -> str:
        """Get the extraction prompt for Manufacturing reports."""
        if self.config_loader:
            return self.config_loader.get_extraction_prompt("Manufacturing")
        return self.config.get('extraction_prompt', """
        Extract all relevant data from the ISM Manufacturing Report PDF.
        
        You must extract:
        1. The month and year of the report
        2. The Manufacturing at a Glance table
        3. All index-specific summaries (New Orders, Production, etc.)
        4. Industry mentions in each index summary

        VERY IMPORTANT CLASSIFICATION RULES:
        For each index, you must carefully identify the correct category for each industry:

        - New Orders, Production, Employment, Backlog of Orders, New Export Orders, Imports:
        * GROWING category: Industries explicitly mentioned as reporting "growth", "expansion", "increase", or similar positive terms
        * DECLINING category: Industries explicitly mentioned as reporting "contraction", "decline", "decrease" or similar negative terms

        - Supplier Deliveries:
        * SLOWER category: Industries reporting "slower" deliveries
        * FASTER category: Industries reporting "faster" deliveries

        - Inventories:
        * HIGHER category: Industries reporting "higher" or "increased" inventories
        * LOWER category: Industries reporting "lower" or "decreased" inventories

        - Customers' Inventories:
        * TOO HIGH category: Industries reporting customers' inventories as "too high"
        * TOO LOW category: Industries reporting customers' inventories as "too low"

        - Prices:
        * INCREASING category: Industries reporting "higher" or "increasing" prices
        * DECREASING category: Industries reporting "lower" or "decreasing" prices

        YOUR FINAL ANSWER MUST BE A VALID DICTIONARY containing all extracted data.
        """)
        
    def get_correction_prompt(self) -> str:
        """Get the correction prompt for Manufacturing reports."""
        if self.config_loader:
            return self.config_loader.get_correction_prompt("Manufacturing")
        return self.config.get('correction_prompt', """
        CRITICAL TASK: You must carefully verify and correct the industry categorization in the extracted data.
        
        STEP 1: Carefully examine the textual summaries in index_summaries to find industry mentions.
        
        STEP 2: For each index (New Orders, Production, etc.), verify which industries are mentioned as:
        - GROWING vs DECLINING for most indices
        - SLOWER vs FASTER for Supplier Deliveries
        - HIGHER vs LOWER for Inventories
        - TOO HIGH vs TOO LOW for Customers' Inventories
        - INCREASING vs DECREASING for Prices

        STEP 3: Compare your findings against industry_data to identify errors.
        Common errors include:
        - Industries placed in the wrong category (e.g., growing when they should be declining)
        - Missing industries that were mentioned in the text
        - Industries appearing in both categories for a single index

        STEP 4: Correct any errors by:
        - Moving industries to the correct category
        - Adding missing industries to appropriate categories
        - Removing industries from incorrect categories

        STEP 5: Return a COMPLETE, CORRECTED copy of the data with your changes implemented.
        """)
        
    def parse_report_month_year(self, text: str) -> Optional[str]:
        """Parse the month and year from the Manufacturing report text."""
        try:
            # Try multiple patterns to find month and year
            patterns = [
                # Pattern for "Month YYYY Manufacturing"
                r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\s+MANUFACTURING",
                # Pattern for "Manufacturing at a Glance Month YYYY"
                r"MANUFACTURING AT A GLANCE\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
                # Pattern for "Month YYYY Manufacturing Index"
                r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\s+MANUFACTURING INDEX",
                # Try to find in PMI Index section
                r"Manufacturing PMI®.*?(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
                # Look for "MONTH YEAR INDEX SUMMARIES"
                r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4}) MANUFACTURING INDEX SUMMARIES",
                # Look for "Report On Business® Month YEAR"
                r"Report\s+On\s+Business®\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return f"{match.group(1)} {match.group(2)}"
            
            # If no match is found through patterns, try to find dates in the content
            all_dates = re.findall(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", text, re.IGNORECASE)
            if all_dates:
                # Use the most frequent date
                date_counts = {}
                for month, year in all_dates:
                    date = f"{month} {year}"
                    date_counts[date] = date_counts.get(date, 0) + 1
                
                most_common_date = max(date_counts.items(), key=lambda x: x[1])[0]
                return most_common_date
            
            return None
        except Exception as e:
            logger.error(f"Error extracting month and year: {str(e)}")
            return None
            
    def extract_industry_data(self, text: str, index_summaries: Dict[str, str]) -> Dict[str, Dict[str, List[str]]]:
        """
        Extract industry data from Manufacturing report text and index summaries.
        Calls the existing extraction logic from pdf_utils.py.
        """
        try:
            from pdf_utils import extract_industry_mentions
            return extract_industry_mentions(text, index_summaries)
        except Exception as e:
            logger.error(f"Error extracting industry data: {str(e)}")
            logger.error(traceback.format_exc())
            return {}
            
    def extract_pmi_values(self, text: str, index_summaries: Dict[str, str]) -> Dict[str, Dict[str, Union[str, float]]]:
        """
        Extract PMI values from Manufacturing report text and index summaries.
        Calls the existing extraction logic from pdf_utils.py.
        """
        try:
            from pdf_utils import extract_pmi_values_from_summaries
            return extract_pmi_values_from_summaries(index_summaries)
        except Exception as e:
            logger.error(f"Error extracting PMI values: {str(e)}")
            logger.error(traceback.format_exc())
            return {}


class ServicesReportHandler(ReportTypeHandler):
    """Handler for Services PMI reports."""
    
    def __init__(self, config_path=None):
        """Initialize with optional custom config path."""
        if not config_path:
            from config_loader import config_loader
            self.config_loader = config_loader
            super().__init__(None)  # No direct config file, using config_loader instead
        else:
            self.config_loader = None
            super().__init__(config_path)
        
        # Default indices if not in config
        self._default_indices = [
            "Services PMI",
            "Business Activity", 
            "New Orders", 
            "Employment", 
            "Supplier Deliveries",
            "Inventories", 
            "Inventory Sentiment", 
            "Prices", 
            "Backlog of Orders",
            "New Export Orders", 
            "Imports"
        ]
        
        # Default index categories if not in config
        self._default_index_categories = {
            "Business Activity": ["Growing", "Declining"],
            "New Orders": ["Growing", "Declining"],
            "Employment": ["Growing", "Declining"],
            "Supplier Deliveries": ["Slower", "Faster"],
            "Inventories": ["Higher", "Lower"],
            "Inventory Sentiment": ["Too High", "Too Low"],
            "Prices": ["Increasing", "Decreasing"],
            "Backlog of Orders": ["Growing", "Declining"],
            "New Export Orders": ["Growing", "Declining"],
            "Imports": ["Growing", "Declining"]
        }
    
    def get_indices(self) -> List[str]:
        """Get the list of indices for Services reports."""
        if self.config_loader:
            return self.config_loader.get_indices("Services")
        return self.config.get('indices', self._default_indices)
        
    def get_index_categories(self, index_name: str) -> List[str]:
        """Get the categories for a specific Services index."""
        if self.config_loader:
            return self.config_loader.get_index_categories("Services", index_name)
        
        # Rest of the method remains the same if using direct config
        if 'index_categories' in self.config and index_name in self.config['index_categories']:
            return self.config['index_categories'][index_name]
        return self._default_index_categories.get(index_name, ["Growing", "Declining"])
    
    def get_extraction_prompt(self) -> str:
        """Get the extraction prompt for Services reports."""
        if self.config_loader:
            return self.config_loader.get_extraction_prompt("Services")
        return self.config.get('extraction_prompt', """
        Extract all relevant data from the ISM Services Report PDF.
        
        You must extract:
        1. The month and year of the report
        2. The Services at a Glance table
        3. All index-specific summaries (Business Activity, New Orders, etc.)
        4. Industry mentions in each index summary

        VERY IMPORTANT CLASSIFICATION RULES:
        For each index, you must carefully identify the correct category for each industry:

        - Business Activity, New Orders, Employment, Backlog of Orders, New Export Orders, Imports:
        * GROWING category: Industries explicitly mentioned as reporting "growth", "expansion", "increase", or similar positive terms
        * DECLINING category: Industries explicitly mentioned as reporting "contraction", "decline", "decrease" or similar negative terms

        - Supplier Deliveries:
        * SLOWER category: Industries reporting "slower" deliveries
        * FASTER category: Industries reporting "faster" deliveries

        - Inventories:
        * HIGHER category: Industries reporting "higher" or "increased" inventories
        * LOWER category: Industries reporting "lower" or "decreased" inventories

        - Inventory Sentiment:
        * TOO HIGH category: Industries reporting inventory sentiment as "too high"
        * TOO LOW category: Industries reporting inventory sentiment as "too low"

        - Prices:
        * INCREASING category: Industries reporting "higher" or "increasing" prices
        * DECREASING category: Industries reporting "lower" or "decreasing" prices

        YOUR FINAL ANSWER MUST BE A VALID DICTIONARY containing all extracted data.
        """)
        
    def get_correction_prompt(self) -> str:
        """Get the correction prompt for Services reports."""
        if self.config_loader:
            return self.config_loader.get_correction_prompt("Services")
        return self.config.get('correction_prompt', """
        CRITICAL TASK: You must carefully verify and correct the industry categorization in the extracted data.
        
        STEP 1: Carefully examine the textual summaries in index_summaries to find industry mentions.
        
        STEP 2: For each index (Business Activity, New Orders, etc.), verify which industries are mentioned as:
        - GROWING vs DECLINING for most indices
        - SLOWER vs FASTER for Supplier Deliveries
        - HIGHER vs LOWER for Inventories
        - TOO HIGH vs TOO LOW for Inventory Sentiment
        - INCREASING vs DECREASING for Prices

        STEP 3: Compare your findings against industry_data to identify errors.
        Common errors include:
        - Industries placed in the wrong category (e.g., growing when they should be declining)
        - Missing industries that were mentioned in the text
        - Industries appearing in both categories for a single index

        STEP 4: Correct any errors by:
        - Moving industries to the correct category
        - Adding missing industries to appropriate categories
        - Removing industries from incorrect categories

        STEP 5: Return a COMPLETE, CORRECTED copy of the data with your changes implemented.
        """)
        
    def parse_report_month_year(self, text: str) -> Optional[str]:
        """Parse the month and year from the Services report text."""
        try:
            # Try multiple patterns to find month and year
            patterns = [
                # Pattern for "Month YYYY Services"
                r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\s+SERVICES",
                # Pattern for "Services at a Glance Month YYYY"
                r"SERVICES AT A GLANCE\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
                # Try to find in PMI Index section
                r"Services PMI®.*?(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
                # Look for "MONTH YEAR SERVICES INDEX SUMMARIES"
                r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4}) SERVICES INDEX SUMMARIES",
                # Look for "Report On Business® Month YEAR"
                r"Services ISM.*?Report On Business®\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return f"{match.group(1)} {match.group(2)}"
            
            # If no match is found through patterns, try to find dates in the content
            all_dates = re.findall(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", text, re.IGNORECASE)
            if all_dates:
                # Use the most frequent date
                date_counts = {}
                for month, year in all_dates:
                    date = f"{month} {year}"
                    date_counts[date] = date_counts.get(date, 0) + 1
                
                most_common_date = max(date_counts.items(), key=lambda x: x[1])[0]
                return most_common_date
            
            return None
        except Exception as e:
            logger.error(f"Error extracting month and year: {str(e)}")
            return None
            
    def extract_industry_data(self, text: str, index_summaries: Dict[str, str]) -> Dict[str, Dict[str, List[str]]]:
        """Extract industry data from Services report text and index summaries."""
        try:
            industry_data = {}
            
            # Process each index summary
            for index_name, summary in index_summaries.items():
                # Skip if it's not a real index
                if index_name not in self.get_indices():
                    continue
                    
                # Get categories for this index
                categories = {category: [] for category in self.get_index_categories(index_name)}
                
                # Process based on index type
                if index_name == "Business Activity":
                    # Extract growing industries
                    growing_pattern = r"The (?:[\w\s]+) industries reporting (?:growth|an increase|increased) in (?:business activity|activity)(?:[^:]*?)(?:are|—|:|-)([^\.]+)"
                    growing_match = re.search(growing_pattern, summary, re.IGNORECASE)
                    
                    if growing_match:
                        growing_text = growing_match.group(1).strip()
                        categories["Growing"] = self._parse_industry_list(growing_text)
                    
                    # Extract declining industries
                    declining_pattern = r"The (?:[\w\s]+) industries reporting (?:a decrease|contraction|decline) in (?:business activity|activity)(?:[^:]*?)(?:are|—|:|-)([^\.]+)"
                    declining_match = re.search(declining_pattern, summary, re.IGNORECASE)
                    
                    if declining_match:
                        declining_text = declining_match.group(1).strip()
                        categories["Declining"] = self._parse_industry_list(declining_text)
                
                elif index_name == "Supplier Deliveries":
                    # Extract slower deliveries
                    slower_pattern = r"The (?:[\w\s]+) industries reporting (?:slower|slowing) (?:supplier )?deliveries(?:[^:]*?)(?:are|—|:|-)([^\.]+)"
                    slower_match = re.search(slower_pattern, summary, re.IGNORECASE)
                    
                    if slower_match:
                        slower_text = slower_match.group(1).strip()
                        categories["Slower"] = self._parse_industry_list(slower_text)
                    
                    # Extract faster deliveries
                    faster_pattern = r"The (?:[\w\s]+) industries reporting (?:faster) (?:supplier )?deliveries(?:[^:]*?)(?:are|—|:|-)([^\.]+)"
                    faster_match = re.search(faster_pattern, summary, re.IGNORECASE)
                    
                    if faster_match:
                        faster_text = faster_match.group(1).strip()
                        categories["Faster"] = self._parse_industry_list(faster_text)
                
                # Similar patterns for other indices...
                
                # Add to industry_data if we have any valid industries
                if any(len(inds) > 0 for inds in categories.values()):
                    industry_data[index_name] = categories
            
            return industry_data
        except Exception as e:
            logger.error(f"Error extracting industry data: {str(e)}")
            logger.error(traceback.format_exc())
            return {}
            
    def _parse_industry_list(self, text: str) -> List[str]:
        """
        Parse a list of industries from text.
        
        Args:
            text: Text containing a list of industries
            
        Returns:
            List of industry names
        """
        if not text:
            return []
            
        # Try to split by common delimiters
        if ';' in text:
            # Semicolon-separated list
            raw_industries = [ind.strip() for ind in text.split(';')]
        elif ',' in text:
            # Comma-separated list
            raw_industries = [ind.strip() for ind in text.split(',')]
        else:
            # Just treat as a single industry
            raw_industries = [text.strip()]
            
        # Clean and validate each industry
        industries = []
        for ind in raw_industries:
            clean_ind = self.clean_industry_name(ind)
            if clean_ind:
                industries.append(clean_ind)
                
        return industries
            
    def extract_pmi_values(self, text: str, index_summaries: Dict[str, str]) -> Dict[str, Dict[str, Union[str, float]]]:
        """Extract PMI values from Services report text and index summaries."""
        try:
            pmi_data = {}
            
            # Process each index summary
            for index_name, summary in index_summaries.items():
                # Skip if it's not a real index
                if index_name not in self.get_indices():
                    continue
                    
                # Extract value
                value_pattern = r"(?:registered|reading of|index of|was) (\d+\.?\d*)"
                value_match = re.search(value_pattern, summary, re.IGNORECASE)
                
                # Extract direction
                direction_pattern = r"(growing|growth|expanding|expansion|contracting|contraction|declining|increasing|decreasing|faster|slower)"
                direction_match = re.search(direction_pattern, summary, re.IGNORECASE)
                
                if value_match:
                    value = float(value_match.group(1))
                    
                    # Determine direction from text or based on value
                    if direction_match:
                        direction = direction_match.group(1)
                        # Standardize direction terms
                        if direction.lower() in ['growing', 'growth', 'expanding', 'expansion', 'increasing']:
                            direction = 'Growing'
                        elif direction.lower() in ['contracting', 'contraction', 'declining', 'decreasing']:
                            direction = 'Contracting'
                        elif direction.lower() == 'slower':
                            direction = 'Slowing'
                        elif direction.lower() == 'faster':
                            direction = 'Faster'
                    else:
                        # Default direction based on value
                        direction = 'Growing' if value >= 50.0 else 'Contracting'
                    
                    pmi_data[index_name] = {
                        'value': value,
                        'direction': direction
                    }
            
            return pmi_data
        except Exception as e:
            logger.error(f"Error extracting PMI values: {str(e)}")
            logger.error(traceback.format_exc())
            return {}


class ReportTypeFactory:
    """Factory for creating report type handlers."""
    
    @staticmethod
    def detect_report_type(pdf_path: str) -> str:
        """
        Detect the report type based on the content of the PDF using enhanced detection.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Report type as a string ('Manufacturing' or 'Services')
        """
        try:
            from report_detection import EnhancedReportTypeDetector
            return EnhancedReportTypeDetector.detect_report_type(pdf_path)
        except ImportError:
            logger.warning("Enhanced detector not available, falling back to basic detection")
            # Fall back to basic detection if enhanced detector is not available
            try:
                from pdf_utils import extract_text_from_pdf
                text = extract_text_from_pdf(pdf_path)
                
                if not text:
                    logger.error(f"Failed to extract text from {pdf_path}")
                    # Default to Manufacturing if text extraction fails
                    return 'Manufacturing'
                
                # Check for Services keywords
                services_keywords = [
                    "SERVICES PMI",
                    "SERVICES ISM",
                    "SERVICES INDEX",
                    "NON-MANUFACTURING",
                    "BUSINESS ACTIVITY"
                ]
                
                # Check for Manufacturing keywords
                manufacturing_keywords = [
                    "MANUFACTURING PMI",
                    "MANUFACTURING ISM",
                    "MANUFACTURING INDEX",
                    "PRODUCTION INDEX",
                    "NEW ORDERS INDEX"
                ]
                
                # Count keyword matches for each type
                services_matches = sum(1 for keyword in services_keywords if keyword in text.upper())
                manufacturing_matches = sum(1 for keyword in manufacturing_keywords if keyword in text.upper())
                
                # Determine report type based on matches
                if services_matches > manufacturing_matches:
                    return 'Services'
                else:
                    return 'Manufacturing'
            except Exception as e:
                logger.error(f"Error detecting report type: {str(e)}")
                # Default to Manufacturing if error occurs
                return 'Manufacturing'
    
    @staticmethod
    def create_handler(report_type: str = None, pdf_path: str = None, config_path: str = None) -> ReportTypeHandler:
        """
        Create a report type handler based on report type or PDF content.
        
        Args:
            report_type: Type of report ('Manufacturing' or 'Services')
            pdf_path: Path to the PDF file (used to detect type if report_type is None)
            config_path: Path to the configuration file
            
        Returns:
            Appropriate ReportTypeHandler subclass instance
        """
        # Detect report type if not provided
        if not report_type and pdf_path:
            report_type = ReportTypeFactory.detect_report_type(pdf_path)
            
        # Default to Manufacturing if still not determined
        if not report_type:
            report_type = 'Manufacturing'
            
        # Create the appropriate handler
        if report_type == 'Services':
            return ServicesReportHandler(config_path)
        else:
            return ManufacturingReportHandler(config_path)