from crewai import Agent
from tools import (
    PDFExtractionTool,
    DataStructurerTool,
    DataValidatorTool,
    GoogleSheetsFormatterTool,
    PDFOrchestratorTool
)

def create_extractor_agent():
    return Agent(
        role="Document Extractor",
        goal="Extract all relevant data from ISM Manufacturing Report PDFs accurately",
        backstory="""You are an expert in data extraction who specializes in analyzing
        manufacturing reports. You excel at identifying key information from complex PDFs
        and transforming it into structured data.""",
        verbose=True,
        allow_delegation=False,
        tools=[PDFExtractionTool()],
        max_retries_on_error=3,
    )

def create_structurer_agent():
    return Agent(
        role="Data Organizer",
        goal="Convert extracted ISM data into properly structured formats",
        backstory="""You are a data organization specialist with deep knowledge of
        manufacturing indices and industry classifications. You ensure that all
        extracted data is correctly categorized and follows ISM's specific structure.""",
        verbose=True,
        allow_delegation=False,
        tools=[DataStructurerTool()],
        max_retries_on_error=3,
    )

def create_validator_agent():
    return Agent(
        role="QA & Validation Specialist",
        goal="Ensure all structured ISM data is complete, accurate, and follows expected formats",
        backstory="""You are a meticulous quality assurance specialist who verifies
        data integrity and catches errors before they propagate. You know exactly what
        makes ISM data valid and can identify any inconsistencies.""",
        verbose=True,
        allow_delegation=False,
        tools=[DataValidatorTool()],
        max_retries_on_error=3,
    )

def create_formatter_agent():
    return Agent(
        role="Output Generator",
        goal="Format and update Google Sheets with validated ISM data",
        backstory="""You are an expert in data presentation who specializes in
        Google Sheets integration. You know how to format data for clarity and
        ensure that updates don't overwrite existing information.""",
        verbose=True,
        allow_delegation=False,
        tools=[GoogleSheetsFormatterTool()],
        max_retries_on_error=3,
    )

def create_orchestrator_agent():
    return Agent(
        role="Workflow Controller",
        goal="Manage the processing of multiple ISM Manufacturing Report PDFs",
        backstory="""You are a skilled project manager who coordinates complex
        data processing workflows. You ensure that all PDFs are processed correctly
        and that the final output meets all requirements.""",
        verbose=True,
        allow_delegation=True,
        tools=[PDFOrchestratorTool()],
        max_retries_on_error=3,
    )