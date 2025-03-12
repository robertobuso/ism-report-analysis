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
    
    def _run(self, pdf_path: str) -> Dict[str, Any]:
        """
        Implementation of the required abstract _run method.
        This extracts data from the ISM Manufacturing Report PDF.
        """
        try:
            logger.info(f"PDF Extraction Tool using pdf_path: {pdf_path}")
            
            # Parse the ISM report
            extracted_data = parse_ism_report(pdf_path)
            if not extracted_data:
                raise Exception(f"Failed to extract data from {pdf_path}")
            
            logger.info(f"Successfully extracted data from {pdf_path}")
            return extracted_data
        except Exception as e:
            logger.error(f"Error in PDF extraction: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

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
                
                # Log the number of industries found for this index
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
                    
                    # Check if the required categories exist for this index
                    if index in INDEX_CATEGORIES:
                        expected_categories = INDEX_CATEGORIES[index]
                        validation_results[index] = all(category in categories for category in expected_categories)
                    else:
                        # For indices without predefined categories, check if any categories exist
                        validation_results[index] = len(categories) > 0
                    
                    if not validation_results[index]:
                        logger.warning(f"Missing or invalid categories for {index}")
                    
                    # Additional validation: check if industries were found
                    if validation_results[index]:
                        has_industries = False
                        for category, industries in categories.items():
                            if industries:  # If there's at least one industry
                                has_industries = True
                                break
                        
                        if not has_industries:
                            validation_results[index] = False
                            logger.warning(f"No industries found for any category in {index}")
            
            return validation_results
        except Exception as e:
            logger.error(f"Error in data validation: {str(e)}")
            raise

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
            if not isinstance(data, dict) or 'structured_data' not in data or 'validation_results' not in data:
                raise ValueError("Input must include structured_data and validation_results")
                
            structured_data = data['structured_data']
            validation_results = data['validation_results']
            extraction_data = data.get('extraction_data', {})
            
            if not structured_data:
                raise ValueError("Structured data not provided")
            
            if not validation_results:
                raise ValueError("Validation results not provided")
                
            # Check if validation passed for at least some indices
            if not any(validation_results.values()):
                logger.warning("All validations failed. Not updating Google Sheets.")
                return False
            
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
                logger.warning("Could not determine month and year. Not updating Google Sheets.")
                return False
            
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
                    
                    # Update the sheet
                    self._update_sheet_tab(service, sheet_id, index, formatted_data, month_year)
            
            logger.info(f"Successfully updated Google Sheets for {month_year}")
            return True
        except Exception as e:
            logger.error(f"Error in Google Sheets formatting: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    def _get_or_create_sheet(self, service, title):
        """Get an existing sheet or create a new one."""
        try:
            # First check if a saved sheet ID exists in sheet_id.txt
            sheet_id = None
            if os.path.exists("sheet_id.txt"):
                with open("sheet_id.txt", "r") as f:
                    sheet_id = f.read().strip()
                    logger.info(f"Found saved sheet ID: {sheet_id}")
                
                # Verify the sheet exists and is accessible
                try:
                    sheet_metadata = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
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
        """Update the Manufacturing at a Glance table with the table content."""
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
            
            # Clear the existing content
            service.spreadsheets().values().clear(
                spreadsheetId=sheet_id,
                range="'Manufacturing at a Glance'!A:Z"
            ).execute()
            
            # Parse the table content to extract structured data
            # Extract index names, values, and directions from the table content
            indices = []
            
            # Try to parse the table using regex
            table_rows = []
            
            # Initialize with a title row
            title_row = [f"Manufacturing at a Glance - {month_year}"]
            table_rows.append(title_row)
            
            # Add header row
            header_row = ["Index", "Current", "Previous", "Change", "Direction", "Rate of Change", "Trend (Months)"]
            table_rows.append(header_row)
            
            # Extract rows for main indices
            main_indices = [
                "PMI", "New Orders", "Production", "Employment", "Supplier Deliveries",
                "Inventories", "Customers' Inventories", "Prices", "Backlog of Orders",
                "New Export Orders", "Imports"
            ]
            
            # Extract data for overall sections
            overall_indices = [
                "OVERALL ECONOMY", "Manufacturing Sector"
            ]
            
            # Function to extract values for an index
            def extract_index_values(index_name):
                # Match patterns like "PMI 50.3 50.9 -0.6 Growing Slower 2"
                # or different variations of the pattern
                patterns = [
                    rf"{re.escape(index_name)}\s+(\d+\.\d+)\s+(\d+\.\d+)\s+([+-]\d+\.\d+)\s+(\w+)\s+(\w+)\s+(\d+)",
                    rf"{re.escape(index_name)}\s+(\d+\.\d+)\s+(\d+\.\d+)\s+([+-]\d+\.\d+)\s+(\w+)\s+(\w+)",
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, table_content, re.IGNORECASE)
                    if match:
                        if len(match.groups()) >= 5:
                            return [
                                index_name,
                                match.group(1),
                                match.group(2),
                                match.group(3),
                                match.group(4),
                                match.group(5),
                                match.group(6) if len(match.groups()) >= 6 else ""
                            ]
                return None
            
            # Extract data for main indices
            for index in main_indices:
                row_data = extract_index_values(index)
                if row_data:
                    table_rows.append(row_data)
                else:
                    # Add empty row if data couldn't be extracted
                    table_rows.append([index, "", "", "", "", "", ""])
            
            # Add a blank row
            table_rows.append([""])
            
            # Extract data for overall sections
            for index in overall_indices:
                row_data = extract_index_values(index)
                if row_data:
                    table_rows.append(row_data)
                else:
                    # Add empty row if data couldn't be extracted
                    table_rows.append([index, "", "", "", "", "", ""])
            
            # Update the sheet with the table data
            service.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range="'Manufacturing at a Glance'!A1",
                valueInputOption="RAW",
                body={"values": table_rows}
            ).execute()
            
            # Apply formatting (bold headers, borders, etc.)
            requests = [
                # Bold the title and header rows
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": mfg_sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": 2,
                            "startColumnIndex": 0,
                            "endColumnIndex": 7
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
                },
                # Add borders
                {
                    "updateBorders": {
                        "range": {
                            "sheetId": mfg_sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": len(table_rows),
                            "startColumnIndex": 0,
                            "endColumnIndex": 7
                        },
                        "top": {"style": "SOLID"},
                        "bottom": {"style": "SOLID"},
                        "left": {"style": "SOLID"},
                        "right": {"style": "SOLID"},
                        "innerHorizontal": {"style": "SOLID"},
                        "innerVertical": {"style": "SOLID"}
                    }
                }
            ]
            
            # Execute formatting requests
            service.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={"requests": requests}
            ).execute()
            
            # Auto-resize columns to fit content
            auto_resize_request = {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": mfg_sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": 7
                    }
                }
            }
            
            service.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={"requests": [auto_resize_request]}
            ).execute()
            
            logger.info("Successfully updated Manufacturing at a Glance tab")
            return True
        except Exception as e:
            logger.error(f"Error updating Manufacturing at a Glance tab: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
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
            
            # Ensure all expected categories exist
            if index in INDEX_CATEGORIES:
                formatted_data = {}
                for category in INDEX_CATEGORIES[index]:
                    formatted_data[category] = categories.get(category, [])
                return formatted_data
            else:
                return categories
        except Exception as e:
            logger.error(f"Error formatting index data for {index}: {str(e)}")
            # Return empty dictionary as fallback
            if index in INDEX_CATEGORIES:
                return {category: [] for category in INDEX_CATEGORIES[index]}
            return {}
    
    def _update_sheet_tab(self, service, sheet_id, index, formatted_data, month_year):
        """Update a specific tab in the Google Sheet."""
        try:
            if not formatted_data:
                logger.warning(f"No formatted data for {index}, skipping tab update")
                return False
                
            # Get the sheet data
            result = service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=f"'{index}'!A:Z"
            ).execute()
            
            values = result.get('values', [])
            
            # Check if header row exists
            if not values or len(values) == 0:
                # Create header row with months
                header_row = ["Industry", month_year]
                new_values = [header_row]
                
                # Add data rows
                all_industries = []
                for category, industries in formatted_data.items():
                    for industry in industries:
                        if industry and industry not in all_industries:
                            all_industries.append(industry)
                            new_values.append([industry, category])
                
                # Update the sheet
                if len(new_values) > 1:  # Only update if we have actual data
                    service.spreadsheets().values().update(
                        spreadsheetId=sheet_id,
                        range=f"'{index}'!A1",
                        valueInputOption="RAW",
                        body={"values": new_values}
                    ).execute()
                    logger.info(f"Created new tab for {index} with {len(new_values)-1} industries")
                else:
                    logger.warning(f"No industries found for {index}, skipping tab creation")
            else:
                # Get existing industries and header row
                header_row = values[0] if values else ["Industry"]
                existing_industries = {}
                
                for i, row in enumerate(values[1:], 1):
                    if row and len(row) > 0:
                        existing_industries[row[0]] = i + 1  # +1 for 1-indexing in sheets
                
                # Check if month already exists in header
                if month_year in header_row:
                    month_col = header_row.index(month_year)
                    logger.info(f"Month {month_year} already exists in {index} tab at column {month_col}")
                else:
                    # Add new month to header
                    month_col = len(header_row)
                    header_row.append(month_year)
                    
                    # Update header row
                    service.spreadsheets().values().update(
                        spreadsheetId=sheet_id,
                        range=f"'{index}'!A1",
                        valueInputOption="RAW",
                        body={"values": [header_row]}
                    ).execute()
                    logger.info(f"Added month {month_year} to {index} tab header")
                
                # Update industry data
                batch_updates = []
                new_industries = []
                
                # Collect all industries from all categories
                for category, industries in formatted_data.items():
                    for industry in industries:
                        if not industry:  # Skip empty industries
                            continue
                            
                        if industry in existing_industries:
                            # Update existing industry
                            row_index = existing_industries[industry]
                            batch_updates.append({
                                "range": f"'{index}'!{chr(65 + month_col)}{row_index}",
                                "values": [[category]]
                            })
                        else:
                            # Add to list of new industries
                            new_industries.append((industry, category))
                
                # Execute batch update for existing industries
                if batch_updates:
                    service.spreadsheets().values().batchUpdate(
                        spreadsheetId=sheet_id,
                        body={
                            "valueInputOption": "RAW",
                            "data": batch_updates
                        }
                    ).execute()
                    logger.info(f"Updated {len(batch_updates)} existing industries in {index} tab")
                
                # Add new industries
                if new_industries:
                    new_rows = []
                    for industry, category in new_industries:
                        # Create a new row with empty cells up to the month column
                        new_row = [industry] + [""] * (month_col - 1) + [category]
                        new_rows.append(new_row)
                    
                    # Append the new rows to the sheet
                    service.spreadsheets().values().append(
                        spreadsheetId=sheet_id,
                        range=f"'{index}'!A{len(values) + 1}",
                        valueInputOption="RAW",
                        body={"values": new_rows}
                    ).execute()
                    logger.info(f"Added {len(new_industries)} new industries to {index} tab")
            
            return True
        
        except Exception as e:
            logger.error(f"Error updating sheet tab {index}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
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