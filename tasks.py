from crewai import Task

def create_extraction_task(agent, pdf_path):
    """Create a task for extracting data from a PDF."""
    return Task(
        description=f"""
        Extract all relevant data from the ISM Manufacturing Report PDF at {pdf_path}.
        
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
        expected_output="""
        A dictionary containing the extracted data with the following keys:
        - month_year: The month and year of the report
        - manufacturing_table: The Manufacturing at a Glance table content
        - index_summaries: Summaries for each index
        - industry_data: Industries mentioned for each index, categorized appropriately
        """,
        agent=agent,
        context={"pdf_path": pdf_path}  # Changed from list of tuples to dictionary
    )

def create_structuring_task(agent, extraction_result):
    """Create a task for structuring extracted data."""
    return Task(
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
        """,
        expected_output="""
        A dictionary containing structured data for each index, with:
        - The index name as the key
        - A sub-dictionary with:
          - month_year: The month and year of the report
          - categories: A dictionary mapping category names to lists of industries
        """,
        agent=agent,
        context={"extracted_data": extraction_result}  # Changed from tuple to dictionary
    )

def create_validation_task(agent, structured_data):
    """Create a task for validating structured data."""
    return Task(
        description=f"""
        Validate the structured ISM Manufacturing Report data for accuracy and completeness.
        
        Check:
        1. All expected indices are present
        2. Each index has the appropriate categories
        3. No missing data or incorrect classifications
        4. Industries are preserved exactly as listed in the report
        
        Flag any issues that would require manual review.
        """,
        expected_output="""
        A dictionary mapping each index name to a boolean indicating whether
        it passed validation.
        """,
        agent=agent,
        context={"structured_data": structured_data}  # Changed from tuple to dictionary
    )

def create_formatting_task(agent, structured_data, validation_results):
    """Create a task for formatting and updating Google Sheets."""
    return Task(
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
        """,
        expected_output="""
        A boolean indicating whether the Google Sheets update was successful.
        """,
        agent=agent,
        context={  # Changed from list of tuples to dictionary
            "structured_data": structured_data,
            "validation_results": validation_results
        }
    )

def create_orchestration_task(agent, pdf_directory):
    """Create a task for orchestrating the processing of multiple PDFs."""
    return Task(
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
        """,
        expected_output="""
        A dictionary containing the processing results for each PDF file.
        """,
        agent=agent,
        context={"pdf_directory": pdf_directory}  # Changed from tuple to dictionary
    )