from crewai import Agent

# Import your BaseTool implementations
from tools import (
    SimplePDFExtractionTool, 
    SimpleDataStructurerTool,
    DataValidatorTool, 
    GoogleSheetsFormatterTool,
    PDFOrchestratorTool
)

def create_extractor_agent():
    """Create an agent specialized in extracting data from PDFs."""
    extraction_tool = SimplePDFExtractionTool()
    
    return Agent(
        role="Document Extractor",
        goal="Extract all relevant data from ISM Manufacturing Report PDFs accurately",
        backstory="""You are an expert in data extraction who specializes in analyzing
        manufacturing reports. You excel at identifying key information from complex PDFs
        and transforming it into structured data.""",
        verbose=True,
        allow_delegation=False,
        tools=[extraction_tool],
        llm_config={"model": "gpt-4o"} 
    )

def create_structurer_agent():
    """Create an agent specialized in structuring extracted data."""
    structurer_tool = SimpleDataStructurerTool()
    
    return Agent(
        role="Data Organizer",
        goal="Convert extracted ISM data into properly structured formats",
        backstory="""You are a data organization specialist with deep knowledge of
        manufacturing indices and industry classifications. You ensure that all
        extracted data is correctly categorized and follows ISM's specific structure.""",
        verbose=True,
        allow_delegation=False,
        tools=[structurer_tool],
        llm_config={"model": "gpt-4o"}
    )

def create_validator_agent():
    """Create an agent specialized in validating structured data."""
    validator_tool = DataValidatorTool()
    
    return Agent(
        role="QA & Validation Specialist",
        goal="Ensure all structured ISM data is complete, accurate, and follows expected formats",
        backstory="""You are a meticulous quality assurance specialist who verifies
        data integrity and catches errors before they propagate. You know exactly what
        makes ISM data valid and can identify any inconsistencies.""",
        verbose=True,
        allow_delegation=False,
        tools=[validator_tool],
        llm_config={"model": "gpt-4o"}
    )

def create_formatter_agent():
    """Create an agent specialized in formatting data for Google Sheets."""
    formatter_tool = GoogleSheetsFormatterTool()
    
    return Agent(
        role="Output Generator",
        goal="Format and update Google Sheets with validated ISM data",
        backstory="""You are an expert in data presentation who specializes in
        Google Sheets integration. You know how to format data for clarity and
        ensure that updates don't overwrite existing information.""",
        verbose=True,
        allow_delegation=False,
        tools=[formatter_tool],
        llm_config={"model": "gpt-4o"}
    )

def create_orchestrator_agent():
    """Create an agent specialized in orchestrating the processing of multiple PDFs."""
    orchestrator_tool = PDFOrchestratorTool()
    
    return Agent(
        role="Workflow Controller",
        goal="Manage the processing of multiple ISM Manufacturing Report PDFs",
        backstory="""You are a skilled project manager who coordinates complex
        data processing workflows. You ensure that all PDFs are processed correctly
        and that the final output meets all requirements.""",
        verbose=True,
        allow_delegation=True,
        tools=[orchestrator_tool],
        llm_config={"model": "gpt-4o"}
    )

def create_data_correction_agent():
    """Create an agent specialized in verifying and correcting extracted data."""
    return Agent(
        role="Data Verification and Correction Specialist",
        goal="Verify the accuracy of extracted industry data and correct any misclassifications",
        backstory="""You are a highly skilled data analyst specializing in ISM Manufacturing Reports.
        Your expertise lies in ensuring data integrity and accurate industry classifications.
        Your task is to carefully examine extracted data and verify that industries are correctly
        categorized based on explicit mentions in the report text.""",
        verbose=True,
        allow_delegation=False,
        llm_config={
            "model": "gpt-4o",
            "temperature": 0.1,  # Lower temperature for more precise fact-based output
            "system_prompt": """
            You are a data verification specialist with extensive experience analyzing ISM Manufacturing Reports.
            Your task is to verify and correct the industry categorization from extracted data,
            ensuring that industries are correctly placed in the appropriate categories based on
            EXPLICIT statements in the report text. Pay particular attention to the exact phrasing 
            in the source text when determining categories. Never invent or assume data.
            
            ALWAYS PRESERVE THE EXACT MONTH AND YEAR from the original data without changing it.
            NEVER CHANGE THE MONTH_YEAR VALUE - copy it exactly as provided in the input data.
            
            When producing corrected data, return a complete dictionary that includes:
            - 'month_year' copied exactly from the original data
            - 'manufacturing_table' from the original data
            - 'index_summaries' from the original data
            - 'corrected_industry_data' with your corrections
            
            Be sure to look carefully for industries in both growing and declining categories for each index.
            
            CRITICAL: Ensure that industries are NOT duplicated across categories within the same index.
            For example, the same industry should not appear in both 'Growing' and 'Declining' categories
            for New Orders. This is a common error that needs correction.
            
            IMPORTANT: Remove any parsing artifacts that aren't actual industries, such as text like
            "in the following order", "are:", or industry names that are incomplete or duplicated.
            
            CRITICAL: Make sure to include ALL industries mentioned in the text in their appropriate
            categories. For example, if the text mentions 11 industries reporting a decline in New Orders,
            make sure all 11 are included in the 'Declining' category.
            
            Pay special attention to the format of the corrected_industry_data - follow exactly this structure:
            'corrected_industry_data': {
                'New Orders': {
                    'Growing': ['Industry1', 'Industry2', ...],
                    'Declining': ['Industry3', 'Industry4', ...]
                },
                'Production': {
                    'Growing': [...],
                    'Declining': [...]
                },
                ...
            }
            """
        }
    )