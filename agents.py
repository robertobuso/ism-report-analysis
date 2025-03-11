# agents.py
from crewai import Agent
from crewai.tools import BaseTool  # Import BaseTool directly from crewai

# Import your tool functions directly
from tools import (
    SimplePDFExtractionTool, 
    SimpleDataStructurerTool,
    DataValidatorTool, 
    GoogleSheetsFormatterTool,
    PDFOrchestratorTool
)

# Function to wrap your tools properly for crewAI
def create_tool_dict(name, description, func):
    """Create a tool dictionary that crewAI can handle."""
    return {
        "name": name,
        "description": description,
        "func": func
    }

def create_extractor_agent():
    # Create tool in the format crewAI expects
    pdf_tool = SimplePDFExtractionTool()
    tool_dict = create_tool_dict(
        name="extract_pdf_data",
        description="Extract data from an ISM Manufacturing Report PDF file",
        func=pdf_tool.run
    )
    
    return Agent(
        role="Document Extractor",
        goal="Extract all relevant data from ISM Manufacturing Report PDFs accurately",
        backstory="""You are an expert in data extraction who specializes in analyzing
        manufacturing reports. You excel at identifying key information from complex PDFs
        and transforming it into structured data.""",
        verbose=True,
        allow_delegation=False,
        tools=[tool_dict],
    )

def create_structurer_agent():
    structurer_tool = SimpleDataStructurerTool()
    tool_dict = create_tool_dict(
        name="structure_data",
        description="Structure extracted ISM Manufacturing Report data",
        func=structurer_tool.run
    )
    
    return Agent(
        role="Data Organizer",
        goal="Convert extracted ISM data into properly structured formats",
        backstory="""You are a data organization specialist with deep knowledge of
        manufacturing indices and industry classifications. You ensure that all
        extracted data is correctly categorized and follows ISM's specific structure.""",
        verbose=True,
        allow_delegation=False,
        tools=[tool_dict],
    )

def create_validator_agent():
    validator_tool = DataValidatorTool()
    tool_dict = create_tool_dict(
        name="validate_data",
        description="Validate structured ISM Manufacturing Report data",
        func=validator_tool.run
    )
    
    return Agent(
        role="QA & Validation Specialist",
        goal="Ensure all structured ISM data is complete, accurate, and follows expected formats",
        backstory="""You are a meticulous quality assurance specialist who verifies
        data integrity and catches errors before they propagate. You know exactly what
        makes ISM data valid and can identify any inconsistencies.""",
        verbose=True,
        allow_delegation=False,
        tools=[tool_dict],
    )

def create_formatter_agent():
    formatter_tool = GoogleSheetsFormatterTool()
    tool_dict = create_tool_dict(
        name="format_for_sheets",
        description="Format and update Google Sheets with validated ISM data",
        func=formatter_tool.run
    )
    
    return Agent(
        role="Output Generator",
        goal="Format and update Google Sheets with validated ISM data",
        backstory="""You are an expert in data presentation who specializes in
        Google Sheets integration. You know how to format data for clarity and
        ensure that updates don't overwrite existing information.""",
        verbose=True,
        allow_delegation=False,
        tools=[tool_dict],
    )

def create_orchestrator_agent():
    orchestrator_tool = PDFOrchestratorTool()
    tool_dict = create_tool_dict(
        name="orchestrate_processing",
        description="Orchestrate the processing of multiple ISM Manufacturing Report PDFs",
        func=orchestrator_tool.run
    )
    
    return Agent(
        role="Workflow Controller",
        goal="Manage the processing of multiple ISM Manufacturing Report PDFs",
        backstory="""You are a skilled project manager who coordinates complex
        data processing workflows. You ensure that all PDFs are processed correctly
        and that the final output meets all requirements.""",
        verbose=True,
        allow_delegation=True,
        tools=[tool_dict],
    )