import unittest
import os
import sqlite3
import tempfile
import shutil
from datetime import datetime

# Import modules to test
from db_utils import initialize_database, get_db_connection, get_all_report_dates
import migrate_db

class TestDatabaseSchema(unittest.TestCase):
    """Test the database schema changes."""
    
    def setUp(self):
        """Set up a test database."""
        # Create a temporary directory for the test database
        self.test_dir = tempfile.mkdtemp()
        
        # Save the original database path
        import db_utils
        self.original_db_path = db_utils.DATABASE_PATH
        
        # Set the test database path
        db_utils.DATABASE_PATH = os.path.join(self.test_dir, 'test_ism_data.db')
        
        # Initialize the test database
        initialize_database()
        
        # Add test data
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Insert a test report
        cursor.execute(
            """
            INSERT INTO reports
            (report_date, file_path, processing_date, month_year)
            VALUES (?, ?, ?, ?)
            """,
            (
                '2023-01-01',
                'test_path.pdf',
                datetime.now().isoformat(),
                'January 2023'
            )
        )
        
        conn.commit()
        conn.close()
    
    def tearDown(self):
        """Clean up after the test."""
        # Restore the original database path
        import db_utils
        db_utils.DATABASE_PATH = self.original_db_path
        
        # Remove the temporary directory
        shutil.rmtree(self.test_dir)
    
    def test_report_type_column_exists(self):
        """Test that the report_type column exists in the reports table."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check table schema
        cursor.execute("PRAGMA table_info(reports)")
        columns = {col[1]: col for col in cursor.fetchall()}
        
        conn.close()
        
        self.assertIn('report_type', columns)
        self.assertEqual(columns['report_type'][2], 'TEXT')  # Check data type
        self.assertEqual(columns['report_type'][3], 1)      # Check NOT NULL constraint
        self.assertEqual(columns['report_type'][4], "'Manufacturing'")  # Check default value
    
    def test_migration_adds_column(self):
        """Test that the migration script adds the report_type column."""
        # First create a database without the report_type column
        conn = sqlite3.connect(os.path.join(self.test_dir, 'migration_test.db'))
        cursor = conn.cursor()
        
        # Create reports table without report_type
        cursor.execute('''
        CREATE TABLE reports (
            id INTEGER PRIMARY KEY,
            report_date DATE UNIQUE NOT NULL,
            file_path TEXT,
            processing_date DATETIME NOT NULL,
            month_year TEXT NOT NULL
        )
        ''')
        
        # Insert a test record
        cursor.execute(
            """
            INSERT INTO reports
            (report_date, file_path, processing_date, month_year)
            VALUES (?, ?, ?, ?)
            """,
            (
                '2023-01-01',
                'test_path.pdf',
                datetime.now().isoformat(),
                'January 2023'
            )
        )
        
        conn.commit()
        conn.close()
        
        # Save the original database path
        import db_utils
        original_db_path = db_utils.DATABASE_PATH
        
        # Set the test migration database path
        db_utils.DATABASE_PATH = os.path.join(self.test_dir, 'migration_test.db')
        
        # Run the migration
        migrate_db.migrate_database()
        
        # Restore the original database path
        db_utils.DATABASE_PATH = original_db_path
        
        # Check if the column was added
        conn = sqlite3.connect(os.path.join(self.test_dir, 'migration_test.db'))
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(reports)")
        columns = {col[1]: col for col in cursor.fetchall()}
        
        # Check the data has been updated
        cursor.execute("SELECT report_type FROM reports")
        report_type = cursor.fetchone()[0]
        
        conn.close()
        
        self.assertIn('report_type', columns)
        self.assertEqual(report_type, 'Manufacturing')  # Check default value is applied
    
    def test_get_all_report_dates_filter(self):
        """Test that get_all_report_dates filters by report_type."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Insert reports with different types
        cursor.execute(
            """
            INSERT INTO reports
            (report_date, file_path, processing_date, month_year, report_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                '2023-02-01',
                'mfg_report.pdf',
                datetime.now().isoformat(),
                'February 2023',
                'Manufacturing'
            )
        )
        
        cursor.execute(
            """
            INSERT INTO reports
            (report_date, file_path, processing_date, month_year, report_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                '2023-03-01',
                'services_report.pdf',
                datetime.now().isoformat(),
                'March 2023',
                'Services'
            )
        )
        
        conn.commit()
        conn.close()
        
        # Get all reports
        all_reports = get_all_report_dates()
        self.assertEqual(len(all_reports), 3)  # 1 from setUp + 2 new ones
        
        # Get only Manufacturing reports
        mfg_reports = get_all_report_dates('Manufacturing')
        self.assertEqual(len(mfg_reports), 2)  # Default from setUp is Manufacturing
        
        # Get only Services reports
        svc_reports = get_all_report_dates('Services')
        self.assertEqual(len(svc_reports), 1)

if __name__ == '__main__':
    unittest.main()