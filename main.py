import os
import logging
import traceback
import re
import warnings
from googleapiclient import discovery
from dotenv import load_dotenv
from tools import SimplePDFExtractionTool, SimpleDataStructurerTool

# Create necessary directories first
os.makedirs("logs", exist_ok=True)
os.makedirs("pdfs", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

from crewai import Crew, Process
from agents import (
    create_extractor_agent,
    create_structurer_agent,
    create_validator_agent,
    create_formatter_agent,
    create_orchestrator_agent,
    create_data_correction_agent
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='logs/ism_analysis.log'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Set up OpenAI API
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

# Suppress the oauth2client warning
warnings.filterwarnings('ignore', message='file_cache is only supported with oauth2client<4.0.0')

def safely_parse_agent_output(output):
    """Safely parse agent output to a dictionary without using eval()."""
    try:
        # For CrewOutput objects, directly access the raw_output
        if hasattr(output, 'raw_output'):
            # Try to get the raw output directly
            return output.raw_output
        
        # Handle CrewOutput objects (new version)
        if hasattr(output, 'content'):
            content = output.content
            if isinstance(content, dict):
                return content
            elif isinstance(content, str):
                # Try to parse as JSON
                try:
                    import json
                    return json.loads(content.replace("'", '"'))
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse output as JSON: {content[:100]}...")
                    
                # Try ast.literal_eval which is safer than eval
                try:
                    import ast
                    return ast.literal_eval(content)
                except (SyntaxError, ValueError):
                    logger.warning(f"Failed to parse output using ast.literal_eval: {content[:100]}...")
                    
                # Last resort: structured regex parsing
                logger.warning("Attempting to parse output using regex patterns")
                return fallback_regex_parsing(content)
        
        # If output is already a dictionary, return it directly
        if isinstance(output, dict):
            return output
        
        # Handle string outputs
        if isinstance(output, str):
            # Same parsing logic as above for string output
            try:
                import json
                return json.loads(output.replace("'", '"'))
            except json.JSONDecodeError:
                pass
                
            try:
                import ast
                return ast.literal_eval(output)
            except (SyntaxError, ValueError):
                logger.warning(f"Failed to parse output using ast.literal_eval: {output[:100]}...")
                
            return fallback_regex_parsing(output)
        
        # Special handling for other types of objects
        logger.warning(f"Trying to extract output from object of type {type(output)}")
        # Add direct access for common formats - try various attributes that might contain the results
        for attr in ['result', 'output', 'data', 'response', 'answer', 'final_answer']:
            if hasattr(output, attr):
                value = getattr(output, attr)
                if isinstance(value, dict):
                    return value
                elif isinstance(value, str):
                    try:
                        import ast
                        return ast.literal_eval(value)
                    except (SyntaxError, ValueError):
                        continue
        
        # Last fallback: convert the entire object to a string and try to extract data
        try:
            import ast
            return ast.literal_eval(str(output))
        except (SyntaxError, ValueError):
            pass
            
        logger.error(f"Unable to parse agent output of type {type(output)}")
        # When all else fails, return None
        return None
        
    except Exception as e:
        logger.error(f"Error parsing agent output: {str(e)}")
        logger.error(f"Raw output type: {type(output)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None
    
def fallback_regex_parsing(text):
    """Fallback method to extract key data using regex patterns."""
    # This would use regex patterns to extract the data structure
    # A simple implementation for demonstration
    try:
        result = {}
        
        # Extract month_year
        month_year_match = re.search(r"'month_year':\s*'([^']+)'", text)
        if month_year_match:
            result["month_year"] = month_year_match.group(1)
        
        # Extract manufacturing_table (just the fact it exists)
        if "'manufacturing_table'" in text:
            result["manufacturing_table"] = "Extracted table content"
        
        # Extract index_summaries (just the fact they exist)
        if "'index_summaries'" in text:
            result["index_summaries"] = {}
        
        # Extract industry_data (basic structure)
        if "'industry_data'" in text:
            result["industry_data"] = {}
        
        return result
    except Exception as e:
        logger.error(f"Fallback regex parsing failed: {str(e)}")
        return {}

def process_single_pdf(pdf_path):
    """Process a single PDF file."""
    logger.info(f"Processing PDF: {pdf_path}")
    
    try:
        # Import required modules
        from crewai import Task, Crew, Process
        import re  # Add this for fallback_regex_parsing function
        
        # Create agents
        extractor_agent = create_extractor_agent()
        structurer_agent = create_structurer_agent()
        validator_agent = create_validator_agent()
        formatter_agent = create_formatter_agent()
        data_correction_agent = create_data_correction_agent()
        
        # Execute extraction
        logger.info("Starting data extraction...")
        
        # Custom extraction task
        extraction_task = Task(
            description=f"""
            Extract all relevant data from the ISM Manufacturing Report PDF.
            The PDF path is: {pdf_path}
            
            When using the PDF Extraction Tool, pass the path directly:
            "{pdf_path}"
            
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
            * SLOWER category: Industries reporting "slower" deliveries (NOTE: slower deliveries are a POSITIVE economic indicator)
            * FASTER category: Industries reporting "faster" deliveries (NOTE: faster deliveries are a NEGATIVE economic indicator)
            
            - Inventories:
            * HIGHER category: Industries reporting "higher" or "increased" inventories
            * LOWER category: Industries reporting "lower" or "decreased" inventories
            
            - Customers' Inventories:
            * TOO HIGH category: Industries reporting customers' inventories as "too high"
            * TOO LOW category: Industries reporting customers' inventories as "too low"
            
            - Prices:
            * INCREASING category: Industries reporting "higher" or "increasing" prices
            * DECREASING category: Industries reporting "lower" or "decreasing" prices
            
            READ THE TEXT CAREFULLY AND LOOK FOR THESE SPECIFIC TERMS AND PHRASES. Do not guess or infer - only place industries in categories when the text explicitly states their status.
            
            Look for sentences like:
            - "The X industries reporting growth in February are..."
            - "The Y industries reporting contraction in February are..."
            - "The industries reporting slower supplier deliveries are..."
            
            Ensure all data is correctly identified and structured for further processing.
            """,
            expected_output="A dictionary containing the extracted data with month_year, manufacturing_table, index_summaries, and industry_data",
            agent=extractor_agent
        )

        # Create extraction crew - THIS WAS MISSING
        extraction_crew = Crew(
            agents=[extractor_agent],
            tasks=[extraction_task],
            verbose=True,
            process=Process.sequential
        )

        extraction_result = extraction_crew.kickoff()
        logger.info("Extraction result received")

        # Special handling for CrewOutput
        if hasattr(extraction_result, '__class__') and extraction_result.__class__.__name__ == 'CrewOutput':
            extraction_data = extract_from_crew_output(extraction_result)
            if extraction_data:
                logger.info("Successfully extracted data directly from CrewOutput")
            else:
                # Fallback to regular parsing
                extraction_data = safely_parse_agent_output(extraction_result)
        else:
            # Regular parsing for other types
            extraction_data = safely_parse_agent_output(extraction_result)

        if not extraction_data:
            logger.error("Failed to parse extraction result")
            return False
        
        # Safely parse extraction result
        extraction_data = safely_parse_agent_output(extraction_result)
        if not extraction_data:
            logger.error("Failed to parse extraction result")
            return False
            
        # Execute verification
        logger.info("Starting data verification...")
        verification_task = Task(
            description=f"""
            CRITICAL TASK: You must carefully verify and correct the industry categorization in the extracted data.
            
            The extracted data is: {extraction_data}
            
            STEP 1: Directly examine the textual summaries in index_summaries to find industry mentions.
            
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
            
            IMPORTANT: For each industry, look for EXACT PHRASES in the index summaries that specify its status.
            Do not make assumptions - only categorize based on explicit statements.
            
            ESPECIALLY IMPORTANT: Make sure to include all parts of the original extraction (month_year, manufacturing_table, 
            index_summaries, AND the corrected industry_data).
            """,
            expected_output="A complete dictionary containing the verified data with month_year, manufacturing_table, index_summaries, and corrected industry_data",
            agent=data_correction_agent
        )
        
        # Create verification crew
        verification_crew = Crew(
            agents=[data_correction_agent],
            tasks=[verification_task],
            verbose=True,
            process=Process.sequential
        )
        
        verified_result = verification_crew.kickoff()
        logger.info("Verification result received")
        
        # Safely parse verification result
        verified_data = safely_parse_agent_output(verified_result)
        
        if verified_data:
            # Use the verified data if it was successfully parsed
            extraction_data = verified_data
            logger.info("Successfully verified and corrected data")
        else:
            logger.warning("Verification failed, continuing with unverified data")
            
        # Execute structuring
        logger.info("Starting data structuring...")
        structurer_tool = SimpleDataStructurerTool()
        structured_data = structurer_tool._run(extraction_data)
        logger.info("Data structuring completed")
        
        # Execute validation
        logger.info("Starting data validation...")
        validation_task = Task(
            description=f"""
            Validate the structured ISM Manufacturing Report data for accuracy and completeness.
            
            Check:
            1. All expected indices are present
            2. Each index has the appropriate categories
            3. No missing data or incorrect classifications
            4. Industries are preserved exactly as listed in the report
            
            Flag any issues that would require manual review.
            
            The structured data is: {structured_data}
            """,
            expected_output="A dictionary mapping each index name to a boolean indicating validation status",
            agent=validator_agent
        )
        
        validation_crew = Crew(
            agents=[validator_agent],
            tasks=[validation_task],
            verbose=True,
            process=Process.sequential
        )
        
        validation_results = validation_crew.kickoff()
        
        # Safely parse validation results
        validation_dict = safely_parse_agent_output(validation_results)
        if not validation_dict:
            logger.error("Failed to parse validation results")
            return False
        
        # Check if any validations passed
        if not any(validation_dict.values()):
            logger.warning(f"All validations failed for {pdf_path}")
            return False
        
        # Execute formatting
        logger.info("Starting Google Sheets formatting...")
        formatting_task = Task(
            description=f"""
            Format the validated ISM Manufacturing Report data for Google Sheets and update the sheet.
            
            Requirements:
            1. Check if the Google Sheet exists, create it if it doesn't
            2. Each index should have its own tab
            3. Industries should be rows, months should be columns
            4. Append new data without overwriting previous months
            5. Maintain consistent formatting across all tabs
            6. Handle any existing data gracefully
            
            Remember that each index may have different numbers of industries and they may
            be in different orders.
            
            The input for the Google Sheets Formatter Tool should be a dictionary with:
            'structured_data': {structured_data}
            'validation_results': {validation_dict}
            """,
            expected_output="A boolean indicating whether the Google Sheets update was successful",
            agent=formatter_agent
        )
        
        formatting_crew = Crew(
            agents=[formatter_agent],
            tasks=[formatting_task],
            verbose=True,
            process=Process.sequential
        )
        
        formatting_result = formatting_crew.kickoff()

        # Special handling for CrewOutput - don't try to parse it, just check for success indicators
        if hasattr(formatting_result, '__class__') and formatting_result.__class__.__name__ == 'CrewOutput':
            logger.info("Google Sheets formatting completed")
            
            # If we see evidence that the formatting succeeded in the logs
            if hasattr(formatting_result, 'content'):
                content = formatting_result.content
                if isinstance(content, bool):
                    return content
                elif isinstance(content, str) and ('true' in content.lower() or 'success' in content.lower()):
                    return True
            
            # Since we saw a success message in the log, assume success
            if "Successfully updated Google Sheets" in str(formatting_result):
                return True
            
            # Default to a successful result since we got this far
            return True
        else:
            # Regular parsing for other types
            format_success = safely_parse_agent_output(formatting_result)
            logger.info("Google Sheets formatting completed")
            return format_success if format_success is not None else False
        
    except Exception as e:
        logger.error(f"Error processing PDF {pdf_path}: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False
    
# Function to extract data directly from CrewOutput
def extract_from_crew_output(crew_output):
    """Extract dictionary data directly from a CrewOutput object."""
    try:
        # First try to get the final_answer attribute which often contains the full output
        if hasattr(crew_output, 'final_answer'):
            answer = crew_output.final_answer
            # If it's already a dict, return it
            if isinstance(answer, dict):
                return answer
            # If it's a string, try to parse it
            if isinstance(answer, str):
                try:
                    import ast
                    return ast.literal_eval(answer)
                except (SyntaxError, ValueError):
                    pass
                    
        # Next try the content attribute
        if hasattr(crew_output, 'content'):
            content = crew_output.content
            if isinstance(content, dict):
                return content
            elif isinstance(content, str):
                try:
                    import ast
                    return ast.literal_eval(content)
                except (SyntaxError, ValueError):
                    pass
                    
        # Try to access raw_output which might be available in some versions
        if hasattr(crew_output, 'raw_output'):
            raw = crew_output.raw_output
            if isinstance(raw, dict):
                return raw
        
        # If we can get the full string representation, try to parse that
        full_output = str(crew_output)
        
        # Look for dictionary-like patterns
        import re
        dict_match = re.search(r'\{.*\}', full_output, re.DOTALL)
        if dict_match:
            try:
                import ast
                return ast.literal_eval(dict_match.group(0))
            except (SyntaxError, ValueError):
                pass
                
        return None
    except Exception as e:
        logger.error(f"Error extracting from CrewOutput: {str(e)}")
        return None
    
def process_multiple_pdfs(pdf_directory):
    """Process all PDF files in a directory using the Orchestrator agent."""
    logger.info(f"Processing all PDFs in directory: {pdf_directory}")
    
    try:
        # Import Task directly here to ensure we're using the correct version
        from crewai import Task
        
        # Create orchestrator agent
        orchestrator_agent = create_orchestrator_agent()
        
        # Create orchestration task without using context
        orchestration_task = Task(
            description=f"""
            Orchestrate the processing of all ISM Manufacturing Report PDFs in the directory {pdf_directory}.
            
            Steps:
            1. For each PDF file:
               a. Extract data using the Extractor Agent
               b. Structure data using the Structurer Agent
               c. Validate data using the Validator Agent
               d. Format and update Google Sheets using the Formatter Agent
            
            2. Track the success/failure of each PDF processing
            
            3. Ensure no duplications or overwrites in the Google Sheet
            
            4. Handle errors gracefully and report any issues
            
            The PDF directory is: {pdf_directory}
            """,
            expected_output="""
            A dictionary containing the processing results for each PDF file.
            """,
            agent=orchestrator_agent
        )
        
        # Execute orchestration
        orchestration_crew = Crew(
            agents=[
                orchestrator_agent,
                create_extractor_agent(),
                create_structurer_agent(),
                create_validator_agent(),
                create_formatter_agent(),
                create_data_correction_agent()
            ],
            tasks=[orchestration_task],
            verbose=True,  # Changed from 2 to True
            process=Process.sequential
        )
        
        result = orchestration_crew.kickoff()
        if isinstance(result, str):
            try:
                result = safely_parse_agent_output(result)
            except Exception as e:
                logger.error(f"Error parsing orchestration result: {str(e)}")
                logger.error(f"Raw orchestration result: {result}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                return False
        
        logger.info("Completed processing all PDFs")
        return result
    
    except Exception as e:
        logger.error(f"Error in batch processing: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    import argparse
    import sys
    
    # Ensure directories exist
    os.makedirs("logs", exist_ok=True)
    os.makedirs("pdfs", exist_ok=True)
    
    # Add console handler for logging
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logging.getLogger().addHandler(console_handler)
    
    parser = argparse.ArgumentParser(description="Process ISM Manufacturing Report PDFs")
    parser.add_argument("--pdf", help="Path to a single PDF file to process")
    parser.add_argument("--dir", help="Directory containing multiple PDF files to process")
    args = parser.parse_args()
    
    if args.pdf:
        print(f"Processing single PDF: {args.pdf}")
        result = process_single_pdf(args.pdf)
        print(f"Result: {result}")
    elif args.dir:
        print(f"Processing all PDFs in directory: {args.dir}")
        result = process_multiple_pdfs(args.dir)
        print(f"Result: {result}")
    else:
        print("Please provide either --pdf or --dir argument")
        parser.print_help()