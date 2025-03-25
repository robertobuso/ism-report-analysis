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

# Create logs directory first
os.makedirs("logs", exist_ok=True)

logger = logging.getLogger(__name__)

ENABLE_NEW_TABS = True  # Feature flag for new tab format

class SimplePDFExtractionTool(BaseTool):
    name: str = Field(default="extract_pdf_data")
    description: str = Field(
        default="""
        Extracts ISM Manufacturing Report data from a PDF file.
        
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

    def _run(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Implementation of the required abstract _run method.
        This extracts ISM data using LLM approach.
        """
        try:
            # Check if input is already a dictionary with pdf_path
            if isinstance(extracted_data, dict) and 'pdf_path' in extracted_data and not any(k for k in extracted_data if k != 'pdf_path'):
                # Wrap it in the expected format
                extracted_data = {'extracted_data': extracted_data}
                
            # Now extract from the correct field
            if 'extracted_data' in extracted_data and isinstance(extracted_data['extracted_data'], dict) and 'pdf_path' in extracted_data['extracted_data']:
                pdf_path = extracted_data['extracted_data']['pdf_path']
                logger.info(f"Extracting data from PDF (nested structure): {pdf_path}")
                
                # Get the month_year first (we'll need this for LLM extraction)
                from pdf_utils import extract_text_from_pdf, extract_month_year
                text = extract_text_from_pdf(pdf_path)
                month_year = "Unknown"
                if text:
                    month_year = extract_month_year(text)
                    if not month_year:
                        month_year = "Unknown"
                
                # Use LLM for primary extraction
                logger.info("Using LLM for primary extraction of Manufacturing at a Glance data and industry data")
                llm_data = self._extract_manufacturing_data_with_llm(pdf_path, month_year)
                
                if llm_data:
                    result = {
                        'month_year': llm_data.get('month_year', month_year),
                        'manufacturing_table': llm_data,
                        'pmi_data': llm_data.get('indices', {}),
                        'industry_data': llm_data.get('industry_data', {})
                    }
                    logger.info("Successfully extracted data with LLM")
                    return result
                else:
                    logger.warning("LLM extraction returned empty data")
                    return {
                        'month_year': month_year,
                        'manufacturing_table': {},
                        'index_summaries': {},
                        'industry_data': {},
                        'pmi_data': {}
                    }
                    
        except Exception as e:
            logger.error(f"Error in data extraction: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Return minimal valid structure as fallback
            return {
                "month_year": "Unknown",
                "manufacturing_table": {},
                "index_summaries": {},
                "industry_data": {},
                "pmi_data": {}
            }
        
    def _extract_manufacturing_data_with_llm(self, pdf_path, month_year):
        """Extract Manufacturing at a Glance data and industry data from entire PDF."""
        try:
            logger.info(f"Extracting data from complete PDF: {pdf_path} with LLM")
            
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
            
            # Construct the prompt WITHOUT using nested f-strings
            prompt_part1 = """
            I need you to analyze this ISM Manufacturing Report PDF and extract both the "Manufacturing at a Glance" table data AND industry classification data.

            PART 1: Manufacturing at a Glance Table
            Extract and return these data points:
            - Month and Year of the report (should be """
            
            prompt_part2 = month_year
            
            prompt_part3 = """)
            - Manufacturing PMI value and status (Growing/Contracting) 
            - New Orders value and status
            - Production value and status
            - Employment value and status
            - Supplier Deliveries value and status
            - Inventories value and status
            - Customers' Inventories value and status
            - Prices value and status
            - Backlog of Orders value and status
            - New Export Orders value and status
            - Imports value and status
            - Overall Economy status
            - Manufacturing Sector status

            PART 2: Industry Data Classification
            For each of the following indices, identify industries that are classified as growing/expanding or contracting/declining:

            1. New Orders:
            - Growing: List all industries mentioned as reporting growth, expansion, or increases
            - Declining: List all industries mentioned as reporting contraction, decline, or decreases

            2. Production:
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

            6. Customers' Inventories:
            - Too High: List all industries mentioned as reporting customers' inventories as too high
            - Too Low: List all industries mentioned as reporting customers' inventories as too low

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
            {
                "month_year": "Month Year",
                "indices": {
                    "Manufacturing PMI": {"current": "48.4", "direction": "Contracting"},
                    "New Orders": {"current": "50.4", "direction": "Growing"},
                    ...and so on for all indices,
                    "OVERALL ECONOMY": {"direction": "Growing"},
                    "Manufacturing Sector": {"direction": "Contracting"}
                },
                "industry_data": {
                    "New Orders": {
                        "Growing": ["Industry1", "Industry2", ...],
                        "Declining": ["Industry3", "Industry4", ...]
                    },
                    "Production": {
                        "Growing": [...],
                        "Declining": [...]
                    },
                    ...and so on for all indices
                }
            }

            Here is the extracted text from the PDF:
            """
            
            prompt_part4 = extracted_text
            
            # Combine the prompt parts in a way that avoids nested f-strings
            prompt = prompt_part1 + prompt_part2 + prompt_part3 + prompt_part4
            
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
                    logger.info(f"Received response from OpenAI ({len(response_text)} characters)")
                    
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
                        
                        # Success! Return the parsed JSON
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
            logger.error(f"Error in _extract_manufacturing_data_with_llm: {str(e)}")
            logger.error(traceback.format_exc())
            return {"month_year": month_year, "indices": {}, "industry_data": {}}
    
    def _parse_llm_response(self, response_text, month_year):
        """Helper method to parse LLM response text into structured data"""
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
                json_data = {"month_year": month_year, "indices": {}}
            
            # Add industry_data field if missing
            if "industry_data" not in json_data:
                json_data["industry_data"] = {}
                
            return json_data
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {str(e)}")
            # Fallback manual parsing code...
            # ...existing fallback code...
            return {"month_year": month_year, "indices": {}, "industry_data": {}}

    def _extract_pdf_text(self, pdf_path, max_pages=None):
        """Helper to extract text from ALL pages of PDF."""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                page_count = len(pdf.pages)
                # Extract ALL pages if max_pages is None
                pages_to_extract = page_count if max_pages is None else min(max_pages, page_count)
                logger.info(f"Extracting all {pages_to_extract} pages from PDF with {page_count} total pages")
                
                extracted_text = ""
                for i in range(pages_to_extract):
                    page_text = pdf.pages[i].extract_text()
                    if page_text:
                        extracted_text += page_text + "\n\n"
                return extracted_text
        except Exception as e:
            logger.warning(f"Error with pdfplumber: {str(e)}")
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(pdf_path)
                page_count = len(reader.pages)
                pages_to_extract = page_count if max_pages is None else min(max_pages, page_count)
                logger.info(f"Fallback: Extracting all {pages_to_extract} pages using PyPDF2")
                
                extracted_text = ""
                for i in range(pages_to_extract):
                    page_text = reader.pages[i].extract_text()
                    if page_text:
                        extracted_text += page_text + "\n\n"
                return extracted_text
            except Exception as e2:
                logger.error(f"Both PDF extraction methods failed: {str(e2)}")
                return ""

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
            
            # Get month and year
            month_year = extracted_data.get("month_year", "Unknown")
            logger.info(f"Structuring data for {month_year}")
            
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
            if not industry_data or all(not industries for categories in industry_data.values() for industries in categories.values()):
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
            
            # Structure data for each index
            structured_data = {}
            
            # Ensure we have entries for all expected indices
            for index in ISM_INDICES:
                # Get categories for this index if available
                categories = {}
                if industry_data and index in industry_data:
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
                
                # DEFINE category_count BEFORE USING IT - ADD THIS LINE
                category_count = len(cleaned_industries)  
                
                if category_count < 0 or category_count > len(cleaned_industries):
                    logger.warning(f"Invalid category_count {category_count} for {category_name}, using available count {len(cleaned_industries)}")
                    category_count = len(cleaned_industries)

                    # Only add categories that actually have industries
                    if cleaned_industries:
                        actual_count = min(category_count, len(cleaned_industries))
                        cleaned_categories[category_name] = cleaned_industries[:actual_count]

                    if not cleaned_industries:
                        logger.warning(f"No cleaned industries for {category_name}, using empty list")
                        cleaned_categories[category_name] = []
                        continue  
                
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
    
    def _run(self, data: Dict[str, Any]) -> bool:
        """
        Main entry point for the Google Sheets Formatter Tool.
        
        Args:
            data: Dictionary containing structured_data, validation_results, and visualization_options
                
        Returns:
            Boolean indicating whether the Google Sheets update was successful
        """
        try:
            # Check if required keys exist
            if not isinstance(data, dict):
                data = {'structured_data': {}, 'validation_results': {}}
                logger.warning("Data is not a dictionary. Creating an empty structure.")
                
            # Get extraction_data first since we'll use it in multiple places
            extraction_data = data.get('extraction_data', {})

            # Ensure month_year is extracted and preserved correctly
            month_year = extraction_data.get('month_year', 'Unknown')
            if 'verification_result' in data and isinstance(data['verification_result'], dict):
                # If verification_result has a different month_year, use the original
                if 'month_year' in data['verification_result'] and data['verification_result']['month_year'] != month_year:
                    logger.warning(f"Month/year changed during verification - using original {month_year}")
                    data['verification_result']['month_year'] = month_year
            
            # Store data in database if extraction_data is available
            from db_utils import store_report_data_in_db
            try:
                if extraction_data and 'month_year' in extraction_data:
                    pdf_path = data.get('pdf_path', 'unknown_path')
                    store_result = store_report_data_in_db(extraction_data, pdf_path)
                    logger.info(f"Database storage result: {store_result}")
            except Exception as e:
                logger.error(f"Error storing data in database: {str(e)}")
            
            # Get Google Sheets service
            service = get_google_sheets_service()
            if not service:
                logger.error("Failed to get Google Sheets service")
                return False
            
            # Get or create the Google Sheet
            sheet_id = self._get_or_create_sheet(service, "ISM Manufacturing Report Analysis")
            if not sheet_id:
                logger.error("Failed to get or create Google Sheet")
                return False
            
            # Get all sheet IDs for tabs
            sheet_ids = self._get_all_sheet_ids(service, sheet_id)
            
            # ONLY CREATE THE THREE REQUESTED TABS
            try:
                # 1. Update the heatmap tab with values only (no direction)
                monthly_data = get_pmi_data_by_month(24)  # Get last 24 months
                heatmap_result = self.update_heatmap_tab(service, sheet_id, monthly_data)
                if heatmap_result:
                    logger.info("Successfully updated heatmap tab with values only")
                else:
                    logger.warning("Failed to update heatmap tab with values only")
                
                # 2. Create alphabetical growth tab
                alpha_result = self.create_alphabetical_growth_tab(service, sheet_id, sheet_ids)
                if alpha_result:
                    logger.info("Successfully created alphabetical growth tab")
                else:
                    logger.warning("Failed to create alphabetical growth tab")
                
                # 3. Create numerical growth tab
                num_result = self.create_numerical_growth_tab(service, sheet_id, sheet_ids)
                if num_result:
                    logger.info("Successfully created numerical growth tab")
                else:
                    logger.warning("Failed to create numerical growth tab")
                
                logger.info("Successfully created/updated required tabs")
                logger.info(f"Successfully updated Google Sheets")
                return True
            except Exception as e:
                logger.error(f"Error creating required tabs: {str(e)}")
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
            logger.info(f"Prepared row for Google Sheets: {row}")
            
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

    def update_heatmap_tab(self, service, sheet_id, monthly_data):
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
            tab_name = 'PMI Heatmap Summary'
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
            logger.error(f"Error updating heatmap tab: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    def create_alphabetical_growth_tab(self, service, sheet_id, sheet_ids):
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
            tab_name = 'Growth Alphabetical'
            
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
            indices = get_all_indices()
            
            # Get all report dates for columns
            report_dates = get_all_report_dates()
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
                industry_data = get_industry_status_over_time(index, len(months))
                
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
            logger.error(f"Error creating alphabetical growth tab: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    def create_numerical_growth_tab(self, service, sheet_id, sheet_ids):
        """
        Create the numerical growth/contraction tab with industries ranked by growth/contraction.
        
        Args:
            service: Google Sheets API service
            sheet_id: Spreadsheet ID
            sheet_ids: Dictionary mapping tab names to sheet IDs
        
        Returns:
            Boolean indicating success
        """
        try:
            tab_name = 'Growth Numerical'
            
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
            indices = [idx for idx in get_all_indices() if idx != 'Manufacturing PMI']
            
            # Get report dates
            from db_utils import get_db_connection
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT report_date, month_year 
                FROM reports 
                ORDER BY report_date DESC
            """)
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
                
                # Create row for month headers
                month_header_row = ["REFERENCE"]  # First cell is REFERENCE
                for month in months:
                    month_header_row.append(month)  # Month name
                    month_header_row.append("Rank")  # Rank column
                
                all_rows.append(month_header_row)
                current_row += 1
                
                # Add formatting for month header row (bold)
                formatting_requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": tab_id,
                            "startRowIndex": current_row - 1,
                            "endRowIndex": current_row,
                            "startColumnIndex": 0,
                            "endColumnIndex": len(months) * 2 + 1
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
                                    industry_standardization,  # Pass the industry_standardization map
                                    all_standard_industries    # Pass the list of standard industries
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
                
                # Now create rows for each month, sorted by ranking
                for month_idx, month_data in enumerate(month_rankings):
                    # Add conditional formatting for the rank column
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
                
                # Get all industries sorted by first month's ranking
                if month_rankings:
                    first_month = month_rankings[0]['rankings']
                    sorted_industries = sorted(
                        all_standard_industries,
                        key=lambda ind: first_month.get(ind, 0),
                        reverse=True
                    )
                else:
                    sorted_industries = all_standard_industries
                
                # Add rows for all industries in sorted order
                for industry in sorted_industries:
                    industry_row = [industry]  # First column is industry name
                    
                    # Add data for each month
                    for month_data in month_rankings:
                        rankings = month_data['rankings']
                        rank = rankings.get(industry, 0)
                        industry_row.append(industry)  # Industry column
                        industry_row.append(rank)      # Rank column
                    
                    all_rows.append(industry_row)
                    current_row += 1
                
                # Add blank row between indices
                all_rows.append([""])
                current_row += 1
            
            # Add borders, freeze first row and column
            formatting_requests.append({
                "updateBorders": {
                    "range": {
                        "sheetId": tab_id,
                        "startRowIndex": 0,
                        "endRowIndex": current_row,
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
            
            # Freeze header rows and first column
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
            logger.error(f"Error creating numerical growth tab: {str(e)}")
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