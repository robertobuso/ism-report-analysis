from crewai import Agent
from langchain.tools import Tool
from tools_new import (
    SimplePDFExtractionTool,
    SimpleDataStructurerTool,
    DataValidatorTool,
    GoogleSheetsFormatterTool,
    PDFOrchestratorTool
)

def create_extractor_agent():
    # Create LangChain tool from our BaseTool implementation
    tool = ()
    extraction_tool = Tool(
        name=tool.name,
        func=tool._run,
        description=tool.description
    )
    
    return Agent(
        role="Document Extractor",
        goal="Extract all relevant data from ISM Manufacturing Report PDFs accurately",
        backstory="""You are an expert in data extraction who specializes in analyzing
        manufacturing reports. You excel at identifying key information from complex PDFs
        and transforming it into structured data.""",
        verbose=True,
        allow_delegation=False,
        tools=[extraction_tool],
    )

def create_structurer_agent():
    # Create LangChain tool from our BaseTool implementation
    tool = SimpleDataStructurerTool()
    structurer_tool = Tool(
        name=tool.name,
        func=tool._run,
        description=tool.description
    )
    
    return Agent(
        role="Data Organizer",
        goal="Convert extracted ISM data into properly structured formats",
        backstory="""You are a data organization specialist with deep knowledge of
        manufacturing indices and industry classifications. You ensure that all
        extracted data is correctly categorized and follows ISM's specific structure.""",
        verbose=True,
        allow_delegation=False,
        tools=[structurer_tool],
    )

def create_validator_agent():
    # Create LangChain tool from our BaseTool implementation
    tool = DataValidatorTool()
    validator_tool = Tool(
        name=tool.name,
        func=tool._run,
        description=tool.description
    )
    
    return Agent(
        role="QA & Validation Specialist",
        goal="Ensure all structured ISM data is complete, accurate, and follows expected formats",
        backstory="""You are a meticulous quality assurance specialist who verifies
        data integrity and catches errors before they propagate. You know exactly what
        makes ISM data valid and can identify any inconsistencies.""",
        verbose=True,
        allow_delegation=False,
        tools=[validator_tool],
    )

def create_formatter_agent():
    # Create LangChain tool from our BaseTool implementation
    tool = GoogleSheetsFormatterTool()
    formatter_tool = Tool(
        name=tool.name,
        func=tool._run,
        description=tool.description
    )
    
    return Agent(
        role="Output Generator",
        goal="Format and update Google Sheets with validated ISM data",
        backstory="""You are an expert in data presentation who specializes in
        Google Sheets integration. You know how to format data for clarity and
        ensure that updates don't overwrite existing information.""",
        verbose=True,
        allow_delegation=False,
        tools=[formatter_tool],
    )

def create_orchestrator_agent():
    # Create LangChain tool from our BaseTool implementation
    tool = PDFOrchestratorTool()
    orchestrator_tool = Tool(
        name=tool.name,
        func=tool._run,
        description=tool.description
    )
    
    return Agent(
        role="Workflow Controller",
        goal="Manage the processing of multiple ISM Manufacturing Report PDFs",
        backstory="""You are a skilled project manager who coordinates complex
        data processing workflows. You ensure that all PDFs are processed correctly
        and that the final output meets all requirements.""",
        verbose=True,
        allow_delegation=True,
        tools=[orchestrator_tool],
    )