# report_detection.py
import re
import logging
from typing import Dict, List, Tuple, Optional, Union
import pdfplumber
import PyPDF2

logger = logging.getLogger(__name__)

class EnhancedReportTypeDetector:
    """Enhanced detection of report types using multiple strategies."""
    
    # Keyword weights (higher = stronger indicator)
    MANUFACTURING_KEYWORDS = {
        "MANUFACTURING PMI": 10,
        "MANUFACTURING INDEX": 8,
        "MANUFACTURING ISM": 8,
        "PRODUCTION INDEX": 6,
        "NEW ORDERS INDEX": 6,
        "MANUFACTURING SECTOR": 5,
        "MANUFACTURING BUSINESS": 4,
        "FABRICATED METAL": 3,
        "PETROLEUM & COAL": 3,
        "COMPUTER & ELECTRONIC PRODUCTS": 3
    }
    
    SERVICES_KEYWORDS = {
        "SERVICES PMI": 10,
        "SERVICES INDEX": 8,
        "SERVICES ISM": 8,
        "BUSINESS ACTIVITY": 6,
        "NON-MANUFACTURING": 5,
        "SERVICE SECTOR": 5,
        "NMI": 4,
        "INFORMATION": 2,
        "HEALTH CARE": 2,
        "FINANCE & INSURANCE": 2,
        "ACCOMMODATION & FOOD SERVICES": 2,
        "SERVICE MANAGEMENT": 2
    }
    
    # Structural patterns
    MANUFACTURING_PATTERNS = [
        r"MANUFACTURING AT A GLANCE",
        r"MANUFACTURING INDEX SUMMARIES",
        r"MANUFACTURING PMI®\s+AT\s+\d+\.\d+",
        r"COMMODITIES UP IN PRICE.*?COMMODITIES DOWN IN PRICE"
    ]
    
    SERVICES_PATTERNS = [
        r"SERVICES AT A GLANCE",
        r"SERVICES INDEX SUMMARIES",
        r"SERVICES PMI®\s+AT\s+\d+\.\d+",
        r"SERVICE COMMODITIES UP IN PRICE.*?SERVICE COMMODITIES DOWN IN PRICE",
        r"BUSINESS ACTIVITY/PRODUCTION"
    ]
    
    # Industry lists specific to each report type
    MANUFACTURING_INDUSTRIES = [
        "CHEMICAL", "COMPUTER & ELECTRONIC", "FABRICATED METAL", "FOOD, BEVERAGE",
        "MACHINERY", "PETROLEUM & COAL", "PLASTICS & RUBBER", "PRIMARY METALS",
        "TRANSPORTATION EQUIPMENT", "WOOD", "NONMETALLIC MINERAL", "PAPER",
        "PRINTING", "APPAREL", "TEXTILE", "ELECTRICAL EQUIPMENT"
    ]
    
    SERVICES_INDUSTRIES = [
        "FINANCE & INSURANCE", "HEALTH CARE", "INFORMATION", "PROFESSIONAL SERVICES",
        "ACCOMMODATION & FOOD", "EDUCATIONAL SERVICES", "UTILITIES", "RETAIL TRADE",
        "WHOLESALE TRADE", "REAL ESTATE", "TRANSPORTATION & WAREHOUSING",
        "PUBLIC ADMINISTRATION", "AGRICULTURE", "MINING", "MANAGEMENT"
    ]
    
    @classmethod
    def detect_report_type(cls, pdf_path: str) -> str:
        """
        Detect report type using multiple strategies and weighted scoring.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Report type as a string ('Manufacturing' or 'Services')
        """
        try:
            # Extract text using multiple methods for better coverage
            text = cls._extract_text_with_fallbacks(pdf_path)
            
            if not text:
                logger.error(f"Failed to extract text from {pdf_path}")
                # Default to Manufacturing if text extraction fails
                return 'Manufacturing'
            
            # Apply multiple detection strategies
            keyword_score = cls._calculate_keyword_score(text)
            structure_score = cls._analyze_document_structure(text)
            industry_score = cls._analyze_industry_mentions(text)
            
            # Log the scores for debugging
            logger.info(f"Detection scores - Keyword: {keyword_score}, Structure: {structure_score}, Industry: {industry_score}")
            
            # Combine scores - each returns a tuple (manufacturing_score, services_score)
            combined_mfg_score = (
                keyword_score[0] * 0.5 + 
                structure_score[0] * 0.3 + 
                industry_score[0] * 0.2
            )
            
            combined_svc_score = (
                keyword_score[1] * 0.5 + 
                structure_score[1] * 0.3 + 
                industry_score[1] * 0.2
            )
            
            logger.info(f"Combined scores - Manufacturing: {combined_mfg_score}, Services: {combined_svc_score}")
            
            # Determine report type based on higher score
            if combined_mfg_score > combined_svc_score:
                return 'Manufacturing'
            else:
                return 'Services'
                
        except Exception as e:
            logger.error(f"Error detecting report type: {str(e)}")
            # Default to Manufacturing if error occurs
            return 'Manufacturing'
    
    @classmethod
    def _extract_text_with_fallbacks(cls, pdf_path: str) -> str:
        """
        Extract text using multiple methods with fallbacks.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Extracted text from the PDF
        """
        text = ""
        
        # Try pdfplumber first (better for maintaining structure)
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text(x_tolerance=3, y_tolerance=3)
                    if page_text:
                        text += page_text + "\n\n"
                        
            if len(text) >= 500:  # Consider it successful if we got a reasonable amount of text
                return text
        except Exception as e:
            logger.warning(f"pdfplumber extraction failed: {str(e)}")
        
        # Fallback to PyPDF2
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n\n"
        except Exception as e:
            logger.warning(f"PyPDF2 extraction failed: {str(e)}")
        
        return text
    
    @classmethod
    def _calculate_keyword_score(cls, text: str) -> Tuple[float, float]:
        """
        Calculate weighted scores based on keyword occurrences.
        
        Args:
            text: Extracted text from the PDF
            
        Returns:
            Tuple of (manufacturing_score, services_score)
        """
        text_upper = text.upper()
        
        # Count weighted occurrences of manufacturing keywords
        mfg_score = 0
        for keyword, weight in cls.MANUFACTURING_KEYWORDS.items():
            count = text_upper.count(keyword)
            mfg_score += count * weight
        
        # Count weighted occurrences of services keywords
        svc_score = 0
        for keyword, weight in cls.SERVICES_KEYWORDS.items():
            count = text_upper.count(keyword)
            svc_score += count * weight
        
        # Normalize scores to account for variance in document length
        total_score = mfg_score + svc_score
        if total_score > 0:
            mfg_normalized = mfg_score / total_score * 100
            svc_normalized = svc_score / total_score * 100
        else:
            mfg_normalized = 50  # Equal weight if no keywords found
            svc_normalized = 50
            
        return (mfg_normalized, svc_normalized)
    
    @classmethod
    def _analyze_document_structure(cls, text: str) -> Tuple[float, float]:
        """
        Analyze document structure using pattern matching.
        
        Args:
            text: Extracted text from the PDF
            
        Returns:
            Tuple of (manufacturing_score, services_score)
        """
        # Check for structural patterns
        mfg_matches = 0
        for pattern in cls.MANUFACTURING_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
                mfg_matches += 1
        
        svc_matches = 0
        for pattern in cls.SERVICES_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
                svc_matches += 1
        
        # Calculate scores based on percentage of patterns found
        mfg_score = mfg_matches / len(cls.MANUFACTURING_PATTERNS) * 100
        svc_score = svc_matches / len(cls.SERVICES_PATTERNS) * 100
        
        return (mfg_score, svc_score)
    
    @classmethod
    def _analyze_industry_mentions(cls, text: str) -> Tuple[float, float]:
        """
        Analyze industry mentions for additional context.
        
        Args:
            text: Extracted text from the PDF
            
        Returns:
            Tuple of (manufacturing_score, services_score)
        """
        text_upper = text.upper()
        
        # Count mentions of manufacturing industries
        mfg_count = 0
        for industry in cls.MANUFACTURING_INDUSTRIES:
            mfg_count += text_upper.count(industry)
        
        # Count mentions of services industries
        svc_count = 0
        for industry in cls.SERVICES_INDUSTRIES:
            svc_count += text_upper.count(industry)
        
        # Normalize scores
        total_count = mfg_count + svc_count
        if total_count > 0:
            mfg_score = mfg_count / total_count * 100
            svc_score = svc_count / total_count * 100
        else:
            mfg_score = 50  # Equal weight if no industries found
            svc_score = 50
        
        return (mfg_score, svc_score)