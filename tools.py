import traceback
from crewai.tools import BaseTool
from typing import Dict, Any, Optional, List, Union, Tuple
import json
import os
import pandas as pd
from google_auth import get_google_sheets_service
from pdf_utils import parse_ism_report
import logging
from config import ISM_INDICES, INDEX_CATEGORIES

# Create logs directory first
os.makedirs("logs", exist_ok=True)

logger = logging.getLogger(__name__)

class SimplePDFExtractionTool(BaseTool):
    name: str = "PDF Extraction Tool"
    description: str = "Extracts ISM Manufacturing Report data from a PDF file"
    
    def _run(self, tool_input: str = None) -> Dict[str, Any]:
        """
        Extract data from an ISM Manufacturing Report PDF.
        
        Args:
            tool_input (str): Path to the PDF file or JSON string with "pdf_path" key
            
        Returns:
            dict: Extracted data from the PDF
        """
        try:
            # Try to parse the input as a path directly
            pdf_path = tool_input
            
            # If it looks like a JSON string, try to parse it
            if tool_input and (tool_input.startswith('{') or tool_input.startswith('[')):
                try:
                    parsed_input = json.loads(tool_input)
                    if isinstance(parsed_input, dict) and 'pdf_path' in parsed_input:
                        pdf_path = parsed_input['pdf_path']
                except json.JSONDecodeError:
                    # Not JSON, treat as a string path
                    pass
            
            logger.info(f"PDF Extraction Tool using pdf_path: {pdf_path}")
            
            if not pdf_path:
                raise ValueError("PDF path not provided")
            
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
    name: str = "Data Structurer Tool"
    description: str = "Structures extracted ISM data into a consistent format"
    
    def _run(self, tool_input: Union[Dict[str, Any], str]) -> Dict[str, Any]:
        """
        Structure the extracted data into a format suitable for Google Sheets.
        
        Args:
            tool_input: Either the extracted data dict or a JSON string
            
        Returns:
            dict: Structured data ready for validation
        """
        try:
            # Parse input if it's a string
            if isinstance(tool_input, str):
                try:
                    extracted_data = json.loads(tool_input)
                except json.JSONDecodeError:
                    raise ValueError("Invalid JSON input for data structuring")
            else:
                extracted_data = tool_input
            
            logger.info("Data Structurer Tool received input")
            
            # Get month and year
            month_year = extracted_data.get("month_year", "Unknown")
            
            # Get industry data
            industry_data = extracted_data.get("industry_data", {})
            
            # Structure data for each index
            structured_data = {}
            
            for index, data in industry_data.items():
                # Logic for structuring data (same as before)
                # ...
                
                # Create data structure for this index
                structured_data[index] = {
                    "month_year": month_year,
                    "categories": data  # Simplified for this example
                }
            
            return structured_data
        except Exception as e:
            logger.error(f"Error in data structuring: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

class DataValidatorTool(BaseTool):
    name: str = "Data Validator Tool"
    description: str = "Validates structured ISM data for accuracy and completeness"
    
    def _run(self, structured_data=None, context=None):
        """Validate the structured data for consistency and completeness."""
        try:
            # If context is provided, extract structured_data from it
            if context and not structured_data:
                for key, value in context:
                    if key == 'structured_data':
                        structured_data = value
                        break
            
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
    name: str = "Google Sheets Formatter Tool"
    description: str = "Formats validated ISM data for Google Sheets and updates the sheet"
    
    def _run(self, structured_data=None, validation_results=None, context=None):
        """Format and update Google Sheets with the validated data."""
        try:
            # If context is provided, extract parameters from it
            if context:
                if not structured_data or not validation_results:
                    for key, value in context:
                        if key == 'structured_data':
                            structured_data = value
                        elif key == 'validation_results':
                            validation_results = value
            
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
            
            if not month_year:
                logger.warning("Could not determine month and year. Not updating Google Sheets.")
                return False
            
            # Get Google Sheets service
            service = get_google_sheets_service()
            
            # Get or create the Google Sheet
            sheet_id = self._get_or_create_sheet(service, "ISM Manufacturing Report Analysis")
            
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
            raise
    
    def _get_or_create_sheet(self, service, title):
        """Get an existing sheet or create a new one."""
        try:
            # Try to find an existing sheet with the given title
            response = service.spreadsheets().list().execute()
            for sheet in response.get('files', []):
                if sheet['name'] == title:
                    return sheet['id']
            
            # If not found, create a new sheet
            sheet_metadata = {
                'properties': {
                    'title': title
                }
            }
            sheet = service.spreadsheets().create(body=sheet_metadata).execute()
            sheet_id = sheet['spreadsheetId']
            
            # Create tabs for each index
            batch_update_request = {
                'requests': []
            }
            
            for index in ISM_INDICES:
                batch_update_request['requests'].append({
                    'addSheet': {
                        'properties': {
                            'title': index
                        }
                    }
                })
            
            service.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body=batch_update_request
            ).execute()
            
            return sheet_id
        except Exception as e:
            logger.error(f"Error finding or creating sheet: {str(e)}")
            
            # Fallback: try to create a new sheet directly
            try:
                sheet_metadata = {
                    'properties': {
                        'title': title
                    }
                }
                sheet = service.spreadsheets().create(body=sheet_metadata).execute()
                sheet_id = sheet['spreadsheetId']
                
                # Create tabs for each index
                batch_update_request = {
                    'requests': []
                }
                
                for index in ISM_INDICES:
                    batch_update_request['requests'].append({
                        'addSheet': {
                            'properties': {
                                'title': index
                            }
                        }
                    })
                
                service.spreadsheets().batchUpdate(
                    spreadsheetId=sheet_id,
                    body=batch_update_request
                ).execute()
                
                return sheet_id
            except Exception as e2:
                logger.error(f"Fallback sheet creation failed: {str(e2)}")
                raise
    
    def _format_index_data(self, index, data):
        """Format data for a specific index."""
        categories = data.get("categories", {})
        
        # Ensure all expected categories exist
        if index in INDEX_CATEGORIES:
            formatted_data = {}
            for category in INDEX_CATEGORIES[index]:
                formatted_data[category] = categories.get(category, [])
            return formatted_data
        else:
            return categories
    
    def _update_sheet_tab(self, service, sheet_id, index, formatted_data, month_year):
        """Update a specific tab in the Google Sheet."""
        try:
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
                        if industry not in all_industries:
                            all_industries.append(industry)
                            new_values.append([industry, category])
                
                # Update the sheet
                service.spreadsheets().values().update(
                    spreadsheetId=sheet_id,
                    range=f"'{index}'!A1",
                    valueInputOption="RAW",
                    body={"values": new_values}
                ).execute()
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
                
                # Update industry data
                batch_updates = []
                new_industries = []
                
                # Collect all industries from all categories
                for category, industries in formatted_data.items():
                    for industry in industries:
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
            
            return True
        
        except Exception as e:
            logger.error(f"Error updating sheet tab {index}: {str(e)}")
            return False

class PDFOrchestratorTool(BaseTool):
    name: str = "PDF Orchestrator Tool"
    description: str = "Orchestrates the processing of multiple ISM Manufacturing Report PDFs"
    
    def _run(self, pdf_directory=None, context=None):
        """Process all PDF files in the given directory."""
        try:
            # If context is provided, extract pdf_directory from it
            if context and not pdf_directory:
                for key, value in context:
                    if key == 'pdf_directory':
                        pdf_directory = value
                        break
            
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
                extracted_data = extraction_tool._run(pdf_path=pdf_path)
                
                # Structure the extracted data
                structurer_tool = SimpleDataStructurerTool()
                structured_data = structurer_tool._run(extracted_data=extracted_data)
                
                # Validate the structured data
                validator_tool = DataValidatorTool()
                validation_results = validator_tool._run(structured_data=structured_data)
                
                # Check if any validations passed
                if any(validation_results.values()):
                    formatter_tool = GoogleSheetsFormatterTool()
                    update_result = formatter_tool._run(
                        structured_data=structured_data, 
                        validation_results=validation_results
                    )
                    results[pdf_file] = update_result
                else:
                    logger.warning(f"All validations failed for {pdf_file}")
                    results[pdf_file] = False
            
            return {"success": True, "results": results}
        except Exception as e:
            logger.error(f"Error in PDF orchestration: {str(e)}")
            return {"success": False, "message": str(e)}