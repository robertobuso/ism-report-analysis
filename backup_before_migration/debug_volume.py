import os
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def debug_volume_access():
    """Debug volume access and file locations."""
    
    # Wait a moment for volume to mount
    time.sleep(2)
    
    logger.info("=== DEBUGGING VOLUME ACCESS ===")
    
    # Check environment variables
    logger.info(f"RAILWAY_VOLUME_MOUNT_PATH: {os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', 'Not set')}")
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"User: {os.environ.get('USER', 'unknown')}")
    
    # Check various paths
    paths_to_check = ['/data', '/app', os.getcwd(), '/tmp']
    
    for path in paths_to_check:
        logger.info(f"\n--- Checking {path} ---")
        try:
            exists = os.path.exists(path)
            logger.info(f"Exists: {exists}")
            
            if exists:
                is_dir = os.path.isdir(path)
                logger.info(f"Is directory: {is_dir}")
                
                if is_dir:
                    # Check permissions
                    readable = os.access(path, os.R_OK)
                    writable = os.access(path, os.W_OK)
                    logger.info(f"Readable: {readable}, Writable: {writable}")
                    
                    # List contents
                    try:
                        contents = os.listdir(path)
                        logger.info(f"Contents ({len(contents)} items): {contents}")
                        
                        # Look for our specific files
                        target_files = ['ism_data.db', 'token.pickle', 'sheet_id.txt']
                        found_files = [f for f in contents if f in target_files]
                        if found_files:
                            logger.info(f"TARGET FILES FOUND: {found_files}")
                    except Exception as e:
                        logger.error(f"Error listing contents: {e}")
        except Exception as e:
            logger.error(f"Error checking {path}: {e}")
    
    # Check from db_utils perspective
    try:
        from db_utils import DATABASE_PATH, DB_DIR
        logger.info(f"\n--- DB Utils Paths ---")
        logger.info(f"DB_DIR: {DB_DIR}")
        logger.info(f"DATABASE_PATH: {DATABASE_PATH}")
        logger.info(f"Database exists: {os.path.exists(DATABASE_PATH)}")
    except Exception as e:
        logger.error(f"Error importing db_utils: {e}")

if __name__ == "__main__":
    debug_volume_access()