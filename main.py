import os
import logging
import traceback
from dotenv import load_dotenv

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
from tasks import (
    create_extraction_task,
    create_structuring_task,
    create_validation_task,
    create_formatting_task,
    create_orchestration_task
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
        # Create agents
        extractor_agent = create_extractor_agent()
        structurer_agent = create_structurer_agent()
        validator_agent = create_validator_agent()
        formatter_agent = create_formatter_agent()
        
        # Execute extraction
        logger.info("Starting data extraction...")
        try:
            extraction_task = create_extraction_task(extractor_agent, pdf_path)
            extraction_crew = Crew(
                agents=[extractor_agent],
                tasks=[extraction_task],
                verbose=2,
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
            structuring_task = create_structuring_task(structurer_agent, extraction_result)
            structuring_crew = Crew(
                agents=[structurer_agent],
                tasks=[structuring_task],
                verbose=2,
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
            validation_task = create_validation_task(validator_agent, structured_data)
            validation_crew = Crew(
                agents=[validator_agent],
                tasks=[validation_task],
                verbose=2,
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
            formatting_task = create_formatting_task(formatter_agent, structured_data, validation_results)
            formatting_crew = Crew(
                agents=[formatter_agent],
                tasks=[formatting_task],
                verbose=2,
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
        # Create orchestrator agent
        orchestrator_agent = create_orchestrator_agent()
        
        # Create orchestration task
        orchestration_task = create_orchestration_task(orchestrator_agent, pdf_directory)
        
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
            verbose=2,
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