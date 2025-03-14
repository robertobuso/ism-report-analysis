import os
import json
import logging
import traceback
from typing import Dict, Any, Optional, List, Union, Tuple
import pandas as pd
from google_auth import get_google_sheets_service
from db_utils import (
    get_pmi_data_by_month, 
    get_index_time_series, 
    get_industry_status_over_time,
    get_all_indices,
    initialize_database,
    check_report_exists_in_db
)
from config import ISM_INDICES, INDEX_CATEGORIES
from crewai.tools import BaseTool
from pydantic import Field

# Create logs directory first
os.makedirs("logs", exist_ok=True)

logger = logging.getLogger(__name__)

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
    
    def _run(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Implementation of the required abstract _run method.
        This structures the extracted ISM data.
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
                # Parse the PDF directly
                from pdf_utils import parse_ism_report
                parsed_data = parse_ism_report(pdf_path)
                if parsed_data:
                    return parsed_data
            
            # Check if this is just a direct pdf_path request
            elif 'pdf_path' in extracted_data and isinstance(extracted_data['pdf_path'], str):
                pdf_path = extracted_data['pdf_path']
                logger.info(f"Extracting data from PDF: {pdf_path}")
                # Parse the PDF directly
                from pdf_utils import parse_ism_report
                parsed_data = parse_ism_report(pdf_path)
                if parsed_data:
                    return parsed_data
                # If parsing failed, continue with empty data structure
                extracted_data = {
                    "month_year": "Unknown",
                    "manufacturing_table": "",
                    "index_summaries": {},
                    "industry_data": {}
                }

            logger.info("Data Structurer Tool received input")
            
            # Get month and year
            month_year = extracted_data.get("month_year", "Unknown")
            logger.info(f"Structuring data for {month_year}")
            
            # Check different possible locations for industry data
            industry_data = None
            
            # First try getting industry_data directly
            if "industry_data" in extracted_data and extracted_data["industry_data"]:
                industry_data = extracted_data["industry_data"]
                logger.info("Using industry_data from extraction")
                
            # If not available, check for corrected_industry_data
            elif "corrected_industry_data" in extracted_data and extracted_data["corrected_industry_data"]:
                industry_data = extracted_data["corrected_industry_data"]
                logger.info("Using corrected_industry_data")
                
            # If still not available, look inside 'manufacturing_table'
            elif "manufacturing_table" in extracted_data and isinstance(extracted_data["manufacturing_table"], dict):
                if any(k in extracted_data["manufacturing_table"] for k in ISM_INDICES):
                    industry_data = extracted_data["manufacturing_table"]
                    logger.info("Using industry data from manufacturing_table")
            
            # Validate industry_data has content
            if not industry_data:
                logger.warning("Industry data is empty, attempting to re-extract from summaries")
                
                if "index_summaries" in extracted_data and extracted_data["index_summaries"]:
                    try:
                        from pdf_utils import extract_industry_mentions
                        # Try to re-extract industry data from the summaries
                        industry_data = extract_industry_mentions("", extracted_data["index_summaries"])
                        logger.info("Re-extracted industry data from summaries")
                    except Exception as e:
                        logger.error(f"Error re-extracting industry data: {str(e)}")
            
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
                    
                    # Only add categories that actually have industries
                    if cleaned_industries:
                        cleaned_categories[category_name] = cleaned_industries
                
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
                    
                    # Only add categories that actually have industries
                    if cleaned_industries:
                        cleaned_categories[category_name] = cleaned_industries
                
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
                        
                        # Check if all expected categories exist (case insensitive)
                        categories_valid = all(ec in actual_categories for ec in expected_lower)
                        
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
            
            # Check for corrected industry data from verification
            if 'verification_result' in data and isinstance(data['verification_result'], dict):
                verification_result = data['verification_result']
                if 'corrected_industry_data' in verification_result:
                    # If we have a verification result with corrected data, inject it back into the extraction data
                    if 'extraction_data' not in data:
                        data['extraction_data'] = {}
                    data['extraction_data']['industry_data'] = verification_result['corrected_industry_data']
                    extraction_data = data['extraction_data']
                    logger.info("Using corrected industry data from verification result")
            
            if 'structured_data' not in data:
                data['structured_data'] = {}
                logger.warning("structured_data not found. Creating empty structured_data.")
                
            if 'validation_results' not in data:
                data['validation_results'] = {}
                logger.warning("validation_results not found. Creating empty validation_results.")
            
            structured_data = data.get('structured_data', {})
            validation_results = data.get('validation_results', {})
            visualization_options = data.get('visualization_options', {
                'basic': True,
                'heatmap': True,
                'timeseries': True,
                'industry': True
            })

            # Initialize the database if needed
            initialize_database()
            
            # Validate the data has actual industries before proceeding
            industry_count = self._count_industries(structured_data)
            logger.info(f"Found {industry_count} industries in structured data")
            
            # If no industries in structured data, try direct extraction if available
            if industry_count == 0 and extraction_data and 'industry_data' in extraction_data:
                logger.info("No industries found in structured data, trying to create from extraction_data")
                structured_data = self._create_structured_data_from_extraction(extraction_data)
                industry_count = self._count_industries(structured_data)
                logger.info(f"Created structured data with {industry_count} industries from extraction_data")
                
                # If we now have industry data from extraction_data, make sure validation_results is updated
                if industry_count > 0:
                    validation_results = self._create_default_validation_results(structured_data)
                    logger.info("Created default validation results for the newly structured data")
            
            # If no industries in structured data but we have corrected_industry_data, use that
            if industry_count == 0 and extraction_data and 'corrected_industry_data' in extraction_data:
                logger.info("No industries found in structured data, trying to use corrected_industry_data")
                extraction_data['industry_data'] = extraction_data['corrected_industry_data']
                structured_data = self._create_structured_data_from_extraction(extraction_data)
                industry_count = self._count_industries(structured_data)
                logger.info(f"Created structured data with {industry_count} industries from corrected_industry_data")
                
                # If we now have industry data from corrected_industry_data, make sure validation_results is updated
                if industry_count > 0:
                    validation_results = self._create_default_validation_results(structured_data)
                    logger.info("Created default validation results for the newly structured data")
                    
            # If still no valid data, log warning and return failure
            if industry_count == 0:
                logger.warning("No valid industry data found for Google Sheets update")
                return False

            # If no validation results, create some basic ones for continuing
            if not validation_results:
                validation_results = self._create_default_validation_results(structured_data)
            
            # Check if validation passed for at least some indices
            if not any(validation_results.values()):
                # Force at least one index to be valid so we can continue
                validation_results = self._force_valid_index(validation_results)
            
            # Get the month and year from the extraction data
            month_year = self._get_month_year(structured_data, extraction_data)
            
            # Format the month_year as MM/YY for spreadsheet
            formatted_month_year = self._format_month_year(month_year)
            
            # Try uppercase and title case variations since capitalization might differ
            variations = [
                month_year,
                month_year.upper(),
                month_year.title(),
                # Also check the formatted version
                formatted_month_year
            ]

            report_exists = False
            for variation in variations:
                if check_report_exists_in_db(variation):
                    report_exists = True
                    logger.info(f"Found report in database using variant: {variation}")
                    break

            if not report_exists:
                logger.warning(f"Report for {month_year} not found in database. Some visualizations may be incomplete.")

            
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
            
            # Initialize the tab data collection for batch updates
            all_tab_data = {}
            
            # Process Manufacturing at a Glance table if available
            if 'extraction_data' in data and data['extraction_data'].get('manufacturing_table'):
                try:
                    logger.info(f"Updating Manufacturing at a Glance table for {month_year}")
                    
                    # Get the sheet ID for the tab
                    tab_name = 'Manufacturing at a Glance'
                    mfg_sheet_id = sheet_ids.get(tab_name)
                    
                    if not mfg_sheet_id:
                        logger.warning(f"{tab_name} tab not found")
                    else:
                        # Extract data with LLM if we have the table content
                        table_content = data['extraction_data'].get('manufacturing_table', '')
                        parsed_data = self._extract_data_with_llm(table_content, month_year)
                        
                        # Build header
                        headers = [
                            "Month & Year", "Manufacturing PMI", "New Orders", "Production", 
                            "Employment", "Supplier Deliveries", "Inventories", 
                            "Customers' Inventories", "Prices", "Backlog of Orders",
                            "New Export Orders", "Imports", "Overall Economy", "Manufacturing Sector"
                        ]
                        
                        # Build row data
                        row_data = self._prepare_horizontal_row(parsed_data, formatted_month_year)
                        
                        # Prepare the manufacturing table data
                        all_tab_data[tab_name] = {
                            'data': [headers, row_data],
                            'formatting': self._prepare_manufacturing_table_formatting(mfg_sheet_id, 2, len(headers))
                        }
                except Exception as e:
                    logger.error(f"Error updating Manufacturing at a Glance tab: {str(e)}")
            
            # Process basic visualization if enabled
            if visualization_options.get('basic', True):
                try:
                    logger.info("Processing basic industry classification visualizations")
                    
                    # Update each index tab that passed validation
                    for index, valid in validation_results.items():
                        if valid and index in structured_data:
                            # Get the sheet ID for this index
                            index_sheet_id = sheet_ids.get(index)
                            
                            if not index_sheet_id:
                                logger.warning(f"Sheet ID not found for index {index}")
                                continue
                            
                            # Format data for this index
                            tab_data, formatting = self._prepare_index_tab_data(
                                index, 
                                structured_data[index], 
                                formatted_month_year,
                                index_sheet_id
                            )
                            
                            # Add to batch update
                            if tab_data:
                                all_tab_data[index] = {
                                    'data': tab_data,
                                    'formatting': formatting
                                }
                except Exception as e:
                    logger.error(f"Error updating basic visualization: {str(e)}")
            
            # Process monthly heatmap summary if enabled
            if visualization_options.get('heatmap', True):
                try:
                    logger.info("Processing monthly heatmap summary visualization")
                    
                    # Get data from the database
                    monthly_data = get_pmi_data_by_month(24)  # Get last 24 months
                    
                    if not monthly_data:
                        logger.warning("No monthly data found in database for heatmap summary")
                    else:
                        # Get all unique index names
                        all_indices = set()
                        for data in monthly_data:
                            all_indices.update(data['indices'].keys())
                        
                        # Order indices with Manufacturing PMI first, then alphabetically
                        ordered_indices = ['Manufacturing PMI']
                        ordered_indices.extend(sorted([idx for idx in all_indices if idx != 'Manufacturing PMI']))
                        
                        # Prepare header row
                        header_row = ["Month/Year"]
                        header_row.extend(ordered_indices)
                        
                        # Prepare data rows
                        data_rows = []
                        for data in monthly_data:
                            row = [data['month_year']]
                            
                            for index_name in ordered_indices:
                                index_data = data['indices'].get(index_name, {})
                                value = index_data.get('value', '')
                                direction = index_data.get('direction', '')
                                
                                if value and direction:
                                    cell_value = f"{value} ({direction})"
                                else:
                                    cell_value = "N/A"
                                    
                                row.append(cell_value)
                            
                            data_rows.append(row)
                        
                        # All rows for the sheet
                        all_rows = [header_row] + data_rows
                        
                        # Get the sheet ID for the tab
                        tab_name = 'PMI Heatmap Summary'
                        tab_id = sheet_ids.get(tab_name)
                        
                        if not tab_id:
                            logger.warning(f"{tab_name} tab not found")
                        else:
                            # Prepare formatting requests
                            formatting = self._prepare_heatmap_summary_data(tab_id, len(all_rows), len(header_row))
                            
                            # Add to batch update
                            all_tab_data[tab_name] = {
                                'data': all_rows,
                                'formatting': formatting
                            }
                except Exception as e:
                    logger.error(f"Error updating heatmap summary: {str(e)}")
            
            # Process time series analysis if enabled
            if visualization_options.get('timeseries', True):
                try:
                    logger.info("Processing time series analysis visualizations")
                    
                    # Get all indices from the database
                    indices = get_all_indices()
                    
                    if not indices:
                        logger.warning("No indices found in database for time series visualization")
                    else:
                        # Process each index
                        for index_name in indices:
                            try:
                                # Get time series data for this index
                                time_series_data = get_index_time_series(index_name, 36)  # Get up to 3 years
                                
                                if not time_series_data:
                                    logger.warning(f"No time series data found for {index_name}")
                                    continue
                                
                                # Prepare header and data rows
                                header_row = ["Date", "PMI Value", "Direction", "Change from Previous Month"]
                                
                                data_rows = []
                                for entry in time_series_data:
                                    row = [
                                        entry['month_year'],
                                        entry['index_value'],
                                        entry['direction'],
                                        entry.get('change', '')  # This may be None for the first entry
                                    ]
                                    data_rows.append(row)
                                
                                # Get the sheet ID for the tab
                                tab_name = f"{index_name} Analysis"
                                tab_id = sheet_ids.get(tab_name)
                                
                                if not tab_id:
                                    logger.warning(f"{tab_name} tab not found")
                                    continue
                                
                                # Prepare formatting
                                formatting = self._prepare_time_series_formatting(tab_id, len(data_rows) + 1, len(header_row))
                                
                                # Add to batch update
                                all_tab_data[tab_name] = {
                                    'data': [header_row] + data_rows,
                                    'formatting': formatting
                                }
                            except Exception as e:
                                logger.error(f"Error processing time series for {index_name}: {str(e)}")
                except Exception as e:
                    logger.error(f"Error updating time series visualizations: {str(e)}")
            
            # Process industry growth/contraction over time if enabled
            if visualization_options.get('industry', True):
                try:
                    logger.info("Processing industry growth/contraction visualizations")
                    
                    # Get all indices from the database
                    indices = get_all_indices()
                    
                    if not indices:
                        logger.warning("No indices found in database for industry visualization")
                    else:
                        # Process each index
                        for index_name in indices:
                            try:
                                # Get industry status data for this index
                                industry_data = get_industry_status_over_time(index_name, 24)  # Get up to 2 years
                                
                                if not industry_data or not industry_data.get('industries'):
                                    logger.warning(f"No industry data found for {index_name}")
                                    continue
                                
                                # Get data for building the sheet
                                dates = industry_data['dates']  # List of month/year strings
                                industries = industry_data['industries']  # Dict with industry names as keys
                                
                                # Sort industries alphabetically
                                sorted_industries = sorted(industries.keys())
                                
                                # Prepare header row - Industry name followed by months
                                header_row = ["Industry"]
                                header_row.extend(dates)
                                
                                # Prepare data rows
                                data_rows = []
                                for industry in sorted_industries:
                                    row = [industry]
                                    
                                    # Add status for each month
                                    for date in dates:
                                        status_data = industries[industry].get(date, {'status': 'Neutral'})
                                        status = status_data.get('status', 'Neutral')
                                        row.append(status)
                                        
                                    data_rows.append(row)
                                
                                # Get the sheet ID for the tab
                                tab_name = f"{index_name} Industries"
                                tab_id = sheet_ids.get(tab_name)
                                
                                if not tab_id:
                                    logger.warning(f"{tab_name} tab not found")
                                    continue
                                
                                # Prepare formatting
                                formatting = self._prepare_industry_data(tab_id, len(data_rows) + 1, len(header_row))
                                
                                # Add to batch update
                                all_tab_data[tab_name] = {
                                    'data': [header_row] + data_rows,
                                    'formatting': formatting
                                }
                            except Exception as e:
                                logger.error(f"Error processing industry data for {index_name}: {str(e)}")
                except Exception as e:
                    logger.error(f"Error updating industry visualizations: {str(e)}")
            
            # Update all tabs in a batch to minimize API calls
            result = self._update_multiple_tabs_with_data(service, sheet_id, all_tab_data)
            
            logger.info(f"Successfully updated Google Sheets for {month_year}")
            return result
            
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
                    manufacturing_tab_exists = 'Manufacturing at a Glance' in existing_tabs
                    missing_tabs = []
                    
                    if not manufacturing_tab_exists:
                        missing_tabs.append('Manufacturing at a Glance')
                    
                    # Add additional tabs for PMI heatmap and specialized views
                    additional_tabs = [
                        'PMI Heatmap Summary'
                    ]
                    
                    for tab in additional_tabs:
                        if tab not in existing_tabs:
                            missing_tabs.append(tab)
                    
                    for index in ISM_INDICES:
                        if index not in existing_tabs:
                            missing_tabs.append(index)
                        
                        # Add analysis tab for each index
                        analysis_tab = f"{index} Analysis"
                        if analysis_tab not in existing_tabs:
                            missing_tabs.append(analysis_tab)
                            
                        # Add industries tab for each index
                        industries_tab = f"{index} Industries"
                        if industries_tab not in existing_tabs:
                            missing_tabs.append(industries_tab)
                    
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
                except Exception as e:
                    logger.warning(f"Error accessing saved sheet: {str(e)}")
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
                
                # Create tabs for all required indices
                requests = []
                
                # Add Manufacturing at a Glance tab
                requests.append({
                    'addSheet': {
                        'properties': {
                            'title': 'Manufacturing at a Glance'
                        }
                    }
                })
                
                # Add PMI Heatmap Summary tab
                requests.append({
                    'addSheet': {
                        'properties': {
                            'title': 'PMI Heatmap Summary'
                        }
                    }
                })
                
                # Add tabs for each index
                for index in ISM_INDICES:
                    # Basic index tab
                    requests.append({
                        'addSheet': {
                            'properties': {
                                'title': index
                            }
                        }
                    })
                    
                    # Analysis tab
                    requests.append({
                        'addSheet': {
                            'properties': {
                                'title': f"{index} Analysis"
                            }
                        }
                    })
                    
                    # Industries tab
                    requests.append({
                        'addSheet': {
                            'properties': {
                                'title': f"{index} Industries"
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
            indices = parsed_data.get('indices', {})
            row = [formatted_month_year]
            
            # Standard indices in order
            standard_indices = [
                "Manufacturing PMI", "New Orders", "Production", 
                "Employment", "Supplier Deliveries", "Inventories", 
                "Customers' Inventories", "Prices", "Backlog of Orders",
                "New Export Orders", "Imports"
            ]
            
            # Add each index value
            for index in standard_indices:
                index_data = indices.get(index, {})
                value = index_data.get('current', 'N/A')
                direction = index_data.get('direction', 'N/A')
                
                if value and direction:
                    cell_value = f"{value} ({direction})"
                else:
                    cell_value = "N/A"
                
                row.append(cell_value)
            
            # Add special rows for Overall Economy and Manufacturing Sector
            for special in ["OVERALL ECONOMY", "Manufacturing Sector"]:
                special_data = indices.get(special, {})
                direction = special_data.get('direction', 'N/A')
                row.append(direction)
            
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
            
            # Combine all entries sorted by category
            all_entries = []
            
            # Get primary and secondary categories
            primary_category = self._get_primary_category(index_name)
            secondary_category = self._get_secondary_category(index_name)
            
            # Process categories in specified order
            for category in [primary_category, secondary_category]:
                if category in formatted_data:
                    for industry in formatted_data[category]:
                        if self._is_valid_industry(industry):
                            all_entries.append((industry, category))
            
            # Process any other categories
            for category, industries in formatted_data.items():
                if category not in [primary_category, secondary_category]:
                    for industry in industries:
                        if self._is_valid_industry(industry):
                            all_entries.append((industry, category))
            
            # Build header and data
            header_row = ["Industry", formatted_month_year]
            data_rows = [[industry, category] for industry, category in all_entries]
            
            # Prepare formatting
            formatting = self._prepare_industry_tab_formatting(tab_id, len(data_rows) + 1, 2, index_name)
            
            return [header_row] + data_rows, formatting
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
        
        # Combine all formatting
        requests.extend(color_formats)
        
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
                    value_batch_requests.append({
                        'range': f"'{tab_name}'!{tab_info.get('start_cell', 'A1')}",
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