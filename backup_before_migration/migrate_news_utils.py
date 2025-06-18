#!/usr/bin/env python3
"""
Automatic Migration Script for News Utils Consolidation
======================================================

This script automatically updates your Python files to use the new consolidated news_utils.py
Run this script in your project directory to update all imports and function calls.

Usage: python migrate_news_utils.py
"""

import os
import re
import glob
import shutil
from pathlib import Path

class NewsUtilsMigrator:
    def __init__(self):
        self.backup_dir = "backup_before_migration"
        self.changes_made = []
        
        # Define all the import replacements
        self.import_replacements = [
            # Enhanced news analysis imports
            (r'from enhanced_news_analysis import AnalysisConfig', 
             'from news_utils import NewsAnalysisConfig as AnalysisConfig'),
            (r'from enhanced_news_analysis import DynamicSourceOrchestrator', 
             'from news_utils import DynamicSourceOrchestrator'),
            (r'from enhanced_news_analysis import ParallelSourceOrchestrator', 
             'from news_utils import ParallelSourceOrchestrator'),
            (r'from enhanced_news_analysis import QualityEnhancedSourceOrchestrator', 
             'from news_utils import QualityEnhancedSourceOrchestrator'),
            (r'from enhanced_news_analysis import RelevanceAssessor', 
             'from news_utils import RelevanceAssessor'),
            (r'from enhanced_news_analysis import fetch_comprehensive_news_guaranteed_30_enhanced.*', 
             'from news_utils import fetch_comprehensive_news_guaranteed_30_enhanced'),
            (r'from enhanced_news_analysis import fetch_enhanced_news.*', 
             'from news_utils import fetch_comprehensive_news_guaranteed_30_enhanced'),
            (r'from enhanced_news_analysis import create_empty_results_enhanced', 
             'from news_utils import create_empty_result'),
            
            # Claude Sonnet 4 imports
            (r'from news_utils_claude_sonnet_4 import generate_premium_analysis.*', 
             'from news_utils import generate_enhanced_analysis'),
            (r'from news_utils_claude_sonnet_4 import setup_claude_sonnet_4', 
             '# Claude Sonnet 4 setup now automatic in news_utils'),
            (r'from news_utils_claude_sonnet_4 import.*', 
             'from news_utils import generate_enhanced_analysis'),
            
            # Quality validation imports
            (r'from quality_validation import QualityValidationEngine', 
             'from news_utils import QualityValidationEngine'),
            (r'from quality_validation import validate_analysis_quality', 
             'from news_utils import validate_analysis_quality'),
            (r'from quality_validation import is_quality_validation_available', 
             'from news_utils import is_quality_validation_available'),
            (r'from quality_validation import.*', 
             'from news_utils import QualityValidationEngine'),
            
            # Configuration imports
            (r'from configuration_and_integration import ConfigurationManager', 
             'from news_utils import ConfigurationManager'),
            (r'from configuration_and_integration import get_analysis_config', 
             'from news_utils import get_analysis_config'),
        ]
        
        # Define function call replacements
        self.function_replacements = [
            # Long function names to main function
            (r'fetch_comprehensive_news_guaranteed_30_enhanced_PARALLEL_WITH_QUALITY\s*\(',
             'fetch_comprehensive_news_guaranteed_30_enhanced('),
            (r'fetch_comprehensive_news_guaranteed_30_enhanced_WITH_OPTIONAL_QUALITY\s*\(',
             'fetch_comprehensive_news_guaranteed_30_enhanced('),
            (r'fetch_comprehensive_news_guaranteed_30_enhanced_WITH_ITERATIVE_QUALITY\s*\(',
             'fetch_comprehensive_news_guaranteed_30_enhanced('),
            (r'fetch_enhanced_news_with_parallel_sources\s*\(',
             'fetch_comprehensive_news_guaranteed_30_enhanced('),
            (r'fetch_enhanced_news_with_quality_validation\s*\(',
             'fetch_comprehensive_news_guaranteed_30_enhanced('),
            
            # Analysis function names
            (r'generate_premium_analysis_upgraded_v2\s*\(',
             'generate_enhanced_analysis('),
            (r'generate_premium_analysis_claude_sonnet_4_enhanced\s*\(',
             'generate_enhanced_analysis('),
            (r'generate_premium_analysis_30_articles\s*\(',
             'generate_enhanced_analysis('),
            
            # Utility functions
            (r'create_empty_results_enhanced\s*\(',
             'create_empty_result('),
        ]
    
    def create_backup(self):
        """Create backup of current files."""
        print(f"📁 Creating backup in {self.backup_dir}/...")
        
        if os.path.exists(self.backup_dir):
            shutil.rmtree(self.backup_dir)
        os.makedirs(self.backup_dir)
        
        # Find all Python files
        python_files = glob.glob("*.py") + glob.glob("**/*.py", recursive=True)
        
        for file_path in python_files:
            if not file_path.startswith(self.backup_dir):
                backup_path = os.path.join(self.backup_dir, file_path)
                os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                shutil.copy2(file_path, backup_path)
        
        print(f"✅ Backup created with {len(python_files)} files")
    
    def update_file(self, file_path: str) -> bool:
        """Update a single file with new imports and function calls."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            changes_in_file = []
            
            # Apply import replacements
            for old_pattern, new_import in self.import_replacements:
                if re.search(old_pattern, content):
                    content = re.sub(old_pattern, new_import, content)
                    changes_in_file.append(f"Updated import: {old_pattern} -> {new_import}")
            
            # Apply function call replacements
            for old_pattern, new_call in self.function_replacements:
                if re.search(old_pattern, content):
                    content = re.sub(old_pattern, new_call, content)
                    changes_in_file.append(f"Updated function call: {old_pattern} -> {new_call}")
            
            # Write back if changes were made
            if content != original_content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                self.changes_made.extend([(file_path, change) for change in changes_in_file])
                print(f"📝 Updated {file_path} ({len(changes_in_file)} changes)")
                return True
            
            return False
            
        except Exception as e:
            print(f"❌ Error updating {file_path}: {e}")
            return False
    
    def find_remaining_issues(self):
        """Find any remaining references to old modules."""
        print("\n🔍 Scanning for remaining issues...")
        
        python_files = glob.glob("*.py") + glob.glob("**/*.py", recursive=True)
        issues_found = []
        
        old_module_patterns = [
            r'import enhanced_news_analysis',
            r'import news_utils_claude_sonnet_4',
            r'import quality_validation',
            r'from enhanced_news_analysis',
            r'from news_utils_claude_sonnet_4',
            r'from quality_validation',
            r'fetch_comprehensive_news_.*_PARALLEL_WITH_QUALITY',
            r'fetch_.*_enhanced_.*_WITH_.*',
            r'generate_premium_analysis_(?!enhanced)',
        ]
        
        for file_path in python_files:
            if file_path.startswith(self.backup_dir):
                continue
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                for line_num, line in enumerate(content.split('\n'), 1):
                    for pattern in old_module_patterns:
                        if re.search(pattern, line) and not line.strip().startswith('#'):
                            issues_found.append((file_path, line_num, line.strip()))
            except:
                continue
        
        if issues_found:
            print(f"⚠️ Found {len(issues_found)} potential issues:")
            for file_path, line_num, line in issues_found:
                print(f"   {file_path}:{line_num}: {line}")
        else:
            print("✅ No remaining issues found!")
        
        return issues_found
    
    def delete_old_files(self):
        """Delete the old module files."""
        old_files = [
            'enhanced_news_analysis.py',
            'news_utils_claude_sonnet_4.py',
            'quality_validation.py'
        ]
        
        deleted = []
        for file_path in old_files:
            if os.path.exists(file_path):
                os.remove(file_path)
                deleted.append(file_path)
                print(f"🗑️ Deleted {file_path}")
        
        if deleted:
            print(f"✅ Deleted {len(deleted)} old module files")
        else:
            print("ℹ️ No old module files found to delete")
    
    def run_migration(self):
        """Run the complete migration process."""
        print("🚀 Starting News Utils Migration...")
        print("=" * 50)
        
        # Step 1: Create backup
        self.create_backup()
        
        # Step 2: Update files
        print(f"\n📝 Updating Python files...")
        python_files = glob.glob("*.py") + glob.glob("**/*.py", recursive=True)
        python_files = [f for f in python_files if not f.startswith(self.backup_dir)]
        
        updated_files = 0
        for file_path in python_files:
            if self.update_file(file_path):
                updated_files += 1
        
        print(f"✅ Updated {updated_files} files")
        
        # Step 3: Find remaining issues
        issues = self.find_remaining_issues()
        
        # Step 4: Delete old files
        print(f"\n🗑️ Cleaning up old files...")
        self.delete_old_files()
        
        # Step 5: Summary
        print(f"\n📊 Migration Summary:")
        print(f"   • Files backed up: {len(glob.glob(self.backup_dir + '/**/*.py', recursive=True))}")
        print(f"   • Files updated: {updated_files}")
        print(f"   • Total changes: {len(self.changes_made)}")
        print(f"   • Remaining issues: {len(issues)}")
        
        if self.changes_made:
            print(f"\n📋 Changes made:")
            for file_path, change in self.changes_made:
                print(f"   {file_path}: {change}")
        
        print(f"\n🎯 Migration complete!")
        print(f"   • Backup available in: {self.backup_dir}/")
        print(f"   • Test your application to ensure everything works")
        
        if issues:
            print(f"   ⚠️ Manual review needed for {len(issues)} remaining issues")
        else:
            print(f"   ✅ No manual changes needed!")
        
        return len(issues) == 0

def main():
    """Main function to run the migration."""
    migrator = NewsUtilsMigrator()
    
    # Check if we're in the right directory
    if not os.path.exists('app.py') and not os.path.exists('main.py'):
        print("⚠️ Warning: No app.py or main.py found. Are you in the right directory?")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            print("Migration cancelled.")
            return
    
    # Run migration
    success = migrator.run_migration()
    
    if success:
        print("\n🎉 Migration completed successfully!")
        print("\nNext steps:")
        print("1. Test your application: python app.py")
        print("2. If issues, restore from backup: cp -r backup_before_migration/* .")
        print("3. Install consolidated news_utils.py from the provided code")
    else:
        print("\n⚠️ Migration completed with issues.")
        print("Please review the remaining issues listed above.")

if __name__ == "__main__":
    main()