import PyPDF2
import re
import json
import logging
import os
import sqlite3
import traceback
from datetime import datetime
from db_utils import get_db_connection, parse_date, initialize_database

# Create logs directory first
os.makedirs("logs", exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='logs/ism_analysis.log'
)
logger = logging.getLogger(__name__)

def extract_text_from_pdf(pdf_path):
    """Extract all text from a PDF file."""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                text += page.extract_text()
            return text
    except Exception as e:
        logger.error(f"Error extracting text from PDF {pdf_path}: {str(e)}")
        return None

def extract_manufacturing_at_a_glance(text):
    """Extract the Manufacturing at a Glance table."""
    try:
        # Pattern to match the table section
        pattern = r"MANUFACTURING AT A GLANCE.*?(?:Month|COMMODITIES REPORTED)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(0).strip()
        
        # Fallback pattern
        pattern2 = r"MANUFACTURING AT A GLANCE.*?OVERALL ECONOMY"
        match2 = re.search(pattern2, text, re.DOTALL | re.IGNORECASE)
        if match2:
            return match2.group(0).strip()
            
        return None
    except Exception as e:
        logger.error(f"Error extracting Manufacturing at a Glance: {str(e)}")
        return None

def extract_month_year(text):
    """Extract the month and year from the report."""
    try:
        # Try multiple patterns to find month and year
        patterns = [
            # Pattern for "Month YYYY Manufacturing"
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\s+MANUFACTURING",
            # Pattern for "Manufacturing at a Glance Month YYYY"
            r"MANUFACTURING AT A GLANCE\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
            # Pattern for "Month YYYY Manufacturing Index"
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\s+MANUFACTURING INDEX",
            # Try to find in PMI Index section
            r"Manufacturing PMI®.*?(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
            # Look for "MONTH YEAR INDEX SUMMARIES"
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4}) MANUFACTURING INDEX SUMMARIES",
            # Look for "Report On Business® Month YEAR"
            r"Report\s+On\s+Business®\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return f"{match.group(1)} {match.group(2)}"
        
        # If no match is found through patterns, try to find dates in the content
        all_dates = re.findall(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", text, re.IGNORECASE)
        if all_dates:
            # Use the most frequent date
            date_counts = {}
            for month, year in all_dates:
                date = f"{month} {year}"
                date_counts[date] = date_counts.get(date, 0) + 1
            
            most_common_date = max(date_counts.items(), key=lambda x: x[1])[0]
            return most_common_date
        
        return None
    except Exception as e:
        logger.error(f"Error extracting month and year: {str(e)}")
        return None
    
def extract_index_summaries(text):
    """Extract summaries for each index (New Orders, Production, etc.)."""
    indices = [
        "NEW ORDERS", "PRODUCTION", "EMPLOYMENT", "SUPPLIER DELIVERIES",
        "INVENTORIES", "CUSTOMERS' INVENTORIES", "PRICES", "BACKLOG OF ORDERS",
        "NEW EXPORT ORDERS", "IMPORTS"
    ]
    
    summaries = {}
    
    # First, find the start of the index summaries section
    summaries_start = re.search(r"MANUFACTURING INDEX SUMMARIES", text, re.IGNORECASE)
    if summaries_start:
        text = text[summaries_start.start():]
    
    # Add another starter pattern to catch summaries
    manufacturing_pmi = re.search(r"MANUFACTURING PMI®", text, re.IGNORECASE)
    if manufacturing_pmi:
        text = text[manufacturing_pmi.start():]
    
    for i, index in enumerate(indices):
        try:
            # If this is the last index, search until the end or next major section
            if i == len(indices) - 1:
                end_pattern = r"(?:MANUFACTURING AT A GLANCE|WHAT RESPONDENTS ARE SAYING|COMMODITIES REPORTED|BUYING POLICY)"
                pattern = rf"{index}[\s\S]*?(.*?)(?:{end_pattern}|$)"
            else:
                # Otherwise, search until the next index
                next_index = indices[i+1]
                pattern = rf"{index}[\s\S]*?(.*?)(?:\s|\n){next_index}"
            
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            
            # If primary pattern fails, try a fallback pattern
            if not match:
                # Create a smaller search window around the likely location of this index
                index_pos = text.upper().find(index)
                if index_pos != -1:
                    search_window = text[index_pos:index_pos + 5000]  # Look at next 5000 chars
                    
                    # Try to find the section between this index and the next section
                    if i < len(indices) - 1:
                        next_index = indices[i+1]
                        alt_pattern = rf"{index}(.*?)(?:{next_index})"
                        match = re.search(alt_pattern, search_window, re.DOTALL | re.IGNORECASE)
                    
                    # If still no match, try a more general pattern
                    if not match:
                        alt_pattern = rf"{index}(.*?)(?:[\r\n]{{2,}}[A-Z][A-Z\s]+[\r\n])"
                        match = re.search(alt_pattern, search_window, re.DOTALL | re.IGNORECASE)
            
            if match:
                summary_text = match.group(1).strip()
                clean_name = index.title().replace("'S", "'s")
                summaries[clean_name.replace("New Orders", "New Orders").replace("Backlog Of Orders", "Backlog of Orders").replace("New Export Orders", "New Export Orders")] = summary_text
            else:
                logger.warning(f"Could not extract summary for {index}")
        except Exception as e:
            logger.error(f"Error extracting {index} summary: {str(e)}")
    
    return summaries

def extract_industry_mentions(text, indices):
    """
    Extract industries mentioned for each index, using improved parsing to handle 
    composite industry names correctly while preserving the exact order as listed in the report.
    """
    industry_data = {}
    
    # Loop through each index and its summary text
    for index, summary in indices.items():
        try:
            # Initialize all pattern matches as None at the beginning
            growth_match = None
            decline_match = None
            slower_match = None
            faster_match = None
            higher_match = None
            lower_match = None
            too_high_match = None
            too_low_match = None
            increasing_match = None
            decreasing_match = None

            # Initialize categories based on index type
            if index == "Supplier Deliveries":
                industry_data[index] = {"Slower": [], "Faster": []}
            elif index == "Inventories":
                industry_data[index] = {"Higher": [], "Lower": []}
            elif index == "Customers' Inventories":
                industry_data[index] = {"Too High": [], "Too Low": []}
            elif index == "Prices":
                industry_data[index] = {"Increasing": [], "Decreasing": []}
            else:
                industry_data[index] = {"Growing": [], "Declining": []}
            
            # Process based on index type
            if index == "Supplier Deliveries":
                # Extract industries reporting slower deliveries
                slower_pattern = r"The (?:[\w\s]+) (?:industries|manufacturing industries) (?:reporting|that reported) slower(?: supplier)? deliveries(?:[^:]*?)(?:are|—|in|:|-)(?:[^:]*?)(?:order|the following order|listed in order|:)[^:]*?([^\.]+)"
                slower_match = re.search(slower_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Fallback pattern if first one doesn't match
                if not slower_match:
                    slower_fallback = r"industries reporting slower supplier deliveries(?:[^:]*?)(?:are|—|in|:|-)([^\.]+)"
                    slower_match = re.search(slower_fallback, summary, re.IGNORECASE | re.DOTALL)
                
                # Extract industries reporting faster deliveries
                faster_pattern = r"The (?:[\w\s]+) (?:industries|manufacturing industries) (?:reporting|that reported) faster(?: supplier)? deliveries(?:[^:]*?)(?:are|—|in|:|-)(?:[^:]*?)(?:order|the following order|listed in order|:)[^:]*?([^\.]+)"
                faster_match = re.search(faster_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Fallback pattern if first one doesn't match
                if not faster_match:
                    faster_fallback = r"industries reporting faster supplier deliveries(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    faster_match = re.search(faster_fallback, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                slower = []
                if slower_match:
                    slower_text = slower_match.group(1).strip()
                    slower = preserve_order_industry_list(slower_text)
                
                faster = []
                if faster_match:
                    faster_text = faster_match.group(1).strip()
                    faster = preserve_order_industry_list(faster_text)
                
                industry_data[index] = {
                    "Slower": slower,
                    "Faster": faster
                }
                
            elif index == "Inventories":
                # Extract industries reporting higher inventories
                higher_pattern = r"The (?:[\w\s]+) industries reporting (?:higher|increased|increasing|growing|growth in) inventories(?:[^:]*?)(?:listed in|—|in|:|-)(?:[^:]*?)(?:order|the following order|:)[^:]*?([^\.]+)"
                higher_match = re.search(higher_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Fallback pattern if first one doesn't match
                if not higher_match:
                    higher_fallback = r"industries reporting (?:higher|increased|increasing) inventories(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    higher_match = re.search(higher_fallback, summary, re.IGNORECASE | re.DOTALL)
                
                # Extract industries reporting lower inventories
                lower_pattern = r"The (?:[\w\s]+) industries reporting (?:lower|decreased|declining|lower or decreased) inventories(?:[^:]*?)(?:in the following|—|in|:|-)(?:[^:]*?)(?:order|the following order|:)[^:]*?([^\.]+)"
                lower_match = re.search(lower_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Fallback pattern if first one doesn't match
                if not lower_match:
                    lower_fallback = r"industries reporting (?:lower|decreased|declining) inventories(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    lower_match = re.search(lower_fallback, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                higher = []
                if higher_match:
                    higher_text = higher_match.group(1).strip()
                    higher = preserve_order_industry_list(higher_text)
                
                lower = []
                if lower_match:
                    lower_text = lower_match.group(1).strip()
                    lower = preserve_order_industry_list(lower_text)
                
                industry_data[index] = {
                    "Higher": higher,
                    "Lower": lower
                }
                
            elif index == "Customers' Inventories":
                # Extract industries reporting customers' inventories as too high
                too_high_pattern = r"The (?:[\w\s]+) (?:industries|industry) reporting (?:customers['']s?|customers) (?:inventories|inventory) as too high(?:[^:]*?)(?:are|—|in|:|-)(?:[^:]*?)(?:order|the following order|:)?[^:]*?([^\.]+)"
                too_high_match = re.search(too_high_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Fallback pattern with more variations
                if not too_high_match:
                    too_high_fallback = r"(?:industries|industry) reporting (?:customers['']s?|customers) (?:inventories|inventory) as too high(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    too_high_match = re.search(too_high_fallback, summary, re.IGNORECASE | re.DOTALL)
                
                # More inclusive fallback pattern
                if not too_high_match:
                    too_high_fallback2 = r"(?:industries|industry) (?:reporting|that reported) .*?too high(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    too_high_match = re.search(too_high_fallback2, summary, re.IGNORECASE | re.DOTALL)
                
                # Extract industries reporting customers' inventories as too low
                too_low_pattern = r"The (?:[\w\s]+) (?:industries|industry) reporting (?:customers['']s?|customers) (?:inventories|inventory) as too low(?:[^:]*?)(?:are|—|in|:|-)(?:[^:]*?)(?:order|the following order|:)?[^:]*?([^\.]+)"
                too_low_match = re.search(too_low_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Fallback pattern with more variations
                if not too_low_match:
                    too_low_fallback = r"(?:industries|industry) reporting (?:customers['']s?|customers) (?:inventories|inventory) as too low(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    too_low_match = re.search(too_low_fallback, summary, re.IGNORECASE | re.DOTALL)
                
                # More inclusive fallback pattern
                if not too_low_match:
                    too_low_fallback2 = r"(?:industries|industry) (?:reporting|that reported) .*?too low(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    too_low_match = re.search(too_low_fallback2, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                too_high = []
                if too_high_match:
                    too_high_text = too_high_match.group(1).strip()
                    too_high = preserve_order_industry_list(too_high_text)
                
                too_low = []
                if too_low_match:
                    too_low_text = too_low_match.group(1).strip()
                    too_low = preserve_order_industry_list(too_low_text)
                
                industry_data[index] = {
                    "Too High": too_high,
                    "Too Low": too_low
                }
                
            elif index == "Prices":
                # Extract industries reporting price increases
                increasing_pattern = r"(?:In (?:[\w\s]+), |The |)(?:[\w\s]+) industries (?:that |)(?:reported|reporting) (?:paying |higher |increased |increasing |price increases)(?:prices|price|prices for raw materials)?(?:[^:]*?)(?:in order|order|:|—|-)(?:[^:]*?)(?:are|:)([^\.]+)"
                increasing_match = re.search(increasing_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Fallback pattern if first one doesn't match
                if not increasing_match:
                    increasing_fallback = r"industries (?:that |)(?:reported|reporting) (?:paying |higher |increased |increasing) prices(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    increasing_match = re.search(increasing_fallback, summary, re.IGNORECASE | re.DOTALL)
                
                # Extract industries reporting price decreases
                decreasing_pattern = r"(?:The only industry|The [\w\s]+ industries) (?:that |)(?:reported|reporting) (?:paying |lower |decreased |decreasing |price decreases)(?:prices|price|prices for raw materials)?(?:[^:]*?)(?:in order|order|:|—|-)(?:[^:]*?)(?:are|is):?([^\.]+)"
                decreasing_match = re.search(decreasing_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Special case for "only industry" pattern
                only_industry = r"The only industry that reported paying decreased prices(?:[^:]*?)is ([^\.]+)"
                only_match = re.search(only_industry, summary, re.IGNORECASE | re.DOTALL)
                if only_match:
                    decreasing_match = only_match
                
                # Fallback pattern if first one doesn't match
                if not decreasing_match:
                    decreasing_fallback = r"industries (?:that |)(?:reported|reporting) (?:paying |lower |decreased |decreasing) prices(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    decreasing_match = re.search(decreasing_fallback, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                increasing = []
                if increasing_match:
                    increasing_text = increasing_match.group(1).strip()
                    increasing = preserve_order_industry_list(increasing_text)
                
                decreasing = []
                if decreasing_match:
                    decreasing_text = decreasing_match.group(1).strip()
                    decreasing = preserve_order_industry_list(decreasing_text)
                
                industry_data[index] = {
                    "Increasing": increasing,
                    "Decreasing": decreasing
                }
                
            elif index == "Imports":
                # Extract industries reporting increased imports
                growth_pattern = r"The (?:[\w\s]+) (?:industries|industry) reporting (?:an |a |)(?:increase|increase in|higher|growth in) (?:import volumes|imports)(?:[^:]*?)(?:are|—|:|in|-)(?:[^:]*?)(?:order|the following order|:)?[^:]*?([^\.]+)"
                growth_match = re.search(growth_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Fallback pattern if first one doesn't match
                if not growth_match:
                    growth_fallback = r"(?:industries|industry) reporting (?:an |a |)(?:increase|higher|growth) in imports(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    growth_match = re.search(growth_fallback, summary, re.IGNORECASE | re.DOTALL)
                
                # Extract industries reporting decreased imports
                decline_pattern = r"The (?:[\w\s]+) (?:industries|industry) (?:that |)(?:reported|reporting) (?:lower|decreased|a decrease in|lower volumes of) (?:import volumes|imports)(?:[^:]*?)(?:are|—|:|in|-)(?:[^:]*?)(?:order|the following order|:)?[^:]*?([^\.]+)"
                decline_match = re.search(decline_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Fallback pattern if first one doesn't match
                if not decline_match:
                    decline_fallback = r"(?:industries|industry) (?:that |)(?:reported|reporting) (?:lower|decreased|a decrease|contraction) in imports(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    decline_match = re.search(decline_fallback, summary, re.IGNORECASE | re.DOTALL)
                
                # More inclusive fallback pattern to catch other variations
                if not decline_match:
                    decline_fallback2 = r"The (?:[\w\s]+) (?:industries|industry) that (?:reported|reporting) lower volumes of imports(?:[^:]*?)(?:are|:|in|-)([^\.]+)"
                    decline_match = re.search(decline_fallback2, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                growing = []
                if growth_match:
                    growing_text = growth_match.group(1).strip()
                    growing = preserve_order_industry_list(growing_text)
                
                declining = []
                if decline_match:
                    declining_text = decline_match.group(1).strip()
                    declining = preserve_order_industry_list(declining_text)
                
                industry_data[index] = {
                    "Growing": growing,
                    "Declining": declining
                }
                
            elif index == "New Export Orders":
                # Extract industries reporting increased export orders
                growth_pattern = r"The (?:[\w\s]+) industries reporting growth in new export orders(?:[^:]*?)(?:are|—|:|-)([^\.]+)"
                growth_match = re.search(growth_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Fallback pattern if first one doesn't match
                if not growth_match:
                    growth_fallback = r"industries reporting (?:an |a |)(?:increase|growth) in (?:new |)export orders(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    growth_match = re.search(growth_fallback, summary, re.IGNORECASE | re.DOTALL)
                
                # Extract industries reporting decreased export orders
                decline_pattern = r"The (?:[\w\s]+) industries reporting a decrease in new export orders(?:[^:]*?)(?:are|—|:|-)([^\.]+)"
                decline_match = re.search(decline_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Fallback pattern if first one doesn't match
                if not decline_match:
                    decline_fallback = r"industries reporting (?:a |)(?:decline|decrease|contraction) in (?:new |)export orders(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    decline_match = re.search(decline_fallback, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                growing = []
                if growth_match:
                    growing_text = growth_match.group(1).strip()
                    growing = preserve_order_industry_list(growing_text)
                
                declining = []
                if decline_match:
                    declining_text = decline_match.group(1).strip()
                    declining = preserve_order_industry_list(declining_text)
                
                industry_data[index] = {
                    "Growing": growing,
                    "Declining": declining
                }
                
            elif index == "Backlog of Orders":
                # Enhanced pattern for growing backlogs with more variations
                growth_pattern = r"(?:[\w\s]+) (?:industries|manufacturing industries|industry) (?:reported|reporting|report) (?:growth|increase|expansion) in (?:order |)backlogs(?:[^:]*?)(?:are|—|:|-)([^\.]+)"
                growth_match = re.search(growth_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Additional fallback patterns
                if not growth_match:
                    growth_fallback = r"industries reporting growth in (?:order |)backlogs(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    growth_match = re.search(growth_fallback, summary, re.IGNORECASE | re.DOTALL)
                
                if not growth_match:
                    growth_fallback2 = r"(?:Of|The) (?:[\w\s]+) manufacturing industries, (?:[\w\s]+) reported growth in (?:order |)backlogs(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    growth_match = re.search(growth_fallback2, summary, re.IGNORECASE | re.DOTALL)
                
                # Enhanced pattern for declining backlogs with more variations
                decline_pattern = r"(?:[\w\s]+) (?:industries|manufacturing industries|industry) reporting (?:lower|decrease|contraction|decline) in (?:order |)backlogs(?:[^:]*?)(?:are|—|:|-)([^\.]+)"
                decline_match = re.search(decline_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Additional fallback patterns
                if not decline_match:
                    decline_fallback = r"industries reporting (?:lower|decreased|a decrease in|declining|contraction in) (?:order |)backlogs(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    decline_match = re.search(decline_fallback, summary, re.IGNORECASE | re.DOTALL)
                
                if not decline_match:
                    decline_fallback2 = r"(?:The|In) (?:[\w\s]+) industries (?:reporting|that reported) (?:lower|decreased|a decrease in) backlogs (?:in|for) (?:February|January|March|April|May|June|July|August|September|October|November|December)(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    decline_match = re.search(decline_fallback2, summary, re.IGNORECASE | re.DOTALL)
                    
                # Process matches
                growing = []
                if growth_match:
                    growing_text = growth_match.group(1).strip()
                    growing = preserve_order_industry_list(growing_text)
                
                declining = []
                if decline_match:
                    declining_text = decline_match.group(1).strip()
                    declining = preserve_order_industry_list(declining_text)
                
                industry_data[index] = {
                    "Growing": growing,
                    "Declining": declining
                }
                
            elif index == "Employment":
                # Enhanced pattern for growing employment with more variations
                growth_pattern = r"(?:[\w\s]+) (?:industries|manufacturing industries|industry) (?:reporting|report|reported) (?:employment|hiring|workforce) (?:growth|increase|expansion|gains)(?:[^:]*?)(?:are|—|:|-)([^\.]+)"
                growth_match = re.search(growth_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Additional fallback patterns
                if not growth_match:
                    growth_fallback = r"industries reporting (?:employment|hiring|workforce) growth(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    growth_match = re.search(growth_fallback, summary, re.IGNORECASE | re.DOTALL)
                
                if not growth_match:
                    growth_fallback2 = r"(?:Of|The) (?:the |)(?:[\w\s]+) manufacturing industries, (?:[\w\s]+) reported (?:employment|hiring|workforce) growth(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    growth_match = re.search(growth_fallback2, summary, re.IGNORECASE | re.DOTALL)
                
                # Enhanced pattern for declining employment with more variations
                decline_pattern = r"(?:[\w\s]+) (?:industries|manufacturing industries|industry) reporting (?:a decrease|decreases|lower|reduced|reduction|decline) in (?:employment|hiring|workforce|headcount)(?:[^:]*?)(?:are|—|:|-)([^\.]+)"
                decline_match = re.search(decline_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Additional fallback patterns
                if not decline_match:
                    decline_fallback = r"industries reporting (?:a |)(?:decrease|decline|reduction|contraction) in (?:employment|hiring|workforce|headcount)(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    decline_match = re.search(decline_fallback, summary, re.IGNORECASE | re.DOTALL)
                
                if not decline_match:
                    decline_fallback2 = r"(?:The |)(?:[\w\s]+) industries reporting a decrease in employment(?:[^:]*?)(?:are|:|in the following order|-)([^\.]+)"
                    decline_match = re.search(decline_fallback2, summary, re.IGNORECASE | re.DOTALL)
                    
                # Process matches
                growing = []
                if growth_match:
                    growing_text = growth_match.group(1).strip()
                    growing = preserve_order_industry_list(growing_text)
                
                declining = []
                if decline_match:
                    declining_text = decline_match.group(1).strip()
                    declining = preserve_order_industry_list(declining_text)
                
                industry_data[index] = {
                    "Growing": growing,
                    "Declining": declining
                }
                
            else:  # Default pattern for growth/decline - including "New Orders"
                # Extract industries reporting growth
                growth_pattern = r"The (?:[\w\s]+) (?:industries|manufacturing industries) (?:that |)(?:reporting|reported|report) (?:growth|expansion|increase|growing|increased|an increase|higher|growth in)(?: in| of)? (?:[\w\s&]+)?(?:[^:]*?)(?:are|—|:|in|-|,)(?:.+?)?(?:order|the following order|listed in order|:)[^:]*?([^\.]+)"
                growth_match = re.search(growth_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Specific pattern for New Orders growth
                if index == "New Orders":
                    new_orders_growth = r"The (?:[\w\s]+) (?:industries|manufacturing industries) that reported growth in new orders in February,(?:[^:]*?)(?:are|in order|:|-)(?:[^:]*?)(?:order|:)[^:]*?([^\.]+)"
                    new_orders_match = re.search(new_orders_growth, summary, re.IGNORECASE | re.DOTALL)
                    if new_orders_match:
                        growth_match = new_orders_match
                
                # Fallback pattern if first one doesn't match
                if not growth_match:
                    growth_fallback = r"(?:[\w\s]+) industries (?:that |)(?:reporting|reported|report) growth(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    growth_match = re.search(growth_fallback, summary, re.IGNORECASE | re.DOTALL)
                
                # Extract industries reporting decline
                decline_pattern = r"The (?:[\w\s]+) (?:industries|manufacturing industries) (?:that |)(?:reporting|reported|report) (?:a |an |)(?:decline|contraction|decrease|declining|decreased|lower)(?: in| of)? (?:[\w\s&]+)?(?:[^:]*?)(?:are|—|:|in|-|,)(?:.+?)?(?:order|the following order|listed in order|:)[^:]*?([^\.]+)"
                decline_match = re.search(decline_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Add specific fallback patterns for New Orders decline
                if index == "New Orders":
                    # More specific pattern for New Orders with explicitly mentioned declining industries
                    new_orders_decline = r"The (?:[\w\s]+) (?:industries|industry) (?:reporting|that reported) a decline in new orders(?:[^:]*?)(?:are|in order|:|-)(?:[^:]*?)(?:order|:)?[^:]*?([^\.]+)"
                    new_orders_decline_match = re.search(new_orders_decline, summary, re.IGNORECASE | re.DOTALL)
                    if new_orders_decline_match:
                        decline_match = new_orders_decline_match
                        
                    # Additional fallback pattern for New Orders declining
                    if not decline_match:
                        new_orders_decline2 = r"(?:industries|industry) (?:reporting|that reported) a decline in (?:new orders|orders)(?:[^:]*?)(?:are|:|-)([^\.]+)"
                        decline_match = re.search(new_orders_decline2, summary, re.IGNORECASE | re.DOTALL)
                        
                    # Another fallback looking for common formatting in reports
                    if not decline_match:
                        new_orders_decline3 = r"industries reporting a decline in (?:February|January|March|April|May|June|July|August|September|October|November|December)(?:[^:]*?)(?:are|:|-)([^\.]+)"
                        decline_match = re.search(new_orders_decline3, summary, re.IGNORECASE | re.DOTALL)
                
                # Fallback pattern if first one doesn't match
                if not decline_match:
                    decline_fallback = r"(?:[\w\s]+) industries (?:that |)(?:reporting|reported|report) (?:a |)(?:decline|decrease|contraction)(?:[^:]*?)(?:are|:|-)([^\.]+)"
                    decline_match = re.search(decline_fallback, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                growing = []
                if growth_match:
                    growing_text = growth_match.group(1).strip()
                    growing = preserve_order_industry_list(growing_text)
                
                declining = []
                if decline_match:
                    declining_text = decline_match.group(1).strip()
                    declining = preserve_order_industry_list(declining_text)
                
                industry_data[index] = {
                    "Growing": growing,
                    "Declining": declining
                }
            
            # Clean up any duplicates in the categories    
            if index in industry_data:
                for category, industries in industry_data[index].items():
                    # Remove duplicates while preserving order
                    seen = set()
                    industry_data[index][category] = [x for x in industries if not (x in seen or seen.add(x))]
                    
                    # Log warning if no industries found for a category
                    if not industry_data[index][category]:
                        logger.warning(f"No industries found for {index} - {category}")
                        
        except Exception as e:
            logger.error(f"Error extracting industry mentions for {index}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
             # Initialize with empty categories if an error occurs
            if index not in industry_data:
                if index == "Supplier Deliveries":
                    industry_data[index] = {"Slower": [], "Faster": []}
                elif index == "Inventories":
                    industry_data[index] = {"Higher": [], "Lower": []}
                elif index == "Customers' Inventories":
                    industry_data[index] = {"Too High": [], "Too Low": []}
                elif index == "Prices":
                    industry_data[index] = {"Increasing": [], "Decreasing": []}
                else:
                    industry_data[index] = {"Growing": [], "Declining": []}
    
    # Extra validation for the data
    for index, categories in industry_data.items():
        # Ensure there are no duplicate industries across categories in the same index
        all_industries = []
        industries_seen = {}
        
        for category, industries_list in categories.items():
            for i, industry in enumerate(industries_list[:]):
                # Skip invalid entries
                if not industry or not isinstance(industry, str):
                    continue
                    
                # Skip parsing artifacts
                if ("following order" in industry.lower() or 
                    "are:" in industry.lower() or
                    industry.startswith(',') or 
                    industry.startswith(':') or
                    len(industry.strip()) < 3):
                    continue
                    
                industry = industry.strip()
                
                # Check if this industry is already in another category within this index
                if industry in all_industries:
                    # Remove from the less likely category based on context
                    current_category = category
                    other_category = industries_seen[industry]
                    
                    # Keep in primary category based on index type
                    primary_categories = {
                        "New Orders": "Growing",
                        "Production": "Growing",
                        "Employment": "Growing",
                        "Supplier Deliveries": "Slower",
                        "Inventories": "Higher",
                        "Customers' Inventories": "Too High",
                        "Prices": "Increasing",
                        "Backlog of Orders": "Growing",
                        "New Export Orders": "Growing",
                        "Imports": "Growing"
                    }
                    
                    # If the current category is the primary category, keep it here and remove from the other
                    if current_category == primary_categories.get(index, current_category):
                        # Find and remove from the other category
                        if industry in categories[other_category]:
                            categories[other_category].remove(industry)
                            logger.info(f"Removed duplicate industry '{industry}' from {index} - {other_category}")
                    else:
                        # Remove from current category
                        categories[current_category][i] = None
                        logger.info(f"Removed duplicate industry '{industry}' from {index} - {current_category}")
                else:
                    all_industries.append(industry)
                    industries_seen[industry] = category
        
        # Remove None values that were marked for deletion
        for category in categories:
            categories[category] = [ind for ind in categories[category] if ind is not None]

    # Return the cleaned up industry data
    return industry_data

def preserve_order_industry_list(text):
    """
    Clean and intelligently split a list of industries into separate items
    while preserving the exact order as listed in the original report.
    """
    if not text:
        return []
    
    # First, standardize the text by removing formatting and special characters
    cleaned_text = text.strip()
    
    # Replace special control characters
    cleaned_text = re.sub(r'[\n\r\t]+', ' ', cleaned_text)
    
    # Primary split: Use semicolons as the main delimiter
    # This is safer than using commas since semicolons are more likely to separate distinct industries
    items = []
    if ';' in cleaned_text:
        # Split by semicolons, which are the primary delimiter between industries
        raw_items = [part.strip() for part in cleaned_text.split(';')]
    else:
        # If no semicolons, comma splitting is a fallback but riskier
        raw_items = [part.strip() for part in cleaned_text.split(',')]
    
    # Process the last item which might have "and" prefixing the last industry
    if raw_items and len(raw_items) > 0:
        last_item = raw_items[-1]
        if last_item.lower().startswith('and '):
            raw_items[-1] = last_item[4:].strip()
    
    # Process each item to ensure proper formatting
    for item in raw_items:
        item = item.strip()
        
        # Skip empty items
        if not item:
            continue
            
        # Clean up the item
        item = re.sub(r'\s*\(\d+\)\s*$', '', item)  # Remove footnote numbers
        item = re.sub(r'\s*\*+\s*$', '', item)      # Remove trailing asterisks
        item = re.sub(r'^\s*-\s*', '', item)        # Remove leading dashes
        
        # Only add non-empty, meaningful items
        if item and len(item) > 1:
            items.append(item)
    
    return items

def parse_ism_report(pdf_path):
    """Parse an ISM manufacturing report and extract key data."""
    try:
        # Extract text from PDF
        text = extract_text_from_pdf(pdf_path)
        if not text:
            logger.error(f"Failed to extract text from {pdf_path}")
            return None
        
        # Log a sample of the text for debugging
        logger.debug(f"Extracted text sample (first 1000 chars): {text[:1000]}")
        
        # Extract month and year
        month_year = extract_month_year(text)
        if not month_year:
            logger.warning(f"Could not extract month and year from {pdf_path}")
            # Try to infer from filename or modification date as fallback
            filename = os.path.basename(pdf_path)
            match = re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*[-_\s]?(\d{2,4})', filename, re.IGNORECASE)
            if match:
                month_map = {
                    'jan': 'January', 'feb': 'February', 'mar': 'March', 'apr': 'April',
                    'may': 'May', 'jun': 'June', 'jul': 'July', 'aug': 'August',
                    'sep': 'September', 'oct': 'October', 'nov': 'November', 'dec': 'December'
                }
                month = month_map.get(match.group(1).lower()[:3], 'Unknown')
                year = match.group(2)
                if len(year) == 2:
                    year = f"20{year}"
                month_year = f"{month} {year}"
            else:
                # Use file modification time as last resort
                mod_time = os.path.getmtime(pdf_path)
                dt = datetime.fromtimestamp(mod_time)
                month_year = dt.strftime("%B %Y")
        
        logger.info(f"Extracted month and year: {month_year}")
        
        # Extract the Manufacturing at a Glance table
        manufacturing_table = extract_manufacturing_at_a_glance(text)
        if not manufacturing_table:
            logger.warning(f"Could not extract manufacturing table from {pdf_path}")
        
        # Extract index-specific summaries
        index_summaries = extract_index_summaries(text)
        if not index_summaries:
            logger.warning(f"Could not extract index summaries from {pdf_path}")
        
        # Log which indices were found
        logger.info(f"Extracted summaries for indices: {', '.join(index_summaries.keys())}")
        
        # Extract industry mentions for each index
        industry_data = extract_industry_mentions(text, index_summaries)
        
        # Log extracted industry data for debugging
        for index, categories in industry_data.items():
            for category, industries in categories.items():
                logger.debug(f"Extracted for {index} - {category}: {len(industries)} industries")
                if not industries:
                    logger.warning(f"No industries found for {index} - {category}")
            
        # Create the result dictionary
        extracted_data = {
            "month_year": month_year,
            "manufacturing_table": manufacturing_table,
            "index_summaries": index_summaries,
            "industry_data": industry_data
        }
            
        # Store the extracted data in the database
        from db_utils import store_report_data_in_db
        try:
            store_result = store_report_data_in_db(extracted_data, pdf_path)
            
            if store_result:
                logger.info(f"Successfully stored data from {pdf_path} in database")
            else:
                logger.warning(f"Failed to store data from {pdf_path} in database")
        except Exception as e:
            logger.error(f"Error storing data in database: {str(e)}")
            # Continue processing to return the data even if database storage fails
        
        return extracted_data

    except Exception as e:
        logger.error(f"Error parsing ISM report: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None
    
def store_report_data_in_db(extracted_data, pdf_path):
    """
    Store the extracted report data in the SQLite database.
    
    Args:
        extracted_data: Dictionary containing the extracted report data
        pdf_path: Path to the PDF file
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not extracted_data:
        logger.error(f"No data to store for {pdf_path}")
        return False
        
    conn = None
    try:
        # Ensure database is initialized
        initialize_database()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Extract necessary data
        month_year = extracted_data.get('month_year', 'Unknown')
        
        # Parse the date from month_year
        report_date = parse_date(month_year)
        if not report_date:
            logger.error(f"Could not parse date from '{month_year}' for {pdf_path}")
            return False
            
        # Insert into reports table
        cursor.execute(
            """
            INSERT OR REPLACE INTO reports
            (report_date, file_path, processing_date, month_year)
            VALUES (?, ?, ?, ?)
            """,
            (
                report_date.isoformat(),
                pdf_path,
                datetime.now().isoformat(),
                month_year
            )
        )
        
        # Get Manufacturing table data
        manufacturing_table = extracted_data.get('manufacturing_table', '')
        
        # Process pmi_indices data
        # This will be extracted from the manufacturing_table text
        # For each index in the report, extract value and direction
        indices_data = {}
        
        # First try to extract from structured index_summaries if available
        index_summaries = extracted_data.get('index_summaries', {})
        for index_name, summary in index_summaries.items():
            # Try to extract numeric value and direction from the summary
            try:
                # Pattern for values like "PMI® registered 50.9 percent in January"
                import re
                value_pattern = r'(?:registered|was|at)\s+(\d+\.\d+)'
                value_match = re.search(value_pattern, summary, re.IGNORECASE)
                
                direction_pattern = r'(growing|growth|expanding|expansion|contracting|contraction|declining|increasing|decreasing|faster|slower)'
                direction_match = re.search(direction_pattern, summary, re.IGNORECASE)
                
                if value_match:
                    value = float(value_match.group(1))
                    direction = direction_match.group(1).capitalize() if direction_match else "Unknown"
                    
                    # Standardize direction terms
                    if direction.lower() in ['growing', 'growth', 'expanding', 'expansion', 'increasing']:
                        direction = 'Growing'
                    elif direction.lower() in ['contracting', 'contraction', 'declining', 'decreasing']:
                        direction = 'Contracting'
                    elif direction.lower() == 'slower':
                        direction = 'Slowing'
                    elif direction.lower() == 'faster':
                        direction = 'Faster'
                    
                    indices_data[index_name] = {
                        'value': value,
                        'direction': direction
                    }
            except Exception as e:
                logger.warning(f"Error extracting index data for {index_name}: {str(e)}")
        
        # Insert pmi_indices data
        for index_name, data in indices_data.items():
            try:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO pmi_indices
                    (report_date, index_name, index_value, direction)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        report_date.isoformat(),
                        index_name,
                        data.get('value', 0.0),
                        data.get('direction', 'Unknown')
                    )
                )
            except Exception as e:
                logger.error(f"Error inserting pmi_indices data for {index_name}: {str(e)}")
        
        # Process industry_status data
        industry_data = extracted_data.get('industry_data', {})
        for index_name, categories in industry_data.items():
            for category, industries in categories.items():
                # Determine status based on category
                if index_name == 'Supplier Deliveries':
                    status = 'Slowing' if category == 'Slower' else 'Faster'
                elif index_name == 'Inventories':
                    status = 'Higher' if category == 'Higher' else 'Lower'
                elif index_name == "Customers' Inventories":
                    status = category  # 'Too High' or 'Too Low'
                elif index_name == 'Prices':
                    status = 'Increasing' if category == 'Increasing' else 'Decreasing'
                else:
                    status = 'Growing' if category == 'Growing' else 'Contracting'
                
                # Insert each industry
                for industry in industries:
                    if not industry or not isinstance(industry, str):
                        continue
                        
                    # Clean industry name
                    industry = industry.strip()
                    if not industry:
                        continue
                        
                    try:
                        cursor.execute(
                            """
                            INSERT OR REPLACE INTO industry_status
                            (report_date, index_name, industry_name, status, category)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                report_date.isoformat(),
                                index_name,
                                industry,
                                status,
                                category
                            )
                        )
                    except Exception as e:
                        logger.error(f"Error inserting industry_status data for {industry}: {str(e)}")
        
        conn.commit()
        logger.info(f"Successfully stored data for report {month_year} in database")
        return True
        
    except Exception as e:
        logger.error(f"Error storing report data in database: {str(e)}")
        logger.error(traceback.format_exc())
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()