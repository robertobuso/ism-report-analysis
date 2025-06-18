import logging
import re
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field, validator, model_validator, ValidationError
from config_loader import config_loader

logger = logging.getLogger(__name__)

class PMIValue(BaseModel):
    """Model for a PMI value with validation."""
    value: Union[float, str]
    direction: str
    
    @validator('value')
    def validate_value(cls, v):
        if v is None: # Allow None
            return None
        if isinstance(v, str):
            try:
                cleaned_v = re.sub(r'[^\d\.\-]', '', v) # Keep digits, dot, minus
                if cleaned_v:
                    return float(cleaned_v)
                else: # String was non-numeric
                    logger.warning(f"PMI value string '{v}' is non-numeric after cleaning. Returning None.")
                    return None 
            except ValueError:
                logger.warning(f"Could not convert PMI value string to float: {v}. Returning None.")
                return None
        return v # Already float or int
    
    @validator('direction')
    def validate_direction(cls, v):
        """Standardize direction strings."""
        v = v.lower()
        
        # Map variations to standard terms
        direction_map = {
            'growing': 'Growing',
            'growth': 'Growing',
            'expanding': 'Growing',
            'expansion': 'Growing',
            'increasing': 'Growing',
            'increased': 'Growing',
            'higher': 'Growing',
            
            'contracting': 'Contracting',
            'contraction': 'Contracting',
            'declining': 'Contracting',
            'decreased': 'Contracting',
            'decreasing': 'Contracting',
            'lower': 'Contracting',
            
            'slowing': 'Slowing',
            'slower': 'Slowing',
            
            'faster': 'Faster',
            
            'too high': 'Too High',
            'too low': 'Too Low'
        }
        
        # Return standardized direction if in map, otherwise return as is with first letter capitalized
        return direction_map.get(v, v.capitalize())

class IndustryCategory(BaseModel):
    """Model for an industry category with validation."""
    industries: List[str]
    
    @validator('industries')
    def validate_industries(cls, v):
        """Clean and validate industry names."""
        if not v:
            return []
            
        # Clean industry names and remove duplicates while preserving order
        cleaned = []
        seen = set()
        
        for industry in v:
            if not industry or not isinstance(industry, str):
                continue
                
            # Skip invalid entries
            if len(industry.strip()) < 3 or industry.strip().lower() in ["are:", "in order", "following order"]:
                continue
                
            # Clean up the name
            industry = industry.strip()
            
            # Only add if not already seen
            if industry.lower() not in seen:
                cleaned.append(industry)
                seen.add(industry.lower())
                
        return cleaned
    
    class Config:
        """Configure model behavior."""
        validate_assignment = True

class ISMReport(BaseModel):
    """Model for the full ISM report data with validation."""
    month_year: str
    report_type: str = "Manufacturing"
    indices: Dict[str, PMIValue] = Field(default_factory=dict)
    industry_data: Dict[str, Dict[str, List[str]]] = Field(default_factory=dict)
    index_summaries: Dict[str, str] = Field(default_factory=dict)
    
    @validator('month_year')
    def validate_month_year(cls, v):
        """Validate and standardize month_year format."""
        if not v or v == "Unknown":
            # Default to current month/year if unknown
            return datetime.now().strftime("%B %Y")
            
        # Try to convert to standard format
        try:
            # Check common patterns
            patterns = [
                # Month YYYY
                (r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})', 
                 lambda m: f"{m.group(1)} {m.group(2)}"),
                # MM/YYYY or MM-YYYY
                (r'(\d{1,2})[/-](\d{4})', 
                 lambda m: f"{cls._month_num_to_name(int(m.group(1)))} {m.group(2)}"),
                # Month Abbreviation YYYY
                (r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})', 
                 lambda m: f"{cls._month_abbr_to_name(m.group(1))} {m.group(2)}")
            ]
            
            for pattern, formatter in patterns:
                match = re.match(pattern, v, re.IGNORECASE)
                if match:
                    return formatter(match)
            
            # If no patterns match, return as is
            return v
        except Exception as e:
            logger.warning(f"Error standardizing month_year format: {str(e)}")
            return v
    
    @validator('indices')
    def validate_indices(cls, v):
        """Validate and standardize indices."""
        # Ensure certain indices exist with valid values
        expected_indices = [
            "Manufacturing PMI", "New Orders", "Production", 
            "Employment", "Supplier Deliveries", "Inventories", 
            "Customers' Inventories", "Prices", "Backlog of Orders",
            "New Export Orders", "Imports", "Services PMI", "Business Activity"
        ]
        
        # Filter to either Manufacturing or Services indices based on report_type
        # (This will be checked in a model_validator)
        
        # Ensure all indices have proper PMIValue objects
        validated = {}
        for key, value in v.items():
            # If it's already a PMIValue, use it
            if isinstance(value, PMIValue):
                validated[key] = value
            elif isinstance(value, dict):
                # Try to convert dict to PMIValue
                try:
                    # Extract value and direction from dict
                    pmi_value = value.get('value', value.get('current', 0))
                    direction = value.get('direction', 'Unknown')
                    
                    validated[key] = PMIValue(value=pmi_value, direction=direction)
                except Exception as e:
                    logger.warning(f"Error converting dict to PMIValue for {key}: {str(e)}")
            else:
                logger.warning(f"Invalid index value for {key}: {value}")
        
        return validated
    
    @validator('industry_data')
    def validate_industry_data(cls, v):
        """Validate and standardize industry data."""
        validated = {}
        
        for index_name, categories in v.items():
            validated_categories = {}
            
            for category, industries in categories.items():
                # Validate industries using IndustryCategory model
                industry_cat = IndustryCategory(industries=industries)
                validated_categories[category] = industry_cat.industries
            
            validated[index_name] = validated_categories
        
        return validated
    
    # Updated to use model_validator instead of root_validator
    @model_validator(mode='after')
    def validate_report_consistency(self):
        """Ensure report type is consistent with indices and industries."""
        # Access values directly from self
        indices = self.indices
        
        # Check if indices are consistent with report type
        if self.report_type == 'Manufacturing':
            # Should have Manufacturing PMI
            if 'Manufacturing PMI' not in indices and 'Services PMI' in indices:
                # This looks like a services report mislabeled as manufacturing
                self.report_type = 'Services'
                logger.warning("Changed report type to Services based on indices")
        elif self.report_type == 'Services':
            # Should have Services PMI or Business Activity
            if 'Services PMI' not in indices and 'Business Activity' not in indices and 'Manufacturing PMI' in indices:
                # This looks like a manufacturing report mislabeled as services
                self.report_type = 'Manufacturing'
                logger.warning("Changed report type to Manufacturing based on indices")
        
        return self
    
    @staticmethod
    def _month_num_to_name(month_num):
        """Convert month number to name."""
        month_names = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        return month_names[month_num] if 1 <= month_num <= 12 else "Unknown"
    
    @staticmethod
    def _month_abbr_to_name(month_abbr):
        """Convert month abbreviation to name."""
        month_map = {
            'jan': 'January', 'feb': 'February', 'mar': 'March', 'apr': 'April',
            'may': 'May', 'jun': 'June', 'jul': 'July', 'aug': 'August',
            'sep': 'September', 'oct': 'October', 'nov': 'November', 'dec': 'December'
        }
        return month_map.get(month_abbr.lower(), month_abbr)
    
    def to_dict(self):
        """Convert model to dictionary."""
        result = {
            "month_year": self.month_year,
            "report_type": self.report_type,
            "indices": {},
            "industry_data": self.industry_data,
            "index_summaries": self.index_summaries
        }
        
        # Convert PMIValue objects to dicts
        for key, value in self.indices.items():
            result["indices"][key] = {
                "value": value.value,
                "direction": value.direction
            }
        
        return result
    
    class Config:
        """Configure model behavior."""
        validate_assignment = True

class DataTransformationPipeline:
    """Pipeline for transforming and validating extracted data."""
    
    @staticmethod
    def process(extracted_data: Dict[str, Any], report_type: str) -> Dict[str, Any]:
        """
        Process extracted data through the validation and transformation pipeline.
        
        Args:
            extracted_data: The data extracted from the report
            report_type: Type of report (Manufacturing or Services)
            
        Returns:
            Validated and transformed data
        """
        try:
            # Add import for JSON serialization in error reporting
            import json
            
            if not isinstance(extracted_data, dict): # Ensure input is a dict
                logger.error(f"Extracted data is not a dictionary: {type(extracted_data)}. Cannot process.")
                # Return a minimal valid structure for this report_type
                return {
                    "month_year": datetime.now().strftime("%B %Y"),
                    "report_type": report_type,
                    "indices": {}, "industry_data": {}, "index_summaries": {}
                }

            # Step 1: Add/ensure report_type
            extracted_data['report_type'] = report_type.capitalize() # Standardize case
            
            # Step 2: Create and validate using Pydantic model
            try:
                report_model = ISMReport(**extracted_data)
            except ValidationError as ve:
                logger.error(f"Pydantic validation failed during initial model creation: {ve}")
                logger.error(f"Problematic extracted_data: {json.dumps(extracted_data, indent=2)}")
                # Fallback: try to create a model with minimal required fields if possible
                minimal_data = {
                    "month_year": extracted_data.get("month_year", datetime.now().strftime("%B %Y")),
                    "report_type": report_type.capitalize(),
                    "indices": extracted_data.get("indices", {}),
                    "industry_data": extracted_data.get("industry_data", {}),
                    "index_summaries": extracted_data.get("index_summaries", {})
                }
                try:
                    report_model = ISMReport(**minimal_data)
                    logger.warning("Created ISMReport model with minimal data due to initial validation errors.")
                except ValidationError as ve_minimal:
                    logger.error(f"Pydantic validation failed even with minimal data: {ve_minimal}")
                    # If even minimal creation fails, return a very basic dict
                    return {
                        "month_year": minimal_data["month_year"],
                        "report_type": minimal_data["report_type"],
                        "indices": {}, "industry_data": {}, "index_summaries": {}
                    }

            # Step 3: Apply additional transformations
            DataTransformationPipeline._standardize_industry_names(report_model)
            DataTransformationPipeline._infer_missing_values(report_model)
            # DataTransformationPipeline._validate_industry_consistency(report_model)
            
            # Step 4: Convert back to dictionary
            return report_model.to_dict()
            
        except Exception as e:
            logger.error(f"Error in data transformation pipeline: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Fallback: return original data with minimal fixes
            try:
                # Add report_type if missing
                if 'report_type' not in extracted_data:
                    extracted_data['report_type'] = report_type
                
                # Ensure month_year is present
                if 'month_year' not in extracted_data or not extracted_data['month_year']:
                    extracted_data['month_year'] = datetime.now().strftime("%B %Y")
                
                # Ensure all required keys exist
                for key in ['indices', 'industry_data', 'index_summaries']:
                    if key not in extracted_data:
                        extracted_data[key] = {}
                
                return extracted_data
            except Exception as e2:
                logger.error(f"Error in fallback processing: {str(e2)}")
                
                # Last resort fallback
                return {
                    "month_year": datetime.now().strftime("%B %Y"),
                    "report_type": report_type,
                    "indices": {},
                    "industry_data": {},
                    "index_summaries": {}
                }
        
    @staticmethod
    def _standardize_industry_names(report: ISMReport) -> None:
        """
        Standardize industry names across all indices using canonical list from config
        and deduplicate them within each category after standardization.
        """
        canonical_industries = config_loader.get_canonical_industries(report.report_type)
        if not canonical_industries:
            logger.warning(f"No canonical industries loaded for report type '{report.report_type}'. Skipping standardization.")
            return

        # Create a mapping for quick lookups (lowercase for case-insensitivity)
        # This map helps find the canonical name from various potential inputs.
        # More sophisticated matching (e.g., fuzzy matching) could be added if needed.
        industry_mapping_to_canonical: Dict[str, str] = {}
        for canon_name in canonical_industries:
            industry_mapping_to_canonical[canon_name.lower()] = canon_name
            # Add common variations (e.g., without "Products", without "& Allied")
            # This part needs to be robust based on observed LLM outputs.
            name_no_products = re.sub(r'\s+Products$', '', canon_name, flags=re.IGNORECASE).strip()
            if name_no_products.lower() != canon_name.lower():
                industry_mapping_to_canonical[name_no_products.lower()] = canon_name
            
            name_with_and = canon_name.replace(" & ", " and ")
            if name_with_and.lower() != canon_name.lower():
                industry_mapping_to_canonical[name_with_and.lower()] = canon_name
            
            # Consider splitting by " & " or " and " and checking parts
            parts = re.split(r'\s+&\s+|\s+and\s+', canon_name, flags=re.IGNORECASE)
            if len(parts) > 1:
                industry_mapping_to_canonical[parts[0].lower()] = canon_name # e.g., "Computer" -> "Computer & Electronic Products"

        updated_industry_data = {}
        for index_name, categories in report.industry_data.items():
            updated_categories = {}
            for category_name, raw_industries_from_llm in categories.items():
                standardized_for_this_category = []
                if not isinstance(raw_industries_from_llm, list):
                    logger.warning(f"Industries for {index_name} - {category_name} is not a list: {raw_industries_from_llm}. Skipping.")
                    continue

                for raw_industry in raw_industries_from_llm:
                    if not isinstance(raw_industry, str): 
                        logger.debug(f"Skipping non-string industry entry: {raw_industry}")
                        continue
                    
                    clean_raw_industry = raw_industry.strip().lower()
                    canonical_name = industry_mapping_to_canonical.get(clean_raw_industry)

                    if not canonical_name:
                        # Try a simple "best match" if direct map fails - find a canonical name that contains the raw_industry (or vice-versa)
                        # This is a basic attempt; more advanced matching (e.g., Levenshtein distance) could be used.
                        best_match_score = 0
                        potential_match = None
                        for canon_ind in canonical_industries:
                            if clean_raw_industry in canon_ind.lower() or canon_ind.lower() in clean_raw_industry:
                                # Simple containment check (could be improved)
                                current_score = len(clean_raw_industry) if clean_raw_industry in canon_ind.lower() else len(canon_ind)
                                if current_score > best_match_score:
                                    best_match_score = current_score
                                    potential_match = canon_ind
                        if potential_match:
                            canonical_name = potential_match
                        else:
                            # If still no match, keep original (after basic cleaning), but log it
                            logger.warning(f"Industry '{raw_industry}' not found in canonical list or mappings for {report.report_type}. Keeping original.")
                            # Basic cleaning for non-standardized names
                            cleaned_non_canonical = re.sub(r'\s*\(\d+\)$', '', raw_industry.strip()).strip() # Remove (1) type notes
                            if len(cleaned_non_canonical) > 2: # Only keep if somewhat substantial
                                standardized_for_this_category.append(cleaned_non_canonical)
                            continue # Skip adding to list if it's too short or problematic

                    if canonical_name: # Ensure we have a name
                        standardized_for_this_category.append(canonical_name)
                
                # Deduplicate the list of standardized canonical names for this category
                unique_standardized_industries = []
                seen_in_category = set()
                for std_name in standardized_for_this_category:
                    if std_name.lower() not in seen_in_category:
                        unique_standardized_industries.append(std_name)
                        seen_in_category.add(std_name.lower())
                
                updated_categories[category_name] = unique_standardized_industries
            updated_industry_data[index_name] = updated_categories
        report.industry_data = updated_industry_data
    
    @staticmethod
    def _infer_missing_values(report: ISMReport) -> None:
        """
        Infer missing values based on available data.
        
        Args:
            report: The report model to update
        """
        # If Manufacturing PMI or Services PMI is missing but we have other indices, try to infer it
        if report.report_type == 'Manufacturing' and 'Manufacturing PMI' not in report.indices and len(report.indices) > 0:
            # Use the average of the primary components as an approximation
            components = ['New Orders', 'Production', 'Employment', 'Supplier Deliveries', 'Inventories']
            values = []
            
            for component in components:
                if component in report.indices:
                    values.append(report.indices[component].value)
            
            if values:
                avg_value = sum(values) / len(values)
                direction = 'Growing' if avg_value >= 50.0 else 'Contracting'
                
                report.indices['Manufacturing PMI'] = PMIValue(value=avg_value, direction=direction)
                logger.info(f"Inferred Manufacturing PMI: {avg_value} ({direction})")
        
        # Similarly for Services PMI
        if report.report_type == 'Services' and 'Services PMI' not in report.indices and len(report.indices) > 0:
            components = ['Business Activity', 'New Orders', 'Employment', 'Supplier Deliveries']
            values = []
            
            for component in components:
                if component in report.indices:
                    values.append(report.indices[component].value)
            
            if values:
                avg_value = sum(values) / len(values)
                direction = 'Growing' if avg_value >= 50.0 else 'Contracting'
                
                report.indices['Services PMI'] = PMIValue(value=avg_value, direction=direction)
                logger.info(f"Inferred Services PMI: {avg_value} ({direction})")
    
    @staticmethod
    def _validate_industry_consistency(report: ISMReport) -> None:
        """
        Validate and correct industry data for consistency.
        
        Args:
            report: The report model to update
        """
        # Check each index to ensure industries aren't duplicated across categories
        for index_name, categories in report.industry_data.items():
            seen_industries = set()
            industries_to_remove = {}
            
            # Identify duplicated industries
            for category, industries in categories.items():
                for i, industry in enumerate(industries):
                    if industry in seen_industries:
                        # Mark for removal
                        if category not in industries_to_remove:
                            industries_to_remove[category] = []
                        industries_to_remove[category].append(i)
                    else:
                        seen_industries.add(industry)
            
            # Remove duplicated industries
            for category, indices in industries_to_remove.items():
                # Remove from highest index to lowest to avoid shifting issues
                for i in sorted(indices, reverse=True):
                    if i < len(categories[category]):
                        industry = categories[category][i]
                        logger.info(f"Removing duplicate industry {industry} from {index_name} - {category}")
                        categories[category].pop(i)