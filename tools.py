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
            
            # Get industry data
            industry_data = extracted_data.get("industry_data", {})
            
            # Structure data for each index
            structured_data = {}
            
            for index, data in industry_data.items():
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
            
            # Update Manufacturing at a Glance tab
            manufacturing_table = data.get('structured_data', {}).get('manufacturing_table', '')
            if not manufacturing_table and 'extraction_data' in data:
                # Try to get from extraction_data if available
                manufacturing_table = data.get('extraction_data', {}).get('manufacturing_table', '')
            
            if manufacturing_table:
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
            raise

    def _get_or_create_sheet(self, service, title):
        """Get an existing sheet or create a new one."""
        try:
            # Try to find an existing sheet with the given title
            response = service.files().list(
                q=f"name='{title}' and mimeType='application/vnd.google-apps.spreadsheet'",
                fields="files(id, name)"
            ).execute()
            
            items = response.get('files', [])
            if items:
                return items[0]['id']
            
            # If not found, create a new sheet
            sheet_metadata = {
                'properties': {
                    'title': title
                }
            }
            sheet = service.spreadsheets().create(body=sheet_metadata).execute()
            sheet_id = sheet['spreadsheetId']
            
            # Create tabs for Manufacturing at a Glance and each index
            batch_update_request = {
                'requests': [
                    {
                        'addSheet': {
                            'properties': {
                                'title': 'Manufacturing at a Glance',
                                'index': 0  # Make this the first tab
                            }
                        }
                    }
                ]
            }
            
            # Add tabs for each index
            index_position = 1  # Start after the Manufacturing at a Glance tab
            for index in ISM_INDICES:
                batch_update_request['requests'].append({
                    'addSheet': {
                        'properties': {
                            'title': index,
                            'index': index_position
                        }
                    }
                })
                index_position += 1
            
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
                
                # Create tabs for Manufacturing at a Glance and each index
                batch_update_request = {
                    'requests': [
                        {
                            'addSheet': {
                                'properties': {
                                    'title': 'Manufacturing at a Glance',
                                    'index': 0  # Make this the first tab
                                }
                            }
                        }
                    ]
                }
                
                # Add tabs for each index
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

    def _update_manufacturing_tab(self, service, sheet_id, month_year, table_content):
        """Update the Manufacturing at a Glance tab with the table content."""
        try:
            # Get the existing content
            result = service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range="'Manufacturing at a Glance'!A:Z"
            ).execute()
            
            values = result.get('values', [])
            
            # Check if month already exists in data
            month_exists = False
            row_index = 1  # Start at row 1 (A1)
            
            if values:
                for i, row in enumerate(values):
                    if i > 0 and len(row) > 0 and row[0] == month_year:
                        month_exists = True
                        row_index = i + 1  # +1 for 1-indexing in sheets
                        break
            
            # Format the table content
            if isinstance(table_content, str):
                # Split the content into lines for better display
                lines = table_content.strip().split('\n')
                
                # Prepare data for update
                if not month_exists:
                    # If month doesn't exist, add it with the table content
                    new_values = []
                    
                    # Add header row if sheet is empty
                    if not values:
                        new_values.append(["Month/Year", "Manufacturing at a Glance"])
                    
                    # Add month and content
                    new_values.append([month_year, lines[0] if lines else ""])
                    
                    # Add remaining lines
                    for i, line in enumerate(lines[1:], 2):
                        if i < len(new_values):
                            new_values[i].append(line)
                        else:
                            new_values.append(["", line])
                    
                    # Update the sheet
                    service.spreadsheets().values().update(
                        spreadsheetId=sheet_id,
                        range=f"'Manufacturing at a Glance'!A{len(values) + 1}",
                        valueInputOption="RAW",
                        body={"values": new_values}
                    ).execute()
                else:
                    # If month exists, update its content
                    updates = []
                    
                    # Update first line
                    updates.append({
                        "range": f"'Manufacturing at a Glance'!B{row_index}",
                        "values": [[lines[0] if lines else ""]]
                    })
                    
                    # Update remaining lines
                    for i, line in enumerate(lines[1:], 1):
                        updates.append({
                            "range": f"'Manufacturing at a Glance'!B{row_index + i}",
                            "values": [[line]]
                        })
                    
                    # Execute batch update
                    service.spreadsheets().values().batchUpdate(
                        spreadsheetId=sheet_id,
                        body={
                            "valueInputOption": "RAW",
                            "data": updates
                        }
                    ).execute()
            
            return True
        except Exception as e:
            logger.error(f"Error updating Manufacturing at a Glance tab: {str(e)}")
            return False

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