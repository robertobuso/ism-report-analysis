import re
import os

def reduce_logging_in_file(filepath):
    """Remove verbose logging statements from a file."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Patterns to remove (log statements with large data)
    patterns_to_remove = [
        r'logger\.info\(f".*\{.*extraction_data.*\}.*"\)',
        r'logger\.info\(f".*\{.*response_text.*\}.*"\)',
        r'logger\.info\(f"Prepared row for Google Sheets:.*"\)',
        r'logger\.info\(f"Database connection opened successfully.*"\)',
    ]
    
    for pattern in patterns_to_remove:
        content = re.sub(pattern, '# Removed verbose logging', content, flags=re.MULTILINE)
    
    with open(filepath, 'w') as f:
        f.write(content)

# Apply to main files
files_to_fix = ['main.py', 'tools.py', 'pdf_utils.py', 'db_utils.py', 'app.py']
for file in files_to_fix:
    if os.path.exists(file):
        reduce_logging_in_file(file)
        print(f"Reduced logging in {file}")