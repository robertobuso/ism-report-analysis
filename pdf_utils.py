import PyPDF2
import re
import json
import logging
import os
from datetime import datetime

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
    """Extract industries mentioned for each index."""
    industry_data = {}
    
    # Loop through each index and its summary text
    for index, summary in indices.items():
        try:
            # Initialize categories dictionary for this index
            categories = {}
            
            # Process based on index type
            if index == "New Orders":
                # Look for growing industries
                growth_pattern = r"The (?:nine|eight|seven|six|five|four|three|two|one|\d+) (?:manufacturing )?industries (?:that )?reported growth in new orders in February,? in order,? are:([^\.]+)"
                growth_match = re.search(growth_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Look for declining industries
                decline_pattern = r"The (?:nine|eight|seven|six|five|four|three|two|one|\d+) industries reporting a decline in new orders in February,? in order,? are:([^\.]+)"
                decline_match = re.search(decline_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                growing = []
                if growth_match:
                    growing_text = growth_match.group(1).strip()
                    growing = clean_and_split_industry_list(growing_text)
                
                declining = []
                if decline_match:
                    declining_text = decline_match.group(1).strip()
                    declining = clean_and_split_industry_list(declining_text)
                
                # Check if we found any industries
                if not growing and not declining:
                    # Try another pattern for growing
                    alt_growth = r"(?:nine|eight|seven|six|five|four|three|two|one|\d+) (?:manufacturing )?industries that reported growth in new orders[^:]*:([^\.]+)"
                    alt_match = re.search(alt_growth, summary, re.IGNORECASE | re.DOTALL)
                    if alt_match:
                        growing = clean_and_split_industry_list(alt_match.group(1).strip())
                    
                    # Try another pattern for declining
                    alt_decline = r"(?:nine|eight|seven|six|five|four|three|two|one|\d+) industries (?:reporting|that reported) a (?:decline|decrease|contraction) in new orders[^:]*:([^\.]+)"
                    alt_match = re.search(alt_decline, summary, re.IGNORECASE | re.DOTALL)
                    if alt_match:
                        declining = clean_and_split_industry_list(alt_match.group(1).strip())
                
                # Store the categories
                categories = {
                    "Growing": growing,
                    "Declining": declining
                }
                
            elif index == "Production":
                # Look for growing industries
                growth_pattern = r"The (?:nine|eight|seven|six|five|four|three|two|one|\d+) industries reporting growth in production (?:during the month of February|in February),? in order,? are:([^\.]+)"
                growth_match = re.search(growth_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Look for declining industries
                decline_pattern = r"The (?:nine|eight|seven|six|five|four|three|two|one|\d+) industries reporting a decrease in production in February[^:]*:([^\.]+)"
                decline_match = re.search(decline_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                growing = []
                if growth_match:
                    growing_text = growth_match.group(1).strip()
                    growing = clean_and_split_industry_list(growing_text)
                
                declining = []
                if decline_match:
                    declining_text = decline_match.group(1).strip()
                    declining = clean_and_split_industry_list(declining_text)
                
                # Check if we found any industries
                if not growing:
                    # Try more general pattern
                    alt_growth = r"(?:seven|six|five|four|three|two|one|\d+) industries reporting growth in production[^:]*:([^\.]+)"
                    alt_match = re.search(alt_growth, summary, re.IGNORECASE | re.DOTALL)
                    if alt_match:
                        growing = clean_and_split_industry_list(alt_match.group(1).strip())
                
                if not declining:
                    # Try more general pattern for industries reporting a decrease
                    alt_decline = r"(?:four|three|two|one|\d+) industries reporting a decrease in production[^:]*are:([^\.]+)"
                    alt_match = re.search(alt_decline, summary, re.IGNORECASE | re.DOTALL)
                    if alt_match:
                        declining = clean_and_split_industry_list(alt_match.group(1).strip())
                    
                    # Try for "The industries reporting a decrease in production"
                    if not declining:
                        alt_decline2 = r"industries reporting a decrease in production[^:]*are:([^\.]+)"
                        alt_match = re.search(alt_decline2, summary, re.IGNORECASE | re.DOTALL)
                        if alt_match:
                            declining = clean_and_split_industry_list(alt_match.group(1).strip())
                
                # Store the categories
                categories = {
                    "Growing": growing,
                    "Declining": declining
                }
                
            elif index == "Employment":
                # Look for growing industries
                growth_pattern = r"The (?:nine|eight|seven|six|five|four|three|two|one|\d+) industries reporting employment growth in February[^:]*:([^\.]+)"
                growth_match = re.search(growth_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Look for declining industries
                decline_pattern = r"The (?:nine|eight|seven|six|five|four|three|two|one|\d+) industries reporting a decrease in employment in February,? in the following order,? are:([^\.]+)"
                decline_match = re.search(decline_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                growing = []
                if growth_match:
                    growing_text = growth_match.group(1).strip()
                    growing = clean_and_split_industry_list(growing_text)
                
                declining = []
                if decline_match:
                    declining_text = decline_match.group(1).strip()
                    declining = clean_and_split_industry_list(declining_text)
                
                # Check if we found any industries
                if not growing:
                    # Try more general patterns
                    alt_growth = r"(?:manufacturing )?industries reporting employment growth[^:]*:([^\.]+)"
                    alt_match = re.search(alt_growth, summary, re.IGNORECASE | re.DOTALL)
                    if alt_match:
                        growing = clean_and_split_industry_list(alt_match.group(1).strip())
                
                if not declining:
                    # Try more general pattern
                    alt_decline = r"industries reporting a decrease in employment[^:]*:([^\.]+)"
                    alt_match = re.search(alt_decline, summary, re.IGNORECASE | re.DOTALL)
                    if alt_match:
                        declining = clean_and_split_industry_list(alt_match.group(1).strip())
                
                # Store the categories
                categories = {
                    "Growing": growing,
                    "Declining": declining
                }
                
            elif index == "Supplier Deliveries":
                # Look for slower deliveries
                slower_pattern = r"The (?:nine|eight|seven|six|five|four|three|two|one|\d+) (?:manufacturing )?industries reporting slower supplier deliveries in February[^:]*:([^\.]+)"
                slower_match = re.search(slower_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Look for faster deliveries
                faster_pattern = r"The (?:nine|eight|seven|six|five|four|three|two|one|\d+) industries reporting faster supplier deliveries in February[^:]*:([^\.]+)"
                faster_match = re.search(faster_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                slower = []
                if slower_match:
                    slower_text = slower_match.group(1).strip()
                    slower = clean_and_split_industry_list(slower_text)
                
                faster = []
                if faster_match:
                    faster_text = faster_match.group(1).strip()
                    faster = clean_and_split_industry_list(faster_text)
                
                # Check if we found any industries
                if not slower:
                    # Try more general pattern
                    alt_slower = r"industries reporting slower supplier deliveries[^:]*:([^\.]+)"
                    alt_match = re.search(alt_slower, summary, re.IGNORECASE | re.DOTALL)
                    if alt_match:
                        slower = clean_and_split_industry_list(alt_match.group(1).strip())
                
                if not faster:
                    # Try more general pattern
                    alt_faster = r"industries reporting faster supplier deliveries[^:]*:([^\.]+)"
                    alt_match = re.search(alt_faster, summary, re.IGNORECASE | re.DOTALL)
                    if alt_match:
                        faster = clean_and_split_industry_list(alt_match.group(1).strip())
                
                # Store the categories
                categories = {
                    "Slower": slower,
                    "Faster": faster
                }
                
            elif index == "Inventories":
                # Look for higher inventories
                higher_pattern = r"The (?:seven|six|five|four|three|two|one|\d+) industries reporting higher inventories in February[^:]*:([^\.]+)"
                higher_match = re.search(higher_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Look for lower inventories
                lower_pattern = r"The (?:six|five|four|three|two|one|\d+) industries reporting lower inventories in February[^:]*:([^\.]+)"
                lower_match = re.search(lower_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                higher = []
                if higher_match:
                    higher_text = higher_match.group(1).strip()
                    higher = clean_and_split_industry_list(higher_text)
                
                lower = []
                if lower_match:
                    lower_text = lower_match.group(1).strip()
                    lower = clean_and_split_industry_list(lower_text)
                
                # Check if we found any industries
                if not higher:
                    # Try more general pattern
                    alt_higher = r"industries reporting higher inventories[^:]*:([^\.]+)"
                    alt_match = re.search(alt_higher, summary, re.IGNORECASE | re.DOTALL)
                    if alt_match:
                        higher = clean_and_split_industry_list(alt_match.group(1).strip())
                
                if not lower:
                    # Try more general pattern
                    alt_lower = r"industries reporting lower inventories[^:]*:([^\.]+)"
                    alt_match = re.search(alt_lower, summary, re.IGNORECASE | re.DOTALL)
                    if alt_match:
                        lower = clean_and_split_industry_list(alt_match.group(1).strip())
                
                # Store the categories
                categories = {
                    "Higher": higher,
                    "Lower": lower
                }
                
            elif index == "Customers' Inventories":
                # Look for too high inventories
                too_high_pattern = r"The (?:two|three|four|five|\d+) industries reporting customers[\''] inventories as too high in February[^:]*:([^\.]+)"
                too_high_match = re.search(too_high_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Look for too low inventories
                too_low_pattern = r"The (?:ten|nine|eight|seven|six|five|four|three|two|one|\d+) industries reporting customers[\''] inventories as too low in February[^:]*:([^\.]+)"
                too_low_match = re.search(too_low_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                too_high = []
                if too_high_match:
                    too_high_text = too_high_match.group(1).strip()
                    too_high = clean_and_split_industry_list(too_high_text)
                
                too_low = []
                if too_low_match:
                    too_low_text = too_low_match.group(1).strip()
                    too_low = clean_and_split_industry_list(too_low_text)
                
                # Check if we found any industries
                if not too_high:
                    # Try more general pattern
                    alt_too_high = r"industries reporting customers[\''] inventories as too high[^:]*:([^\.]+)"
                    alt_match = re.search(alt_too_high, summary, re.IGNORECASE | re.DOTALL)
                    if alt_match:
                        too_high = clean_and_split_industry_list(alt_match.group(1).strip())
                
                if not too_low:
                    # Try more general pattern
                    alt_too_low = r"industries reporting customers[\''] inventories as too low[^:]*:([^\.]+)"
                    alt_match = re.search(alt_too_low, summary, re.IGNORECASE | re.DOTALL)
                    if alt_match:
                        too_low = clean_and_split_industry_list(alt_match.group(1).strip())
                
                # Store the categories
                categories = {
                    "Too High": too_high,
                    "Too Low": too_low
                }
                
            elif index == "Prices":
                # Look for increasing prices
                increasing_pattern = r"In February, the (?:fourteen|thirteen|twelve|eleven|ten|nine|eight|seven|six|five|four|three|two|one|\d+) industries that reported paying increased prices for raw materials[^:]*:([^\.]+)"
                increasing_match = re.search(increasing_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Look for decreasing prices
                decreasing_pattern = r"The only industry that reported paying decreased prices for raw materials in February is ([^\.]+)"
                decreasing_match = re.search(decreasing_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                increasing = []
                if increasing_match:
                    increasing_text = increasing_match.group(1).strip()
                    increasing = clean_and_split_industry_list(increasing_text)
                
                decreasing = []
                if decreasing_match:
                    decreasing_text = decreasing_match.group(1).strip()
                    decreasing = [decreasing_text.strip()]  # For single industry, don't split
                
                # Check if we found any industries
                if not increasing:
                    # Try more general pattern
                    alt_increasing = r"industries that reported paying increased prices for raw materials[^:]*:([^\.]+)"
                    alt_match = re.search(alt_increasing, summary, re.IGNORECASE | re.DOTALL)
                    if alt_match:
                        increasing = clean_and_split_industry_list(alt_match.group(1).strip())
                    
                    # Try the specific "five" pattern from the summary
                    if not increasing:
                        five_pattern = r"five — ([^—]+)(?:—| — | reported price increases)"
                        five_match = re.search(five_pattern, summary, re.IGNORECASE | re.DOTALL)
                        if five_match:
                            increasing = clean_and_split_industry_list(five_match.group(1).strip())
                
                if not decreasing:
                    # Try more general pattern for "only industry"
                    alt_decreasing = r"only industry that reported paying decreased prices[^:]*is ([^\.]+)"
                    alt_match = re.search(alt_decreasing, summary, re.IGNORECASE | re.DOTALL)
                    if alt_match:
                        decreasing = [alt_match.group(1).strip()]
                
                # Store the categories
                categories = {
                    "Increasing": increasing,
                    "Decreasing": decreasing
                }
                
            elif index == "Backlog of Orders":
                # Look for growing backlogs
                growth_pattern = r"(?:five|four|three|two|one|\d+) reported growth in order backlogs in February:([^\.]+)"
                growth_match = re.search(growth_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Look for declining backlogs
                decline_pattern = r"(?:eight|seven|six|five|four|three|two|one|\d+) industries reporting lower backlogs in February[^:]*:([^\.]+)"
                decline_match = re.search(decline_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                growing = []
                if growth_match:
                    growing_text = growth_match.group(1).strip()
                    growing = clean_and_split_industry_list(growing_text)
                
                declining = []
                if decline_match:
                    declining_text = decline_match.group(1).strip()
                    declining = clean_and_split_industry_list(declining_text)
                
                # Check if we found any industries
                if not growing:
                    # Try more general pattern
                    alt_growth = r"reported growth in order backlogs[^:]*:([^\.]+)"
                    alt_match = re.search(alt_growth, summary, re.IGNORECASE | re.DOTALL)
                    if alt_match:
                        growing = clean_and_split_industry_list(alt_match.group(1).strip())
                
                if not declining:
                    # Try more general pattern
                    alt_decline = r"industries reporting lower backlogs[^:]*:([^\.]+)"
                    alt_match = re.search(alt_decline, summary, re.IGNORECASE | re.DOTALL)
                    if alt_match:
                        declining = clean_and_split_industry_list(alt_match.group(1).strip())
                
                # Store the categories
                categories = {
                    "Growing": growing,
                    "Declining": declining
                }
                
            elif index == "New Export Orders":
                # Look for growing export orders
                growth_pattern = r"The (?:four|three|two|one|\d+) industries reporting growth in new export orders in February are:([^\.]+)"
                growth_match = re.search(growth_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Look for declining export orders
                decline_pattern = r"The (?:four|three|two|one|\d+) industries reporting a decrease in new export orders in February are:([^\.]+)"
                decline_match = re.search(decline_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                growing = []
                if growth_match:
                    growing_text = growth_match.group(1).strip()
                    growing = clean_and_split_industry_list(growing_text)
                
                declining = []
                if decline_match:
                    declining_text = decline_match.group(1).strip()
                    declining = clean_and_split_industry_list(declining_text)
                
                # Check if we found any industries
                if not growing:
                    # Try more general pattern
                    alt_growth = r"industries reporting growth in new export orders[^:]*:([^\.]+)"
                    alt_match = re.search(alt_growth, summary, re.IGNORECASE | re.DOTALL)
                    if alt_match:
                        growing = clean_and_split_industry_list(alt_match.group(1).strip())
                
                if not declining:
                    # Try more general pattern
                    alt_decline = r"industries reporting a decrease in new export orders[^:]*:([^\.]+)"
                    alt_match = re.search(alt_decline, summary, re.IGNORECASE | re.DOTALL)
                    if alt_match:
                        declining = clean_and_split_industry_list(alt_match.group(1).strip())
                
                # Store the categories
                categories = {
                    "Growing": growing,
                    "Declining": declining
                }
                
            elif index == "Imports":
                # Look for increasing imports
                growth_pattern = r"The (?:seven|six|five|four|three|two|one|\d+) industries reporting an increase in import volumes in February[^:]*:([^\.]+)"
                growth_match = re.search(growth_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Look for decreasing imports
                decline_pattern = r"The (?:three|two|one|\d+) industries that reported lower volumes of imports in February are:([^\.]+)"
                decline_match = re.search(decline_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                growing = []
                if growth_match:
                    growing_text = growth_match.group(1).strip()
                    growing = clean_and_split_industry_list(growing_text)
                
                declining = []
                if decline_match:
                    declining_text = decline_match.group(1).strip()
                    declining = clean_and_split_industry_list(declining_text)
                
                # Check if we found any industries
                if not growing:
                    # Try more general pattern
                    alt_growth = r"industries reporting an increase in import volumes[^:]*:([^\.]+)"
                    alt_match = re.search(alt_growth, summary, re.IGNORECASE | re.DOTALL)
                    if alt_match:
                        growing = clean_and_split_industry_list(alt_match.group(1).strip())
                
                if not declining:
                    # Try more general pattern
                    alt_decline = r"industries that reported lower volumes of imports[^:]*:([^\.]+)"
                    alt_match = re.search(alt_decline, summary, re.IGNORECASE | re.DOTALL)
                    if alt_match:
                        declining = clean_and_split_industry_list(alt_match.group(1).strip())
                
                # Store the categories
                categories = {
                    "Growing": growing,
                    "Declining": declining
                }
                
            # Store the categories for this index
            industry_data[index] = categories
            
            # Log warning if no industries found for a category
            for category, industries in categories.items():
                if not industries:
                    logger.warning(f"No industries found for {index} - {category}")
                        
        except Exception as e:
            logger.error(f"Error extracting industry mentions for {index}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            industry_data[index] = {}
    
    return industry_data

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
        
        return {
            "month_year": month_year,
            "manufacturing_table": manufacturing_table,
            "index_summaries": index_summaries,
            "industry_data": industry_data
        }
    except Exception as e:
        logger.error(f"Error parsing ISM report: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None

def clean_and_split_industry_list(text):
    """Clean and split a list of industries into separate items."""
    if not text:
        return []
    
    # First, standardize the text by removing formatting and special characters
    cleaned_text = text.strip()
    
    # Replace special control characters
    cleaned_text = re.sub(r'[\n\r\t]+', ' ', cleaned_text)
    
    # Replace semicolons with commas
    cleaned_text = re.sub(r';\s*', ', ', cleaned_text)
    
    # Replace "and" at the end of a list with a comma
    cleaned_text = re.sub(r'\s+and\s+(?=\S+$)', ', ', cleaned_text, flags=re.IGNORECASE)
    
    # Split by commas and clean up each item
    industries = []
    for item in cleaned_text.split(','):
        item = item.strip()
        if not item:
            continue
            
        # Clean up the item
        item = re.sub(r'\s*\(\d+\)\s*$', '', item)  # Remove footnote numbers like (1)
        item = re.sub(r'\s*\*+\s*$', '', item)      # Remove trailing asterisks
        item = re.sub(r'^\s*-\s*', '', item)        # Remove leading dashes
        
        # Remove any other special characters
        item = re.sub(r'[^\w\s&;,\'()-]', '', item)
        
        if item and len(item) > 1:  # Only include non-empty, meaningful items
            industries.append(item)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_industries = []
    for industry in industries:
        if industry not in seen:
            seen.add(industry)
            unique_industries.append(industry)
    
    return unique_industries