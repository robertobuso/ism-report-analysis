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
            if index == "Supplier Deliveries":
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

                # Extract industries reporting slower deliveries
                slower_pattern = r"(?:The|The \d+) (?:industries|manufacturing industries)(?:.+?)(?:reporting|that reported)(?:.+?)slower(?:.+?)(?:supplier )?deliveries[^:]*:(.+?)(?:\.|The|$)"
                slower_match = re.search(slower_pattern, summary, re.IGNORECASE | re.DOTALL)
                specific_slower = r"industries reporting slower supplier deliveries in (?:January|February|March|April|May|June|July|August|September|October|November|December)(?:.+?)(?:are|—|in)(?:.+?)(?:order|the following order)[^:]*:([^\.]+)"
                specific_faster = r"industries reporting faster supplier deliveries in (?:January|February|March|April|May|June|July|August|September|October|November|December)(?:.+?)(?:are|—|in)(?:.+?)(?:order|the following order)[^:]*:([^\.]+)"
                
                # Try more specific pattern for ISM reports
                if not slower_match:
                    slower_match = re.search(specific_slower, summary, re.IGNORECASE | re.DOTALL)
                
                # Extract industries reporting faster deliveries
                faster_pattern = r"(?:The|The \d+) (?:industries|manufacturing industries)(?:.+?)(?:reporting|that reported)(?:.+?)faster(?:.+?)(?:supplier )?deliveries[^:]*:(.+?)(?:\.|The|$)"
                faster_match = re.search(faster_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Try more specific pattern for ISM reports
                if not faster_match:
                    faster_match = re.search(specific_faster, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                slower = []
                if slower_match:
                    slower_text = slower_match.group(1).strip()
                    slower = [i.strip() for i in re.split(r';|and|,', slower_text) if i.strip()]
                
                faster = []
                if faster_match:
                    faster_text = faster_match.group(1).strip()
                    faster = [i.strip() for i in re.split(r';|and|,', faster_text) if i.strip()]
                
                industry_data[index] = {
                    "Slower": slower,
                    "Faster": faster
                }
                
            elif index == "Inventories":
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

                # Extract industries reporting higher inventories
                higher_pattern = r"(?:The|The \d+) (?:industries|manufacturing industries)(?:.+?)(?:reporting|that reported) (?:higher|increased|increasing|growing|growth in) (?:inventories|inventory)[^:]*:(.+?)(?:\.|The|$)"
                higher_match = re.search(higher_pattern, summary, re.IGNORECASE | re.DOTALL)
                specific_higher = r"industries reporting higher inventories in (?:January|February|March|April|May|June|July|August|September|October|November|December)(?:.+?)(?:listed in|—|in)(?:.+?)(?:order|the following order)[^:]*:([^\.]+)"
                specific_lower = r"industries reporting lower inventories in (?:January|February|March|April|May|June|July|August|September|October|November|December)(?:.+?)(?:in the following|—|in)(?:.+?)(?:order|the following order)[^:]*:([^\.]+)"
                
                # Try more specific pattern for ISM reports
                if not higher_match:
                    higher_match = re.search(specific_higher, summary, re.IGNORECASE | re.DOTALL)
                
                # Extract industries reporting lower inventories
                    lower_match = re.search(lower_pattern, summary, re.IGNORECASE | re.DOTALL)
                
                # Try more specific pattern for ISM reports
                if not lower_match:
                    specific_lower = r"industries reporting lower inventories in (?:January|February|March|April|May|June|July|August|September|October|November|December)(?:.+?)(?:in the following|—|in)(?:.+?)(?:order|the following order)[^:]*:([^\.]+)"
                    lower_match = re.search(specific_lower, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                higher = []
                if higher_match:
                    higher_text = higher_match.group(1).strip()
                    higher = [i.strip() for i in re.split(r';|and|,', higher_text) if i.strip()]
                
                lower = []
                if lower_match:
                    lower_text = lower_match.group(1).strip()
                    lower = [i.strip() for i in re.split(r';|and|,', lower_text) if i.strip()]
                
                industry_data[index] = {
                    "Higher": higher,
                    "Lower": lower
                }
                
            elif index == "Customers' Inventories":
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

                # Extract industries reporting customers' inventories as too high
                too_high_pattern = r"(?:The|The \d+) (?:industries|manufacturing industries)(?:.+?)(?:reporting|that reported) (?:customers'|customer) (?:inventories|inventory) as too high[^:]*:(.+?)(?:\.|The|$)"
                too_high_match = re.search(too_high_pattern, summary, re.IGNORECASE | re.DOTALL)
                specific_too_high = r"industries reporting customers' inventories as too high in (?:January|February|March|April|May|June|July|August|September|October|November|December)(?:.+?)(?:are|—|in)(?:.+?)(?:order|the following order)[^:]*:([^\.]+)"
                specific_too_low = r"industries reporting customers' inventories as too low in (?:January|February|March|April|May|June|July|August|September|October|November|December)(?:.+?)(?:are|—|in)(?:.+?)(?:order|the following order)[^:]*:([^\.]+)"
                
                # Try more specific pattern for ISM reports
                if not too_high_match:
                    specific_too_high = r"industries reporting customers' inventories as too high in (?:January|February|March|April|May|June|July|August|September|October|November|December)(?:.+?)(?:are|—|in)(?:.+?)(?:order|the following order)[^:]*:([^\.]+)"
                    too_high_match = re.search(specific_too_high, summary, re.IGNORECASE | re.DOTALL)
                               
                # Try more specific pattern for ISM reports
                if not too_low_match:
                    too_low_match = re.search(specific_too_low, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                too_high = []
                if too_high_match:
                    too_high_text = too_high_match.group(1).strip()
                    too_high = [i.strip() for i in re.split(r';|and|,', too_high_text) if i.strip()]
                
                too_low = []
                if too_low_match:
                    too_low_text = too_low_match.group(1).strip()
                    too_low = [i.strip() for i in re.split(r';|and|,', too_low_text) if i.strip()]
                
                industry_data[index] = {
                    "Too High": too_high,
                    "Too Low": too_low
                }
                
            elif index == "Prices":
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
                
                # Extract industries reporting price increases
                increasing_pattern = r"(?:The|The \d+) (?:industries|manufacturing industries)(?:.+?)(?:reporting|that reported) (?:paying |higher |increased |increasing |price increases)[^:]*:(.+?)(?:\.|The|$)"
                increasing_match = re.search(increasing_pattern, summary, re.IGNORECASE | re.DOTALL)
                specific_increasing = r"industries that reported paying increased prices for raw materials(?:.+?)(?:are|—|in)(?:.+?)(?:order|the following order)[^:]*:([^\.]+)"
                specific_decreasing = r"(?:The only industry|The \d+ industries) that reported paying decreased prices for raw materials(?:.+?)(?:are|is|—|in)(?:.+?)(?:order|the following order)?[^:]*:?\s*([^\.]+)"
                
                # Special case for "only industry" pattern
                only_industry = r"The only industry that reported paying decreased prices for raw materials[^:]*is ([^\.]+)"
                
                # Try enhanced patterns if original ones fail
                if not increasing_match:
                    increasing_match = re.search(specific_increasing, summary, re.IGNORECASE | re.DOTALL)
                
                if not decreasing_match:
                    decreasing_match = re.search(specific_decreasing, summary, re.IGNORECASE | re.DOTALL)
                    if not decreasing_match:
                        only_match = re.search(only_industry, summary, re.IGNORECASE | re.DOTALL)
                        if only_match:
                            decreasing_match = only_match
                
                # Process matches
                increasing = []
                if increasing_match:
                    increasing_text = increasing_match.group(1).strip()
                    increasing = [i.strip() for i in re.split(r';|and|,', increasing_text) if i.strip()]
                
                decreasing = []
                if decreasing_match:
                    decreasing_text = decreasing_match.group(1).strip()
                    decreasing = [i.strip() for i in re.split(r';|and|,', decreasing_text) if i.strip()]
                
                industry_data[index] = {
                    "Increasing": increasing,
                    "Decreasing": decreasing
                }
                
            else:  # Default pattern for growth/decline
                # Extract industries reporting growth
                growth_pattern = r"(?:The|The \d+) (?:industries|manufacturing industries)(?:.+?)(?:reporting|that reported) (?:growth|expansion|increase|growing|increased)[^:]*:(.+?)(?:\.|The|$)"
                growth_match = re.search(growth_pattern, summary, re.IGNORECASE | re.DOTALL)
                specific_growth = r"industries (?:reporting|that reported) growth in (?:new orders|production|employment|order backlogs|new export orders|imports) in (?:January|February|March|April|May|June|July|August|September|October|November|December)(?:.+?)(?:are|—|in)(?:.+?)(?:order|the following order)[^:]*:([^\.]+)"
                specific_decline = r"industries (?:reporting|that reported) (?:a |)(?:decline|decrease|contraction) in (?:new orders|production|employment|order backlogs|new export orders|imports) in (?:January|February|March|April|May|June|July|August|September|October|November|December)(?:.+?)(?:are|—|in)(?:.+?)(?:order|the following order)[^:]*:([^\.]+)"
                
                # Try more specific pattern for ISM reports
                if not growth_match:
                    growth_match = re.search(specific_growth, summary, re.IGNORECASE | re.DOTALL)
                
                # Try alternative pattern
                if not growth_match:
                    alt_growth = r"The (?:\w+) (?:industries|manufacturing industries) (?:that |)(?:reporting|reported) growth in[^:]*:([^\.]+)"
                    growth_match = re.search(alt_growth, summary, re.IGNORECASE | re.DOTALL)
                
                # Try more specific pattern for ISM reports
                if not decline_match:
                    decline_match = re.search(specific_decline, summary, re.IGNORECASE | re.DOTALL)
                
                # Process matches
                growing = []
                if growth_match:
                    growing_text = growth_match.group(1).strip()
                    growing = [i.strip() for i in re.split(r';|and|,', growing_text) if i.strip()]
                
                declining = []
                if decline_match:
                    declining_text = decline_match.group(1).strip()
                    declining = [i.strip() for i in re.split(r';|and|,', declining_text) if i.strip()]
                
                # Handle case of special "format one per line" industries separated by semicolons or "and"
                if not growing and "in order" in summary.lower() and "growth" in summary.lower():
                    # Look for the phrase "in order" and extract industries
                    order_pattern = r"in order[^:]*:([^\.]+)"
                    order_match = re.search(order_pattern, summary, re.IGNORECASE | re.DOTALL)
                    if order_match:
                        industry_text = order_match.group(1).strip()
                        industries = [i.strip() for i in re.split(r';|and|,', industry_text) if i.strip()]
                        
                        # Check if the phrase before "in order" contains "growth"
                        if "growth" in summary.split("in order")[0].lower():
                            growing = industries
                        elif "decline" in summary.split("in order")[0].lower() or "contraction" in summary.split("in order")[0].lower():
                            declining = industries
                
                # Final attempt to find industries listed after "are:"
                if not growing and "growth" in summary.lower() and "are:" in summary.lower():
                    growth_parts = summary.lower().split("growth")
                    for part in growth_parts[1:]:
                        if "are:" in part:
                            text_after_are = part.split("are:")[1].split(".")[0]
                            growing = [i.strip() for i in re.split(r';|and|,', text_after_are) if i.strip()]
                            break
                
                if not declining and ("decline" in summary.lower() or "contraction" in summary.lower()) and "are:" in summary.lower():
                    decline_parts = summary.lower().split("contraction" if "contraction" in summary.lower() else "decline")
                    for part in decline_parts[1:]:
                        if "are:" in part:
                            text_after_are = part.split("are:")[1].split(".")[0]
                            declining = [i.strip() for i in re.split(r';|and|,', text_after_are) if i.strip()]
                            break
                
                industry_data[index] = {
                    "Growing": growing,
                    "Declining": declining
                }
                
        except Exception as e:
            logger.error(f"Error extracting industry mentions for {index}: {str(e)}")
            industry_data[index] = {}
    
    # Add post-processing for all indices to remove duplicates while preserving order
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
    
    # Replace common list markers with commas
    text = re.sub(r';\s*', ', ', text)
    text = re.sub(r'\band\b', ',', text, flags=re.IGNORECASE)
    
    # Split by commas
    industries = [i.strip() for i in text.split(',') if i.strip()]
    
    # Remove any extraneous text like "in order" or footnotes
    industries = [re.sub(r'\s*\(\d+\)$', '', i) for i in industries]  # Remove footnote numbers
    industries = [re.sub(r'\s*\*+$', '', i) for i in industries]  # Remove asterisks
    
    return [i for i in industries if i]