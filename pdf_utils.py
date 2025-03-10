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
        # First, try to find it in the title or header
        title_pattern = r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\s+MANUFACTURING"
        title_match = re.search(title_pattern, text, re.IGNORECASE)
        if title_match:
            return f"{title_match.group(1)} {title_match.group(2)}"
        
        # Try to find it in the Manufacturing at a Glance table
        table_pattern = r"MANUFACTURING AT A GLANCE\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})"
        table_match = re.search(table_pattern, text, re.IGNORECASE)
        if table_match:
            return f"{table_match.group(1)} {table_match.group(2)}"
        
        # Look for it in any section header
        section_pattern = r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\s+MANUFACTURING INDEX"
        section_match = re.search(section_pattern, text, re.IGNORECASE)
        if section_match:
            return f"{section_match.group(1)} {section_match.group(2)}"
        
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
    
    for i, index in enumerate(indices):
        try:
            # If this is the last index, search until the end or next major section
            if i == len(indices) - 1:
                end_pattern = r"(?:MANUFACTURING AT A GLANCE|WHAT RESPONDENTS ARE SAYING|COMMODITIES REPORTED)"
                pattern = rf"{index}(.*?)(?:{end_pattern}|$)"
            else:
                # Otherwise, search until the next index
                pattern = rf"{index}(.*?){indices[i+1]}"
                
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
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
    
    for index, summary in indices.items():
        try:
            # Define patterns based on the index type
            if index == "Supplier Deliveries":
                # Find industries reporting slower deliveries
                slower_pattern = r"(?:The|The \d+) (?:industries|manufacturing industries) reporting slower (?:supplier )?deliveries[^:]*:(.+?)(?:\.|The)"
                faster_pattern = r"(?:The|The \d+) (?:industries|manufacturing industries) reporting faster (?:supplier )?deliveries[^:]*:(.+?)(?:\.|The)"
                
                # Alternative patterns
                alt_slower_pattern = r"(?:in|—)\s+(?:order|the following order)[^:]*:\s*(.+?)(?:\.|The)"
                
                # Try to match the patterns
                slower_match = re.search(slower_pattern, summary, re.IGNORECASE | re.DOTALL)
                faster_match = re.search(faster_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # If primary patterns fail, try alternatives
                if not slower_match and "slower" in summary.lower():
                    slower_match = re.search(alt_slower_pattern, summary[summary.lower().find("slower"):], re.IGNORECASE | re.DOTALL)
                
                if not faster_match and "faster" in summary.lower():
                    faster_match = re.search(alt_slower_pattern, summary[summary.lower().find("faster"):], re.IGNORECASE | re.DOTALL)
                
                # Process the matches
                slower = []
                if slower_match:
                    slower_text = slower_match.group(1).strip()
                    slower = [i.strip() for i in re.split(r';|and', slower_text) if i.strip()]
                
                faster = []
                if faster_match:
                    faster_text = faster_match.group(1).strip()
                    faster = [i.strip() for i in re.split(r';|and', faster_text) if i.strip()]
                
                industry_data[index] = {
                    "Slower": slower,
                    "Faster": faster
                }
                
            elif index == "Inventories":
                # Find industries reporting higher/lower inventories
                higher_pattern = r"(?:The|The \d+) (?:industries|manufacturing industries) reporting (?:higher|increased) (?:inventories|inventory)[^:]*:(.+?)(?:\.|The)"
                lower_pattern = r"(?:The|The \d+) (?:industries|manufacturing industries) reporting (?:lower|decreased) (?:inventories|inventory)[^:]*:(.+?)(?:\.|The)"
                
                # Alternative patterns
                alt_higher_pattern = r"(?:in|—)\s+(?:order|the following order)[^:]*:\s*(.+?)(?:\.|The)"
                
                # Try to match the patterns
                higher_match = re.search(higher_pattern, summary, re.IGNORECASE | re.DOTALL)
                lower_match = re.search(lower_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # If primary patterns fail, try alternatives
                if not higher_match and "higher" in summary.lower():
                    higher_match = re.search(alt_higher_pattern, summary[summary.lower().find("higher"):], re.IGNORECASE | re.DOTALL)
                
                if not lower_match and "lower" in summary.lower():
                    lower_match = re.search(alt_higher_pattern, summary[summary.lower().find("lower"):], re.IGNORECASE | re.DOTALL)
                
                # Process the matches
                higher = []
                if higher_match:
                    higher_text = higher_match.group(1).strip()
                    higher = [i.strip() for i in re.split(r';|and', higher_text) if i.strip()]
                
                lower = []
                if lower_match:
                    lower_text = lower_match.group(1).strip()
                    lower = [i.strip() for i in re.split(r';|and', lower_text) if i.strip()]
                
                industry_data[index] = {
                    "Higher": higher,
                    "Lower": lower
                }
                
            elif index == "Customers' Inventories":
                # Find industries reporting customer inventories as too high/low
                too_high_pattern = r"(?:The|The \d+) (?:industries|manufacturing industries) reporting (?:customers'|customer) (?:inventories|inventory) as too high[^:]*:(.+?)(?:\.|The)"
                too_low_pattern = r"(?:The|The \d+) (?:industries|manufacturing industries) reporting (?:customers'|customer) (?:inventories|inventory) as too low[^:]*:(.+?)(?:\.|The)"
                
                # Alternative patterns
                alt_too_high_pattern = r"(?:in|—)\s+(?:order|the following order)[^:]*:\s*(.+?)(?:\.|The)"
                
                # Try to match the patterns
                too_high_match = re.search(too_high_pattern, summary, re.IGNORECASE | re.DOTALL)
                too_low_match = re.search(too_low_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # If primary patterns fail, try alternatives
                if not too_high_match and "too high" in summary.lower():
                    too_high_match = re.search(alt_too_high_pattern, summary[summary.lower().find("too high"):], re.IGNORECASE | re.DOTALL)
                
                if not too_low_match and "too low" in summary.lower():
                    too_low_match = re.search(alt_too_high_pattern, summary[summary.lower().find("too low"):], re.IGNORECASE | re.DOTALL)
                
                # Process the matches
                too_high = []
                if too_high_match:
                    too_high_text = too_high_match.group(1).strip()
                    too_high = [i.strip() for i in re.split(r';|and', too_high_text) if i.strip()]
                
                too_low = []
                if too_low_match:
                    too_low_text = too_low_match.group(1).strip()
                    too_low = [i.strip() for i in re.split(r';|and', too_low_text) if i.strip()]
                
                industry_data[index] = {
                    "Too High": too_high,
                    "Too Low": too_low
                }
                
            else:  # Default pattern for growth/decline for other indices
                # Pattern to find industries reporting growth
                growth_pattern = r"(?:The|The \d+) (?:industries|manufacturing industries) (?:that )?reporting (?:growth|expansion|increase|growing)[^:]*:(.+?)(?:\.|The)"
                decline_pattern = r"(?:The|The \d+) (?:industries|manufacturing industries) (?:that )?reporting (?:contraction|decline|decrease|declining)[^:]*:(.+?)(?:\.|The)"
                
                # Alternative patterns to capture industries listed in order
                alt_growth_pattern = r"(?:in|—)\s+(?:order|the following order)[^:]*:\s*(.+?)(?:\.|The)" 
                
                # Try to match the patterns
                growth_match = re.search(growth_pattern, summary, re.IGNORECASE | re.DOTALL)
                decline_match = re.search(decline_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # If primary patterns fail, try alternatives based on context
                if not growth_match:
                    # Look for growth indicators and then try alternative pattern
                    if any(term in summary.lower() for term in ["growth", "growing", "expansion", "increase", "higher"]):
                        growth_section = summary
                        for term in ["decline", "declining", "contraction", "decrease", "lower"]:
                            if term in summary.lower():
                                # Split at the decline term to isolate growth section
                                growth_section = summary[:summary.lower().find(term)]
                                break
                        growth_match = re.search(alt_growth_pattern, growth_section, re.IGNORECASE | re.DOTALL)
                
                if not decline_match:
                    # Look for decline indicators and then try alternative pattern
                    if any(term in summary.lower() for term in ["decline", "declining", "contraction", "decrease", "lower"]):
                        decline_section = summary
                        for term in ["growth", "growing", "expansion", "increase", "higher"]:
                            if term in summary.lower():
                                # Split at the growth term to isolate decline section
                                if summary.lower().find(term) > 0:
                                    decline_section = summary[summary.lower().find(term):]
                                break
                        decline_match = re.search(alt_growth_pattern, decline_section, re.IGNORECASE | re.DOTALL)
                
                # Process the matches
                growing = []
                if growth_match:
                    growing_text = growth_match.group(1).strip()
                    growing = [i.strip() for i in re.split(r';|and', growing_text) if i.strip()]
                
                declining = []
                if decline_match:
                    declining_text = decline_match.group(1).strip()
                    declining = [i.strip() for i in re.split(r';|and', declining_text) if i.strip()]
                
                # Determine appropriate category names based on index
                if index == "Prices":
                    categories = {"Increasing": growing, "Decreasing": declining}
                else:
                    categories = {"Growing": growing, "Declining": declining}
                
                industry_data[index] = categories
                
        except Exception as e:
            logger.error(f"Error extracting industry mentions for {index}: {str(e)}")
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
        
        # Extract month and year
        month_year = extract_month_year(text)
        if not month_year:
            logger.warning(f"Could not extract month and year from {pdf_path}")
            # Try to infer from filename or modification date
            filename = os.path.basename(pdf_path)
            if re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*[-_\s]?(\d{2,4})', filename, re.IGNORECASE):
                match = re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*[-_\s]?(\d{2,4})', filename, re.IGNORECASE)
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
        
        # Extract the Manufacturing at a Glance table
        manufacturing_table = extract_manufacturing_at_a_glance(text)
        
        # Extract index-specific summaries
        index_summaries = extract_index_summaries(text)
        
        # Extract industry mentions for each index
        industry_data = extract_industry_mentions(text, index_summaries)
        
        return {
            "month_year": month_year,
            "manufacturing_table": manufacturing_table,
            "index_summaries": index_summaries,
            "industry_data": industry_data
        }
    except Exception as e:
        logger.error(f"Error parsing ISM report: {str(e)}")
        return None