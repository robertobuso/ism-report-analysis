import os
import csv
import sqlite3
import datetime
import logging
import re
import traceback

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database path
DB_PATH = os.environ.get('ISM_DB_PATH', 'ism_data.db')

def parse_date(month_str):
    """Parse date string in expected format MMM-YY (e.g., 'Oct-13')."""
    try:
        # Extract month and year using regex
        match = re.match(r'(\w+)[- ](\d+)', month_str)
        if not match:
            logger.error(f"Failed to parse date format: {month_str}")
            return None
        
        month_abbr, year_str = match.groups()
        
        # Convert month abbreviation to number
        month_map = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
        }
        
        month_num = month_map.get(month_abbr, None)
        if month_num is None:
            logger.error(f"Unknown month abbreviation: {month_abbr}")
            return None
        
        # Convert 2-digit year to 4-digit year
        year = int(year_str)
        if year < 100:
            # Assume 20XX for years less than 100
            if year < 50:  # Arbitrary cutoff
                year += 2000
            else:
                year += 1900
        
        # Create date object for the 1st of the month
        return datetime.date(year, month_num, 1)
        
    except Exception as e:
        logger.error(f"Error parsing date '{month_str}': {str(e)}")
        return None

def is_row_index_column(values):
    """Check if a column appears to be a row index column by examining its values."""
    # Check if all values are integers or incrementing numbers
    try:
        if not values:
            return False
            
        # Check if all values are numeric
        all_numeric = all(val.strip().isdigit() for val in values if val.strip())
        
        # Check if values are sequential
        sequential = False
        numeric_values = [int(val) for val in values if val.strip().isdigit()]
        if len(numeric_values) > 1:
            diff_count = sum(1 for i in range(len(numeric_values)-1) 
                             if numeric_values[i+1] - numeric_values[i] == 1)
            sequential = diff_count / (len(numeric_values) - 1) > 0.9  # 90% are sequential
            
        return all_numeric and sequential
    except:
        return False

def clean_and_rebuild_database_from_csv(csv_path):
    """Completely rebuild the database from the CSV file."""
    # Delete the existing database file if it exists
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        logger.info(f"Removed existing database file: {DB_PATH}")
    
    # Create a new database connection
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create tables with explicit column definitions
    # Modify the reports table creation to use report_date as the primary key
    cursor.execute('''
    CREATE TABLE reports (
        report_date TEXT PRIMARY KEY,
        file_path TEXT,
        processing_date TEXT NOT NULL,
        month_year TEXT NOT NULL
    )
    ''')

    # Modify the pmi_indices table to also use natural keys instead of an auto-incrementing ID
    cursor.execute('''
    CREATE TABLE pmi_indices (
        report_date TEXT NOT NULL,
        index_name TEXT NOT NULL,
        index_value REAL NOT NULL,
        direction TEXT NOT NULL,
        PRIMARY KEY (report_date, index_name),
        FOREIGN KEY(report_date) REFERENCES reports(report_date)
    )
    ''')
    
    conn.commit()
    logger.info("Created new database tables")
    
    # Map CSV column names to database index names
    column_mapping = {
        'PMI': 'Manufacturing PMI',
        'New Orders': 'New Orders',
        'Production': 'Production',
        'Employment': 'Employment',
        'Deliveries': 'Supplier Deliveries',
        'Inventories': 'Inventories',
        'Customer Inv': 'Customers\' Inventories',
        'Prices': 'Prices',
        'Ord Backlog': 'Backlog of Orders',
        'Exports': 'New Export Orders',
        'Imports': 'Imports'
    }
    
    # First pre-scan the file to detect row index column
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        all_rows = list(reader)  # Read all rows into memory
        
        if not all_rows:
            logger.error("CSV file is empty")
            conn.close()
            return
            
        headers = all_rows[0]
        
        # Check first column for potential row index
        if len(headers) > 0:
            first_col_values = [row[0] if len(row) > 0 else "" for row in all_rows[1:]]
            if is_row_index_column(first_col_values):
                logger.info("First column appears to be a row index - will skip it")
                skip_first_column = True
            else:
                skip_first_column = False
                logger.info("First column does not appear to be a row index")
        else:
            skip_first_column = False
    
    # Now process the rows
    start_col_idx = 1 if skip_first_column else 0
    
    # Get the headers again (applying the column skip)
    headers = [h.strip() for h in all_rows[0][start_col_idx:]]
    
    month_col_index = None
    col_indices = {}
    
    # Find the indices of all needed columns (adjusted for column skipping)
    for i, header in enumerate(headers):
        clean_header = header.strip()
        if clean_header == 'Month':
            month_col_index = i
        elif clean_header in column_mapping.keys():
            col_indices[clean_header] = i
    
    if month_col_index is None:
        logger.error(f"Could not find 'Month' column in CSV. Available headers: {headers}")
        conn.close()
        return
        
    logger.info(f"Found Month column at adjusted index {month_col_index}")
    logger.info(f"Found data columns: {col_indices}")
    
    # Process each row
    records_added = 0
    indices_added = 0
    
    for row_data in all_rows[1:]:  # Skip header row
        # Apply column skipping
        row = row_data[start_col_idx:]
        
        if len(row) <= month_col_index:
            logger.warning(f"Skipping short row: {row}")
            continue
            
        month_str = row[month_col_index].strip()
        if not month_str:
            logger.warning(f"Skipping row with empty Month value: {row}")
            continue
        
        # Parse the date with our improved function
        date_obj = parse_date(month_str)
        if not date_obj:
            logger.warning(f"Could not parse date from '{month_str}'")
            continue
            
        month_year = date_obj.strftime("%B %Y")
        report_date = date_obj.strftime("%Y-%m-%d")
        
        # Print the parsed date for verification
        logger.info(f"Parsed '{month_str}' as {month_year} ({report_date})")
        
        # Insert the report record
        try:
            cursor.execute(
                """
                INSERT INTO reports
                (report_date, file_path, processing_date, month_year)
                VALUES (?, ?, ?, ?)
                """,
                (
                    report_date,
                    "imported_from_csv",
                    datetime.datetime.now().isoformat(),
                    month_year
                )
            )
            
            records_added += 1
            
            # Insert the PMI indices
            for col_name, col_index in col_indices.items():
                if col_index >= len(row):
                    continue
                    
                value_str = row[col_index].strip()
                if not value_str or value_str.lower() in ('na', 'n/a'):
                    continue
                
                try:
                    value = float(value_str)
                    db_index = column_mapping[col_name]
                    
                    # Determine direction
                    if db_index == 'Supplier Deliveries':
                        direction = 'Slowing' if value >= 50 else 'Faster'
                    elif db_index == 'Customers\' Inventories':
                        direction = 'Too High' if value >= 50 else 'Too Low'
                    elif db_index == 'Prices':
                        direction = 'Increasing' if value >= 50 else 'Decreasing'
                    else:
                        direction = 'Growing' if value >= 50 else 'Contracting'
                    
                    cursor.execute(
                        """
                        INSERT INTO pmi_indices
                        (report_date, index_name, index_value, direction)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            report_date,
                            db_index,
                            value,
                            direction
                        )
                    )
                    
                    indices_added += 1
                except ValueError:
                    logger.warning(f"Could not convert '{value_str}' to float")
            
        except Exception as e:
            logger.error(f"Error adding data for {month_year}: {str(e)}")
            logger.error(traceback.format_exc())
            conn.rollback()
    
    conn.commit()
    
    logger.info(f"Database rebuild completed: Added {records_added} reports and {indices_added} indices")
    
    # Verify the data
    cursor.execute("SELECT COUNT(*) FROM reports")
    report_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM pmi_indices")
    index_count = cursor.fetchone()[0]
    
    logger.info(f"Database contains {report_count} reports and {index_count} indices")
    
    # Close the connection
    conn.close()

if __name__ == "__main__":
    # Path to your CSV file
    csv_path = "pmi_data_heatmap_summary.csv"
    
    # Clean and rebuild the database
    clean_and_rebuild_database_from_csv(csv_path)
    print("Database rebuild completed!")