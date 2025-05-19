# extraction_strategy.py
import logging
import re
import abc
from typing import Dict, List, Any, Optional, Union, Set, Type
import pdfplumber
from PyPDF2 import PdfReader
import json

logger = logging.getLogger(__name__)

class ExtractionStrategy(abc.ABC):
    """Abstract base class for all extraction strategies."""
    
    @abc.abstractmethod
    def extract(self, text: str, pdf_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract information using this strategy.
        
        Args:
            text: The text content to extract from
            pdf_path: Optional path to the original PDF for direct access if needed
            
        Returns:
            Dictionary containing the extracted data
        """
        pass
    
    @classmethod
    def get_strategy_metadata(cls) -> Dict[str, Any]:
        """
        Get metadata about this strategy for the registry.
        
        Returns:
            Dictionary with metadata like applicable_report_types, section_type, etc.
        """
        # Default implementation - should be overridden by subclasses
        return {
            "name": cls.__name__,
            "applicable_report_types": ["Manufacturing", "Services"],
            "section_type": "generic",
            "priority": 5  # Scale of 1-10, 10 being highest
        }

class DateExtractionStrategy(ExtractionStrategy):
    """Strategy for extracting month and year from report."""
    
    def extract(self, text: str, pdf_path: Optional[str] = None) -> Dict[str, Any]:
        """Extract month and year from the report text."""
        try:
            # Try multiple patterns to find month and year
            patterns = [
                # Month YYYY Report Type
                r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\s+(MANUFACTURING|SERVICES)",
                # Report Type at a Glance Month YYYY
                r"(MANUFACTURING|SERVICES) AT A GLANCE\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
                # Month YYYY Index
                r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\s+(?:MANUFACTURING|SERVICES) INDEX",
                # Generic Month YYYY pattern
                r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})"
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    groups = match.groups()
                    if len(groups) == 3:  # Pattern with report type
                        month, year, _ = groups if groups[0].lower() in [m.lower() for m in ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]] else (groups[1], groups[2], groups[0])
                    else:  # Pattern without report type
                        month, year = groups
                    
                    return {"month_year": f"{month} {year}"}
            
            # If no match is found, try to find any dates
            all_dates = re.findall(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", text, re.IGNORECASE)
            if all_dates:
                # Use the most frequent date
                date_counts = {}
                for month, year in all_dates:
                    date = f"{month} {year}"
                    date_counts[date] = date_counts.get(date, 0) + 1
                
                most_common_date = max(date_counts.items(), key=lambda x: x[1])[0]
                return {"month_year": most_common_date}
            
            return {"month_year": "Unknown"}
        except Exception as e:
            logger.error(f"Error extracting month and year: {str(e)}")
            return {"month_year": "Unknown"}
    
    @classmethod
    def get_strategy_metadata(cls) -> Dict[str, Any]:
        return {
            "name": cls.__name__,
            "applicable_report_types": ["Manufacturing", "Services"],
            "section_type": "date",
            "priority": 9  # High priority - needed early
        }

class TableExtractionStrategy(ExtractionStrategy):
    """Strategy for extracting 'At a Glance' tables from reports."""
    
    def extract(self, text: str, pdf_path: Optional[str] = None) -> Dict[str, Any]:
        """Extract table data from the report."""
        try:
            # Different approach for Manufacturing vs Services
            if "MANUFACTURING AT A GLANCE" in text.upper():
                return self._extract_manufacturing_table(text, pdf_path)
            elif "SERVICES AT A GLANCE" in text.upper():
                return self._extract_services_table(text, pdf_path)
            else:
                # Try both approaches and see which gives better results
                mfg_result = self._extract_manufacturing_table(text, pdf_path)
                svc_result = self._extract_services_table(text, pdf_path)
                
                # Determine which result is better based on number of indices found
                mfg_indices = mfg_result.get("indices", {})
                svc_indices = svc_result.get("indices", {})
                
                if len(mfg_indices) >= len(svc_indices):
                    return mfg_result
                else:
                    return svc_result
        except Exception as e:
            logger.error(f"Error extracting table: {str(e)}")
            return {"indices": {}}
    
    def _extract_manufacturing_table(self, text: str, pdf_path: Optional[str] = None) -> Dict[str, Any]:
        """Extract Manufacturing at a Glance table."""
        try:
            # Try to locate the table section
            table_pattern = r"MANUFACTURING AT A GLANCE.*?(?:Month|COMMODITIES REPORTED)"
            match = re.search(table_pattern, text, re.DOTALL | re.IGNORECASE)
            if not match:
                # Fallback pattern
                table_pattern = r"MANUFACTURING AT A GLANCE.*?OVERALL ECONOMY"
                match = re.search(table_pattern, text, re.DOTALL | re.IGNORECASE)
            
            table_text = match.group(0) if match else ""
            
            # Extract indices and their values
            indices = {}
            
            # List of indices to extract
            index_names = [
                "Manufacturing PMI", "New Orders", "Production", "Employment",
                "Supplier Deliveries", "Inventories", "Customers' Inventories",
                "Prices", "Backlog of Orders", "New Export Orders", "Imports"
            ]
            
            for index in index_names:
                # Pattern to find index values like "Manufacturing PMI® at 52.8%"
                pattern = rf"{re.escape(index)}®?\s*(?:at|was|registered|is)\s*(\d+\.\d+)%?.*?(Growing|Contracting|Too High|Too Low|Slowing|Faster)"
                match = re.search(pattern, table_text, re.IGNORECASE)
                
                if match:
                    value = match.group(1)
                    direction = match.group(2)
                    indices[index] = {
                        "value": value,
                        "direction": direction
                    }
            
            return {"indices": indices}
        except Exception as e:
            logger.error(f"Error extracting manufacturing table: {str(e)}")
            return {"indices": {}}
    
    def _extract_services_table(self, text: str, pdf_path: Optional[str] = None) -> Dict[str, Any]:
        """Extract Services at a Glance table."""
        try:
            # Try to locate the table section
            table_pattern = r"SERVICES AT A GLANCE.*?(?:Month|COMMODITIES REPORTED)"
            match = re.search(table_pattern, text, re.DOTALL | re.IGNORECASE)
            if not match:
                # Fallback pattern
                table_pattern = r"SERVICES AT A GLANCE.*?OVERALL ECONOMY"
                match = re.search(table_pattern, text, re.DOTALL | re.IGNORECASE)
            
            table_text = match.group(0) if match else ""
            
            # Extract indices and their values
            indices = {}
            
            # List of indices to extract
            index_names = [
                "Services PMI", "Business Activity", "New Orders", "Employment",
                "Supplier Deliveries", "Inventories", "Inventory Sentiment",
                "Prices", "Backlog of Orders", "New Export Orders", "Imports"
            ]
            
            for index in index_names:
                # Pattern to find index values like "Services PMI® at 52.8%"
                pattern = rf"{re.escape(index)}®?\s*(?:at|was|registered|is)\s*(\d+\.\d+)%?.*?(Growing|Contracting|Too High|Too Low|Slowing|Faster)"
                match = re.search(pattern, table_text, re.IGNORECASE)
                
                if match:
                    value = match.group(1)
                    direction = match.group(2)
                    indices[index] = {
                        "value": value,
                        "direction": direction
                    }
            
            return {"indices": indices}
        except Exception as e:
            logger.error(f"Error extracting services table: {str(e)}")
            return {"indices": {}}
    
    @classmethod
    def get_strategy_metadata(cls) -> Dict[str, Any]:
        return {
            "name": cls.__name__,
            "applicable_report_types": ["Manufacturing", "Services"],
            "section_type": "table",
            "priority": 8
        }

class IndustryExtractionStrategy(ExtractionStrategy):
    """Strategy for extracting industry mentions from reports."""
    
    def extract(self, text: str, pdf_path: Optional[str] = None) -> Dict[str, Any]:
        """Extract industry mentions for each index."""
        try:
            # Extract index summaries first
            summaries = self._extract_index_summaries(text)
            
            # Extract industry mentions from summaries
            industry_data = {}
            
            # Process each index summary
            for index_name, summary in summaries.items():
                industry_categories = self._extract_industry_categories(index_name, summary)
                if industry_categories:
                    industry_data[index_name] = industry_categories
            
            return {"industry_data": industry_data, "index_summaries": summaries}
        except Exception as e:
            logger.error(f"Error extracting industry mentions: {str(e)}")
            return {"industry_data": {}, "index_summaries": {}}
    
    def _extract_index_summaries(self, text: str) -> Dict[str, str]:
        """Extract summaries for each index."""
        # List of indices to look for
        manufacturing_indices = [
            "MANUFACTURING PMI", "NEW ORDERS", "PRODUCTION", "EMPLOYMENT", 
            "SUPPLIER DELIVERIES", "INVENTORIES", "CUSTOMERS' INVENTORIES", 
            "PRICES", "BACKLOG OF ORDERS", "NEW EXPORT ORDERS", "IMPORTS"
        ]
        
        services_indices = [
            "SERVICES PMI", "BUSINESS ACTIVITY", "NEW ORDERS", "EMPLOYMENT", 
            "SUPPLIER DELIVERIES", "INVENTORIES", "INVENTORY SENTIMENT", 
            "PRICES", "BACKLOG OF ORDERS", "NEW EXPORT ORDERS", "IMPORTS"
        ]
        
        # Determine if this is a manufacturing or services report
        if "MANUFACTURING AT A GLANCE" in text.upper() or "MANUFACTURING PMI" in text.upper():
            indices = manufacturing_indices
            report_type = "Manufacturing"
        else:
            indices = services_indices
            report_type = "Services"
        
        # Extract summaries
        summaries = {}
        
        # Find the summaries section
        summaries_section = None
        if report_type == "Manufacturing":
            match = re.search(r"MANUFACTURING INDEX SUMMARIES", text, re.IGNORECASE)
            if match:
                summaries_section = text[match.start():]
        else:
            match = re.search(r"SERVICES INDEX SUMMARIES", text, re.IGNORECASE)
            if match:
                summaries_section = text[match.start():]
        
        # If no explicit summaries section, use the whole text
        if not summaries_section:
            summaries_section = text
        
        # Extract each index summary
        for i, index in enumerate(indices):
            if index == "MANUFACTURING PMI":
                clean_index = "Manufacturing PMI"
            elif index == "SERVICES PMI":
                clean_index = "Services PMI"
            elif index == "CUSTOMERS' INVENTORIES":
                clean_index = "Customers' Inventories"
            elif index == "INVENTORY SENTIMENT":
                clean_index = "Inventory Sentiment"
            elif index == "BUSINESS ACTIVITY":
                clean_index = "Business Activity"
            else:
                clean_index = index.title()
            
            try:
                # If this is the last index, search until the end or next major section
                if i == len(indices) - 1:
                    end_pattern = r"(?:AT A GLANCE|WHAT RESPONDENTS ARE SAYING|COMMODITIES REPORTED|BUYING POLICY)"
                    pattern = rf"{index}[\s\S]*?(.*?)(?:{end_pattern}|$)"
                else:
                    # Otherwise, search until the next index
                    next_index = indices[i+1]
                    pattern = rf"{index}[\s\S]*?(.*?)(?:\s|\n){next_index}"
                
                match = re.search(pattern, summaries_section, re.DOTALL | re.IGNORECASE)
                
                if match:
                    summary_text = match.group(1).strip()
                    summaries[clean_index] = summary_text
            except Exception as e:
                logger.warning(f"Error extracting summary for {index}: {str(e)}")
        
        return summaries
    
    def _extract_industry_categories(self, index_name: str, summary: str) -> Dict[str, List[str]]:
        """Extract industry categories for a specific index."""
        # Define category names based on index type
        if index_name == "Supplier Deliveries":
            categories = ["Slower", "Faster"]
        elif index_name == "Inventories":
            categories = ["Higher", "Lower"]
        elif index_name == "Customers' Inventories" or index_name == "Inventory Sentiment":
            categories = ["Too High", "Too Low"]
        elif index_name == "Prices":
            categories = ["Increasing", "Decreasing"]
        else:
            categories = ["Growing", "Declining"]
        
        result = {}
        
        # Extract industries for each category
        for category in categories:
            industries = self._extract_industries_for_category(index_name, category, summary)
            if industries:
                result[category] = industries
        
        return result
    
    def _extract_industries_for_category(self, index_name: str, category: str, summary: str) -> List[str]:
        """Extract industries for a specific category of an index."""
        patterns = []
        
        # Build appropriate patterns based on index and category
        if index_name == "Supplier Deliveries":
            if category == "Slower":
                patterns = [
                    r"industries reporting slower (?:supplier )?deliveries(?:[^:]*?)(?:are|—|in|:|-)(?:[^:]*?)(?:order|the following order|listed in order|:)[^:]*?([^\.]+)",
                    r"industries reporting slower (?:supplier )?deliveries(?:[^:]*?)(?:are|:|-)([^\.]+)"
                ]
            else:  # Faster
                patterns = [
                    r"industries reporting faster (?:supplier )?deliveries(?:[^:]*?)(?:are|—|in|:|-)(?:[^:]*?)(?:order|the following order|listed in order|:)[^:]*?([^\.]+)",
                    r"industries reporting faster (?:supplier )?deliveries(?:[^:]*?)(?:are|:|-)([^\.]+)"
                ]
        elif index_name == "Inventories":
            if category == "Higher":
                patterns = [
                    r"industries reporting (?:higher|increased|increasing|growing|growth in) inventories(?:[^:]*?)(?:listed in|—|in|:|-)(?:[^:]*?)(?:order|the following order|:)[^:]*?([^\.]+)",
                    r"industries reporting (?:higher|increased|increasing) inventories(?:[^:]*?)(?:are|:|-)([^\.]+)"
                ]
            else:  # Lower
                patterns = [
                    r"industries reporting (?:lower|decreased|declining|lower or decreased) inventories(?:[^:]*?)(?:in the following|—|in|:|-)(?:[^:]*?)(?:order|the following order|:)[^:]*?([^\.]+)",
                    r"industries reporting (?:lower|decreased|declining) inventories(?:[^:]*?)(?:are|:|-)([^\.]+)"
                ]
        elif index_name in ["Customers' Inventories", "Inventory Sentiment"]:
            if category == "Too High":
                patterns = [
                    r"industries reporting (?:customers['']s?|customers) (?:inventories|inventory) as too high(?:[^:]*?)(?:are|—|in|:|-)(?:[^:]*?)(?:order|the following order|:)?[^:]*?([^\.]+)",
                    r"(?:industries|industry) reporting (?:customers['']s?|customers) (?:inventories|inventory) as too high(?:[^:]*?)(?:are|:|-)([^\.]+)"
                ]
            else:  # Too Low
                patterns = [
                    r"industries reporting (?:customers['']s?|customers) (?:inventories|inventory) as too low(?:[^:]*?)(?:are|—|in|:|-)(?:[^:]*?)(?:order|the following order|:)?[^:]*?([^\.]+)",
                    r"(?:industries|industry) reporting (?:customers['']s?|customers) (?:inventories|inventory) as too low(?:[^:]*?)(?:are|:|-)([^\.]+)"
                ]
        elif index_name == "Prices":
            if category == "Increasing":
                patterns = [
                    r"(?:In (?:[\w\s]+), |The |)(?:[\w\s]+) industries (?:that |)(?:reported|reporting) (?:paying |higher |increased |increasing |price increases)(?:prices|price|prices for raw materials)?(?:[^:]*?)(?:in order|order|:|—|-)(?:[^:]*?)(?:are|:)([^\.]+)",
                    r"industries (?:that |)(?:reported|reporting) (?:paying |higher |increased |increasing) prices(?:[^:]*?)(?:are|:|-)([^\.]+)"
                ]
            else:  # Decreasing
                patterns = [
                    r"(?:The only industry|The [\w\s]+ industries) (?:that |)(?:reported|reporting) (?:paying |lower |decreased |decreasing |price decreases)(?:prices|price|prices for raw materials)?(?:[^:]*?)(?:in order|order|:|—|-)(?:[^:]*?)(?:are|is):?([^\.]+)",
                    r"industries (?:that |)(?:reported|reporting) (?:paying |lower |decreased |decreasing) prices(?:[^:]*?)(?:are|:|-)([^\.]+)"
                ]
        else:  # Default for most indices including New Orders, Production, etc.
            if category == "Growing":
                patterns = [
                    r"(?:[\w\s]+) (?:industries|manufacturing industries) (?:that |)(?:reporting|reported|report) (?:growth|expansion|increase|growing|increased|an increase|higher|growth in)(?: in| of)? (?:[\w\s&]+)?(?:[^:]*?)(?:are|—|:|in|-|,)(?:.+?)?(?:order|the following order|listed in order|:)[^:]*?([^\.]+)",
                    r"(?:[\w\s]+) industries (?:that |)(?:reporting|reported|report) growth(?:[^:]*?)(?:are|:|-)([^\.]+)"
                ]
            else:  # Declining
                patterns = [
                    r"(?:[\w\s]+) (?:industries|manufacturing industries) (?:that |)(?:reporting|reported|report) (?:a |an |)(?:decline|contraction|decrease|declining|decreased|lower)(?: in| of)? (?:[\w\s&]+)?(?:[^:]*?)(?:are|—|:|in|-|,)(?:.+?)?(?:order|the following order|listed in order|:)[^:]*?([^\.]+)",
                    r"(?:[\w\s]+) industries (?:that |)(?:reporting|reported|report) (?:a |)(?:decline|decrease|contraction)(?:[^:]*?)(?:are|:|-)([^\.]+)"
                ]
        
        # Try each pattern
        for pattern in patterns:
            match = re.search(pattern, summary, re.IGNORECASE | re.DOTALL)
            if match:
                industries_text = match.group(1).strip()
                return self._parse_industry_list(industries_text)
        
        return []
    
    def _parse_industry_list(self, text: str) -> List[str]:
        """Parse a list of industries from text."""
        if not text:
            return []
        
        # Clean up the text
        cleaned_text = text.strip()
        
        # Remove common artifacts
        artifacts = [
            r"in (?:January|February|March|April|May|June|July|August|September|October|November|December)(?:\s+\d{4})?(?:\s*[-—]\s*)?",
            r"in (?:the )?following order(?:\s*[-—]\s*)?",
            r"in order(?:\s*[-—]\s*)?",
            r"are(?:\s*:)?",
            r"is(?:\s*:)?",
            r"(?:listed|in) order(?:\s*[-—]\s*)?",
            r":",
            r"^[,;.\s]*",  # Remove leading punctuation
            r"(?:and|&)\s+"  # Remove "and" or "&" at beginning
        ]
        
        for artifact in artifacts:
            cleaned_text = re.sub(artifact, '', cleaned_text, flags=re.IGNORECASE)
        
        # Split by delimiters
        if ';' in cleaned_text:
            items = [part.strip() for part in cleaned_text.split(';')]
        else:
            items = [part.strip() for part in cleaned_text.split(',')]
        
        # Clean each item
        result = []
        for item in items:
            if not item:
                continue
                
            # Clean up each industry name
            item = re.sub(r'\s*\(\d+\)\s*$', '', item)  # Remove footnote numbers
            item = re.sub(r'\s*\*+\s*$', '', item)      # Remove trailing asterisks
            item = re.sub(r'^\s*-\s*', '', item)        # Remove leading dashes
            item = item.strip()
            
            if len(item) > 1:
                result.append(item)
        
        return result
    
    @classmethod
    def get_strategy_metadata(cls) -> Dict[str, Any]:
        return {
            "name": cls.__name__,
            "applicable_report_types": ["Manufacturing", "Services"],
            "section_type": "industry",
            "priority": 7
        }

class StrategyRegistry:
    """Registry for extraction strategies."""
    
    _strategies: Dict[str, Type[ExtractionStrategy]] = {}
    
    @classmethod
    def register(cls, strategy_class: Type[ExtractionStrategy]) -> None:
        """
        Register a strategy class.
        
        Args:
            strategy_class: The strategy class to register
        """
        metadata = strategy_class.get_strategy_metadata()
        cls._strategies[metadata["name"]] = strategy_class
        logger.info(f"Registered strategy: {metadata['name']}")
    
    @classmethod
    def get_strategies_for_report_type(cls, 
                                       report_type: str, 
                                       section_type: Optional[str] = None) -> List[Type[ExtractionStrategy]]:
        """
        Get all strategies applicable to a specific report type and section.
        
        Args:
            report_type: The report type to get strategies for
            section_type: Optional section type to filter by
            
        Returns:
            List of strategy classes, sorted by priority
        """
        result = []
        for strategy_name, strategy_class in cls._strategies.items():
            metadata = strategy_class.get_strategy_metadata()
            if report_type in metadata["applicable_report_types"]:
                if section_type is None or metadata["section_type"] == section_type:
                    result.append(strategy_class)
        
        # Sort by priority (highest first)
        result.sort(key=lambda x: x.get_strategy_metadata()["priority"], reverse=True)
        return result
    
    @classmethod
    def get_all_strategies(cls) -> List[Type[ExtractionStrategy]]:
        """Get all registered strategies."""
        return list(cls._strategies.values())

# Register built-in strategies
StrategyRegistry.register(DateExtractionStrategy)
StrategyRegistry.register(TableExtractionStrategy)
StrategyRegistry.register(IndustryExtractionStrategy)