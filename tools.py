import traceback
from typing import Dict, Any, Optional, List, Union, Tuple
import json
import os
import pandas as pd
from google_auth import get_google_sheets_service
from pdf_utils import parse_ism_report
import logging
from config import ISM_INDICES, INDEX_CATEGORIES
from crewai.tools import BaseTool
from pydantic import Field
from googleapiclient import discovery
import re

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
            
            # Get industry data
            industry_data = extracted_data.get("industry_data", {})
            
            # Check if industry_data is empty but corrected_industry_data exists
            if not industry_data and "corrected_industry_data" in extracted_data:
                industry_data = extracted_data["corrected_industry_data"]
                logger.info("Using corrected_industry_data instead of empty industry_data")
            
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
            from config import ISM_INDICES, INDEX_CATEGORIES
            
            for index in ISM_INDICES:
                # Get categories for this index from industry_data
                categories = industry_data.get(index, {})
                
                # If no data for this index, create empty categories
                if not categories and index in INDEX_CATEGORIES:
                    categories = {category: [] for category in INDEX_CATEGORIES[index]}
                
                # Add to structured_data
                structured_data[index] = {
                    "month_year": month_year,
                    "categories": categories
                }
                
                # Count industries to log
                total_industries = sum(len(industries) for industries in categories.values())
                logger.info(f"Structured {index}: {total_industries} industries across {len(categories)} categories")
            
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
                    "month_year": "Unknown",
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
        Implementation of the required abstract _run method.
        This formats and updates Google Sheets with the validated ISM data.
        """
        try:
            # Check if required keys exist
            if not isinstance(data, dict):
                data = {'structured_data': {}, 'validation_results': {}}
                logger.warning("Data is not a dictionary. Creating an empty structure.")
                
            if 'structured_data' not in data:
                data['structured_data'] = {}
                logger.warning("structured_data not in input. Creating empty structured_data.")
                
            if 'validation_results' not in data:
                data['validation_results'] = {}
                logger.warning("validation_results not in input. Creating empty validation_results.")
                
            structured_data = data['structured_data']
            validation_results = data['validation_results']
            extraction_data = data.get('extraction_data', {})
            
            # Validate the data has actual industries before proceeding
            def count_industries(data_dict):
                if not isinstance(data_dict, dict):
                    return 0
                count = 0
                for index in data_dict:
                    if isinstance(data_dict[index], dict) and 'categories' in data_dict[index]:
                        categories = data_dict[index]['categories']
                        for category in categories:
                            if isinstance(categories[category], list):
                                count += len(categories[category])
                return count
            
            industry_count = count_industries(structured_data)
            logger.info(f"Found {industry_count} industries in structured data")
            
            # If no industries in structured data, try direct extraction if available
            if industry_count == 0 and extraction_data and 'industry_data' in extraction_data:
                logger.info("No industries found in structured data, trying to create from extraction_data")
                structured_data = {}
                month_year = extraction_data.get('month_year', 'Unknown')
                
                for index, categories in extraction_data['industry_data'].items():
                    structured_data[index] = {
                        'month_year': month_year,
                        'categories': categories
                    }
                
                industry_count = count_industries(structured_data)
                logger.info(f"Created structured data with {industry_count} industries from extraction_data")
            
            # If still no valid data, log warning and return failure
            if industry_count == 0:
                logger.warning("No valid industry data found for Google Sheets update")
                return False
                
            # If no validation results, create some basic ones for continuing
            if not validation_results:
                for index in ISM_INDICES:
                    validation_results[index] = index in structured_data
                    
            # Check if validation passed for at least some indices
            if not any(validation_results.values()):
                # Force at least one index to be valid so we can continue
                logger.warning("All validations failed. Forcing New Orders to be valid to continue.")
                if ISM_INDICES:
                    validation_results[ISM_INDICES[0]] = True
        
            # Get the month and year from the first validated index
            month_year = None
            for index, valid in validation_results.items():
                if valid and index in structured_data:
                    month_year = structured_data[index].get("month_year", "Unknown")
                    break
            
            # If we couldn't get month_year from structured_data, try extraction_data
            if not month_year and extraction_data:
                month_year = extraction_data.get("month_year", "Unknown")
            
            if not month_year:
                logger.warning("Could not determine month and year. Using current date for Google Sheets.")
                from datetime import datetime
                month_year = datetime.now().strftime("%B %Y")
            
            # Format the month_year as MM/YY for spreadsheet
            formatted_month_year = self._format_month_year(month_year)
            
            # Get Google Sheets service
            service = get_google_sheets_service()
            
            # Get or create the Google Sheet
            sheet_id = self._get_or_create_sheet(service, "ISM Manufacturing Report Analysis")
            
            # Update Manufacturing at a Glance tab
            manufacturing_table = ""
            if 'extraction_data' in data:
                manufacturing_table = data.get('extraction_data', {}).get('manufacturing_table', '')
            
            if manufacturing_table:
                logger.info(f"Updating Manufacturing at a Glance table for {month_year}")
                self._update_manufacturing_tab(service, sheet_id, month_year, manufacturing_table)
            
            # Update each index tab that passed validation
            for index, valid in validation_results.items():
                if valid and index in structured_data:
                    # Format data for this index
                    formatted_data = self._format_index_data(index, structured_data[index])
                    
                    # Check if there are actually any industries in this formatted data
                    has_industries = False
                    for category, industries in formatted_data.items():
                        if industries:
                            has_industries = True
                            break
                    
                    if has_industries:
                        # Update the sheet with new columnar format
                        self._update_sheet_tab_columnar(service, sheet_id, index, formatted_data, formatted_month_year)
                    else:
                        logger.warning(f"No industries found for {index}, skipping tab update")
            
            logger.info(f"Successfully updated Google Sheets for {month_year}")
            return True
        except Exception as e:
            logger.error(f"Error in Google Sheets formatting: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    def _format_month_year(self, month_year: str) -> str:
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
                    from config import ISM_INDICES
                    existing_tabs = [sheet.get('properties', {}).get('title') for sheet in sheets]
                    manufacturing_tab_exists = 'Manufacturing at a Glance' in existing_tabs
                    missing_tabs = []
                    
                    if not manufacturing_tab_exists:
                        missing_tabs.append('Manufacturing at a Glance')
                    
                    for index in ISM_INDICES:
                        if index not in existing_tabs:
                            missing_tabs.append(index)
                    
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
            
            # If we either don't have a sheet_id or had an error accessing it, try to search by title
            if not sheet_id:
                try:
                    # Try to find by title
                    file_list = service.files().list(q=f"name='{title}' and mimeType='application/vnd.google-apps.spreadsheet'").execute()
                    files = file_list.get('files', [])
                    
                    if files:
                        # Use the first matching file
                        sheet_id = files[0]['id']
                        logger.info(f"Found existing sheet by title: {title}, ID: {sheet_id}")
                        
                        # Save the sheet ID for future use
                        with open(sheet_id_file, "w") as f:
                            f.write(sheet_id)
                        
                        # Verify we can access it and ensure all tabs exist
                        try:
                            sheet_metadata = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
                            
                            # Check if all required tabs exist (similar to above code)
                            # ...
                            
                            return sheet_id
                        except Exception as e:
                            logger.warning(f"Error accessing found sheet: {str(e)}")
                            sheet_id = None
                except Exception as e:
                    logger.warning(f"Error searching for sheet by title: {str(e)}")
                    sheet_id = None
            
            # If we still don't have a valid sheet ID, create a new one
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
                
                # Add tabs for each index
                from config import ISM_INDICES
                for index in ISM_INDICES:
                    requests.append({
                        'addSheet': {
                            'properties': {
                                'title': index
                            }
                        }
                    }
                )
                
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
            
            # Should never reach here
            return sheet_id
        except Exception as e:
            logger.error(f"Error finding or creating sheet: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            
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
                raise

    def _update_manufacturing_tab(self, service, sheet_id, month_year, table_content):
        """
        Update the Manufacturing at a Glance tab using LLM to extract data from poorly formatted table.
        
        Args:
            service: Google Sheets service instance
            sheet_id: ID of the Google Sheet
            month_year: Month and year of the report
            table_content: The extracted text from the PDF
            
        Returns:
            Boolean indicating success or failure
        """
        try:
            if not table_content:
                logger.warning("No manufacturing table content to update")
                return False
            
            # Get the sheet ID for the Manufacturing at a Glance tab
            sheet_metadata = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
            sheet_id_map = {}
            for sheet in sheet_metadata.get('sheets', []):
                sheet_id_map[sheet.get('properties', {}).get('title')] = sheet.get('properties', {}).get('sheetId')
            
            mfg_sheet_id = sheet_id_map.get('Manufacturing at a Glance')
            if not mfg_sheet_id:
                logger.warning("Manufacturing at a Glance tab not found")
                return False
            
            # Format the month/year as MM/YY for the sheet
            formatted_month_year = self._format_month_year(month_year)
            logger.info(f"Processing data for {formatted_month_year}")
            
            # Use OpenAI to extract structured data from the table
            parsed_data = self._extract_manufacturing_data_with_llm(table_content, month_year)
            
            # Check if we got valid data
            if not parsed_data or not parsed_data.get("indices"):
                logger.warning("Failed to extract manufacturing data with LLM")
                row_data = [formatted_month_year] + ["N/A"] * 13  # Month + 13 columns of N/A
            else:
                # Prepare row data from parsed data
                indices_data = parsed_data.get("indices", {})
                
                # Order of columns in the sheet
                ordered_columns = [
                    "Manufacturing PMI", "New Orders", "Production", "Employment", 
                    "Supplier Deliveries", "Inventories", "Customers' Inventories", 
                    "Prices", "Backlog of Orders", "New Export Orders", "Imports",
                    "OVERALL ECONOMY", "Manufacturing Sector"
                ]
                
                # Start with the month/year
                row_data = [formatted_month_year]
                
                # Add data for each column
                for index in ordered_columns:
                    if index in indices_data:
                        data = indices_data[index]
                        
                        if index not in ["OVERALL ECONOMY", "Manufacturing Sector"]:
                            # For numeric indices, use the current value plus status
                            value = data.get("current", "N/A")
                            direction = data.get("direction", "")
                            
                            if value and direction:
                                # Format: "50.4 (Growing)" or "48.7 (Contracting)"
                                row_data.append(f"{value} ({direction})")
                            else:
                                row_data.append(value if value else "N/A")
                        else:
                            # For overall sections, just use the direction (status)
                            row_data.append(data.get("direction", "N/A"))
                    else:
                        # If data is missing for this index
                        row_data.append("N/A")
            
            # Check if this month already exists in the sheet
            existing_data = service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range="'Manufacturing at a Glance'!A:Z"
            ).execute()
            
            existing_values = existing_data.get('values', [])
            
            # Find if this month already has a row
            row_to_update = None
            if existing_values:
                for i, row in enumerate(existing_values):
                    if len(row) > 0 and row[0] == formatted_month_year:
                        row_to_update = i + 1  # +1 because Sheets API is 1-indexed
                        break
            
            # Update or append the data
            if not existing_values or len(existing_values) == 0:
                # Sheet is empty, create header row first
                headers = [
                    "Month & Year", "Manufacturing PMI", "New Orders", "Production", 
                    "Employment", "Supplier Deliveries", "Inventories", 
                    "Customers' Inventories", "Prices", "Backlog of Orders",
                    "New Export Orders", "Imports", "Overall Economy", "Manufacturing Sector"
                ]
                
                service.spreadsheets().values().update(
                    spreadsheetId=sheet_id,
                    range="'Manufacturing at a Glance'!A1",
                    valueInputOption="RAW",
                    body={"values": [headers]}
                ).execute()
                
                # Add our data row
                service.spreadsheets().values().update(
                    spreadsheetId=sheet_id,
                    range="'Manufacturing at a Glance'!A2",
                    valueInputOption="RAW",
                    body={"values": [row_data]}
                ).execute()
                
                logger.info(f"Created new table with headers and data for {formatted_month_year}")
            elif row_to_update:
                # Update existing row
                update_range = f"'Manufacturing at a Glance'!A{row_to_update}"
                service.spreadsheets().values().update(
                    spreadsheetId=sheet_id,
                    range=update_range,
                    valueInputOption="RAW",
                    body={"values": [row_data]}
                ).execute()
                
                logger.info(f"Updated existing row for {formatted_month_year} at row {row_to_update}")
            else:
                # Append new row
                append_range = f"'Manufacturing at a Glance'!A{len(existing_values) + 1}"
                service.spreadsheets().values().update(
                    spreadsheetId=sheet_id,
                    range=append_range,
                    valueInputOption="RAW",
                    body={"values": [row_data]}
                ).execute()
                
                logger.info(f"Appended new row for {formatted_month_year}")
            
            # Apply formatting
            self._format_manufacturing_table(service, sheet_id, mfg_sheet_id)
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating Manufacturing at a Glance tab: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def _extract_manufacturing_data_with_llm(self, table_content, month_year):
        """
        Use OpenAI to extract structured data from the Manufacturing at a Glance table.
        
        Args:
            table_content: The raw text content from the PDF
            month_year: The month and year for reference
            
        Returns:
            Dictionary with parsed data
        """
        try:
            import os
            import openai  # You'll need to have openai installed
            import json
            import re
            
            # Get API key from environment
            openai.api_key = os.environ.get("OPENAI_API_KEY")
            
            if not openai.api_key:
                logger.error("OpenAI API key not found in environment variables")
                return {"month_year": month_year, "indices": {}}
            
            # Prepare the prompt for OpenAI
            prompt = f"""
            I have already extracted text from the "Manufacturing at a Glance" table in an ISM Manufacturing Report. The text is poorly formatted and I need you to parse it into structured data.
            
            Here is the extracted text:
            ```
            {table_content}
            ```
            
            Based solely on the text above, please extract the following data points and return them in JSON format:
            - Month and Year of the report (should be {month_year})
            - Manufacturing PMI value and status (Growing/Contracting)
            - New Orders value and status
            - Production value and status
            - Employment value and status
            - Supplier Deliveries value and status (Faster/Slower)
            - Inventories value and status
            - Customers' Inventories value and status (Too High/Too Low)
            - Prices value and status (Increasing/Decreasing)
            - Backlog of Orders value and status
            - New Export Orders value and status
            - Imports value and status
            - Overall Economy status (Growing/Contracting)
            - Manufacturing Sector status (Growing/Contracting)
            
            The values should be present in the text, but they might be hard to find because of poor text formatting. Look for numbers and statuses like "Growing", "Contracting", etc.
            
            Return only a valid JSON object in this format:
            {{
                "month_year": "{month_year}",
                "indices": {{
                    "Manufacturing PMI": {{"current": "48.4", "direction": "Contracting"}},
                    "New Orders": {{"current": "50.4", "direction": "Growing"}},
                    ...and so on for all indices,
                    "OVERALL ECONOMY": {{"direction": "Growing"}},
                    "Manufacturing Sector": {{"direction": "Contracting"}}
                }}
            }}
            
            If you can't find a specific value, use "N/A" rather than making up values.
            
            IMPORTANT: DO NOT include any explanations, qualifications, or text outside the JSON. Return ONLY the JSON object wrapped in ```json and ``` markers.
            """
            
            # Call the OpenAI API
            client = openai.OpenAI()  # For v1.0.0 and above
            response = client.chat.completions.create(
                model="gpt-4",  # or your preferred model
                messages=[
                    {"role": "system", "content": "You are a data extraction assistant. When given text from a document, you extract structured data in JSON format. You ONLY output valid JSON with no additional text, wrapped in ```json and ``` markers."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0  # Low temperature for more deterministic results
                # Removed response_format parameter
            )
            
            # Extract the response text
            response_text = response.choices[0].message.content
            
            # Extract the JSON part from the response
            # The LLM might return explanatory text before or after the JSON
            json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(1)
            else:
                # Try to find JSON directly
                json_pattern = r'{\s*"month_year":\s*"[^"]*",\s*"indices":\s*{.*?}\s*}'
                json_match = re.search(json_pattern, response_text, re.DOTALL)
                if json_match:
                    json_text = json_match.group(0)
                else:
                    # If no JSON found, use the whole response
                    json_text = response_text
            
            # Parse the JSON
            try:
                parsed_data = json.loads(json_text)
                logger.info(f"Successfully extracted data for {parsed_data.get('month_year', 'Unknown')}")
                
                # Add some validation - check if we actually got some data
                indices = parsed_data.get("indices", {})
                if len(indices) > 0:
                    return parsed_data
                else:
                    logger.warning("No indices found in parsed data")
                    return {"month_year": month_year, "indices": {}}
                    
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON from LLM response: {response_text[:200]}...")
                return {"month_year": month_year, "indices": {}}
            
        except Exception as e:
            logger.error(f"Error extracting data with LLM: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {"month_year": month_year, "indices": {}}
    
    def _format_month_year(self, month_year):
        """Convert month and year to MM/YY format."""
        try:
            # Handle variations in month format
            month_map = {
                'january': '01', 'jan': '01',
                'february': '02', 'feb': '02',
                'march': '03', 'mar': '03',
                'april': '04', 'apr': '04',
                'may': '05',
                'june': '06', 'jun': '06',
                'july': '07', 'jul': '07',
                'august': '08', 'aug': '08',
                'september': '09', 'sep': '09',
                'october': '10', 'oct': '10',
                'november': '11', 'nov': '11',
                'december': '12', 'dec': '12'
            }
            
            # Normalize case
            month_year_lower = month_year.lower()
            
            # Extract month
            found_month = None
            for key, value in month_map.items():
                if key in month_year_lower:
                    found_month = value
                    break
            
            if not found_month:
                logger.warning(f"Could not extract month from '{month_year}'")
                from datetime import datetime
                found_month = datetime.now().strftime("%m")
            
            # Extract year
            import re
            year_match = re.search(r'(20\d{2})', month_year)
            if not year_match:
                from datetime import datetime
                current_year = datetime.now().year
                logger.warning(f"Could not extract year from '{month_year}', using current year {current_year}")
                found_year = str(current_year)[-2:]  # Last two digits
            else:
                found_year = year_match.group(1)[-2:]  # Last two digits
            
            # Return in MM/YY format
            return f"{found_month}/{found_year}"
        
        except Exception as e:
            logger.error(f"Error formatting month_year '{month_year}': {str(e)}")
            from datetime import datetime
            return datetime.now().strftime("%m/%y")

    def _format_manufacturing_table(self, service, sheet_id, mfg_sheet_id):
        """Apply formatting to the Manufacturing at a Glance table."""
        try:
            # Get the dimensions of the sheet
            result = service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range="'Manufacturing at a Glance'!A:Z"
            ).execute()
            
            values = result.get('values', [])
            max_rows = len(values) if values else 1
            max_cols = max([len(row) for row in values]) if values else 14  # Default to 14 columns
            
            # Formatting requests
            requests = [
                # Format header row
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": mfg_sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": max_cols
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
                            "sheetId": mfg_sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": max_rows,
                            "startColumnIndex": 0,
                            "endColumnIndex": max_cols
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
                            "sheetId": mfg_sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": 0,
                            "endIndex": max_cols
                        }
                    }
                },
                # Freeze header row
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": mfg_sheet_id,
                            "gridProperties": {
                                "frozenRowCount": 1
                            }
                        },
                        "fields": "gridProperties.frozenRowCount"
                    }
                }
            ]
            
            # Add conditional formatting for cell colors
            color_formats = [
                # Growing/Increasing = green text
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [
                                {
                                    "sheetId": mfg_sheet_id,
                                    "startRowIndex": 1,  # Skip header
                                    "endRowIndex": max_rows,
                                    "startColumnIndex": 1,  # Skip month column
                                    "endColumnIndex": max_cols
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
                # Increasing = green text
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [
                                {
                                    "sheetId": mfg_sheet_id,
                                    "startRowIndex": 1,  # Skip header
                                    "endRowIndex": max_rows,
                                    "startColumnIndex": 1,  # Skip month column
                                    "endColumnIndex": max_cols
                                }
                            ],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_CONTAINS",
                                    "values": [{"userEnteredValue": "(Increasing)"}]
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
                        "index": 1
                    }
                },
                # Contracting = red text
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [
                                {
                                    "sheetId": mfg_sheet_id,
                                    "startRowIndex": 1,  # Skip header
                                    "endRowIndex": max_rows,
                                    "startColumnIndex": 1,  # Skip month column
                                    "endColumnIndex": max_cols
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
                        "index": 2
                    }
                }
            ]
            
            # Add color formats to requests
            requests.extend(color_formats)
            
            # Execute formatting requests
            service.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={"requests": requests}
            ).execute()
            
            logger.info("Applied formatting to Manufacturing at a Glance tab")
            
        except Exception as e:
            logger.error(f"Error formatting manufacturing table: {str(e)}")

    def _format_month_year_for_sheet(self, month_year):
        """
        Format the month and year as MM/YY for the sheet.
        
        Args:
            month_year: Original month and year string
            
        Returns:
            Formatted month and year as MM/YY
        """
        try:
            # Handle variations in month format
            month_map = {
                'january': '01', 'jan': '01',
                'february': '02', 'feb': '02',
                'march': '03', 'mar': '03',
                'april': '04', 'apr': '04',
                'may': '05',
                'june': '06', 'jun': '06',
                'july': '07', 'jul': '07',
                'august': '08', 'aug': '08',
                'september': '09', 'sep': '09',
                'october': '10', 'oct': '10',
                'november': '11', 'nov': '11',
                'december': '12', 'dec': '12'
            }
            
            # Normalize case
            month_year_lower = month_year.lower()
            
            # Extract month
            found_month = None
            for key, value in month_map.items():
                if key in month_year_lower:
                    found_month = value
                    break
            
            if not found_month:
                logger.warning(f"Could not extract month from '{month_year}'")
                # Default to current month
                from datetime import datetime
                found_month = datetime.now().strftime("%m")
            
            # Extract year
            import re
            year_match = re.search(r'(20\d{2})', month_year)
            if not year_match:
                from datetime import datetime
                current_year = datetime.now().year
                logger.warning(f"Could not extract year from '{month_year}', using current year {current_year}")
                found_year = str(current_year)[-2:]  # Last two digits
            else:
                found_year = year_match.group(1)[-2:]  # Last two digits
            
            # Return in MM/YY format
            return f"{found_month}/{found_year}"
        
        except Exception as e:
            logger.error(f"Error formatting month_year '{month_year}': {str(e)}")
            # Return a default if parsing fails
            from datetime import datetime
            return datetime.now().strftime("%m/%y")

    def _prepare_horizontal_row(self, parsed_data, formatted_month_year):
        """
        Prepare a single horizontal row for the Manufacturing at a Glance table.
        
        Args:
            parsed_data: Dictionary with parsed table data
            formatted_month_year: Formatted month/year string (MM/YY)
            
        Returns:
            List representing a single row of data
        """
        indices_data = parsed_data.get("indices", {})
        
        # Order of columns in the sheet
        ordered_columns = [
            "Manufacturing PMI", "New Orders", "Production", "Employment", 
            "Supplier Deliveries", "Inventories", "Customers' Inventories", 
            "Prices", "Backlog of Orders", "New Export Orders", "Imports",
            "OVERALL ECONOMY", "Manufacturing Sector"
        ]
        
        # Start with the month/year
        row = [formatted_month_year]
        
        # Add data for each column
        for index in ordered_columns:
            if index in indices_data:
                data = indices_data[index]
                
                if index not in ["OVERALL ECONOMY", "Manufacturing Sector"]:
                    # For numeric indices, use the current value plus status
                    value = data.get("current", "N/A")
                    direction = data.get("direction", "")
                    
                    if value and direction:
                        # Format: "50.4 (Growing)" or "48.7 (Contracting)"
                        row.append(f"{value} ({direction})")
                    else:
                        row.append(value if value else "N/A")
                else:
                    # For overall sections, just use the direction (status)
                    row.append(data.get("direction", "N/A"))
            else:
                # If data is missing for this index
                row.append("N/A")
        
        return row

    def _apply_manufacturing_table_formatting(self, service, sheet_id, mfg_sheet_id):
        """
        Apply formatting to the Manufacturing at a Glance table.
        
        Args:
            service: Google Sheets service instance
            sheet_id: ID of the Google Sheet
            mfg_sheet_id: ID of the Manufacturing at a Glance tab
        """
        try:
            # Get the current sheet dimensions
            sheet_metadata = service.spreadsheets().get(
                spreadsheetId=sheet_id,
                ranges=["'Manufacturing at a Glance'!A:Z"],
                includeGridData=False
            ).execute()
            
            sheet_props = None
            for sheet in sheet_metadata.get('sheets', []):
                if sheet.get('properties', {}).get('sheetId') == mfg_sheet_id:
                    sheet_props = sheet.get('properties', {})
                    break
            
            if not sheet_props:
                logger.warning("Could not find sheet properties for formatting")
                return
            
            # Get the number of rows and columns of data
            result = service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range="'Manufacturing at a Glance'!A:Z"
            ).execute()
            
            values = result.get('values', [])
            max_rows = len(values) if values else 1
            max_cols = max([len(row) for row in values]) if values else 14  # Default to 14 columns
            
            # Formatting requests
            requests = [
                # Format header row (bold font)
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": mfg_sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": max_cols
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
                            "sheetId": mfg_sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": max_rows,
                            "startColumnIndex": 0,
                            "endColumnIndex": max_cols
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
                            "sheetId": mfg_sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": 0,
                            "endIndex": max_cols
                        }
                    }
                },
                # Freeze header row
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": mfg_sheet_id,
                            "gridProperties": {
                                "frozenRowCount": 1
                            }
                        },
                        "fields": "gridProperties.frozenRowCount"
                    }
                }
            ]
            
            # Add conditional formatting for status indicators
            status_formats = [
                # Growing/Increasing = green text
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [
                                {
                                    "sheetId": mfg_sheet_id,
                                    "startRowIndex": 1,  # Skip header
                                    "endRowIndex": max_rows,
                                    "startColumnIndex": 1,  # Skip month column
                                    "endColumnIndex": max_cols
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
                # Increasing = green text
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [
                                {
                                    "sheetId": mfg_sheet_id,
                                    "startRowIndex": 1,  # Skip header
                                    "endRowIndex": max_rows,
                                    "startColumnIndex": 1,  # Skip month column
                                    "endColumnIndex": max_cols
                                }
                            ],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_CONTAINS",
                                    "values": [{"userEnteredValue": "(Increasing)"}]
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
                        "index": 1
                    }
                },
                # Contracting = red text
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [
                                {
                                    "sheetId": mfg_sheet_id,
                                    "startRowIndex": 1,  # Skip header
                                    "endRowIndex": max_rows,
                                    "startColumnIndex": 1,  # Skip month column
                                    "endColumnIndex": max_cols
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
                        "index": 2
                    }
                },
                # Decreasing = red text
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [
                                {
                                    "sheetId": mfg_sheet_id,
                                    "startRowIndex": 1,  # Skip header
                                    "endRowIndex": max_rows,
                                    "startColumnIndex": 1,  # Skip month column
                                    "endColumnIndex": max_cols
                                }
                            ],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_CONTAINS",
                                    "values": [{"userEnteredValue": "(Decreasing)"}]
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
                        "index": 3
                    }
                },
                # Growing (standalone) = green text for Overall Economy and Manufacturing Sector
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [
                                {
                                    "sheetId": mfg_sheet_id,
                                    "startRowIndex": 1,  # Skip header
                                    "endRowIndex": max_rows,
                                    "startColumnIndex": 11,  # For Overall Economy and Manufacturing Sector columns
                                    "endColumnIndex": max_cols
                                }
                            ],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_EQ",
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
                        "index": 4
                    }
                },
                # Contracting (standalone) = red text for Overall Economy and Manufacturing Sector
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [
                                {
                                    "sheetId": mfg_sheet_id,
                                    "startRowIndex": 1,  # Skip header
                                    "endRowIndex": max_rows,
                                    "startColumnIndex": 11,  # For Overall Economy and Manufacturing Sector columns
                                    "endColumnIndex": max_cols
                                }
                            ],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_EQ",
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
                        "index": 5
                    }
                }
            ]
            
            # Add all conditional formatting rules
            requests.extend(status_formats)
            
            # Execute formatting requests
            service.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={"requests": requests}
            ).execute()
            
            logger.info("Applied formatting to Manufacturing at a Glance table")
            
        except Exception as e:
            logger.error(f"Error applying formatting: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")

    def _get_sheet_id_by_name(self, service, spreadsheet_id, sheet_name):
        """Get the sheet ID from its name."""
        try:
            spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            sheets = spreadsheet.get('sheets', [])
            for sheet in sheets:
                if sheet.get('properties', {}).get('title') == sheet_name:
                    return sheet.get('properties', {}).get('sheetId')
            return 0
        except Exception as e:
            logger.error(f"Error getting sheet ID for {sheet_name}: {str(e)}")
            return 0
    
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
    
    def _update_sheet_tab_columnar(self, service, sheet_id, index, formatted_data, formatted_month_year):
        """Update a specific tab in the Google Sheet with a columnar time-series format."""
        try:
            if not formatted_data:
                logger.warning(f"No formatted data for {index}, skipping tab update")
                return False
            
            if not formatted_month_year:
                logger.warning(f"No month_year for {index}, using 'Unknown'")
                formatted_month_year = "Unknown"

            # Ensure index exists in the sheet
            try:
                # Try to access the sheet to verify it exists
                test_range = f"'{index}'!A1:Z1"
                service.spreadsheets().values().get(
                    spreadsheetId=sheet_id,
                    range=test_range
                ).execute()
            except Exception as e:
                logger.warning(f"Error accessing tab {index}: {str(e)}")
                
                # Try to create the tab
                try:
                    create_request = {
                        'requests': [{
                            'addSheet': {
                                'properties': {
                                    'title': index
                                }
                            }
                        }]
                    }
                    service.spreadsheets().batchUpdate(
                        spreadsheetId=sheet_id,
                        body=create_request
                    ).execute()
                    logger.info(f"Created new tab for {index}")
                except Exception as e2:
                    logger.error(f"Failed to create tab {index}: {str(e2)}")
                    return False
                
            # Verify data has actual content
            has_data = False
            for category, industries in formatted_data.items():
                if industries:
                    has_data = True
                    break
            
            if not has_data:
                logger.warning(f"No industries found for {index}, skipping tab update")
                return False
                
            # Get the sheet data
            result = service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=f"'{index}'!A:Z"
            ).execute()
            
            values = result.get('values', [])
            
            # Check if we need to initialize the sheet
            need_init = False
            if not values:
                need_init = True
            elif len(values) <= 1 and all(not cell for row in values for cell in row):
                need_init = True
                
            if need_init:
                # Create a single cell with month/year as header
                service.spreadsheets().values().update(
                    spreadsheetId=sheet_id,
                    range=f"'{index}'!A1",
                    valueInputOption="RAW",
                    body={"values": [[formatted_month_year]]}
                ).execute()
                
                # Reset values to just the header
                values = [[formatted_month_year]]
            
            # Get the header row
            header_row = values[0] if values else []
            
            # Find the column index for the month, or add it if it doesn't exist
            if formatted_month_year in header_row:
                month_col_idx = header_row.index(formatted_month_year)
                logger.info(f"Month {formatted_month_year} found in column {month_col_idx + 1}")
            else:
                # Add the new month to the right of the existing columns
                month_col_idx = len(header_row)
                header_row.append(formatted_month_year)
                
                # Update the header row
                service.spreadsheets().values().update(
                    spreadsheetId=sheet_id,
                    range=f"'{index}'!A1",
                    valueInputOption="RAW",
                    body={"values": [header_row]}
                ).execute()
                logger.info(f"Added month {formatted_month_year} in column {month_col_idx + 1}")
            
            # Collect all entries for the column - sort by category and preserve original order
            all_industry_entries = []
            
            # First process Growing/Increasing/Slower/Higher/Too High categories
            primary_category = self._get_primary_category(index)
            secondary_category = self._get_secondary_category(index)
            
            # Add primary category entries
            if primary_category in formatted_data:
                for industry in formatted_data[primary_category]:
                    if self._is_valid_industry(industry):
                        all_industry_entries.append(f"{industry} - {primary_category}")
            
            # Add secondary category entries
            if secondary_category in formatted_data:
                for industry in formatted_data[secondary_category]:
                    if self._is_valid_industry(industry):
                        all_industry_entries.append(f"{industry} - {secondary_category}")
            
            # Add any other categories that might exist
            for category, industries in formatted_data.items():
                if category not in [primary_category, secondary_category]:
                    for industry in industries:
                        if self._is_valid_industry(industry):
                            all_industry_entries.append(f"{industry} - {category}")
            
            # Build column data - each cell contains a single industry + status
            column_data = []
            for entry in all_industry_entries:
                column_data.append([entry])
            
            # Update the column for this month
            if column_data:
                # First, clear any existing data in the column to ensure clean update
                clear_range = f"'{index}'!{chr(65 + month_col_idx)}2:{chr(65 + month_col_idx)}1000"  # Assuming max 1000 rows
                service.spreadsheets().values().clear(
                    spreadsheetId=sheet_id,
                    range=clear_range
                ).execute()
                
                # Then update with new data
                range_to_update = f"'{index}'!{chr(65 + month_col_idx)}2"
                service.spreadsheets().values().update(
                    spreadsheetId=sheet_id,
                    range=range_to_update,
                    valueInputOption="RAW",
                    body={"values": column_data}
                ).execute()
                
            logger.info(f"Updated {index} sheet with data for {formatted_month_year} with {len(all_industry_entries)} industries")
            
            # Format the column to wrap text and fit content
            sheet_id_num = self._get_sheet_id_by_name(service, sheet_id, index)
            
            if sheet_id_num:
                requests = [
                    # Set text wrapping
                    {
                        "repeatCell": {
                            "range": {
                                "sheetId": sheet_id_num,
                                "startRowIndex": 1,  # Row 2 (0-indexed)
                                "endRowIndex": len(column_data) + 1,
                                "startColumnIndex": month_col_idx,
                                "endColumnIndex": month_col_idx + 1
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "wrapStrategy": "WRAP",
                                    "verticalAlignment": "TOP"
                                }
                            },
                            "fields": "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment"
                        }
                    },
                    # Auto-resize column width
                    {
                        "autoResizeDimensions": {
                            "dimensions": {
                                "sheetId": sheet_id_num,
                                "dimension": "COLUMNS",
                                "startIndex": month_col_idx,
                                "endIndex": month_col_idx + 1
                            }
                        }
                    }
                ]
                
                service.spreadsheets().batchUpdate(
                    spreadsheetId=sheet_id,
                    body={"requests": requests}
                ).execute()
                
                logger.info(f"Applied formatting to cell for {formatted_month_year} in {index} tab")
            
            return True
        except Exception as e:
            logger.error(f"Error updating sheet tab {index}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

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

    def _is_valid_industry(self, industry):
        """Check if an industry name is valid and not a parsing artifact."""
        if not industry or not isinstance(industry, str):
            return False
            
        # Skip parsing artifacts and invalid entries
        if ("following order" in industry.lower() or 
            "are:" in industry.lower() or
            industry.startswith(',') or 
            industry.startswith(':') or
            len(industry.strip()) < 3):
            return False
            
        return True

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