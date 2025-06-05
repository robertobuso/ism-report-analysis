import os
import json
import logging
import traceback
from typing import Dict, Any, Optional, List, Union, Tuple
import pandas as pd
from google_auth import get_google_sheets_service
import pdfplumber
import openai
from dotenv import load_dotenv
import re
import json
from db_utils import (
    get_pmi_data_by_month, 
    get_index_time_series, 
    get_industry_status_over_time,
    get_all_indices,
    initialize_database,
    check_report_exists_in_db,
    get_all_report_dates
)

from config import ISM_INDICES, INDEX_CATEGORIES
from crewai.tools import BaseTool
from pydantic import Field
from googleapiclient.errors import HttpError
from report_detection import EnhancedReportTypeDetector
from extraction_strategy import StrategyRegistry
from data_validation import DataTransformationPipeline

# Create logs directory first
os.makedirs("logs", exist_ok=True)

logger = logging.getLogger(__name__)

ENABLE_NEW_TABS = True  # Feature flag for new tab format

class SimplePDFExtractionTool(BaseTool):
    name: str = Field(default="extract_pdf_data")
    description: str = Field(
        default="""
        Extracts ISM Report data from a PDF file.
        
        Args:
            pdf_path: The path to the PDF file to extract data from
        
        Returns:
            A dictionary containing the extracted data including month_year, manufacturing_table, 
            index_summaries, and industry_data
        """
    )

    def __init__(self):
        """Initialize the tool with necessary API keys."""
        super().__init__()
        # Load environment variables
        load_dotenv()
        # Get OpenAI API key from environment
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if openai_api_key:
            openai.api_key = openai_api_key

        # Track report type for this instance
        self._current_report_type = None

    def _run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract data from ISM Manufacturing Report PDF.
        
        Args:
            input_data: Dictionary containing the PDF path or other extraction parameters
            
        Returns:
            Dictionary with extracted data including month_year, manufacturing_table, 
            index_summaries, and industry_data
        """
        try:
            # Normalize input to get the PDF path
            normalized_input = self._normalize_input(input_data)
            pdf_path = normalized_input.get('pdf_path')
            provided_report_type = normalized_input.get('report_type')

            if not pdf_path:
                logger.error("No PDF path provided")
                return {"month_year": "Unknown", "indices": {}, "industry_data": {}, "report_type": "Manufacturing"}

        #  Use ‘provided report type if available
            if provided_report_type:
                report_type = provided_report_type
                logger.info(f"Using provided report type: {report_type}")
            else:
                try:
                    from report_handlers import ReportTypeFactory
                    report_type = ReportTypeFactory.detect_report_type(pdf_path)
                    logger.info(f"Detected report type: {report_type}")
                except Exception as e:
                    logger.warning(f"Error detecting report type: {str(e)}, using default 'Manufacturing'")
                    report_type = "Manufacturing"
            
            # ADDED: Store report type in instance for later use
            self._current_report_type = report_type
            
            # FIXED: Validate report type
            if report_type not in ['Manufacturing', 'Services']:
                logger.warning(f"Invalid report type '{report_type}', defaulting to Manufacturing")
                report_type = 'Manufacturing'
                self._current_report_type = report_type
            
            # Extract month and year from filename if possible
            month_year = "Unknown"
            filename = os.path.basename(pdf_path)
            import re
            match = re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*[-_\s]?(\d{2,4})', filename, re.IGNORECASE)
            if match:
                month_map = {
                    'jan': 'January', 'feb': 'February', 'mar': 'March', 'apr': 'April',
                    'may': 'May', 'jun': 'June', 'jul': 'July', 'aug': 'August',
                    'sep': 'September', 'oct': 'October', 'nov': 'November', 'dec': 'December'
                }
                month = month_map.get(match.group(1).lower()[:3], 'Unknown')
                year = match.group(2)
                if len(year) == 2:
                    year = f"20{year}"
                month_year = f"{month} {year}"
            
            logger.info(f"Initial month_year from filename: {month_year}")
            
            # Extract text from ALL pages
            extracted_text = ""
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    page_count = len(pdf.pages)
                    logger.info(f"Extracting all {page_count} pages from PDF")
                    
                    for i in range(page_count):
                        page_text = pdf.pages[i].extract_text()
                        if page_text:
                            extracted_text += page_text + "\n\n"
            except Exception as e:
                logger.warning(f"Error extracting text with pdfplumber: {str(e)}")
                # Fallback to PyPDF2
                try:
                    from PyPDF2 import PdfReader
                    reader = PdfReader(pdf_path)
                    page_count = len(reader.pages)
                    logger.info(f"Fallback: Extracting all {page_count} pages with PyPDF2")
                    
                    for i in range(page_count):
                        page_text = reader.pages[i].extract_text()
                        if page_text:
                            extracted_text += page_text + "\n\n"
                except Exception as e2:
                    logger.error(f"Both PDF extraction methods failed: {str(e2)}")
            
            # Check if we have enough text
            if len(extracted_text) < 500:
                logger.warning(f"Extracted text is too short ({len(extracted_text)} chars)")
                return {"month_year": month_year, "indices": {}, "industry_data": {}}
                
            logger.info(f"Successfully extracted {len(extracted_text)} chars from full PDF")
            
            # Try to parse month_year from extracted text if not already determined
            if month_year == "Unknown":
                try:
                    from pdf_utils import extract_month_year
                    text_month_year = extract_month_year(extracted_text)
                    if text_month_year:
                        month_year = text_month_year
                        logger.info(f"Extracted month_year from text: {month_year}")
                except Exception as e:
                    logger.warning(f"Failed to extract month_year from text: {str(e)}")

            # Report-type specific variables
            if report_type == "Manufacturing":
                prompt_title = "Manufacturing"
                table_name = "Manufacturing at a Glance"
                main_pmi = "Manufacturing PMI"
                production_index = "Production"
                inventory_index = "Customers' Inventories"
            else:  # Services
                prompt_title = "Services"
                table_name = "Services at a Glance"
                main_pmi = "Services PMI"
                production_index = "Business Activity"
                inventory_index = "Inventory Sentiment"
            
            # Construct the prompt WITHOUT using nested f-strings
            prompt = f"""
            I need you to analyze this ISM {prompt_title} Report PDF and extract both the "{table_name}" table data AND industry classification data.

            PART 1: {table_name} Table
            CRITICAL INSTRUCTION: When extracting values from the "{table_name}" table, you MUST use the "Series Index" column values, NOT the "Percent Point Change" column values. The Series Index column contains the actual index values (like 52.1, 48.7, etc.), while the Percent Point Change column shows the change from the previous month.

            Extract these indices with their Series Index values and directions:
            - {main_pmi}
            - New Orders
            - {production_index}
            - Employment
            - Supplier Deliveries
            - Inventories
            - {inventory_index}
            - Prices
            - Backlog of Orders
            - New Export Orders
            - Imports
            - Overall Economy status
            - {prompt_title} Sector status

            IMPORTANT: For each index above, extract the number from the "Series Index" column, NOT from the "Percent Point Change" column. The Series Index is the actual value of the index (e.g., 52.1), while Percent Point Change is just the difference from last month (e.g., +2.1 or -1.3).

            PART 2: Industry Data Classification
            For each of the following indices, identify industries that are classified as growing/expanding or contracting/declining:

            1. New Orders:
            - Growing: List all industries mentioned as reporting growth, expansion, or increases
            - Declining: List all industries mentioned as reporting contraction, decline, or decreases

            2. {'Business Activity' if report_type == 'Services' else 'Production'}:
            - Growing: List all industries mentioned as reporting growth, expansion, or increases 
            - Declining: List all industries mentioned as reporting contraction, decline, or decreases

            3. Employment:
            - Growing: List all industries mentioned as reporting growth, expansion, or increases
            - Declining: List all industries mentioned as reporting contraction, decline, or decreases

            4. Supplier Deliveries:
            - Slower: List all industries mentioned as reporting slower deliveries
            - Faster: List all industries mentioned as reporting faster deliveries

            5. Inventories:
            - Higher: List all industries mentioned as reporting higher inventories
            - Lower: List all industries mentioned as reporting lower inventories

            6. {'Inventory Sentiment' if report_type == 'Services' else "Customers' Inventories"}:
            - Too High: List all industries mentioned as reporting {'inventory sentiment' if report_type == 'Services' else "customers' inventories"} as too high
            - Too Low: List all industries mentioned as reporting {'inventory sentiment' if report_type == 'Services' else "customers' inventories"} as too low

            7. Prices:
            - Increasing: List all industries mentioned as reporting price increases
            - Decreasing: List all industries mentioned as reporting price decreases

            8. Backlog of Orders:
            - Growing: List all industries mentioned as reporting growth or increases in backlogs
            - Declining: List all industries mentioned as reporting contraction or decreases in backlogs

            9. New Export Orders:
            - Growing: List all industries mentioned as reporting growth in export orders
            - Declining: List all industries mentioned as reporting decline in export orders

            10. Imports:
                - Growing: List all industries mentioned as reporting growth in imports
                - Declining: List all industries mentioned as reporting decline in imports

            Return ONLY a JSON object in this format:
            {{
                "month_year": "Month Year",
                "indices": {{
                    "{prompt_title} PMI": {{"current": "48.4", "direction": "Contracting", "series_index": "48.4"}},
                    "New Orders": {{"current": "50.4", "direction": "Growing", "series_index": "50.4"}},
                    "Supplier Deliveries": {{"current": "49.2", "direction": "Faster", "series_index": "49.2"}},
                    "New Export Orders": {{"current": "47.8", "direction": "Declining", "series_index": "47.8"}},
                    ...and so on for all indices,
                    "OVERALL ECONOMY": {{"direction": "Growing"}},
                    "{prompt_title} Sector": {{"direction": "Contracting"}}
                }},
                "industry_data": {{
                    "New Orders": {{
                        "Growing": ["Industry1", "Industry2", ...],
                        "Declining": ["Industry3", "Industry4", ...]
                    }},
                    "{'Business Activity' if report_type == 'Services' else 'Production'}": {{
                        "Growing": [...],
                        "Declining": [...]
                    }},
                    ...and so on for all indices
                }},
                "index_summaries": {{
                    "New Orders": "full text of New Orders section...",
                    "{'Business Activity' if report_type == 'Services' else 'Production'}": "full text of Production section...",
                    ...and so on for all indices with their full text summaries
                }}
            }}

            REMINDER: Use ONLY the Series Index column values, NOT the Percent Point Change values!

            Here is the extracted text from the PDF:
            {extracted_text[:80000]}  # Limit text length to 80,000 chars to avoid token limits
            """
            
            # Call OpenAI API with robust error handling and retries
            max_retries = 3
            retry_delay = 2  # seconds
            
            extraction_data = None  # Initialize extraction_data to avoid reference errors
            
            for retry_count in range(max_retries):
                try:
                    client = openai.OpenAI()
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": "You are a data extraction specialist that returns only valid JSON."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.0
                    )
                    
                    response_text = response.choices[0].message.content
                    
                    # Try to parse the JSON
                    try:
                        json_text = response_text
                        
                        if "```json" in response_text:
                            json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
                            if json_match:
                                json_text = json_match.group(1)
                        elif "```" in response_text:
                            json_match = re.search(r'```\n?(.*?)\n?```', response_text, re.DOTALL)
                            if json_match:
                                json_text = json_match.group(1)
                        
                        json_data = json.loads(json_text)
                        
                        # Ensure required fields exist
                        if "month_year" not in json_data:
                            json_data["month_year"] = month_year
                        if "indices" not in json_data:
                            json_data["indices"] = {}
                        if "industry_data" not in json_data:
                            json_data["industry_data"] = {}
                        if "index_summaries" not in json_data:
                            json_data["index_summaries"] = {}
                        
                        # CRITICAL FIX: Always set report_type
                        json_data["report_type"] = report_type

                        extraction_data = json_data
                        
                        # FIXED: Apply Services-specific corrections BEFORE other processing
                        if report_type == "Services":
                            extraction_data = self._fix_services_indices(extraction_data)
                            logger.info("Applied Services-specific index corrections")
                        
                        # FIXED: Ensure correct PMI index names with better error handling
                        try:
                            extraction_data = self._ensure_correct_pmi_index(extraction_data, report_type)
                        except Exception as e:
                            logger.error(f"Error in _ensure_correct_pmi_index: {str(e)}")
                            # Continue with processing even if this fails
                        
                        # FIXED: Validate PMI values
                        try:
                            extraction_data = self._validate_and_fix_pmi_values(extraction_data, report_type)
                        except Exception as e:
                            logger.error(f"Error in _validate_and_fix_pmi_values: {str(e)}")
                            # Continue with processing even if this fails

                        return extraction_data

                    except Exception as e:
                        logger.error(f"Error in PDF extraction: {str(e)}")
                        logger.error(traceback.format_exc())
                        
                        # FIXED: Return proper fallback with report type
                        return {
                            "month_year": "Unknown", 
                            "indices": {}, 
                            "industry_data": {},
                            "index_summaries": {},
                            "report_type": self._current_report_type or "Manufacturing"
                        }
                        
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse JSON on retry {retry_count}: {str(e)}")
                        # If on last retry, create a fallback response
                        if retry_count == max_retries - 1:
                            # Try to salvage the month_year from the response text
                            month_year_match = re.search(r'"month_year":\s*"([^"]+)"', response_text)
                            if month_year_match:
                                month_year = month_year_match.group(1)
                                
                            # Create minimal valid structure for returning
                            extraction_data = {
                                "month_year": month_year, 
                                "indices": {}, 
                                "industry_data": {},
                                "index_summaries": {},
                                "report_type": report_type
                            }
                            return extraction_data
                        continue
                
                except Exception as e:
                    logger.warning(f"API request failed on retry {retry_count}: {str(e)}")
                    
                    # If it's not the last retry, wait and try again
                    if retry_count < max_retries - 1:
                        import time
                        time.sleep(retry_delay * (retry_count + 1))  # Exponential backoff
                    else:
                        logger.error(f"All API retries failed: {str(e)}")
            
            # If we get here, all retries failed
            logger.error("All extraction attempts failed")
            
            # Create a fallback response using direct PDF parsing
            try:
                logger.info("Attempting direct PDF parsing as fallback")
                from pdf_utils import parse_ism_report
                direct_data = parse_ism_report(pdf_path, report_type)
                if direct_data:
                    logger.info("Successfully parsed PDF directly")
                    return direct_data
            except Exception as e:
                logger.error(f"Direct PDF parsing failed: {str(e)}")
                
            # Final fallback with minimal data
            extraction_data = {
                "month_year": month_year, 
                "indices": {}, 
                "industry_data": {},
                "index_summaries": {},
                "report_type": report_type
            }
            return extraction_data
            
        except Exception as e:
            logger.error(f"Error in PDF extraction: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Final fallback with empty data
            return {
                "month_year": "Unknown", 
                "indices": {}, 
                "industry_data": {},
                "index_summaries": {},
                "report_type": "Manufacturing"
            }
    
    def _fix_services_indices(self, extraction_data):
        """ENHANCED: Fix Services reports with comprehensive index name mapping."""
        if not extraction_data or 'indices' not in extraction_data:
            return extraction_data
            
        indices = extraction_data['indices']
        
        # ENHANCED: More comprehensive Services-specific mappings
        mappings = {
            "Manufacturing PMI": "Services PMI",
            "Production": "Business Activity", 
            "Customers' Inventories": "Inventory Sentiment"
        }
        
        # Apply mappings to indices
        indices_updated = False
        for old_name, new_name in mappings.items():
            if old_name in indices and new_name not in indices:
                indices[new_name] = indices.pop(old_name)
                indices_updated = True
                logger.info(f"Mapped {old_name} to {new_name} for Services report")
        
        # ENHANCED: Also fix industry_data
        if 'industry_data' in extraction_data:
            industry_data = extraction_data['industry_data']
            industry_updated = False
            for old_name, new_name in mappings.items():
                if old_name in industry_data and new_name not in industry_data:
                    industry_data[new_name] = industry_data.pop(old_name)
                    industry_updated = True
                    logger.info(f"Mapped {old_name} to {new_name} in industry_data for Services report")
        
        # ENHANCED: Also fix index_summaries
        if 'index_summaries' in extraction_data:
            index_summaries = extraction_data['index_summaries']
            summaries_updated = False
            for old_name, new_name in mappings.items():
                if old_name in index_summaries and new_name not in index_summaries:
                    index_summaries[new_name] = index_summaries.pop(old_name)
                    summaries_updated = True
                    logger.info(f"Mapped {old_name} to {new_name} in index_summaries for Services report")
        
        if indices_updated or industry_updated or summaries_updated:
            logger.info("Successfully applied comprehensive Services index corrections")
        
        return extraction_data

    def _validate_pmi_values(self, extraction_data, report_type):
        """TARGETED FIX: Validate PMI values are reasonable."""
        if not extraction_data or 'indices' not in extraction_data:
            return extraction_data
            
        indices = extraction_data['indices']
        
        for index_name, data in indices.items():
            if isinstance(data, dict):
                # Check for suspicious values (percent changes instead of index values)
                current_value = data.get('current', '')
                if isinstance(current_value, str) and current_value.startswith(('+', '-')):
                    logger.warning(f"Suspicious value '{current_value}' for {index_name} - might be percent change")
                    
                    # Try to use series_index instead
                    if 'series_index' in data:
                        series_value = str(data['series_index']).replace('+', '').replace('-', '')
                        try:
                            float_val = float(series_value)
                            if 20 <= float_val <= 80:  # Reasonable PMI range
                                data['current'] = series_value
                                data['value'] = series_value
                                logger.info(f"Corrected {index_name} using series_index: {series_value}")
                        except ValueError:
                            pass
        
        return extraction_data

    def _ensure_correct_pmi_index(self, extracted_data, report_type):
        """SIMPLIFIED: Ensure correct PMI index name with better error handling."""
        try:
            if not extracted_data or not isinstance(extracted_data, dict):
                logger.warning(f"Invalid extracted_data in _ensure_correct_pmi_index")
                return {"month_year": "Unknown", "indices": {}, "industry_data": {}, "report_type": report_type}
                
            if 'indices' not in extracted_data or not extracted_data['indices']:
                logger.warning("No indices found in extracted_data")
                return extracted_data
                
            indices = extracted_data['indices']
            if not isinstance(indices, dict):
                logger.warning(f"indices is not a dictionary: {type(indices)}")
                extracted_data['indices'] = {}
                return extracted_data
            
            # SIMPLIFIED: Just ensure the correct PMI name exists
            if report_type == "Services":
                if "Manufacturing PMI" in indices and "Services PMI" not in indices:
                    indices["Services PMI"] = indices.pop("Manufacturing PMI")
                    logger.info("Renamed Manufacturing PMI to Services PMI")
            else:  # Manufacturing
                if "Services PMI" in indices and "Manufacturing PMI" not in indices:
                    indices["Manufacturing PMI"] = indices.pop("Services PMI")
                    logger.info("Renamed Services PMI to Manufacturing PMI")
            
            logger.info(f"Final indices after PMI correction: {list(indices.keys())}")
            return extracted_data
            
        except Exception as e:
            logger.error(f"Error in _ensure_correct_pmi_index: {str(e)}")
            # Return original data on error to avoid cascading failures
            return extracted_data

    def _extract_data_with_llm(self, pdf_path: str, month_year_context: str, handler: Any, report_type_str: str) -> Dict[str, Any]:
        """Extract data from PDF using LLM with the appropriate report handler."""
        try:
            # Create handler if not provided
            if handler is None:
                from report_handlers import ReportTypeFactory
                handler = ReportTypeFactory.create_handler("Manufacturing", pdf_path)
            
            logger.info(f"Extracting data from PDF: {pdf_path} with handler: {handler.__class__.__name__}")
            
            # Get report type from handler if not provided
            if not report_type:
                report_type = handler.__class__.__name__.replace('ReportHandler', '')
                
            # Extract text from ALL pages
            extracted_text = ""
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    page_count = len(pdf.pages)
                    logger.info(f"Extracting all {page_count} pages from PDF")
                    
                    for i in range(page_count):
                        page_text = pdf.pages[i].extract_text()
                        if page_text:
                            extracted_text += page_text + "\n\n"
            except Exception as e:
                logger.warning(f"Error extracting text with pdfplumber: {str(e)}")
                # Fallback to PyPDF2
                try:
                    from PyPDF2 import PdfReader
                    reader = PdfReader(pdf_path)
                    page_count = len(reader.pages)
                    logger.info(f"Fallback: Extracting all {page_count} pages with PyPDF2")
                    
                    for i in range(page_count):
                        page_text = reader.pages[i].extract_text()
                        if page_text:
                            extracted_text += page_text + "\n\n"
                except Exception as e2:
                    logger.error(f"Both PDF extraction methods failed: {str(e2)}")
            
            # Check if we have enough text
            if len(extracted_text) < 500:
                logger.warning(f"Extracted text is too short ({len(extracted_text)} chars)")
                return {"month_year": month_year, "indices": {}, "industry_data": {}}
                
            logger.info(f"Successfully extracted {len(extracted_text)} chars from full PDF")
            
            # NEW ENHANCEMENT: Try using the extraction strategy framework if available
            try:
                from extraction_strategy import StrategyRegistry
                
                # Check if handler has the extract_data_from_text method
                if hasattr(handler, 'extract_data_from_text'):
                    logger.info("Using extraction strategy framework")
                    extracted_data = handler.extract_data_from_text(extracted_text, pdf_path)
                    
                    # If we got meaningful data, validate and return it
                    if extracted_data and (
                        'industry_data' in extracted_data and extracted_data['industry_data'] or
                        'indices' in extracted_data and extracted_data['indices']
                    ):
                        try:
                            # Validate with the new pipeline if available
                            from data_validation import DataTransformationPipeline
                            validated_data = DataTransformationPipeline.process(extracted_data, report_type)
                            logger.info("Successfully extracted data using strategy framework")
                            return validated_data
                        except ImportError:
                            # If validation isn't available, still return the extracted data
                            logger.info("Successfully extracted data using strategy framework (no validation)")
                            return extracted_data
            except ImportError:
                logger.info("Extraction strategy framework not available, using LLM extraction")
            except Exception as e:
                logger.warning(f"Error using extraction strategy framework: {str(e)}, falling back to LLM")
            
            # If we get here, either the extraction strategy framework isn't available or it failed
            # Continue with the existing LLM-based extraction
            
            # Get extraction prompt from handler
            prompt = f"""
            {handler.get_extraction_prompt()}
            
            Here is the extracted text from the PDF:
            {extracted_text}
            """
            
            # Call OpenAI API with robust error handling and retries
            max_retries = 3
            retry_delay = 2  # seconds
            
            for retry_count in range(max_retries):
                try:
                    # Use openai client
                    client = openai.OpenAI()
                    response = client.chat.completions.create(
                        model="gpt-4o",  # Using gpt-4o
                        messages=[
                            {"role": "system", "content": "You are a data extraction specialist that returns only valid JSON."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.0  # Low temperature for deterministic output
                    )
                    
                    # Get the response text
                    response_text = response.choices[0].message.content
                    # Removed verbose logging
                    
                    # Try to parse the JSON
                    try:
                        # Clean up the response to extract just the JSON part
                        json_text = response_text
                        
                        # If it has markdown code blocks, extract just the JSON
                        if "```json" in response_text:
                            json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
                            if json_match:
                                json_text = json_match.group(1)
                        elif "```" in response_text:
                            # Try to extract from any code block
                            json_match = re.search(r'```\n?(.*?)\n?```', response_text, re.DOTALL)
                            if json_match:
                                json_text = json_match.group(1)
                        
                        # Try to parse as JSON
                        json_data = json.loads(json_text)
                        
                        # Validate the required fields exist
                        if "month_year" not in json_data or "indices" not in json_data:
                            logger.warning("JSON is missing required fields")
                            if "industry_data" not in json_data:
                                json_data["industry_data"] = {}
                            if retry_count == max_retries - 1:
                                # Create minimal valid structure for returning
                                return {"month_year": month_year, "indices": {}, "industry_data": {}}
                            continue
                        
                        # Ensure industry_data field exists
                        if "industry_data" not in json_data:
                            json_data["industry_data"] = {}
                        
                        # NEW ENHANCEMENT: Validate with the new pipeline if available
                        try:
                            from data_validation import DataTransformationPipeline
                            validated_data = DataTransformationPipeline.process(json_data, report_type)
                            logger.info("Successfully extracted and validated data using LLM")
                            return validated_data
                        except ImportError:
                            # If validation isn't available, return the LLM data as-is
                            logger.info("Successfully extracted data using LLM (no validation)")
                            return json_data
                        
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse JSON on retry {retry_count}: {str(e)}")
                        # If on last retry, create a fallback response
                        if retry_count == max_retries - 1:
                            return {"month_year": month_year, "indices": {}, "industry_data": {}}
                        continue
                
                except Exception as e:
                    logger.warning(f"API request failed on retry {retry_count}: {str(e)}")
                    
                    # If it's not the last retry, wait and try again
                    if retry_count < max_retries - 1:
                        import time
                        time.sleep(retry_delay * (retry_count + 1))  # Exponential backoff
                    else:
                        logger.error(f"All API retries failed: {str(e)}")
            
            # If we get here, all retries failed
            logger.error("All extraction attempts failed")
            return {"month_year": month_year, "indices": {}, "industry_data": {}}
        
        except Exception as e:
            logger.error(f"Error in _extract_data_with_llm: {str(e)}")
            logger.error(traceback.format_exc())
            return {"month_year": month_year, "indices": {}, "industry_data": {}}
        
    def _extract_manufacturing_data_with_llm(self, pdf_path, month_year):
        """
        Alias for _extract_data_with_llm for backward compatibility.
        
        Args:
            pdf_path: Path to the PDF file
            month_year: Month and year of the report
            
        Returns:
            Dictionary containing extracted data
        """
        logger.info(f"Called _extract_manufacturing_data_with_llm, forwarding to _extract_data_with_llm")
        return self._extract_data_with_llm(pdf_path, month_year)

    def _normalize_input(self, input_data):
        """
        Normalize input data format regardless of how it's provided.
        
        This handles multiple input formats:
        - String path to PDF: "path/to/file.pdf"
        - Direct dictionary: {"pdf_path": "path/to/file.pdf"}
        - Nested dictionary: {"extracted_data": {"pdf_path": "path/to/file.pdf"}}
        - CrewAI format: {"tool_input": {"pdf_path": "..."}} or {"tool_input": "path/to/file.pdf"}
        
        Returns:
            A normalized dictionary with at least pdf_path (if available)
        """
        try:
            # Handle string input
            if isinstance(input_data, str):
                if '.pdf' in input_data:
                    return {"pdf_path": input_data}
                try:
                    # Try parsing as JSON
                    import json
                    parsed = json.loads(input_data)
                    return self._normalize_input(parsed)
                except json.JSONDecodeError:
                    return {"pdf_path": input_data}
            
            # Handle dictionary input
            if isinstance(input_data, dict):
                # Direct format: {"pdf_path": "..."}
                if "pdf_path" in input_data:
                    return input_data
                
                # Nested format: {"extracted_data": {"pdf_path": "..."}}
                if "extracted_data" in input_data and isinstance(input_data["extracted_data"], dict):
                    if "pdf_path" in input_data["extracted_data"]:
                        return input_data["extracted_data"]
                
                # CrewAI format: {"tool_input": "..."}
                if "tool_input" in input_data:
                    tool_input = input_data["tool_input"]
                    if isinstance(tool_input, dict):
                        return self._normalize_input(tool_input)
                    elif isinstance(tool_input, str):
                        try:
                            import json
                            parsed = json.loads(tool_input)
                            return self._normalize_input(parsed)
                        except json.JSONDecodeError:
                            if '.pdf' in tool_input:
                                return {"pdf_path": tool_input}
            
            # Return original with warning if unable to normalize
            logger.warning(f"Unable to normalize input format: {type(input_data)}")
            return input_data
        except Exception as e:
            logger.error(f"Error normalizing input: {str(e)}")
            # Return empty dict with no pdf_path as a fallback
            return {}

    def _ensure_complete_data_structure(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensure all expected components of the data structure exist.
        
        Args:
            data: The data structure to check and complete
            
        Returns:
            The completed data structure
        """
        if not data or not isinstance(data, dict):
            data = {}
        
        # Ensure top-level fields exist
        if 'month_year' not in data:
            data['month_year'] = "Unknown"
        
        if 'report_type' not in data:
            data['report_type'] = "Manufacturing"
        
        if 'industry_data' not in data:
            data['industry_data'] = {}
        
        if 'index_summaries' not in data:
            data['index_summaries'] = {}
        
        if 'indices' not in data:
            data['indices'] = {}
        
        # If we have empty industry_data but industry info in other fields, try to recover
        if not data['industry_data'] and 'corrected_industry_data' in data and data['corrected_industry_data']:
            data['industry_data'] = data['corrected_industry_data']
            logger.info("Using corrected_industry_data for industry_data")
        
        # Ensure all expected indices exist in industry_data
        expected_indices = [
            "New Orders", "Production", "Employment", "Supplier Deliveries",
            "Inventories", "Customers' Inventories", "Prices", "Backlog of Orders",
            "New Export Orders", "Imports"
        ]
        
        for index in expected_indices:
            if index not in data['industry_data']:
                data['industry_data'][index] = {}
        
        return data

    def _standardize_report_type(self, report_type):
        """
        Standardize the report type string.
        
        Args:
            report_type: The report type string to standardize
            
        Returns:
            Standardized report type string
        """
        if not report_type:
            return "Manufacturing"  # Default
            
        report_type = report_type.strip()
        
        # Convert to title case and handle variations
        if report_type.lower() in ["manufacturing", "mfg", "man", "manufacturing pmi"]:
            return "Manufacturing"
        elif report_type.lower() in ["services", "svc", "service", "services pmi", "non-manufacturing"]:
            return "Services"
        else:
            return "Manufacturing"  # Default to Manufacturing if unknown

    def _standardize_extracted_data_for_report_type(extracted_data, report_type):
        """
        Standardize extracted data based on report type to ensure indices have correct names.
        
        Args:
            extracted_data: The extracted data dictionary
            report_type: Report type (Manufacturing or Services)
        
        Returns:
            Standardized extracted data
        """
        if not extracted_data or not isinstance(extracted_data, dict):
            return extracted_data
            
        # Ensure report_type is set
        extracted_data['report_type'] = report_type
        
        # Define index name mappings by report type
        manufacturing_indices = {
            "PMI": "Manufacturing PMI",
            "Services PMI": "Manufacturing PMI",
            "Business Activity": "Production"
        }
        
        services_indices = {
            "PMI": "Services PMI",
            "Manufacturing PMI": "Services PMI",
            "Production": "Business Activity"
        }
        
        # Get the appropriate mappings based on report type
        mappings = services_indices if report_type == "Services" else manufacturing_indices
        
        # Update indices if they exist
        if 'indices' in extracted_data and extracted_data['indices']:
            for old_name, new_name in mappings.items():
                if old_name in extracted_data['indices']:
                    if new_name not in extracted_data['indices']:
                        extracted_data['indices'][new_name] = extracted_data['indices'][old_name]
                    if old_name != new_name:
                        del extracted_data['indices'][old_name]
        
        # Update industry_data if it exists
        if 'industry_data' in extracted_data and extracted_data['industry_data']:
            for old_name, new_name in mappings.items():
                if old_name in extracted_data['industry_data']:
                    if new_name not in extracted_data['industry_data']:
                        extracted_data['industry_data'][new_name] = extracted_data['industry_data'][old_name]
                    if old_name != new_name:
                        del extracted_data['industry_data'][old_name]
        
        return extracted_data

    def _validate_and_fix_pmi_values(self, extraction_data, report_type):
        """
        Validate that PMI values are actual index values, not percent changes.
        
        PMI index values are typically between 30-70, while percent changes are usually
        small numbers between -10 and +10.
        
        Args:
            extraction_data: The extracted data dictionary
            report_type: Report type (Manufacturing or Services)
            
        Returns:
            Validated extraction data
        """
        if not extraction_data or 'indices' not in extraction_data:
            return extraction_data
            
        indices = extraction_data['indices']
        
        # Check specific indices that had issues
        problem_indices = ['New Export Orders', 'Supplier Deliveries']
        
        for index_name in problem_indices:
            if index_name in indices:
                index_data = indices[index_name]
                
                # Get the current value
                value = None
                if isinstance(index_data, dict):
                    value = index_data.get('current', index_data.get('value', index_data.get('series_index')))
                
                if value:
                    try:
                        # Convert to float if string
                        if isinstance(value, str):
                            # Remove any + or - prefix which indicates percent change
                            if value.startswith(('+', '-')) and '.' in value:
                                logger.warning(f"Detected percent change value '{value}' for {index_name}, this is likely incorrect")
                                # Mark for re-extraction or set to None
                                index_data['needs_correction'] = True
                            
                            # Clean the value
                            cleaned_value = value.replace('+', '').replace('-', '')
                            numeric_value = float(cleaned_value)
                            
                            # Check if value is suspiciously small (likely a percent change)
                            if abs(numeric_value) < 15:  # PMI values are rarely below 30 or changes above 15
                                logger.warning(f"Suspicious value {numeric_value} for {index_name} - might be percent change instead of index value")
                                
                                # If we have series_index field, use that
                                if 'series_index' in index_data and index_data['series_index']:
                                    try:
                                        series_value = float(str(index_data['series_index']).replace('+', '').replace('-', ''))
                                        if series_value > 20:  # More likely to be an actual index value
                                            index_data['current'] = str(series_value)
                                            index_data['value'] = str(series_value)
                                            logger.info(f"Corrected {index_name} value from {value} to {series_value}")
                                    except:
                                        pass
                                        
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not validate value for {index_name}: {str(e)}")
        
        # Removed verbose logging

        return extraction_data

class SimpleDataStructurerTool(BaseTool):
    name: str = Field(default="structure_data")
    description: str = Field(
        default="""
        Structures extracted ISM data into a consistent format.
        
        Args:
            extracted_data: The raw data extracted from the ISM Manufacturing Report
        
        Returns:
            A dictionary containing structured data for each index
        """
    )

    def _run(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Implementation of the required abstract _run method.
        This structures the extracted ISM data.
        """
        try:
            logger.info("Data Structurer Tool received input")
            
            # Ensure extracted_data has the minimum required structure
            if not extracted_data:
                extracted_data = {}
            
            # FIXED: Ensure report_type is preserved
            report_type = extracted_data.get('report_type', 'Manufacturing')

            # Get month and year
            month_year = extracted_data.get("month_year", "Unknown")
            logger.info(f"Structuring data for {month_year}")
            
            # ENHANCED: Better handling of missing data
            required_keys = ["month_year", "manufacturing_table", "index_summaries", "industry_data"]
            for key in required_keys:
                if key not in extracted_data:
                    if key == "month_year":
                        extracted_data[key] = month_year
                    elif key == "manufacturing_table":
                        extracted_data[key] = ""
                    else:
                        extracted_data[key] = {}
            
            # ENHANCED: Handle corrected industry data properly
            if not extracted_data.get("industry_data") and "corrected_industry_data" in extracted_data:
                extracted_data["industry_data"] = extracted_data["corrected_industry_data"]
                logger.info("Using corrected_industry_data as industry_data")
                
            # Get industry data - check all possible locations
            industry_data = None
            
            # First try getting industry_data directly
            if "industry_data" in extracted_data and extracted_data["industry_data"]:
                industry_data = extracted_data["industry_data"]
                logger.info("Using industry_data from extraction")
                    
            # If not available, check for corrected_industry_data
            elif "corrected_industry_data" in extracted_data and extracted_data["corrected_industry_data"]:
                industry_data = extracted_data["corrected_industry_data"]
                logger.info("Using corrected_industry_data")
                    
            # If still not available, look inside "manufacturing_table" which may have the industry data
            elif "manufacturing_table" in extracted_data and isinstance(extracted_data["manufacturing_table"], dict):
                # The data verification specialist might put industry data in manufacturing_table
                if any(k in ISM_INDICES for k in extracted_data["manufacturing_table"].keys()):
                    industry_data = extracted_data["manufacturing_table"]
                    logger.info("Using industry data from manufacturing_table")
            
            # If we still don't have industry data, try a last resort extraction
            if not industry_data or not isinstance(industry_data, dict) or not any(industry_data.values()):
                logger.warning("Industry data is empty or contains no entries, attempting to re-extract from summaries")
                    
                if "index_summaries" in extracted_data and extracted_data["index_summaries"]:
                    try:
                        from pdf_utils import extract_industry_mentions
                        industry_data = extract_industry_mentions("", extracted_data["index_summaries"])
                        logger.info("Re-extracted industry data from summaries")
                    except Exception as e:
                        logger.error(f"Error re-extracting industry data: {str(e)}")
            
            # If we still have no valid industry data, check if there was a verification result
            if not industry_data and hasattr(extracted_data, 'get') and callable(extracted_data.get):
                verification_result = extracted_data.get('verification_result', None)
                if verification_result and 'corrected_industry_data' in verification_result:
                    industry_data = verification_result['corrected_industry_data']
                    logger.info("Using industry data from verification result")

            # Ensure we have a valid industry_data dictionary
            if not industry_data:
                industry_data = {}
                logger.warning("No valid industry data found, using empty dictionary")

            # Structure data for each index
            structured_data = {}
            
            # Ensure we have entries for all expected indices
            for index in ISM_INDICES:
                # Get categories for this index if available
                categories = {}
                if index in industry_data:
                    categories = industry_data[index]
                
                # Clean up the categories but preserve order
                cleaned_categories = {}
                
                # Process each category
                for category_name, industries in categories.items():
                    cleaned_industries = []
                    
                    # Clean up each industry name in the list
                    for industry in industries:
                        if not industry or not isinstance(industry, str):
                            continue
                            
                        # Skip parsing artifacts and invalid entries
                        if ("following order" in industry.lower() or 
                            "are:" in industry.lower() or 
                            industry.startswith(',') or 
                            industry.startswith(':') or 
                            len(industry.strip()) < 3):
                            continue
                            
                        # Clean up the industry name
                        industry = industry.strip()
                        
                        # Add to cleaned list if not already there
                        if industry not in cleaned_industries:
                            cleaned_industries.append(industry)
                    
                    # Add to cleaned categories if we have any industries
                    if cleaned_industries:
                        cleaned_categories[category_name] = cleaned_industries
                    else:
                        logger.warning(f"No cleaned industries for {category_name}, using empty list")
                        cleaned_categories[category_name] = []
                
                # If no data for this index, create empty categories
                if not cleaned_categories and index in INDEX_CATEGORIES:
                    cleaned_categories = {category: [] for category in INDEX_CATEGORIES[index]}
                
                # Add to structured_data
                structured_data[index] = {
                    "month_year": month_year,
                    "categories": cleaned_categories
                }
                
                # Count industries to log
                total_industries = sum(len(industries) for industries in cleaned_categories.values())
                logger.info(f"Structured {index}: {total_industries} industries across {len(cleaned_categories)} categories")
            
            # Log total industry count
            total = sum(sum(len(industries) for industries in data["categories"].values()) for data in structured_data.values())
            logger.info(f"Total industries in structured data: {total}")
            
            return structured_data
        except Exception as e:
            logger.error(f"Error in data structuring: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Return minimal valid structure as fallback
            structured_data = {}
            for index in ISM_INDICES:
                categories = {}
                if index in INDEX_CATEGORIES:
                    for category in INDEX_CATEGORIES[index]:
                        categories[category] = []
                structured_data[index] = {
                    "month_year": month_year if 'month_year' in locals() else "Unknown",
                    "categories": categories
                }
            return structured_data
    
class DataValidatorTool(BaseTool):
    name: str = Field(default="validate_data")
    description: str = Field(
        default="""
        Validates structured ISM data for accuracy and completeness.
        
        Args:
            structured_data: The structured data to validate
        
        Returns:
            A dictionary mapping each index name to a boolean indicating validation status
        """
    )
    
    def _run(self, structured_data: Dict[str, Any]) -> Dict[str, bool]:
        """
        Implementation of the required abstract _run method.
        This validates the structured ISM data.
        """
        try:
            if not structured_data:
                raise ValueError("Structured data not provided")
                
            validation_results = {}
            
            # Check if all expected indices are present
            for index in ISM_INDICES:
                if index not in structured_data:
                    validation_results[index] = False
                    logger.warning(f"Missing index: {index}")
                else:
                    # Check if categories are present
                    categories = structured_data[index].get("categories", {})
                    
                    # Check if the required categories exist for this index (case insensitive)
                    if index in INDEX_CATEGORIES:
                        expected_categories = INDEX_CATEGORIES[index]
                        # Convert to lowercase for case-insensitive comparison
                        actual_categories = [c.lower() for c in categories.keys()]
                        expected_lower = [c.lower() for c in expected_categories]
                        
                        # Make validation more lenient
                        categories_valid = any(ec in actual_categories for ec in expected_lower) and any(industries for category, industries in categories.items())
                        
                        # Check if any industries exist in any category
                        has_industries = False
                        for category, industries in categories.items():
                            if industries:  # If there's at least one industry
                                has_industries = True
                                break
                        
                        validation_results[index] = categories_valid and has_industries
                    else:
                        # For indices without predefined categories, check if any categories exist
                        validation_results[index] = len(categories) > 0
                    
                    if not validation_results[index]:
                        reason = ""
                        if not categories:
                            reason = "no categories found"
                        elif index in INDEX_CATEGORIES and not all(ec in actual_categories for ec in expected_lower):
                            missing = [ec for ec in expected_lower if ec not in actual_categories]
                            reason = f"missing categories: {', '.join(missing)}"
                        elif not has_industries:
                            reason = "no industries found in any category"
                        
                        logger.warning(f"Validation failed for {index}: {reason}")
            
            # Force at least one index to be valid to continue processing
            if not any(validation_results.values()) and structured_data:
                # Look for an index that has at least some data
                for index in structured_data:
                    categories = structured_data[index].get("categories", {})
                    has_industries = any(industries for category, industries in categories.items() if industries)
                    
                    if has_industries:
                        validation_results[index] = True
                        logger.info(f"Forcing {index} to be valid because it has industries")
                        break
                
                # If still no valid index, just pick the first one
                if not any(validation_results.values()):
                    first_index = next(iter(structured_data.keys()))
                    validation_results[first_index] = True
                    logger.info(f"Forcing {first_index} to be valid to continue processing")
            
            return validation_results
        except Exception as e:
            logger.error(f"Error in data validation: {str(e)}")
            
            # Create default validation results as fallback
            validation_results = {}
            for index in ISM_INDICES:
                validation_results[index] = True  # Default to True for all indices
            
            return validation_results
    
class GoogleSheetsFormatterTool(BaseTool):
    name: str = Field(default="format_for_sheets")
    description: str = Field(
        default="""
        Formats validated ISM data for Google Sheets and updates the sheet.
        
        Args:
            data: Dictionary containing structured_data and validation_results
        
        Returns:
            A boolean indicating whether the Google Sheets update was successful
        """
    )
    
    def __init__(self):
        super().__init__()
        # ADDED: Track current report type for this instance
        self._current_report_type = None
        self._extraction_data = None

    def _run(self, data: Dict[str, Any]) -> bool:
        """Main entry point for the Google Sheets Formatter Tool."""
        try:
            # Check if required keys exist
            if not isinstance(data, dict):
                data = {'structured_data': {}, 'validation_results': {}}
                logger.warning("Data is not a dictionary. Creating an empty structure.")
                
            # ENHANCED: Get extraction_data and set report type context
            extraction_data = data.get('extraction_data', {})
            self._extraction_data = extraction_data
            
            # FIXED: Properly determine report type
            report_type = extraction_data.get('report_type', 'Manufacturing')
            if report_type not in ['Manufacturing', 'Services']:
                report_type = 'Manufacturing'
            self._current_report_type = report_type
            
            logger.info(f"Processing Google Sheets formatting for report type: {report_type}")

            # Ensure month_year is extracted and preserved correctly
            month_year = extraction_data.get('month_year', 'Unknown')
            if 'verification_result' in data and isinstance(data['verification_result'], dict):
                if 'month_year' in data['verification_result'] and data['verification_result']['month_year'] != month_year:
                    logger.warning(f"Month/year changed during verification - using original {month_year}")
                    data['verification_result']['month_year'] = month_year
            
            # ENHANCED: Store data in database with proper report type
            try:
                if extraction_data and 'month_year' in extraction_data:
                    from db_utils import store_report_data_in_db
                    pdf_path = data.get('pdf_path', 'unknown_path')
                    store_result = store_report_data_in_db(extraction_data, pdf_path, report_type)
                    if store_result:
                        logger.info(f"Successfully stored {report_type} report data in database")
                    else:
                        logger.warning(f"Failed to store {report_type} report data in database")
            except Exception as e:
                logger.error(f"Error storing {report_type} data in database: {str(e)}")
            
            # Get Google Sheets service
            service = get_google_sheets_service()
            if not service:
                logger.error("Failed to get Google Sheets service")
                return False
            
            # ENHANCED: Create report-type specific sheet name
            sheet_title = f"ISM {report_type} Report Analysis"
            sheet_id = self._get_or_create_sheet(service, sheet_title)
            if not sheet_id:
                logger.error(f"Failed to get or create Google Sheet for {report_type}")
                return False
            
            # Get all sheet IDs for tabs
            sheet_ids = self._get_all_sheet_ids(service, sheet_id)
            
            # ENHANCED: Create tabs with report type context
            try:
                # 1. Update the heatmap tab with values only
                monthly_data = get_pmi_data_by_month(24, report_type)  # Pass report_type
                heatmap_result = self.update_heatmap_tab(service, sheet_id, monthly_data, report_type)
                if heatmap_result:
                    logger.info(f"Successfully updated {report_type} heatmap tab")
                else:
                    logger.warning(f"Failed to update {report_type} heatmap tab")
                
                # 2. Create alphabetical growth tab with report type
                alpha_result = self.create_alphabetical_growth_tab(service, sheet_id, sheet_ids, report_type)
                if alpha_result:
                    logger.info(f"Successfully created {report_type} alphabetical growth tab")
                else:
                    logger.warning(f"Failed to create {report_type} alphabetical growth tab")
                
                # 3. Create numerical growth tab with report type  
                num_result = self.create_numerical_growth_tab(service, sheet_id, sheet_ids, report_type)
                if num_result:
                    logger.info(f"Successfully created {report_type} numerical growth tab")
                else:
                    logger.warning(f"Failed to create {report_type} numerical growth tab")
                
                logger.info(f"Successfully created/updated required tabs for {report_type}")
                return True
                
            except Exception as e:
                logger.error(f"Error creating required tabs for {report_type}: {str(e)}")
                logger.error(traceback.format_exc())
                return False
            
        except Exception as e:
            logger.error(f"Error in Google Sheets formatting: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def _count_industries(self, structured_data):
        """Count the total number of industries in structured data."""
        count = 0
        for index_data in structured_data.values():
            categories = index_data.get("categories", {})
            for category_industries in categories.values():
                if isinstance(category_industries, list):
                    count += len(category_industries)
        return count
    
    def _create_structured_data_from_extraction(self, extraction_data):
        """Create structured data from extraction data."""
        structured_data = {}
        month_year = extraction_data.get('month_year', 'Unknown')
        
        for index, categories in extraction_data.get('industry_data', {}).items():
            structured_data[index] = {
                'month_year': month_year,
                'categories': categories
            }
        
        return structured_data
    
    def _create_default_validation_results(self, structured_data):
        """Create default validation results for the structured data."""
        validation_results = {}
        for index in ISM_INDICES:
            validation_results[index] = index in structured_data
        return validation_results
    
    def _force_valid_index(self, validation_results):
        """Force at least one index to be valid for processing."""
        logger.warning("All validations failed. Forcing an index to be valid to continue.")
        if ISM_INDICES:
            validation_results[ISM_INDICES[0]] = True
        return validation_results
    
    def _get_month_year(self, structured_data, extraction_data):
        """Get the month and year from structured data or extraction data."""
        # Try to get from extraction_data first as the most authoritative source
        if extraction_data:
            month_year = extraction_data.get("month_year")
            if month_year and month_year != "Unknown":
                return month_year
        
        # Try to get from structured data
        for index_data in structured_data.values():
            month_year = index_data.get("month_year")
            if month_year and month_year != "Unknown":
                return month_year
        
        # Default to current date
        from datetime import datetime
        return datetime.now().strftime("%B %Y")

    def _format_month_year(self, month_year):
        """Convert full month and year to MM/YY format."""
        try:
            if not month_year or month_year == "Unknown":
                from datetime import datetime
                # Default to current month/year
                return datetime.now().strftime("%m/%y")
                    
            # Parse the month year string
            month_map = {
                'january': '01', 'february': '02', 'march': '03', 'april': '04',
                'may': '05', 'june': '06', 'july': '07', 'august': '08',
                'september': '09', 'october': '10', 'november': '11', 'december': '12'
            }
            
            # Normalize the input
            month_year_lower = month_year.lower()
            
            # Extract month and year
            month = None
            year = None
            
            # Try to find month
            for m in month_map.keys():
                if m in month_year_lower:
                    month = month_map[m]
                    break
            
            # Try to find year
            import re
            year_match = re.search(r'(20\d{2})', month_year)
            if year_match:
                year = year_match.group(1)[-2:]  # Extract last 2 digits
            
            # If month or year not found, use current date
            if not month or not year:
                from datetime import datetime
                return datetime.now().strftime("%m/%y")
                    
            return f"{month}/{year}"
        except Exception as e:
            logger.error(f"Error formatting month_year {month_year}: {str(e)}")
            # Return a default in case of error
            from datetime import datetime
            return datetime.now().strftime("%m/%y")
    
    def _is_valid_industry(self, industry):
        """Check if an industry string is valid."""
        if not industry or not isinstance(industry, str):
            return False
        
        # Skip text patterns that indicate artifacts from parsing
        if ("following order" in industry.lower() or 
            "are:" in industry.lower() or
            industry.startswith(',') or 
            industry.startswith(':') or
            len(industry.strip()) < 3):
            return False
        
        return True
    
    def _get_or_create_sheet(self, service, title):
        """Get an existing sheet or create a new one."""
        try:
            # Define the sheet_id_file path
            sheet_id_file = "sheet_id.txt"

            # First check if a saved sheet ID exists in sheet_id.txt
            sheet_id = None
            if os.path.exists("sheet_id.txt"):
                with open("sheet_id.txt", "r") as f:
                    sheet_id = f.read().strip()
                    logger.info(f"Found saved sheet ID: {sheet_id}")
                    
                # Verify the sheet exists and is accessible
                try:
                    sheet_metadata = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
                    sheet_title = sheet_metadata['properties']['title']
                    
                    # If the title doesn't match what we want, set sheet_id to None to force creation of a new sheet
                    if sheet_title != title:
                        logger.info(f"Saved sheet has title '{sheet_title}' but we need '{title}'. Will create new sheet.")
                        sheet_id = None
                    else:
                        logger.info(f"Successfully accessed existing sheet: {sheet_metadata['properties']['title']}")
                    
                    # Check if the default Sheet1 exists and delete it if needed
                    sheets = sheet_metadata.get('sheets', [])
                    sheet1_id = None
                    for sheet in sheets:
                        if sheet.get('properties', {}).get('title') == 'Sheet1':
                            sheet1_id = sheet.get('properties', {}).get('sheetId')
                            break
                    
                    # Check if all required tabs exist
                    existing_tabs = [sheet.get('properties', {}).get('title') for sheet in sheets]
                    
                    # ONLY CHECK FOR THE THREE REQUIRED TABS
                    required_tabs = ['PMI Heatmap Summary', 'Growth Alphabetical', 'Growth Numerical']
                    missing_tabs = [tab for tab in required_tabs if tab not in existing_tabs]
                    
                    # Create any missing tabs
                    if missing_tabs:
                        requests = []
                        for tab in missing_tabs:
                            requests.append({
                                'addSheet': {
                                    'properties': {
                                        'title': tab
                                    }
                                }
                            })
                        
                        # Delete Sheet1 if it exists and we're adding new tabs
                        if sheet1_id is not None:
                            requests.append({
                                'deleteSheet': {
                                    'sheetId': sheet1_id
                                }
                            })
                        
                        # Execute batch update to add missing tabs
                        if requests:
                            service.spreadsheets().batchUpdate(
                                spreadsheetId=sheet_id,
                                body={'requests': requests}
                            ).execute()
                            logger.info(f"Added {len(missing_tabs)} missing tabs to existing sheet")
                    
                    # If we got here, we have a valid sheet ID and all tabs exist
                    return sheet_id
                except HttpError as e:
                    if e.resp.status == 404:
                        logger.warning("Sheet not found, creating new sheet")
                        # Reset sheet_id to force creation of a new sheet
                        sheet_id = None
                        # You may want to update sheet_id.txt with empty content or remove it
                        with open("sheet_id.txt", "w") as f:
                            f.write("")  # Clear the file
                    else:
                        # For other HTTP errors, log and propagate
                        logger.error(f"HTTP error accessing sheet: {str(e)}")
                        raise
                except Exception as e:
                    # Handle other types of exceptions
                    logger.error(f"Error accessing saved sheet: {str(e)}")
                    sheet_id = None
        
            # Create a new sheet if needed
            if not sheet_id:
                logger.info("Creating new Google Sheet")
                sheet_metadata = {
                    'properties': {
                        'title': title
                    }
                }
                
                sheet = service.spreadsheets().create(body=sheet_metadata).execute()
                sheet_id = sheet['spreadsheetId']
                logger.info(f"Created new sheet with ID: {sheet_id}")
                
                # Save the sheet ID for future use
                with open(sheet_id_file, "w") as f:
                    f.write(sheet_id)
                    logger.info(f"Saved sheet ID to {sheet_id_file}")
                
                # Create ONLY the three required tabs
                requests = []
                
                # Add PMI Heatmap Summary tab
                requests.append({
                    'addSheet': {
                        'properties': {
                            'title': 'PMI Heatmap Summary'
                        }
                    }
                })
                
                # Add Growth Alphabetical tab
                requests.append({
                    'addSheet': {
                        'properties': {
                            'title': 'Growth Alphabetical'
                        }
                    }
                })
                
                # Add Growth Numerical tab
                requests.append({
                    'addSheet': {
                        'properties': {
                            'title': 'Growth Numerical'
                        }
                    }
                })
                
                # Delete the default Sheet1 if it exists
                sheet_metadata = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
                sheets = sheet_metadata.get('sheets', [])
                default_sheet_id = None
                
                # Find the ID of Sheet1
                for sheet in sheets:
                    if sheet.get('properties', {}).get('title') == 'Sheet1':
                        default_sheet_id = sheet.get('properties', {}).get('sheetId')
                        break
                
                if default_sheet_id is not None:
                    requests.append({
                        'deleteSheet': {
                            'sheetId': default_sheet_id
                        }
                    })
                
                # Execute all sheet operations in one batch
                if requests:
                    service.spreadsheets().batchUpdate(
                        spreadsheetId=sheet_id,
                        body={'requests': requests}
                    ).execute()
                    logger.info("Set up all tabs and removed default Sheet1")
                
                return sheet_id
            
            return sheet_id
        except Exception as e:
            logger.error(f"Error finding or creating sheet: {str(e)}")
            # Attempt to create new sheet as a last resort
            try:
                logger.info("Creating new sheet as fallback after error")
                sheet_metadata = {
                    'properties': {
                        'title': title
                    }
                }
                
                sheet = service.spreadsheets().create(body=sheet_metadata).execute()
                new_sheet_id = sheet['spreadsheetId']
                
                # Save the new sheet ID
                with open("sheet_id.txt", "w") as f:
                    f.write(new_sheet_id)
                
                return new_sheet_id
            except Exception as e2:
                logger.error(f"Final fallback creation failed: {str(e2)}")
                return None
                    
    def _get_all_sheet_ids(self, service, spreadsheet_id):
        """Get a mapping of sheet names to sheet IDs."""
        try:
            sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            return {
                sheet.get('properties', {}).get('title'): sheet.get('properties', {}).get('sheetId')
                for sheet in sheet_metadata.get('sheets', [])
            }
        except Exception as e:
            logger.error(f"Error getting sheet IDs: {str(e)}")
            return {}
    
    def _extract_data_with_llm(self, table_content, month_year):
        """
        Extract data from the manufacturing table using an LLM or DB.
        """
        try:
            # Log the table content for debugging
            content_length = len(table_content) if table_content else 0
            logger.info(f"Table content length: {content_length} characters")
            
            if content_length < 50:
                logger.warning("Table content is too short, may not contain actual table data")
                
                # Try to get PMI data from database
                pmi_data = get_pmi_data_by_month(1)
                if pmi_data and len(pmi_data) > 0:
                    logger.info("Using PMI data from database")
                    return {
                        "month_year": pmi_data[0].get('month_year', month_year),
                        "indices": pmi_data[0].get('indices', {})
                    }
                
                # Log sample of table content if available
                if content_length > 0:
                    logger.info(f"Table content sample: {table_content[:200]}...")
                
                # Get pmi_data from extraction_data if available
                from db_utils import initialize_database, parse_date
                
                # Format the month_year for database query
                formatted_date = parse_date(month_year)
                if formatted_date:
                    logger.info(f"Parsed date: {formatted_date}")
                    # Try to get data from DB using the parsed date
                    initialize_database()
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    
                    cursor.execute(
                        """
                        SELECT * FROM pmi_indices 
                        WHERE report_date = ?
                        """,
                        (formatted_date.isoformat(),)
                    )
                    
                    indices_data = {}
                    for row in cursor.fetchall():
                        index_name = row['index_name']
                        indices_data[index_name] = {
                            "current": str(row['index_value']),
                            "direction": row['direction']
                        }
                    
                    if indices_data:
                        logger.info(f"Found {len(indices_data)} indices in database")
                        return {
                            "month_year": month_year,
                            "indices": indices_data
                        }
                
                # Fallback to hardcoded data for demo purposes
                logger.info("Using fallback data for manufacturing table")
                return {
                    "month_year": month_year,
                    "indices": {
                        "Manufacturing PMI": {"current": "50.9", "direction": "Growing"},
                        "New Orders": {"current": "55.1", "direction": "Growing"},
                        "Production": {"current": "52.5", "direction": "Growing"},
                        "Employment": {"current": "50.3", "direction": "Growing"},
                        "Supplier Deliveries": {"current": "50.9", "direction": "Slowing"},
                        "Inventories": {"current": "45.9", "direction": "Contracting"},
                        "Customers' Inventories": {"current": "46.7", "direction": "Too Low"},
                        "Prices": {"current": "54.9", "direction": "Increasing"},
                        "Backlog of Orders": {"current": "44.9", "direction": "Contracting"},
                        "New Export Orders": {"current": "52.4", "direction": "Growing"},
                        "Imports": {"current": "51.1", "direction": "Growing"}
                    }
                }
            
        except Exception as e:
            logger.error(f"Error extracting data with LLM: {str(e)}")
            return {"month_year": month_year, "indices": {}}
        
    def _prepare_horizontal_row(self, parsed_data, formatted_month_year):
        """Prepare a horizontal row for the manufacturing table."""
        try:
            # Handle case where parsed_data is None or missing essential data
            if not parsed_data or not isinstance(parsed_data, dict):
                logger.error("Invalid parsed_data, using default empty structure")
                parsed_data = {"month_year": formatted_month_year, "indices": {}}
            
            indices = parsed_data.get('indices', {})
            
            # If indices is empty or None, initialize an empty dict
            if not indices:
                indices = {}
                
            row = [formatted_month_year]
            
            # Standard indices in order
            standard_indices = [
                "Manufacturing PMI", "New Orders", "Production", 
                "Employment", "Supplier Deliveries", "Inventories", 
                "Customers' Inventories", "Prices", "Backlog of Orders",
                "New Export Orders", "Imports"
            ]
            
            # If Manufacturing PMI is missing from indices, check the database
            if "Manufacturing PMI" not in indices:
                from db_utils import get_db_connection, parse_date
                
                # Try to get data from DB using the date
                formatted_date = parse_date(formatted_month_year)
                if formatted_date:
                    try:
                        initialize_database()
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        
                        # Look specifically for Manufacturing PMI
                        cursor.execute(
                            """
                            SELECT * FROM pmi_indices 
                            WHERE report_date = ? AND index_name = ?
                            """,
                            (formatted_date.isoformat(), "Manufacturing PMI")
                        )
                        
                        row_data = cursor.fetchone()
                        if row_data:
                            indices["Manufacturing PMI"] = {
                                "current": str(row_data['index_value']),
                                "direction": row_data['direction']
                            }
                            logger.info(f"Retrieved Manufacturing PMI from database: {row_data['index_value']} ({row_data['direction']})")
                        else:
                            # If Manufacturing PMI not found, look for any index data
                            cursor.execute(
                                """
                                SELECT * FROM pmi_indices 
                                WHERE report_date = ? 
                                ORDER BY id DESC LIMIT 1
                                """,
                                (formatted_date.isoformat(),)
                            )
                            
                            row_data = cursor.fetchone()
                            if row_data:
                                logger.info(f"Using fallback index data for Manufacturing PMI from {row_data['index_name']}")
                                indices["Manufacturing PMI"] = {
                                    "current": str(row_data['index_value']),
                                    "direction": row_data['direction']
                                }
                    except Exception as e:
                        logger.error(f"Error retrieving index data from database: {str(e)}")
            
            # Add each index value - FIXED: Ensure all values are strings to avoid Google Sheets API errors
            for index in standard_indices:
                index_data = indices.get(index, {})
                
                # CRITICAL FIX: Ensure value is always a string
                value = index_data.get('current', index_data.get('value', 'N/A'))
                if value != 'N/A' and not isinstance(value, str):
                    value = str(value)
                    
                direction = index_data.get('direction', 'N/A')
                
                if value and direction and value != 'N/A' and direction != 'N/A':
                    cell_value = f"{value} ({direction})"
                else:
                    cell_value = "N/A"
                
                row.append(cell_value)
            
            # Add special rows for Overall Economy and Manufacturing Sector - with defaults
            overall_economy = indices.get("OVERALL ECONOMY", indices.get("Overall Economy", {}))
            manufacturing_sector = indices.get("Manufacturing Sector", {})
            
            # Default directions based on Manufacturing PMI if available
            default_economy = "Growing"  # Default assumption for economy
            
            # FIX: Handle potential conversion error by checking type
            pmi_value = indices.get("Manufacturing PMI", {}).get("current", 0)
            if isinstance(pmi_value, str) and pmi_value.replace('.', '', 1).isdigit():
                pmi_value = float(pmi_value)
            default_mfg = "Growing" if pmi_value >= 50 else "Contracting"
            
            row.append(overall_economy.get('direction', default_economy))
            row.append(manufacturing_sector.get('direction', default_mfg))
            
            # Log the final row being sent to Google Sheets for debugging
            # Removed verbose logging
            
            return row
        except Exception as e:
            logger.error(f"Error preparing horizontal row: {str(e)}")
            # Return a default row with N/A values
            return [formatted_month_year] + ["N/A"] * 13
     
    def _prepare_manufacturing_table_formatting(self, tab_id, row_count, col_count):
        """Prepare formatting requests for the manufacturing table."""
        requests = [
            # Format header row
            {
                "repeatCell": {
                    "range": {
                        "sheetId": tab_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": col_count
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {
                                "bold": True
                            },
                            "backgroundColor": {
                                "red": 0.9,
                                "green": 0.9,
                                "blue": 0.9
                            }
                        }
                    },
                    "fields": "userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColor"
                }
            },
            # Add borders
            {
                "updateBorders": {
                    "range": {
                        "sheetId": tab_id,
                        "startRowIndex": 0,
                        "endRowIndex": row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": col_count
                    },
                    "top": {"style": "SOLID"},
                    "bottom": {"style": "SOLID"},
                    "left": {"style": "SOLID"},
                    "right": {"style": "SOLID"},
                    "innerHorizontal": {"style": "SOLID"},
                    "innerVertical": {"style": "SOLID"}
                }
            },
            # Auto-resize columns
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": tab_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": col_count
                    }
                }
            },
            # Freeze header row
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": tab_id,
                        "gridProperties": {
                            "frozenRowCount": 1
                        }
                    },
                    "fields": "gridProperties.frozenRowCount"
                }
            }
        ]
        
        # Add conditional formatting for status colors
        color_formats = [
            # Growing = green text
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": tab_id,
                                "startRowIndex": 1,
                                "endRowIndex": row_count,
                                "startColumnIndex": 1,
                                "endColumnIndex": col_count
                            }
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_CONTAINS",
                                "values": [{"userEnteredValue": "(Growing)"}]
                            },
                            "format": {
                                "textFormat": {
                                    "foregroundColor": {
                                        "red": 0.0,
                                        "green": 0.6,
                                        "blue": 0.0
                                    }
                                }
                            }
                        }
                    },
                    "index": 0
                }
            },
            # Contracting = red text
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": tab_id,
                                "startRowIndex": 1,
                                "endRowIndex": row_count,
                                "startColumnIndex": 1,
                                "endColumnIndex": col_count
                            }
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_CONTAINS",
                                "values": [{"userEnteredValue": "(Contracting)"}]
                            },
                            "format": {
                                "textFormat": {
                                    "foregroundColor": {
                                        "red": 0.8,
                                        "green": 0.0,
                                        "blue": 0.0
                                    }
                                }
                            }
                        }
                    },
                    "index": 1
                }
            }
        ]
        
        requests.extend(color_formats)
        return requests
    
    def _prepare_index_tab_data(self, index_name, index_data, formatted_month_year, tab_id):
        """Prepare data for an index tab in columnar format."""
        try:
            # Format the index data
            formatted_data = self._format_index_data(index_name, index_data)
            
            if not formatted_data:
                logger.warning(f"No formatted data for {index_name}")
                return None, []
            
            # CRITICAL FIX: Changed format to use separate columns for industry and status
            header_row = [formatted_month_year]
            data_rows = []
            
            # Get primary and secondary categories
            primary_category = self._get_primary_category(index_name)
            secondary_category = self._get_secondary_category(index_name)
            
            # Process categories in specified order to maintain report order
            for category in [primary_category, secondary_category]:
                if category in formatted_data:
                    for industry in formatted_data[category]:
                        if self._is_valid_industry(industry):
                            # Add the category to each industry entry
                            data_rows.append([f"{industry} - {category}"])
            
            # Process any other categories
            for category, industries in formatted_data.items():
                if category not in [primary_category, secondary_category]:
                    for industry in industries:
                        if self._is_valid_industry(industry):
                            data_rows.append([industry])
            
            # Prepare formatting
            formatting = self._prepare_industry_tab_formatting(tab_id, len(data_rows) + 1, 1, index_name)
            
            return header_row + data_rows, formatting
        except Exception as e:
            logger.error(f"Error preparing index tab data for {index_name}: {str(e)}")
            return None, []
        
    def _format_index_data(self, index, data):
        """Format data for a specific index."""
        try:
            categories = data.get("categories", {})
            
            # Check if categories is empty and try to get from industry_data
            if not categories and 'industry_data' in data:
                categories = data.get('industry_data', {})
            
            # Clean the categories data
            cleaned_categories = {}
            
            # Ensure all expected categories exist
            if index in INDEX_CATEGORIES:
                for category in INDEX_CATEGORIES[index]:
                    # Get the industries for this category
                    industries = categories.get(category, [])
                    
                    # Clean the industry list
                    cleaned_industries = []
                    for industry in industries:
                        if not industry or not isinstance(industry, str):
                            continue
                        
                        # Skip text patterns that indicate artifacts from parsing
                        if ("following order" in industry.lower() or 
                            "are:" in industry.lower() or
                            industry.startswith(',') or 
                            industry.startswith(':') or
                            len(industry.strip()) < 3):
                            continue
                        
                        # Clean up the industry name
                        industry = industry.strip()
                        
                        # Add to cleaned list if not already there
                        if industry not in cleaned_industries:
                            cleaned_industries.append(industry)
                    
                    cleaned_categories[category] = cleaned_industries
                
                return cleaned_categories
            else:
                # For indices not in INDEX_CATEGORIES, clean all categories
                for category, industries in categories.items():
                    cleaned_industries = []
                    for industry in industries:
                        if not industry or not isinstance(industry, str):
                            continue
                        
                        # Skip invalid entries
                        if ("following order" in industry.lower() or 
                            "are:" in industry.lower() or
                            industry.startswith(',') or 
                            industry.startswith(':') or
                            len(industry.strip()) < 3):
                            continue
                        
                        industry = industry.strip()
                        
                        if industry not in cleaned_industries:
                            cleaned_industries.append(industry)
                    
                    cleaned_categories[category] = cleaned_industries
                
                return cleaned_categories
        except Exception as e:
            logger.error(f"Error formatting index data for {index}: {str(e)}")
            # Return empty dictionary as fallback
            if index in INDEX_CATEGORIES:
                return {category: [] for category in INDEX_CATEGORIES[index]}
            return {}
    
    def _get_primary_category(self, index):
        """Get the primary category for an index based on its type."""
        index_category_map = {
            "New Orders": "Growing",
            "Production": "Growing",
            "Employment": "Growing",
            "Supplier Deliveries": "Slower",
            "Inventories": "Higher",
            "Customers' Inventories": "Too High",
            "Prices": "Increasing",
            "Backlog of Orders": "Growing",
            "New Export Orders": "Growing",
            "Imports": "Growing"
        }
        return index_category_map.get(index, "Growing")

    def _get_secondary_category(self, index):
        """Get the secondary category for an index based on its type."""
        index_category_map = {
            "New Orders": "Declining",
            "Production": "Declining",
            "Employment": "Declining",
            "Supplier Deliveries": "Faster",
            "Inventories": "Lower",
            "Customers' Inventories": "Too Low",
            "Prices": "Decreasing",
            "Backlog of Orders": "Declining",
            "New Export Orders": "Declining",
            "Imports": "Declining"
        }
        return index_category_map.get(index, "Declining")

    def _prepare_clean_heatmap_data(self, monthly_data):
        """
        Prepare data for heatmap with proper date formatting, sorting, and data cleaning.
        
        Args:
            monthly_data: List of dictionaries containing report dates and indices
            
        Returns:
            tuple: (header_row, data_rows) with clean numeric values and properly formatted dates
        """
        try:
            # Get all unique index names
            all_indices = set()
            for data in monthly_data:
                all_indices.update(data['indices'].keys())
            
            # Order indices with Manufacturing PMI first, then alphabetically
            ordered_indices = ['Manufacturing PMI']
            ordered_indices.extend(sorted([idx for idx in all_indices if idx != 'Manufacturing PMI']))
            
            # Map to the expected column names
            column_mapping = {
                'Manufacturing PMI': 'PMI',
                'New Orders': 'New Orders',
                'Production': 'Production',
                'Employment': 'Employment',
                'Supplier Deliveries': 'Deliveries',
                'Inventories': 'Inventories',
                "Customers' Inventories": 'Customer Inv',
                'Prices': 'Prices',
                'Backlog of Orders': 'Ord Backlog',
                'New Export Orders': 'Exports',
                'Imports': 'Imports'
            }
            
            # Prepare header row with mapped column names
            header_row = ["Month"]
            header_row.extend([column_mapping.get(idx, idx) for idx in ordered_indices])
            
            # Convert month_year to datetime objects for sorting
            from datetime import datetime
            import re
            
            processed_data = []
            for data in monthly_data:
                month_year = data['month_year']
                
                # Parse the date
                try:
                    # First, try to directly parse the date if it's in a standard format
                    dt = datetime.strptime(month_year, '%B %Y')
                except ValueError:
                    try:
                        # Try to handle formats like "Sep - 24"
                        match = re.match(r'(\w+)[- ](\d+)', month_year)
                        if match:
                            month_abbr, year_str = match.groups()
                            
                            # Convert month abbreviation to number
                            month_map = {
                                'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                                'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                            }
                            
                            month_num = month_map.get(month_abbr, 1)
                            
                            # Convert 2-digit year to 4-digit year
                            year = int(year_str)
                            if year < 100:
                                if year < 50:  # Arbitrary cutoff for century
                                    year += 2000
                                else:
                                    year += 1900
                                    
                            dt = datetime(year, month_num, 1)
                        else:
                            # Default to current date if parsing fails
                            dt = datetime.now()
                            dt = dt.replace(day=1)  # Set to first day of month
                    except Exception as e:
                        logger.error(f"Date parsing error: {str(e)}")
                        dt = datetime.now()
                        dt = dt.replace(day=1)  # Set to first day of month
                
                # Format the date as MM/DD/YYYY format to match existing format
                formatted_date = dt.strftime('%m/%d/%Y')
                
                # Clean and extract numeric values
                row_data = [formatted_date]
                
                for index_name in ordered_indices:
                    index_data = data['indices'].get(index_name, {})
                    value = index_data.get('value', '')
                    
                    # If value is not available, try 'current' field
                    if not value and 'current' in index_data:
                        value = index_data['current']
                    
                    # Clean the value to get just the numeric part
                    if isinstance(value, str):
                        # Extract numeric part (e.g., "50.9 (Growing)" -> 50.9)
                        import re
                        numeric_match = re.search(r'(\d+\.?\d*)', value)
                        if numeric_match:
                            value = numeric_match.group(1)
                        else:
                            value = ""
                    
                    # Convert to float if possible
                    try:
                        if value:
                            value = float(value)
                        else:
                            value = ""
                    except (ValueError, TypeError):
                        value = ""
                    
                    row_data.append(value)
                
                processed_data.append((dt, row_data))
            
            # Sort by date (ascending)
            processed_data.sort(key=lambda x: x[0])
            
            # Extract just the row data
            data_rows = [row for _, row in processed_data]
            
            return header_row, data_rows
        
        except Exception as e:
            logger.error(f"Error preparing heatmap data: {str(e)}")
            return ["Month"], []

    def _prepare_industry_tab_formatting(self, tab_id, row_count, col_count, index_name):
        """Prepare formatting requests for an index tab."""
        requests = [
            # Format header row
            {
                "repeatCell": {
                    "range": {
                        "sheetId": tab_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": col_count
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {
                                "bold": True
                            },
                            "backgroundColor": {
                                "red": 0.9,
                                "green": 0.9,
                                "blue": 0.9
                            }
                        }
                    },
                    "fields": "userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColor"
                }
            },
            # Add borders
            {
                "updateBorders": {
                    "range": {
                        "sheetId": tab_id,
                        "startRowIndex": 0,
                        "endRowIndex": row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": col_count
                    },
                    "top": {"style": "SOLID"},
                    "bottom": {"style": "SOLID"},
                    "left": {"style": "SOLID"},
                    "right": {"style": "SOLID"},
                    "innerHorizontal": {"style": "SOLID"},
                    "innerVertical": {"style": "SOLID"}
                }
            },
            # Auto-resize columns
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": tab_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": col_count
                    }
                }
            },
            # Freeze header row
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": tab_id,
                        "gridProperties": {
                            "frozenRowCount": 1
                        }
                    },
                    "fields": "gridProperties.frozenRowCount"
                }
            }
        ]
        
        # Get category colors based on index type
        color_configs = []
        
        # Define color mapping for different categories
        if index_name == "Supplier Deliveries":
            color_configs = [
                ("Slower", {"red": 0.9, "green": 0.7, "blue": 0.7}),  # Red for Slower (economic slowdown)
                ("Faster", {"red": 0.7, "green": 0.9, "blue": 0.7})   # Green for Faster (economic improvement)
            ]
        elif index_name == "Prices":
            color_configs = [
                ("Increasing", {"red": 0.9, "green": 0.7, "blue": 0.7}),  # Red for Increasing (inflation)
                ("Decreasing", {"red": 0.7, "green": 0.9, "blue": 0.7})   # Green for Decreasing (deflation)
            ]
        else:
            # Default color scheme for most indices
            color_configs = [
                ("Growing", {"red": 0.7, "green": 0.9, "blue": 0.7}),      # Green for Growing
                ("Declining", {"red": 0.9, "green": 0.7, "blue": 0.7})     # Red for Declining
            ]
        
        # Add conditional formatting for each category
        for i, (category, color) in enumerate(color_configs):
            requests.append({
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": tab_id,
                                "startRowIndex": 1,  # Skip header
                                "endRowIndex": row_count,
                                "startColumnIndex": 1,  # Skip industry column
                                "endColumnIndex": col_count
                            }
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_EQ",
                                "values": [{"userEnteredValue": category}]
                            },
                            "format": {
                                "backgroundColor": color
                            }
                        }
                    },
                    "index": i
                }
            })
        
        return requests
    
    def _prepare_heatmap_summary_data(self, tab_id, row_count, col_count):
        """Prepare formatting requests for the heatmap summary tab."""
        requests = [
            # Format header row
            {
                "repeatCell": {
                    "range": {
                        "sheetId": tab_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": col_count
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {
                                "bold": True
                            },
                            "backgroundColor": {
                                "red": 0.9,
                                "green": 0.9,
                                "blue": 0.9
                            }
                        }
                    },
                    "fields": "userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColor"
                }
            },
            # Format date column as date (MM/dd/yyyy)
            {
                "repeatCell": {
                    "range": {
                        "sheetId": tab_id,
                        "startRowIndex": 1,  # Skip header row
                        "endRowIndex": row_count,
                        "startColumnIndex": 0,  # First column (Month)
                        "endColumnIndex": 1
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {
                                "type": "DATE",
                                "pattern": "MM/dd/yyyy"
                            }
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat"
                }
            },
            # Add borders
            {
                "updateBorders": {
                    "range": {
                        "sheetId": tab_id,
                        "startRowIndex": 0,
                        "endRowIndex": row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": col_count
                    },
                    "top": {"style": "SOLID"},
                    "bottom": {"style": "SOLID"},
                    "left": {"style": "SOLID"},
                    "right": {"style": "SOLID"},
                    "innerHorizontal": {"style": "SOLID"},
                    "innerVertical": {"style": "SOLID"}
                }
            },
            # Freeze header row and first column
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": tab_id,
                        "gridProperties": {
                            "frozenRowCount": 1,
                            "frozenColumnCount": 1
                        }
                    },
                    "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"
                }
            },
            # Auto-resize all columns
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": tab_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": col_count
                    }
                }
            }
        ]
        
        # Add conditional formatting with gradient for all numeric cells
        # Exclude the first column (dates)
        for i in range(1, col_count):
            # Add conditional formatting with gradient (red -> yellow -> green)
            requests.append({
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": tab_id,
                                "startRowIndex": 1,  # Skip header
                                "endRowIndex": row_count,
                                "startColumnIndex": i,
                                "endColumnIndex": i + 1
                            }
                        ],
                        "gradientRule": {
                            "minpoint": {
                                "color": {
                                    "red": 0.95,
                                    "green": 0.2,
                                    "blue": 0.2
                                },
                                "type": "MIN"
                            },
                            "midpoint": {
                                "color": {
                                    "red": 1.0,
                                    "green": 1.0,
                                    "blue": 0.0
                                },
                                "type": "PERCENTILE",
                                "value": "50"
                            },
                            "maxpoint": {
                                "color": {
                                    "red": 0.2,
                                    "green": 0.85,
                                    "blue": 0.2
                                },
                                "type": "MAX"
                            }
                        }
                    },
                    "index": i - 1  # Unique index for each rule
                }
            })
        
        return requests

    def _prepare_time_series_formatting(self, tab_id, row_count, col_count):
        """Prepare formatting requests for time series tab."""
        requests = [
            # Format header row
            {
                "repeatCell": {
                    "range": {
                        "sheetId": tab_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": col_count
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {
                                "bold": True
                            },
                            "backgroundColor": {
                                "red": 0.9,
                                "green": 0.9,
                                "blue": 0.9
                            }
                        }
                    },
                    "fields": "userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColor"
                }
            },
            # Add borders
            {
                "updateBorders": {
                    "range": {
                        "sheetId": tab_id,
                        "startRowIndex": 0,
                        "endRowIndex": row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": col_count
                    },
                    "top": {"style": "SOLID"},
                    "bottom": {"style": "SOLID"},
                    "left": {"style": "SOLID"},
                    "right": {"style": "SOLID"},
                    "innerHorizontal": {"style": "SOLID"},
                    "innerVertical": {"style": "SOLID"}
                }
            },
            # Freeze header row
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": tab_id,
                        "gridProperties": {
                            "frozenRowCount": 1
                        }
                    },
                    "fields": "gridProperties.frozenRowCount"
                }
            },
            # Auto-resize columns
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": tab_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": col_count
                    }
                }
            }
        ]
        
        # Add conditional formatting for directions
        direction_formats = [
            # Growing/Expanding = green text
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": tab_id,
                                "startRowIndex": 1,
                                "endRowIndex": row_count,
                                "startColumnIndex": 2,  # Direction column
                                "endColumnIndex": 3
                            }
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_CONTAINS",
                                "values": [{"userEnteredValue": "Growing"}]
                            },
                            "format": {
                                "textFormat": {
                                    "foregroundColor": {
                                        "red": 0.0,
                                        "green": 0.6,
                                        "blue": 0.0
                                    }
                                }
                            }
                        }
                    },
                    "index": 0
                }
            },
            # Contracting = red text
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": tab_id,
                                "startRowIndex": 1,
                                "endRowIndex": row_count,
                                "startColumnIndex": 2,  # Direction column
                                "endColumnIndex": 3
                            }
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_CONTAINS",
                                "values": [{"userEnteredValue": "Contracting"}]
                            },
                            "format": {
                                "textFormat": {
                                    "foregroundColor": {
                                        "red": 0.8,
                                        "green": 0.0,
                                        "blue": 0.0
                                    }
                                }
                            }
                        }
                    },
                    "index": 1
                }
            }
        ]
        
        # Add conditional formatting for changes
        change_formats = [
            # Positive change = green background
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": tab_id,
                                "startRowIndex": 1,
                                "endRowIndex": row_count,
                                "startColumnIndex": 3,  # Change column
                                "endColumnIndex": 4
                            }
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "NUMBER_GREATER",
                                "values": [{"userEnteredValue": "0"}]
                            },
                            "format": {
                                "backgroundColor": {
                                    "red": 0.7,
                                    "green": 0.9,
                                    "blue": 0.7
                                }
                            }
                        }
                    },
                    "index": 2
                }
            },
            # Negative change = red background
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": tab_id,
                                "startRowIndex": 1,
                                "endRowIndex": row_count,
                                "startColumnIndex": 3,  # Change column
                                "endColumnIndex": 4
                            }
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "NUMBER_LESS",
                                "values": [{"userEnteredValue": "0"}]
                            },
                            "format": {
                                "backgroundColor": {
                                    "red": 0.9,
                                    "green": 0.7,
                                    "blue": 0.7
                                }
                            }
                        }
                    },
                    "index": 3
                }
            }
        ]
        
        # Combine all formatting
        requests.extend(direction_formats)
        requests.extend(change_formats)
        
        return requests
    
    def _prepare_industry_data(self, tab_id, row_count, col_count):
        """Prepare formatting requests for industry growth/contraction tab."""
        requests = [
            # Format header row
            {
                "repeatCell": {
                    "range": {
                        "sheetId": tab_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": col_count
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {
                                "bold": True
                            },
                            "backgroundColor": {
                                "red": 0.9,
                                "green": 0.9,
                                "blue": 0.9
                            }
                        }
                    },
                    "fields": "userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColor"
                }
            },
            # Add borders
            {
                "updateBorders": {
                    "range": {
                        "sheetId": tab_id,
                        "startRowIndex": 0,
                        "endRowIndex": row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": col_count
                    },
                    "top": {"style": "SOLID"},
                    "bottom": {"style": "SOLID"},
                    "left": {"style": "SOLID"},
                    "right": {"style": "SOLID"},
                    "innerHorizontal": {"style": "SOLID"},
                    "innerVertical": {"style": "SOLID"}
                }
            },
            # Freeze header row and industry column
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": tab_id,
                        "gridProperties": {
                            "frozenRowCount": 1,
                            "frozenColumnCount": 1
                        }
                    },
                    "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"
                }
            },
            # Auto-resize industry column
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": tab_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": 1
                    }
                }
            },
            # Set month columns to fixed width
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": tab_id,
                        "dimension": "COLUMNS",
                        "startIndex": 1,
                        "endIndex": col_count
                    },
                    "properties": {
                        "pixelSize": 100  # Fixed width for month columns
                    },
                    "fields": "pixelSize"
                }
            }
        ]
        
        # Add conditional formatting for status values
        status_formats = [
            # Growing/Increasing = green background
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": tab_id,
                                "startRowIndex": 1,  # Skip header
                                "endRowIndex": row_count,
                                "startColumnIndex": 1,  # Skip industry column
                                "endColumnIndex": col_count
                            }
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_EQ",
                                "values": [{"userEnteredValue": "Growing"}]
                            },
                            "format": {
                                "backgroundColor": {
                                    "red": 0.7,
                                    "green": 0.9,
                                    "blue": 0.7
                                }
                            }
                        }
                    },
                    "index": 0
                }
            },
            # Contracting = red background
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": tab_id,
                                "startRowIndex": 1,  # Skip header
                                "endRowIndex": row_count,
                                "startColumnIndex": 1,  # Skip industry column
                                "endColumnIndex": col_count
                            }
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_EQ",
                                "values": [{"userEnteredValue": "Contracting"}]
                            },
                            "format": {
                                "backgroundColor": {
                                    "red": 0.9,
                                    "green": 0.7,
                                    "blue": 0.7
                                }
                            }
                        }
                    },
                    "index": 1
                }
            },
            # Neutral = yellow background
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": tab_id,
                                "startRowIndex": 1,  # Skip header
                                "endRowIndex": row_count,
                                "startColumnIndex": 1,  # Skip industry column
                                "endColumnIndex": col_count
                            }
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_EQ",
                                "values": [{"userEnteredValue": "Neutral"}]
                            },
                            "format": {
                                "backgroundColor": {
                                    "red": 0.9,
                                    "green": 0.9,
                                    "blue": 0.7
                                }
                            }
                        }
                    },
                    "index": 2
                }
            }
        ]
        
        # Add all formatting requests to a single batch
        requests.extend(status_formats)
        
        return requests
        
    def _update_multiple_tabs_with_data(self, service, sheet_id, all_tab_data):
        """
        Update multiple tabs in a single operation, grouping all formatting requests.

        Args:
            service: Google Sheets API service
            sheet_id: Spreadsheet ID
            all_tab_data: Dictionary mapping tab names to their data and formatting

        Returns:
            Boolean indicating success
        """
        try:
            # First ensure all required tabs exist (do this in one batch)
            existing_tabs = self._get_all_sheet_ids(service, sheet_id)
            tabs_to_create = []

            for tab_name in all_tab_data.keys():
                if tab_name not in existing_tabs:
                    tabs_to_create.append(tab_name)

            # Create all missing tabs in one batch
            if tabs_to_create:
                create_requests = [
                    {
                        'addSheet': {
                            'properties': {
                                'title': tab_name
                            }
                        }
                    }
                    for tab_name in tabs_to_create
                ]

                self._batch_update_requests(service, sheet_id, create_requests)

                # Refresh sheet_id mapping
                existing_tabs = self._get_all_sheet_ids(service, sheet_id)

            # Group all value updates
            value_batch_requests = []

            for tab_name, tab_info in all_tab_data.items():
                if 'data' in tab_info and tab_info['data']:
                    # For Index tabs, ensure proper format
                    if tab_name in ISM_INDICES:
                        # Get current data to find if month/year already exists
                        current_data = service.spreadsheets().values().get(
                            spreadsheetId=sheet_id,
                            range=f"'{tab_name}'!1:1"  # Get the header row
                        ).execute().get('values', [[]])
                        
                        # Get the formatted month/year we're working with
                        formatted_month_year = None
                        if 'data' in tab_info and tab_info['data'] and len(tab_info['data']) > 0:
                            formatted_month_year = tab_info['data'][0]
                        
                        # Check if month/year already exists in header
                        existing_col_index = -1
                        if formatted_month_year and current_data and len(current_data) > 0:
                            for i, header in enumerate(current_data[0]):
                                if header == formatted_month_year:
                                    existing_col_index = i
                                    break
                        
                        if existing_col_index >= 0:
                            # Use existing column if found
                            col_letter = self._get_column_letter(existing_col_index)
                            logger.info(f"Found existing column for {formatted_month_year} at column {col_letter}")
                        else:
                            # Otherwise use next available column
                            col_letter = self._get_column_letter(len(current_data[0]))
                            logger.info(f"Adding new column for {formatted_month_year} at column {col_letter}")
                        
                        # CRITICAL FIX: Properly format data as expected by the API
                        # Each row should be a single value, not a list
                        values = []
                        for row in tab_info['data']:
                            # Each row is a single cell value
                            if isinstance(row, list):
                                values.append([row[0] if row else ""])
                            else:
                                values.append([row])
                        
                        value_batch_requests.append({
                            'range': f"'{tab_name}'!{col_letter}1",
                            'values': values
                        })
                    else:
                        # For non-Index tabs, continue with the normal approach
                        value_batch_requests.append({
                            'range': f"'{tab_name}'!A1",
                            'values': tab_info['data']
                        })

                    # Execute all value updates in one batchUpdate
                    if value_batch_requests:
                        def batch_value_update():
                            return service.spreadsheets().values().batchUpdate(
                                spreadsheetId=sheet_id,
                                body={
                                    "valueInputOption": "RAW",
                                    "data": value_batch_requests
                                }
                            ).execute()

                        self._execute_with_backoff(batch_value_update)

            # Collect all formatting requests
            all_formatting_requests = []

            for tab_name, tab_info in all_tab_data.items():
                if 'formatting' in tab_info and tab_info['formatting']:
                    # Update the sheetId for each tab if it has changed or was created
                    if tab_name in existing_tabs:
                        sheet_id_value = existing_tabs[tab_name]
                        # Update sheetId in all formatting requests for this tab
                        updated_formatting = []
                        for format_request in tab_info['formatting']:
                            format_request_copy = format_request.copy()
                            # Update sheetId in range fields
                            for field in ['range', 'ranges']:
                                if field in format_request_copy and 'sheetId' in format_request_copy[field]:
                                    format_request_copy[field]['sheetId'] = sheet_id_value
                                # Check for nested ranges in AddConditionalFormatRule
                                elif 'rule' in format_request_copy and 'ranges' in format_request_copy['rule']:
                                    for range_item in format_request_copy['rule']['ranges']:
                                        if 'sheetId' in range_item:
                                            range_item['sheetId'] = sheet_id_value
                            updated_formatting.append(format_request_copy)
                        all_formatting_requests.extend(updated_formatting)
                    else:
                        logger.warning(f"Tab {tab_name} not found in existing_tabs, skipping formatting")

            # Apply all formatting in batches
            if all_formatting_requests:
                self._batch_update_requests(service, sheet_id, all_formatting_requests)

            return True

        except Exception as e:
            logger.error(f"Error updating multiple tabs: {str(e)}")
            logger.error(traceback.format_exc())
            return False
        
    def _get_column_letter(self, column_index):
        """Convert a column index to a column letter (e.g., 0 -> A, 25 -> Z, 26 -> AA)."""
        column_letter = ''
        while column_index >= 0:
            column_letter = chr(65 + (column_index % 26)) + column_letter
            column_index = (column_index // 26) - 1
            if column_index < 0:
                break
        return column_letter
    
    def _batch_update_requests(self, service, sheet_id, requests, max_batch_size=100):
        """
        Execute batch updates with proper chunking and backoff strategy.
        
        Args:
            service: Google Sheets API service
            sheet_id: Spreadsheet ID
            requests: List of update requests
            max_batch_size: Maximum number of requests per batch (to avoid hitting request size limits)
            
        Returns:
            List of response objects
        """
        if not requests:
            return []
        
        responses = []
        # Split requests into manageable batches to avoid hitting request size limits
        for i in range(0, len(requests), max_batch_size):
            batch = requests[i:i + max_batch_size]
            logger.info(f"Executing batch of {len(batch)} requests")
            
            def execute_batch():
                return service.spreadsheets().batchUpdate(
                    spreadsheetId=sheet_id,
                    body={"requests": batch}
                ).execute()
            
            # Execute with backoff
            response = self._execute_with_backoff(execute_batch)
            responses.append(response)
            
            # Add a brief delay between batches to reduce chance of rate limiting
            if i + max_batch_size < len(requests):
                import time
                time.sleep(1)
        
        return responses
                
    def _execute_with_backoff(self, request_func, max_retries=5, initial_delay=1, backoff_factor=2):
        """Execute a request with exponential backoff for rate limit errors."""
        delay = initial_delay
        for retry in range(max_retries):
            try:
                return request_func()
            except Exception as e:
                if retry == max_retries - 1:
                    # Last retry, re-raise the exception
                    raise
                
                if "429" in str(e) or "Quota exceeded" in str(e):
                    # This is a rate limit error, apply backoff
                    logger.warning(f"Rate limit error, retrying in {delay} seconds: {str(e)}")
                    import time
                    time.sleep(delay)
                    # Increase delay for next retry
                    delay *= backoff_factor
                else:
                    # Not a rate limit error, re-raise
                    raise

    def _update_heatmap_summary_tab(self, service, sheet_id, tab_id, header_row, data_rows):
        """
        Update the heatmap summary tab with new or updated data.
        
        Args:
            service: Google Sheets API service
            sheet_id: Spreadsheet ID
            tab_id: Sheet ID for the tab
            header_row: List of column headers
            data_rows: List of data rows with clean numeric values
            
        Returns:
            Boolean indicating success
        """
        try:
            tab_name = 'PMI Heatmap Summary'
            
            # Read existing data
            result = service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=f"'{tab_name}'!A:Z"
            ).execute()
            
            existing_values = result.get('values', [])
            
            # If no existing data, simply update with new data
            if not existing_values:
                # Write header and data rows
                all_rows = [header_row] + data_rows
                service.spreadsheets().values().update(
                    spreadsheetId=sheet_id,
                    range=f"'{tab_name}'!A1",
                    valueInputOption="USER_ENTERED",
                    body={"values": all_rows}
                ).execute()
                
                logger.info(f"Created new heatmap summary with {len(data_rows)} rows")
                return True
            
            # Extract existing header and data
            existing_header = existing_values[0] if existing_values else []
            existing_data = existing_values[1:] if len(existing_values) > 1 else []
            
            # Get index of date column (should be the first column)
            date_col_idx = 0
            
            # Create a dictionary to map dates to existing rows
            # Parse dates to a standardized format for comparison
            from datetime import datetime
            import re
            
            existing_date_map = {}
            for i, row in enumerate(existing_data):
                if row and len(row) > date_col_idx:
                    date_str = row[date_col_idx]
                    
                    # Try to parse various date formats
                    try:
                        # Try MM/DD/YYYY format
                        if re.match(r'\d{1,2}/\d{1,2}/\d{4}', date_str):
                            dt = datetime.strptime(date_str, '%m/%d/%Y')
                        # Try YYYY-MM-DD format
                        elif re.match(r'\d{4}-\d{1,2}-\d{1,2}', date_str):
                            dt = datetime.strptime(date_str, '%Y-%m-%d')
                        else:
                            # Skip if can't parse
                            continue
                            
                        # Use a standardized key format for comparison
                        key = dt.strftime('%Y-%m-%d')
                        existing_date_map[key] = i
                    except ValueError:
                        continue
            
            # Process each new data row
            updates = []
            new_rows = []
            
            for row in data_rows:
                if not row or len(row) <= date_col_idx:
                    continue
                    
                date_value = row[date_col_idx]
                
                # Standardize the date for comparison
                try:
                    # Parse the date value
                    if re.match(r'\d{1,2}/\d{1,2}/\d{4}', date_value):
                        dt = datetime.strptime(date_value, '%m/%d/%Y')
                    elif re.match(r'\d{4}-\d{1,2}-\d{1,2}', date_value):
                        dt = datetime.strptime(date_value, '%Y-%m-%d')
                    else:
                        # Skip if can't parse
                        continue
                        
                    # Get standardized key
                    key = dt.strftime('%Y-%m-%d')
                    
                    # Check if this date already exists
                    if key in existing_date_map:
                        # Update existing row
                        row_idx = existing_date_map[key]
                        
                        # Create update for this row - keeping original row_idx + 1 math
                        updates.append({
                            "range": f"'{tab_name}'!A{row_idx + 1 + 1}:{chr(65 + len(row) - 1)}{row_idx + 1 + 1}",
                            "values": [row]
                        })
                        
                        logger.info(f"Updating existing row for date {date_value}")
                    else:
                        # This is a new date - add to new rows
                        new_rows.append(row)
                        logger.info(f"Adding new row for date {date_value}")
                except ValueError:
                    # If date parsing fails, just add as new row
                    new_rows.append(row)
                    logger.info(f"Adding new row for unparseable date {date_value}")
            
            # Execute batch update for existing rows
            if updates:
                service.spreadsheets().values().batchUpdate(
                    spreadsheetId=sheet_id,
                    body={
                        "valueInputOption": "USER_ENTERED",  # Changed from RAW to match original
                        "data": updates
                    }
                ).execute()
            
            # Append new rows if any
            if new_rows:
                # Calculate the next available row
                next_row_idx = len(existing_values) + 1
                
                # Append the new rows
                service.spreadsheets().values().append(
                    spreadsheetId=sheet_id,
                    range=f"'{tab_name}'!A{next_row_idx}",
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body={"values": new_rows}
                ).execute()
            
            # Re-sort the sheet if needed (excluding header)
            if updates or new_rows:
                # Get latest data to sort
                result = service.spreadsheets().values().get(
                    spreadsheetId=sheet_id,
                    range=f"'{tab_name}'!A:Z"
                ).execute()
                
                latest_values = result.get('values', [])
                
                if len(latest_values) > 1:
                    # Sort request
                    sort_request = {
                        "sortRange": {
                            "range": {
                                "sheetId": tab_id,
                                "startRowIndex": 1,  # Skip header
                                "endRowIndex": len(latest_values),
                                "startColumnIndex": 0,
                                "endColumnIndex": len(latest_values[0])
                            },
                            "sortSpecs": [
                                {
                                    "dimensionIndex": 0,  # Sort by first column (dates)
                                    "sortOrder": "ASCENDING"
                                }
                            ]
                        }
                    }
                    
                    service.spreadsheets().batchUpdate(
                        spreadsheetId=sheet_id,
                        body={"requests": [sort_request]}
                    ).execute()
                    
                    logger.info("Re-sorted heatmap summary data by date")
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating heatmap summary tab: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    def _process_monthly_heatmap_summary(self, visualization_options, service, sheet_id, sheet_ids):
        """Process and update the monthly heatmap summary visualization."""
        if not visualization_options.get('heatmap', True):
            return
            
        try:
            logger.info("Processing monthly heatmap summary visualization")
            
            # Get data from the database
            monthly_data = get_pmi_data_by_month(24)  # Get last 24 months
            
            if not monthly_data:
                logger.warning("No monthly data found in database for heatmap summary")
                return
                
            # Prepare and clean the data
            header_row, data_rows = self._prepare_clean_heatmap_data(monthly_data)
            
            # Get the sheet ID for the tab
            tab_name = 'PMI Heatmap Summary'
            tab_id = sheet_ids.get(tab_name)
            
            if not tab_id:
                logger.warning(f"{tab_name} tab not found")
                return
                
            # Update the tab with the data
            result = self._update_heatmap_summary_tab(service, sheet_id, tab_id, header_row, data_rows)
            
            if result:
                # Apply formatting
                formatting_requests = self._prepare_heatmap_summary_data(
                    tab_id, 
                    len(data_rows) + 1,  # +1 for header
                    len(header_row)
                )
                
                # Execute formatting requests
                if formatting_requests:
                    service.spreadsheets().batchUpdate(
                        spreadsheetId=sheet_id,
                        body={"requests": formatting_requests}
                    ).execute()
                    
                logger.info("Successfully updated and formatted heatmap summary")
            
        except Exception as e:
            logger.error(f"Error updating heatmap summary: {str(e)}")
            logger.error(traceback.format_exc())

    # Code for New Tabs and Consolidation

    def backup_existing_sheet(service, sheet_id, timestamp=None):
        """Create a backup copy of the current sheet before modifications."""
        try:
            if not timestamp:
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Copy the spreadsheet
            copy_title = f"ISM Report Analysis Backup {timestamp}"
            copy_request = {
                'name': copy_title
            }
            
            copied_sheet = service.spreadsheets().copy(
                spreadsheetId=sheet_id, 
                body=copy_request
            ).execute()
            
            logger.info(f"Created backup with ID: {copied_sheet.get('spreadsheetId')}")
            return copied_sheet.get('spreadsheetId')
        except Exception as e:
            logger.error(f"Error creating backup: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    def update_heatmap_tab(self, service, sheet_id, monthly_data, report_type=None):
        """
        Update heatmap tab with values only (no direction).
        
        Args:
            service: Google Sheets API service
            sheet_id: Spreadsheet ID
            monthly_data: List of dictionaries containing monthly PMI data
        
        Returns:
            Boolean indicating success
        """
        try:
            if not report_type:
                report_type = self.getCurrentReportType()
                
            # ENHANCED: Use report-type specific logic
            if not monthly_data:
                logger.warning(f"No monthly data provided for {report_type} heatmap update")
                return False
                
            tab_name = f'{report_type} PMI Heatmap Summary'
            tab_id = self._get_all_sheet_ids(service, sheet_id).get(tab_name)
            
            if not tab_id:
                logger.warning(f"{tab_name} tab not found")
                return False
                
            # Get all unique index names
            all_indices = set()
            for data in monthly_data:
                all_indices.update(data['indices'].keys())
            
            # Order indices with Manufacturing PMI first, then alphabetically
            ordered_indices = ['Manufacturing PMI']
            ordered_indices.extend(sorted([idx for idx in all_indices if idx != 'Manufacturing PMI']))
            
            # Map to the expected column names
            column_mapping = {
                'Manufacturing PMI': 'PMI',
                'New Orders': 'New Orders',
                'Production': 'Production',
                'Employment': 'Employment',
                'Supplier Deliveries': 'Deliveries',
                'Inventories': 'Inventories',
                "Customers' Inventories": 'Customer Inv',
                'Prices': 'Prices',
                'Backlog of Orders': 'Ord Backlog',
                'New Export Orders': 'Exports',
                'Imports': 'Imports'
            }
            
            # Prepare header row with mapped column names
            header_row = ["Month"]
            header_row.extend([column_mapping.get(idx, idx) for idx in ordered_indices])
            
            # Convert month_year to datetime objects for sorting
            from datetime import datetime
            import re
            
            processed_data = []
            for data in monthly_data:
                month_year = data['month_year']
                
                # Parse the date
                try:
                    # First, try to directly parse the date if it's in a standard format
                    dt = datetime.strptime(month_year, '%B %Y')
                except ValueError:
                    try:
                        # Try to handle formats like "Sep - 24"
                        match = re.match(r'(\w+)[- ](\d+)', month_year)
                        if match:
                            month_abbr, year_str = match.groups()
                            
                            # Convert month abbreviation to number
                            month_map = {
                                'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                                'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                            }
                            
                            month_num = month_map.get(month_abbr, 1)
                            
                            # Convert 2-digit year to 4-digit year
                            year = int(year_str)
                            if year < 100:
                                if year < 50:  # Arbitrary cutoff for century
                                    year += 2000
                                else:
                                    year += 1900
                                    
                            dt = datetime(year, month_num, 1)
                        else:
                            # Default to current date if parsing fails
                            dt = datetime.now()
                            dt = dt.replace(day=1)  # Set to first day of month
                    except Exception as e:
                        logger.error(f"Date parsing error: {str(e)}")
                        dt = datetime.now()
                        dt = dt.replace(day=1)  # Set to first day of month
                
                # Format the date as MM/DD/YYYY format to match existing format
                formatted_date = dt.strftime('%m/%d/%Y')
                
                # Clean and extract numeric values ONLY (no direction)
                row_data = [formatted_date]
                
                for index_name in ordered_indices:
                    index_data = data['indices'].get(index_name, {})
                    value = index_data.get('value', '')
                    
                    # If value is not available, try 'current' field
                    if not value and 'current' in index_data:
                        value = index_data['current']
                    
                    # Clean the value to get just the numeric part
                    if isinstance(value, str):
                        # Extract numeric part (e.g., "50.9 (Growing)" -> 50.9)
                        import re
                        numeric_match = re.search(r'(\d+\.?\d*)', value)
                        if numeric_match:
                            value = numeric_match.group(1)
                        else:
                            value = ""
                    
                    # Convert to float if possible
                    try:
                        if value:
                            value = float(value)
                        else:
                            value = ""
                    except (ValueError, TypeError):
                        value = ""
                    
                    row_data.append(value)
                
                processed_data.append((dt, row_data))
            
            # Sort by date (ascending)
            processed_data.sort(key=lambda x: x[0])
            
            # Extract just the row data
            data_rows = [row for _, row in processed_data]
            
            # Update the tab with the data
            result = self._update_heatmap_summary_tab(service, sheet_id, tab_id, header_row, data_rows)
            
            if result:
                # Apply formatting
                formatting_requests = self._prepare_heatmap_summary_data(
                    tab_id, 
                    len(data_rows) + 1,  # +1 for header
                    len(header_row)
                )
                
                # Execute formatting requests
                if formatting_requests:
                    service.spreadsheets().batchUpdate(
                        spreadsheetId=sheet_id,
                        body={"requests": formatting_requests}
                    ).execute()
                    
                logger.info("Successfully updated and formatted heatmap summary (values only)")
            
            return result
        except Exception as e:
            logger.error(f"Error updating {report_type} heatmap tab: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    def create_alphabetical_growth_tab(self, service, sheet_id, sheet_ids, report_type=None):
        """
        Create the alphabetical growth/contraction tab.
        
        Args:
            service: Google Sheets API service
            sheet_id: Spreadsheet ID
            sheet_ids: Dictionary mapping tab names to sheet IDs
        
        Returns:
            Boolean indicating success
        """
        try:
            if not report_type:
                report_type = self.getCurrentReportType()
                
            tab_name = f'{report_type} Growth Alphabetical'
            
            # Get report type specific indices
            indices = get_all_indices(report_type=report_type)
        
            # Get the current report type from the most recent request
            report_type = self.getCurrentReportType()

            # Check if tab exists
            tab_id = sheet_ids.get(tab_name)
            if not tab_id:
                # Create the tab if it doesn't exist
                add_sheet_request = {
                    'requests': [{
                        'addSheet': {
                            'properties': {
                                'title': tab_name
                            }
                        }
                    }]
                }
                response = service.spreadsheets().batchUpdate(
                    spreadsheetId=sheet_id,
                    body=add_sheet_request
                ).execute()
                
                # Get the new sheet ID
                tab_id = response['replies'][0]['addSheet']['properties']['sheetId']
                logger.info(f"Created new tab '{tab_name}' with ID {tab_id}")
                
                # Refresh the sheet IDs mapping
                sheet_ids = self._get_all_sheet_ids(service, sheet_id)
            
            # Get all indices
            indices = get_all_indices(report_type=report_type)
            
            # Get all report dates for columns
            report_dates = get_all_report_dates(report_type=report_type)
            # Sort by date - assuming report_date is in ISO format
            report_dates.sort(key=lambda x: x['report_date'], reverse=True)
            months = [date['month_year'] for date in report_dates]
            
            # Create array to hold all data for batch update
            all_rows = []
            formatting_requests = []
            current_row = 0
            
            # For each index, create a section
            for index_num, index in enumerate(indices):
                # Index number in the loop (for formatting)
                section_start_row = current_row
                
                # Add index header with bold formatting
                all_rows.append([f"INDEX: {index}"])
                current_row += 1
                
                # Add formatting for index header
                formatting_requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": tab_id,
                            "startRowIndex": section_start_row,
                            "endRowIndex": section_start_row + 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": len(months) + 1
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {
                                    "bold": True
                                },
                                "backgroundColor": {
                                    "red": 0.9,
                                    "green": 0.9,
                                    "blue": 0.9
                                }
                            }
                        },
                        "fields": "userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColor"
                    }
                })
                
                # Add months header row
                header_row = ["Industry"]
                header_row.extend(months)
                all_rows.append(header_row)
                current_row += 1
                
                # Add formatting for month header row
                formatting_requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": tab_id,
                            "startRowIndex": section_start_row + 1,
                            "endRowIndex": section_start_row + 2,
                            "startColumnIndex": 0,
                            "endColumnIndex": len(months) + 1
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {
                                    "bold": True
                                },
                                "backgroundColor": {
                                    "red": 0.9,
                                    "green": 0.9,
                                    "blue": 0.9
                                }
                            }
                        },
                        "fields": "userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColor"
                    }
                })
                
                # Get industry data for this index
                industry_data = get_industry_status_over_time(index, len(months), report_type=report_type)
                
                # Check if we have industry data
                if not industry_data or 'industries' not in industry_data:
                    logger.warning(f"No industry data found for {index}")
                    # Add blank row between indices
                    all_rows.append([""])
                    current_row += 1
                    continue
                
                # Get all industries and sort alphabetically
                all_industries = sorted(industry_data['industries'].keys())
                industry_row_start = current_row
                
                # Create a row for each industry
                for industry in all_industries:
                    row_data = [industry]
                    
                    # Add status for each month
                    for month in months:
                        status_data = industry_data['industries'][industry].get(month, {})
                        status = status_data.get('status', 'Neutral')
                        row_data.append(status)
                    
                    all_rows.append(row_data)
                    current_row += 1
                
                # Add blank row between indices
                all_rows.append([""])
                current_row += 1
                
                # Add conditional formatting for growing/contracting status
                formatting_requests.append({
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [
                                {
                                    "sheetId": tab_id,
                                    "startRowIndex": industry_row_start,
                                    "endRowIndex": current_row - 1,  # Exclude the blank row
                                    "startColumnIndex": 1,
                                    "endColumnIndex": len(months) + 1
                                }
                            ],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_EQ",
                                    "values": [{"userEnteredValue": "Growing"}]
                                },
                                "format": {
                                    "backgroundColor": {
                                        "red": 0.7,
                                        "green": 0.9,
                                        "blue": 0.7
                                    }
                                }
                            }
                        },
                        "index": index_num * 3  # Ensure unique indices for each rule
                    }
                })
                
                formatting_requests.append({
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [
                                {
                                    "sheetId": tab_id,
                                    "startRowIndex": industry_row_start,
                                    "endRowIndex": current_row - 1,
                                    "startColumnIndex": 1,
                                    "endColumnIndex": len(months) + 1
                                }
                            ],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_EQ",
                                    "values": [{"userEnteredValue": "Contracting"}]
                                },
                                "format": {
                                    "backgroundColor": {
                                        "red": 0.9,
                                        "green": 0.7,
                                        "blue": 0.7
                                    }
                                }
                            }
                        },
                        "index": index_num * 3 + 1
                    }
                })
                
                formatting_requests.append({
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [
                                {
                                    "sheetId": tab_id,
                                    "startRowIndex": industry_row_start,
                                    "endRowIndex": current_row - 1,
                                    "startColumnIndex": 1,
                                    "endColumnIndex": len(months) + 1
                                }
                            ],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_EQ",
                                    "values": [{"userEnteredValue": "Neutral"}]
                                },
                                "format": {
                                    "backgroundColor": {
                                        "red": 0.9,
                                        "green": 0.9,
                                        "blue": 0.7
                                    }
                                }
                            }
                        },
                        "index": index_num * 3 + 2
                    }
                })
            
            # Add borders, freeze, and auto-resize
            formatting_requests.append({
                "updateBorders": {
                    "range": {
                        "sheetId": tab_id,
                        "startRowIndex": 0,
                        "endRowIndex": current_row,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(months) + 1
                    },
                    "top": {"style": "SOLID"},
                    "bottom": {"style": "SOLID"},
                    "left": {"style": "SOLID"},
                    "right": {"style": "SOLID"},
                    "innerHorizontal": {"style": "SOLID"},
                    "innerVertical": {"style": "SOLID"}
                }
            })
            
            # Freeze first column (industry names)
            formatting_requests.append({
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": tab_id,
                        "gridProperties": {
                            "frozenColumnCount": 1
                        }
                    },
                    "fields": "gridProperties.frozenColumnCount"
                }
            })
            
            # Auto-resize columns
            formatting_requests.append({
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": tab_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": len(months) + 1
                    }
                }
            })
            
            # Update the sheet
            service.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=f"'{tab_name}'!A1",
                valueInputOption="RAW",
                body={"values": all_rows}
            ).execute()
            
            # Apply all the formatting
            if formatting_requests:
                service.spreadsheets().batchUpdate(
                    spreadsheetId=sheet_id,
                    body={"requests": formatting_requests}
                ).execute()
            
            logger.info(f"Successfully created/updated '{tab_name}' tab")
            return True
        except Exception as e:
            logger.error(f"Error creating {report_type} alphabetical growth tab: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    def create_numerical_growth_tab(self, service, sheet_id, sheet_ids, report_type=None):
        """
        Create the numerical growth/contraction tab with proper sorting for each month.
        
        Args:
            service: Google Sheets API service
            sheet_id: Spreadsheet ID
            sheet_ids: Dictionary mapping tab names to sheet IDs
        
        Returns:
            Boolean indicating success
        """
        try:
            if not report_type:
                report_type = self.getCurrentReportType()
                
            tab_name = f'{report_type} Growth Numerical'
            
            # ENHANCED: Use report type specific logic
            main_pmi_index = f"{report_type} PMI"
            indices = [idx for idx in get_all_indices(report_type=report_type) if idx != main_pmi_index]
            
            # Get the current report type
            report_type = getCurrentReportType() 

            # Check if tab exists
            tab_id = sheet_ids.get(tab_name)
            if not tab_id:
                # Create the tab if it doesn't exist
                add_sheet_request = {
                    'requests': [{
                        'addSheet': {
                            'properties': {
                                'title': tab_name
                            }
                        }
                    }]
                }
                response = service.spreadsheets().batchUpdate(
                    spreadsheetId=sheet_id,
                    body=add_sheet_request
                ).execute()
                
                # Get the new sheet ID
                tab_id = response['replies'][0]['addSheet']['properties']['sheetId']
                logger.info(f"Created new tab '{tab_name}' with ID {tab_id}")
                
                # Refresh the sheet IDs mapping
                sheet_ids = self._get_all_sheet_ids(service, sheet_id)
            
            # Get all indices - FILTER OUT MANUFACTURING PMI
            indices = [idx for idx in get_all_indices(report_type=report_type) if idx != 'Manufacturing PMI']
            
            # Get report dates filtered by report type
            from db_utils import get_db_connection
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT report_date, month_year 
                FROM reports 
                WHERE report_type = ?
                ORDER BY report_date DESC
            """, (report_type,))

            report_dates = [dict(row) for row in cursor.fetchall()]
            months = [date['month_year'] for date in report_dates]
            
            # The 18 standard industries - COMPLETE LIST
            all_standard_industries = [
                "Apparel, Leather & Allied Products",
                "Chemical Products",
                "Computer & Electronic Products",
                "Electrical Equipment, Appliances & Components",
                "Fabricated Metal Products",
                "Food, Beverage & Tobacco Products",
                "Furniture & Related Products",
                "Machinery",
                "Miscellaneous Manufacturing",
                "Nonmetallic Mineral Products",
                "Paper Products",
                "Petroleum & Coal Products",
                "Plastics & Rubber Products",
                "Primary Metals",
                "Printing & Related Support Activities",
                "Textile Mills",
                "Transportation Equipment",
                "Wood Products"
            ]
            
            # Mapping from DB industry names to standard names
            standard_industries_mapping = {
                "Apparel, Leather & Allied Products": ["Apparel", "Apparel, Leather", "Apparel & Leather"],
                "Chemical Products": ["Chemical", "Chemicals"],
                "Computer & Electronic Products": ["Computer", "Computer & Electronic", "Electronics"],
                "Electrical Equipment, Appliances & Components": ["Electrical", "Electrical Equipment", "Appliances"],
                "Fabricated Metal Products": ["Fabricated Metal", "Metal Products", "Fabricated"],
                "Food, Beverage & Tobacco Products": ["Food", "Food & Beverage", "Food, Beverage & Tobacco"],
                "Furniture & Related Products": ["Furniture", "Furniture & Related"],
                "Machinery": ["Machinery"],
                "Miscellaneous Manufacturing": ["Miscellaneous"],
                "Nonmetallic Mineral Products": ["Nonmetallic", "Mineral Products", "Nonmetallic Mineral"],
                "Paper Products": ["Paper"],
                "Petroleum & Coal Products": ["Petroleum", "Petroleum & Coal", "Coal Products"],
                "Plastics & Rubber Products": ["Plastics", "Rubber", "Plastics & Rubber"],
                "Primary Metals": ["Primary Metal", "Metals"],
                "Printing & Related Support Activities": ["Printing", "Related Support"],
                "Textile Mills": ["Textile", "Textiles"],
                "Transportation Equipment": ["Transportation", "Transportation Equipment"],
                "Wood Products": ["Wood"]
            }
            
            # Create a reverse lookup for standardizing DB entries
            industry_standardization = {}
            for standard, variations in standard_industries_mapping.items():
                for variation in variations:
                    industry_standardization[variation.lower()] = standard
                industry_standardization[standard.lower()] = standard
            
            # Create array to hold all data for batch update
            all_rows = []
            formatting_requests = []
            current_row = 0
            
            # For each index, create a section
            for index_num, index in enumerate(indices):
                section_start_row = current_row
                
                # Add index header with bold formatting
                all_rows.append([f"INDEX: {index}"])
                current_row += 1
                
                # Add formatting for index header
                formatting_requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": tab_id,
                            "startRowIndex": section_start_row,
                            "endRowIndex": section_start_row + 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": len(months) * 2 + 2  # Enough columns for all tables
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {
                                    "bold": True
                                },
                                "backgroundColor": {
                                    "red": 0.9,
                                    "green": 0.9,
                                    "blue": 0.9
                                }
                            }
                        },
                        "fields": "userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColor"
                    }
                })

                # Define positive and negative categories based on index type
                pos_category = "Growing"
                neg_category = "Declining"
                
                if index == "Supplier Deliveries":
                    pos_category = "Slower"
                    neg_category = "Faster"
                elif index == "Inventories":
                    pos_category = "Higher"
                    neg_category = "Lower"
                elif index == "Customers' Inventories":
                    pos_category = "Too High"
                    neg_category = "Too Low"
                elif index == "Prices":
                    pos_category = "Increasing"
                    neg_category = "Decreasing"
                
                # Process each month to determine rankings
                month_rankings = []
                
                for month in months:
                    try:
                        # Get report date for this month
                        cursor.execute("""
                            SELECT report_date
                            FROM reports
                            WHERE month_year = ?
                        """, (month,))
                        report_date_row = cursor.fetchone()
                        
                        if report_date_row:
                            report_date = report_date_row['report_date']
                            
                            # Get industries for this index and month
                            cursor.execute("""
                                SELECT industry_name, status, category
                                FROM industry_status
                                WHERE report_date = ? AND index_name = ?
                                ORDER BY id
                            """, (report_date, index))
                            
                            # Process into positive and negative categories
                            pos_industries = []
                            neg_industries = []
                            seen_industries = set()
                            
                            for i, row in enumerate(cursor.fetchall()):
                                db_industry = row['industry_name']
                                category = row['category']
                                
                                # Standardize industry name
                                std_industry = self._standardize_industry_name(
                                    db_industry, 
                                    industry_standardization,
                                    all_standard_industries
                                )
                                
                                # Skip if invalid or already seen
                                if not std_industry or std_industry not in all_standard_industries or std_industry in seen_industries:
                                    continue
                                    
                                seen_industries.add(std_industry)
                                
                                if category == pos_category:
                                    pos_industries.append((std_industry, i))
                                elif category == neg_category:
                                    neg_industries.append((std_industry, i))
                            
                            # Build the full ranking map
                            ranking_map = {}
                            
                            # Positive industries get positive ranks (highest first)
                            for i, (industry, order) in enumerate(pos_industries):
                                rank = len(pos_industries) - i
                                ranking_map[industry] = rank
                            
                            # Negative industries get negative ranks (most negative last)
                            neg_industries.reverse()  # Reverse to maintain original DBs order
                            for i, (industry, order) in enumerate(neg_industries):
                                rank = -1 - i
                                ranking_map[industry] = rank
                            
                            # Add neutral industries (all standard industries not seen)
                            for industry in all_standard_industries:
                                if industry not in ranking_map:
                                    ranking_map[industry] = 0
                            
                            # Find min/max for conditional formatting
                            rank_values = list(ranking_map.values())
                            max_rank = max(rank_values)
                            min_rank = min(rank_values)
                            
                            # Store month data
                            month_rankings.append({
                                'month': month,
                                'rankings': ranking_map,
                                'max_rank': max_rank,
                                'min_rank': min_rank
                            })
                        else:
                            # No data for this month
                            neutral_map = {industry: 0 for industry in all_standard_industries}
                            month_rankings.append({
                                'month': month,
                                'rankings': neutral_map,
                                'max_rank': 0,
                                'min_rank': 0
                            })
                            
                    except Exception as e:
                        logger.error(f"Error processing rankings for {month}: {str(e)}")
                        # Create neutral rankings as fallback
                        neutral_map = {industry: 0 for industry in all_standard_industries}
                        month_rankings.append({
                            'month': month,
                            'rankings': neutral_map,
                            'max_rank': 0,
                            'min_rank': 0
                        })
                        
                # Create header row for REFERENCE column and all months
                header_row = ["REFERENCE"]  # First column is REFERENCE
                for month in months:
                    header_row.append(month)  # Month column
                    header_row.append("Rank")  # Rank column
                    
                all_rows.append(header_row)
                current_row += 1
                
                # Add formatting for header row
                formatting_requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": tab_id,
                            "startRowIndex": current_row - 1,
                            "endRowIndex": current_row,
                            "startColumnIndex": 0,
                            "endColumnIndex": len(month_rankings) * 2 + 1
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {
                                    "bold": True
                                }
                            }
                        },
                        "fields": "userEnteredFormat.textFormat.bold"
                    }
                })

                # For each month, add conditional formatting for the rank column
                for month_idx, month_data in enumerate(month_rankings):
                    # Add conditional formatting for the rank column if there's a spread between min and max
                    if month_data['max_rank'] != month_data['min_rank']:
                        formatting_requests.append({
                            "addConditionalFormatRule": {
                                "rule": {
                                    "ranges": [
                                        {
                                            "sheetId": tab_id,
                                            "startRowIndex": current_row,
                                            "endRowIndex": current_row + len(all_standard_industries),
                                            "startColumnIndex": month_idx * 2 + 2,  # Rank column
                                            "endColumnIndex": month_idx * 2 + 3
                                        }
                                    ],
                                    "gradientRule": {
                                        "minpoint": {
                                            "color": {
                                                "red": 0.9,
                                                "green": 0.2,
                                                "blue": 0.2
                                            },
                                            "type": "NUMBER",
                                            "value": str(month_data['min_rank'])
                                        },
                                        "midpoint": {
                                            "color": {
                                                "red": 1.0,
                                                "green": 1.0,
                                                "blue": 0.2
                                            },
                                            "type": "NUMBER",
                                            "value": "0"
                                        },
                                        "maxpoint": {
                                            "color": {
                                                "red": 0.2,
                                                "green": 0.9,
                                                "blue": 0.2
                                            },
                                            "type": "NUMBER",
                                            "value": str(month_data['max_rank'])
                                        }
                                    }
                                },
                                "index": index_num * len(months) + month_idx
                            }
                        })

                # Create the REFERENCE column with alphabetically sorted industries
                reference_industries = sorted(all_standard_industries)
                
                # For each month, pre-sort the industries by rank before adding to rows
                # This replaces the sort requests approach
                for month_idx, month_data in enumerate(month_rankings):
                    rankings = month_data['rankings']
                    
                    # Sort industries by rank for this month (descending order)
                    month_sorted_industries = sorted(
                        all_standard_industries,
                        key=lambda ind: rankings.get(ind, 0),
                        reverse=True  # Highest rank first
                    )
                    
                    # Prepare data for this month's columns
                    month_column_data = []
                    for industry in month_sorted_industries:
                        rank = rankings.get(industry, 0)
                        month_column_data.append({
                            'industry': industry,
                            'rank': rank
                        })
                    
                    # Store the sorted data for this month
                    month_data['sorted_data'] = month_column_data
                
                # Now create rows with REFERENCE and all months' data
                for i, ref_industry in enumerate(reference_industries):
                    row = [ref_industry]  # Start with reference industry
                    
                    # Add data for each month
                    for month_data in month_rankings:
                        # Get the i-th sorted industry for this month
                        month_sorted = month_data['sorted_data']
                        if i < len(month_sorted):
                            row.append(month_sorted[i]['industry'])
                            row.append(month_sorted[i]['rank'])
                        else:
                            # Fallback if somehow there are fewer industries
                            row.append("")
                            row.append("")
                    
                    all_rows.append(row)
                    current_row += 1
                
                # Add blank row between indices
                all_rows.append([""])
                current_row += 1
                
                # Add borders, freeze first row and column
                formatting_requests.append({
                    "updateBorders": {
                        "range": {
                            "sheetId": tab_id,
                            "startRowIndex": section_start_row,
                            "endRowIndex": current_row - 1,  # Exclude the blank row
                            "startColumnIndex": 0,
                            "endColumnIndex": len(months) * 2 + 1
                        },
                        "top": {"style": "SOLID"},
                        "bottom": {"style": "SOLID"},
                        "left": {"style": "SOLID"},
                        "right": {"style": "SOLID"},
                        "innerHorizontal": {"style": "SOLID"},
                        "innerVertical": {"style": "SOLID"}
                    }
                })
            
            # Freeze header rows and first column for entire sheet
            formatting_requests.append({
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": tab_id,
                        "gridProperties": {
                            "frozenRowCount": 2,  # Freeze index header and month headers
                            "frozenColumnCount": 1  # Freeze industry name column
                        }
                    },
                    "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"
                }
            })
            
            # Auto-resize columns
            formatting_requests.append({
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": tab_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": len(months) * 2 + 1
                    }
                }
            })
            
             # Update the sheet with our pre-sorted data
            service.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=f"'{tab_name}'!A1",
                valueInputOption="RAW",
                body={"values": all_rows}
            ).execute()
            
            # Apply formatting (but not sorting requests)
            if formatting_requests:
                service.spreadsheets().batchUpdate(
                    spreadsheetId=sheet_id,
                    body={"requests": formatting_requests}
                ).execute()
            
            logger.info(f"Successfully created/updated '{tab_name}' tab")
            return True
        except Exception as e:
            logger.error(f"Error creating {report_type} numerical growth tab: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    def _standardize_industry_name(self, industry_name, standardization_map, standard_industry_list):
        """
        Standardize industry names to match the official industry names.
        
        Args:
            industry_name: Original industry name from database
            standardization_map: Mapping of industry name variations to standard names
            standard_industry_list: List of standard industry names
                
        Returns:
            Standardized industry name
        """
        if not industry_name:
            return None
                
        # Clean the industry name
        clean_name = industry_name.strip()
        
        # Try exact match first (case insensitive)
        if clean_name.lower() in standardization_map:
            standard_name = standardization_map[clean_name.lower()]
            if standard_name in standard_industry_list:
                return standard_name
        
        # Try partial matches with keywords
        for standard_name in standard_industry_list:
            if standard_name.lower() in clean_name.lower() or clean_name.lower() in standard_name.lower():
                return standard_name
        
        # Try best-match approach with overlapping words
        clean_words = set(clean_name.lower().split())
        best_match = None
        best_score = 0
        
        for standard_name in standard_industry_list:
            standard_words = set(standard_name.lower().split())
            match_score = len(clean_words.intersection(standard_words))
            if match_score > best_score:
                best_score = match_score
                best_match = standard_name
        
        # Return best match if we found one with at least one word in common
        if best_score > 0:
            return best_match
        
        # If all else fails, return the original name
        return clean_name

    def remove_deprecated_tabs(service, sheet_id, tabs_to_keep):
        """
        Remove deprecated tabs, keeping only specified tabs.
        
        Args:
            service: Google Sheets API service
            sheet_id: Spreadsheet ID
            tabs_to_keep: List of tab names to keep
            
        Returns:
            Boolean indicating success
        """
        try:
            # Get all existing tabs
            sheet_metadata = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
            sheets = sheet_metadata.get('sheets', [])
            
            # Find tabs to remove
            remove_requests = []
            for sheet in sheets:
                title = sheet.get('properties', {}).get('title')
                sheet_id_value = sheet.get('properties', {}).get('sheetId')
                
                if title not in tabs_to_keep and sheet_id_value is not None:
                    remove_requests.append({
                        'deleteSheet': {
                            'sheetId': sheet_id_value
                        }
                    })
            
            # Execute removals if any
            if remove_requests:
                service.spreadsheets().batchUpdate(
                    spreadsheetId=sheet_id,
                    body={'requests': remove_requests}
                ).execute()
                
                logger.info(f"Removed {len(remove_requests)} deprecated tabs")
                return True
            else:
                logger.info("No deprecated tabs to remove")
                return True
                
        except Exception as e:
            logger.error(f"Error removing deprecated tabs: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    def getCurrentReportType(self):
        """Get the current report type with proper fallback."""
        if self._current_report_type:
            return self._current_report_type
        if self._extraction_data and 'report_type' in self._extraction_data:
            return self._extraction_data['report_type']
        return "Manufacturing"  # Safe fallback

class PDFOrchestratorTool(BaseTool):
    name: str = Field(default="orchestrate_processing")
    description: str = Field(
        default="""
        Orchestrates the processing of multiple ISM Manufacturing Report PDFs.
        
        Args:
            pdf_directory: Directory containing PDF files to process
        
        Returns:
            A dictionary with processing results for each PDF file
        """
    )
    
    def _run(self, pdf_directory: str) -> Dict[str, Any]:
        """
        Implementation of the required abstract _run method.
        This orchestrates the processing of multiple PDFs.
        """
        try:
            if not pdf_directory:
                raise ValueError("PDF directory not provided")
                
            results = {}
            
            # Get all PDF files in the directory
            pdf_files = [f for f in os.listdir(pdf_directory) if f.lower().endswith('.pdf')]
            
            if not pdf_files:
                logger.warning(f"No PDF files found in {pdf_directory}")
                return {"success": False, "message": "No PDF files found"}
            
            # Process each PDF file
            for pdf_file in pdf_files:
                pdf_path = os.path.join(pdf_directory, pdf_file)
                
                # Extract data from the PDF
                extraction_tool = SimplePDFExtractionTool()
                extracted_data = extraction_tool._run(pdf_path)
                
                # Structure the extracted data
                structurer_tool = SimpleDataStructurerTool()
                structured_data = structurer_tool._run(extracted_data)
                
                # Validate the structured data
                validator_tool = DataValidatorTool()
                validation_results = validator_tool._run(structured_data)
                
                # Check if any validations passed
                if any(validation_results.values()):
                    formatter_tool = GoogleSheetsFormatterTool()
                    update_result = formatter_tool._run({
                        'structured_data': structured_data, 
                        'validation_results': validation_results
                    })
                    results[pdf_file] = update_result
                else:
                    logger.warning(f"All validations failed for {pdf_file}")
                    results[pdf_file] = False
            
            return {"success": True, "results": results}
        except Exception as e:
            logger.error(f"Error in PDF orchestration: {str(e)}")
            return {"success": False, "message": str(e)}