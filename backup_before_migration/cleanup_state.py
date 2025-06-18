import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define paths using the volume mount point expected in Railway
VOLUME_PATH = '/data'
TOKEN_PATH = os.path.join(VOLUME_PATH, 'token.pickle')
SHEET_ID_PATH = os.path.join(VOLUME_PATH, 'sheet_id.txt')
DB_PATH = os.path.join(VOLUME_PATH, 'ism_data.db')

files_to_delete = [TOKEN_PATH, SHEET_ID_PATH,DB_PATH]
# Optional: Add DB_PATH here if you want to delete it too
files_to_delete.append(DB_PATH)

logger.info(f"Attempting to delete state files from {VOLUME_PATH}...")

# First, check if the volume directory exists
if not os.path.isdir(VOLUME_PATH):
    logger.error(f"Volume directory {VOLUME_PATH} does not exist or is not accessible inside the container.")
    # Exit with an error code if the directory isn't there
    # This helps diagnose the mount issue if 'ls /data' failed
    exit(1)
else:
    logger.info(f"Volume directory {VOLUME_PATH} found.")

deleted_count = 0
not_found_count = 0
error_count = 0

for file_path in files_to_delete:
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Successfully deleted: {file_path}")
            deleted_count += 1
        else:
            logger.warning(f"File not found, skipping: {file_path}")
            not_found_count += 1
    except OSError as e:
        logger.error(f"Error deleting file {file_path}: {e}", exc_info=True)
        error_count += 1
    except Exception as e:
        logger.error(f"Unexpected error deleting file {file_path}: {e}", exc_info=True)
        error_count += 1

logger.info(f"Cleanup summary: {deleted_count} deleted, {not_found_count} not found, {error_count} errors.")

if error_count > 0:
     exit(1) # Exit with error if deletion failed
