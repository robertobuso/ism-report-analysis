"""
Configuration for Quality Validation Engine
==========================================
"""

import os
from typing import Dict, Any

class QualityConfig:
    """Configuration for quality validation system."""
    
    def __init__(self):
        self.load_config()
    
    def load_config(self):
        """Load configuration from environment and defaults."""
        
        # Quality thresholds
        self.MINIMUM_QUALITY_SCORE = float(os.getenv('QUALITY_MIN_SCORE', '7.0'))
        self.TARGET_QUALITY_SCORE = float(os.getenv('QUALITY_TARGET_SCORE', '8.0'))
        self.EXCELLENT_QUALITY_SCORE = float(os.getenv('QUALITY_EXCELLENT_SCORE', '8.5'))
        
        # Validation settings
        self.MAX_VALIDATION_RETRIES = int(os.getenv('QUALITY_MAX_RETRIES', '2'))
        self.VALIDATION_TIMEOUT = int(os.getenv('QUALITY_TIMEOUT', '180'))
        self.ENABLE_WEB_SEARCH = os.getenv('QUALITY_ENABLE_WEB_SEARCH', 'true').lower() == 'true'
        
        # Claude settings
        self.CLAUDE_MODEL = os.getenv('CLAUDE_MODEL', 'claude-sonnet-4-20250514')
        self.CLAUDE_MAX_TOKENS = int(os.getenv('CLAUDE_MAX_TOKENS', '8000'))
        self.CLAUDE_TEMPERATURE = float(os.getenv('CLAUDE_TEMPERATURE', '0.05'))
        
        # Monitoring
        self.ENABLE_QUALITY_LOGGING = os.getenv('QUALITY_LOGGING', 'true').lower() == 'true'
        self.QUALITY_LOG_LEVEL = os.getenv('QUALITY_LOG_LEVEL', 'INFO')
        
    def get_validation_config(self) -> Dict[str, Any]:
        """Get validation configuration."""
        return {
            'minimum_score': self.MINIMUM_QUALITY_SCORE,
            'target_score': self.TARGET_QUALITY_SCORE,
            'excellent_score': self.EXCELLENT_QUALITY_SCORE,
            'max_retries': self.MAX_VALIDATION_RETRIES,
            'timeout': self.VALIDATION_TIMEOUT,
            'enable_web_search': self.ENABLE_WEB_SEARCH
        }
    
    def get_claude_config(self) -> Dict[str, Any]:
        """Get Claude configuration."""
        return {
            'model': self.CLAUDE_MODEL,
            'max_tokens': self.CLAUDE_MAX_TOKENS,
            'temperature': self.CLAUDE_TEMPERATURE
        }

# Global config instance
quality_config = QualityConfig()