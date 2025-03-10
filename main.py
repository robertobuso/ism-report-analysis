import os
import logging
import traceback
from dotenv import load_dotenv
from tools import SimplePDFExtractionTool

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
    create_orchestrator_agent
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

def process_single_pdf(pdf_path):
    """Process a single PDF file."""
    logger.info(f"Processing PDF: {pdf_path}")
    
    try:
        # Import Task directly here to ensure we're using the correct version
        from crewai import Task
        
        # Create agents
        extractor_agent = create_extractor_agent()
        structurer_agent = create_structurer_agent()
        validator_agent = create_validator_agent()
        formatter_agent = create_formatter_agent()
        
        # Execute extraction
        logger.info("Starting data extraction...")
        try:
            # Custom extraction task without context parameter
            extraction_task = Task(
                description=f"""
                Extract all relevant data from the ISM Manufacturing Report PDF.
                The PDF path is: {pdf_path}

                IMPORTANT: When using the PDF Extraction Tool, pass the input in this exact format: 
                {{
                    "path": "{pdf_path}"
                }}
                
                You must extract:
                1. The month and year of the report
                2. The Manufacturing at a Glance table
                3. All index-specific summaries (New Orders, Production, etc.)
                4. Industry mentions in each index summary
                
                Pay special attention to correctly identifying:
                - Different classifications based on the index (Growing/Declining for most indices,
                Slower/Faster for Supplier Deliveries, Higher/Lower for Inventories, etc.)
                - The exact list of industries in each category
                - The correct month and year of the report
                
                Ensure all data is correctly identified and structured for further processing.
                """,
                expected_output="""A dictionary containing the extracted data with the following keys:
                - month_year: The month and year of the report
                - manufacturing_table: The Manufacturing at a Glance table content
                - index_summaries: Summaries for each index
                - industry_data: Industries mentioned for each index, categorized appropriately
                """,
                agent=extractor_agent,
                tools=[SimplePDFExtractionTool()],
                async_execution=False
            )

            extraction_crew = Crew(
                agents=[extractor_agent],
                tasks=[extraction_task],
                verbose=True,  # Changed from 2 to True
                process=Process.sequential
            )
            
            extraction_result = extraction_crew.kickoff()
            logger.info("Extraction result received")
            
            if isinstance(extraction_result, str):
                try:
                    extraction_result = eval(extraction_result)
                except Exception as e:
                    logger.error(f"Error parsing extraction result: {str(e)}")
                    logger.error(f"Raw extraction result: {extraction_result}")
                    return False
        except Exception as e:
            logger.error(f"Error during extraction phase: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
        
        logger.info("Data extraction completed")
        
        # Execute structuring
        logger.info("Starting data structuring...")
        try:
            # Create structuring task without context
            structuring_task = Task(
                description=f"""
                Convert the extracted ISM Manufacturing Report data into a structured format.
                
                Requirements:
                1. For each index, organize industries into the correct categories:
                   - Growing/Declining for most indices
                   - Slower/Faster for Supplier Deliveries
                   - Higher/Lower for Inventories
                   - Too High/Too Low for Customers' Inventories
                
                2. Ensure industry names are preserved exactly as they appear in the report
                
                3. Keep the original month and year for proper sheet updates
                
                4. Handle any edge cases such as missing categories or inconsistent naming
                
                The extracted data is: {extraction_result}
                """,
                expected_output="""
                A dictionary containing structured data for each index, with:
                - The index name as the key
                - A sub-dictionary with:
                  - month_year: The month and year of the report
                  - categories: A dictionary mapping category names to lists of industries
                """,
                agent=structurer_agent
            )
            
            structuring_crew = Crew(
                agents=[structurer_agent],
                tasks=[structuring_task],
                verbose=True,  # Changed from 2 to True
                process=Process.sequential
            )
            
            structured_data = structuring_crew.kickoff()
            if isinstance(structured_data, str):
                try:
                    structured_data = eval(structured_data)
                except Exception as e:
                    logger.error(f"Error parsing structured data: {str(e)}")
                    return False
        except Exception as e:
            logger.error(f"Error during structuring phase: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
        
        logger.info("Data structuring completed")
        
        # Execute validation
        logger.info("Starting data validation...")
        try:
            # Create validation task without context
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
                expected_output="""
                A dictionary mapping each index name to a boolean indicating whether
                it passed validation.
                """,
                agent=validator_agent
            )
            
            validation_crew = Crew(
                agents=[validator_agent],
                tasks=[validation_task],
                verbose=True,  # Changed from 2 to True
                process=Process.sequential
            )
            
            validation_results = validation_crew.kickoff()
            if isinstance(validation_results, str):
                try:
                    validation_results = eval(validation_results)
                except Exception as e:
                    logger.error(f"Error parsing validation results: {str(e)}")
                    return False
        except Exception as e:
            logger.error(f"Error during validation phase: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
        
        logger.info("Data validation completed")
        
        # Check if any validations passed
        if not any(validation_results.values()):
            logger.warning(f"All validations failed for {pdf_path}")
            return False
        
        # Execute formatting
        logger.info("Starting Google Sheets formatting...")
        try:
            # Create formatting task without context
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
                
                The structured data is: {structured_data}
                The validation results are: {validation_results}
                """,
                expected_output="""
                A boolean indicating whether the Google Sheets update was successful.
                """,
                agent=formatter_agent
            )
            
            formatting_crew = Crew(
                agents=[formatter_agent],
                tasks=[formatting_task],
                verbose=True,  # Changed from 2 to True
                process=Process.sequential
            )
            
            formatting_result = formatting_crew.kickoff()
            if isinstance(formatting_result, str):
                try:
                    formatting_result = eval(formatting_result)
                except Exception as e:
                    logger.error(f"Error parsing formatting result: {str(e)}")
                    return False
        except Exception as e:
            logger.error(f"Error during formatting phase: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
        
        logger.info("Google Sheets formatting completed")
        
        return formatting_result
    
    except Exception as e:
        logger.error(f"Error processing PDF {pdf_path}: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

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
                create_formatter_agent()
            ],
            tasks=[orchestration_task],
            verbose=True,  # Changed from 2 to True
            process=Process.sequential
        )
        
        result = orchestration_crew.kickoff()
        if isinstance(result, str):
            try:
                result = eval(result)
            except Exception as e:
                logger.error(f"Error parsing orchestration result: {str(e)}")
                return False
        
        logger.info("Completed processing all PDFs")
        return result
    
    except Exception as e:
        logger.error(f"Error in batch processing: {str(e)}")
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