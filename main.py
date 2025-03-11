import os
import logging
import traceback
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

def process_single_pdf(pdf_path):
    """Process a single PDF file."""
    logger.info(f"Processing PDF: {pdf_path}")
    
    try:
        # Import Task directly here to ensure we're using the correct version
        from crewai import Task, Crew, Process
        from tools import SimpleDataStructurerTool
        
        # Create agents
        extractor_agent = create_extractor_agent()
        structurer_agent = create_structurer_agent()
        validator_agent = create_validator_agent()
        formatter_agent = create_formatter_agent()
        data_correction_agent = create_data_correction_agent()
        
        # Execute extraction
        logger.info("Starting data extraction...")
        try:
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
                
                PAY SPECIAL ATTENTION to correctly identifying:
                - For each index like New Orders, Production, etc., carefully identify which industries are in the GROWING category and which are in the DECLINING category
                - READ THE TEXT CAREFULLY to determine whether an industry is growing/expanding or declining/contracting
                - For Supplier Deliveries, identify which industries report SLOWER deliveries and which report FASTER deliveries
                - For Inventories, identify which industries report HIGHER inventories and which report LOWER inventories
                - For Customers' Inventories, identify which industries report TOO HIGH inventories and which report TOO LOW inventories
                - For Prices, identify which industries report INCREASING prices and which report DECREASING prices
                
                VERY IMPORTANT: For each index, make sure industries are placed in the correct category based on the explicit statements in the report.
                
                Ensure all data is correctly identified and structured for further processing.
                """,
                expected_output="A dictionary containing the extracted data with month_year, manufacturing_table, index_summaries, and industry_data",
                agent=extractor_agent
            )

            extraction_crew = Crew(
                agents=[extractor_agent],
                tasks=[extraction_task],
                verbose=True,
                process=Process.sequential
            )
            
            extraction_result = extraction_crew.kickoff()
            logger.info("Extraction result received")
            
            # Convert extraction result to usable format for structuring
            if hasattr(extraction_result, 'content'):
                extraction_result = extraction_result.content

            # Convert extraction result to usable format
            if isinstance(extraction_result, str):
                try:
                    extraction_result = eval(extraction_result)
                except Exception as e:
                    logger.error(f"Error parsing extraction result: {str(e)}")
                    logger.error(f"Raw extraction result: {extraction_result}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    return False
            elif hasattr(extraction_result, 'content'):
                content = extraction_result.content
                if isinstance(content, str):
                    try:
                        extraction_result = eval(content)
                    except Exception as e:
                        logger.error(f"Error parsing extraction result content: {str(e)}")
                        logger.error(f"Raw extraction result content: {content}")
                        logger.error(f"Traceback: {traceback.format_exc()}")
                        return False
                else:
                    extraction_result = content
            else:
                print("Please provide either --pdf or --dir argument")
                parser.print_help()

            # Convert extraction result to usable format for structuring
            if hasattr(extraction_result, 'content'):
                content = extraction_result.content
                if isinstance(content, str):
                    try:
                        extraction_result = eval(content)
                    except Exception as e:
                        logger.error(f"Error parsing extraction result content: {str(e)}")
                        logger.error(f"Raw extraction result: {extraction_result}")
                        logger.error(f"Traceback: {traceback.format_exc()}")
                        return False
                else:
                    extraction_result = content
                    
            # ADD VERIFICATION STEP HERE
            logger.info("Starting data verification...")
            verification_task = Task(
                description=f"""
                IMPORTANT: Carefully verify that the extracted industry data is CORRECTLY CATEGORIZED.
                
                For each index (New Orders, Production, Employment, etc.):
                1. Review the actual text in the index_summaries to find explicit mentions of industries
                2. For each index, check if industries are correctly categorized as:
                - Growing or Declining for most indices
                - Slower or Faster for Supplier Deliveries
                - Higher or Lower for Inventories
                - Too High or Too Low for Customers' Inventories
                - Increasing or Decreasing for Prices
                
                COMMON ERRORS TO LOOK FOR:
                - Industries might be listed in the wrong category (e.g., in Declining when they should be in Growing)
                - Some industries might be missing entirely
                - There could be empty categories when they should contain industries
                
                IF YOU FIND ANY ERRORS:
                - Move industries to their correct categories
                - Add any missing industries to appropriate categories
                - Make sure no industry appears in both categories for the same index
                
                Original extracted data to verify: {extraction_result}. The PDF path is: {pdf_path}
                """,
                expected_output="A corrected dictionary containing the verified data with month_year, manufacturing_table, index_summaries, and industry_data",
                agent=data_correction_agent
            )
            
            verification_crew = Crew(
                agents=[data_correction_agent],
                tasks=[verification_task],
                verbose=True,
                process=Process.sequential
            )
            
            verified_result = verification_crew.kickoff()
            logger.info("Verification result received")
            
            # Convert verification result to usable format
            if isinstance(verified_result, str):
                try:
                    verified_result = eval(verified_result)
                    extraction_result = verified_result  # Use the verified data
                except Exception as e:
                    logger.error(f"Error parsing verification result: {str(e)}")
                    logger.error(f"Raw verification result: {verified_result}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    # Continue with original extraction result
            elif hasattr(verified_result, 'content'):
                content = verified_result.content
                if isinstance(content, str):
                    try:
                        verified_result = eval(content)
                        extraction_result = verified_result  # Use the verified data
                    except Exception as e:
                        logger.error(f"Error parsing verification result content: {str(e)}")
                        logger.error(f"Raw verification result content: {content}")
                        logger.error(f"Traceback: {traceback.format_exc()}")
                        # Continue with original extraction result
                else:
                    extraction_result = content
                    
            logger.info("Data extraction and verification completed")
                
        except Exception as e:
            logger.error(f"Error during extraction phase: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
        
        # Execute structuring
        logger.info("Starting data structuring...")
        structurer_tool = SimpleDataStructurerTool()
        structured_data = structurer_tool._run(extraction_result)
        
        logger.info("Data structuring completed")
        
        # Execute validation
        logger.info("Starting data validation...")
        try:
            # Create validation task
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
            if isinstance(validation_results, str):
                try:
                    validation_results = eval(validation_results)
                except Exception as e:
                    logger.error(f"Error parsing validation results: {str(e)}")
                    logger.error(f"Raw validation results: {validation_results}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    return False
            elif hasattr(validation_results, 'content'):
                content = validation_results.content
                if isinstance(content, str):
                    try:
                        validation_results = eval(content)
                    except Exception as e:
                        logger.error(f"Error parsing validation results content: {str(e)}")
                        logger.error(f"Raw validation results content: {content}")
                        logger.error(f"Traceback: {traceback.format_exc()}")
                        return False
                else:
                    validation_results = content
        except Exception as e:
            logger.error(f"Error during validation phase: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
        
        logger.info("Data validation completed")
        
        # First convert the CrewOutput to a dictionary if needed
        if hasattr(validation_results, 'content'):
            validation_dict = validation_results.content
            if isinstance(validation_dict, str):
                try:
                    validation_dict = eval(validation_dict)
                except:
                    logger.error(f"Error parsing validation_dict content: {validation_dict}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    validation_dict = {}
        else:
            validation_dict = validation_results

        # Then check if any values are True
        if not any(validation_dict.values()):
            logger.warning(f"All validations failed for {pdf_path}")
            return False
        
        # Execute formatting
        logger.info("Starting Google Sheets formatting...")
        try:
            # Create formatting task
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
                'validation_results': {validation_results}
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
            if isinstance(formatting_result, str):
                try:
                    formatting_result = eval(formatting_result)
                except Exception as e:
                    logger.error(f"Error parsing formatting result: {str(e)}")
                    logger.error(f"Raw formatting result: {formatting_result}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
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
                result = eval(result)
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