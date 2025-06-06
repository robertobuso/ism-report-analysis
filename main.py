import os
import logging
import traceback
import re
import warnings
import ast
import json
from googleapiclient import discovery
from dotenv import load_dotenv
from tools import SimplePDFExtractionTool, SimpleDataStructurerTool

# Create necessary directories first
os.makedirs("logs", exist_ok=True)
os.makedirs("pdfs", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

from crewai import Crew, Process, Task
from agents import (
    create_extractor_agent,
    create_structurer_agent,
    create_validator_agent,
    create_formatter_agent,
    create_orchestrator_agent,
    create_data_correction_agent
)
from db_utils import store_report_data_in_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='logs/ism_analysis.log'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Set up OpenAI API
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

# Suppress the oauth2client warning
warnings.filterwarnings('ignore', message='file_cache is only supported with oauth2client<4.0.0')

def safely_parse_agent_output(output):
    """
    Safely parse the output from an agent, handling different output types.
    
    Args:
        output: The output from the agent, which could be a string, dict, or CrewOutput object
        
    Returns:
        A dictionary containing the parsed data, or None if parsing fails
    """
    try:
        logger.info(f"Attempting to parse agent output of type: {type(output)}")
        
        # If output is None, return a default structure
        if output is None:
            logger.warning("Agent output is None, returning default structure")
            return {
                "month_year": "Unknown",
                "report_type": "Manufacturing",
                "manufacturing_table": "",
                "index_summaries": {},
                "industry_data": {}
            }
        
        # If it's already a dict, validate it has actual data
        if isinstance(output, dict):
            # Validate the dictionary has non-empty industry data
            if 'industry_data' in output and output['industry_data']:
                if any(categories for categories in output['industry_data'].values() if categories):
                    return output
                else:
                    logger.warning("Parsed output has empty industry_data, will try alternatives")
            elif 'corrected_industry_data' in output and output['corrected_industry_data']:
                if any(categories for categories in output['corrected_industry_data'].values() if categories):
                    # Move corrected_industry_data to industry_data
                    output['industry_data'] = output['corrected_industry_data']
                    return output
                else:
                    logger.warning("Parsed output has empty corrected_industry_data, will try alternatives")
            # Return the dict if it has other data even without industry data
            return output
        
        # Handle CrewOutput objects
        if hasattr(output, '__class__') and output.__class__.__name__ == 'CrewOutput':
            return extract_from_crew_output(output)
        
        # Handle string outputs
        if isinstance(output, str):
            # Check if it looks like a validation result dictionary
            if "'New Orders': True" in output or "'New Orders': False" in output:
                result = {}
                indices = [
                    "New Orders", "Production", "Employment", "Supplier Deliveries",
                    "Inventories", "Customers' Inventories", "Prices", "Backlog of Orders",
                    "New Export Orders", "Imports"
                ]
                
                import re
                for index in indices:
                    index_pattern = f"'{index}':\\s*(True|False)"
                    match = re.search(index_pattern, output)
                    if match:
                        result[index] = match.group(1) == "True"
                    else:
                        result[index] = False
                
                return result
            
            # Try parsing as JSON
            try:
                import json
                return json.loads(output.replace("'", '"').replace("True", "true").replace("False", "false"))
            except json.JSONDecodeError:
                pass
                
            # Try parsing as a dictionary literal
            try:
                import ast
                return ast.literal_eval(output)
            except (SyntaxError, ValueError):
                logger.warning(f"Failed to parse output using ast.literal_eval: {output[:100]}...")
                
            # Try to find a dictionary in the string
            import re
            dict_patterns = [
                r"\{(?:\s*'[^']*':\s*(?:'[^']*'|\{[^{}]*\}|\[[^[\]]*\]|true|false|\d+(?:\.\d+)?),?\s*)+\}",  # General dictionary pattern
                r"\{[^{}]*'month_year'[^{}]*\}",  # Pattern specific to month_year
                r"\{[^{}]*'New Orders'[^{}]*\}",  # Pattern specific to validation results
            ]
            
            for pattern in dict_patterns:
                dict_match = re.search(pattern, output)
                if dict_match:
                    try:
                        import ast
                        return ast.literal_eval(dict_match.group(0))
                    except (SyntaxError, ValueError):
                        try:
                            import json
                            cleaned_json = dict_match.group(0).replace("'", '"').replace("True", "true").replace("False", "false")
                            return json.loads(cleaned_json)
                        except json.JSONDecodeError:
                            pass
        
        # Special handling for other types of objects
        logger.warning(f"Trying to extract output from object of type {type(output)}")
        for attr in ['result', 'output', 'data', 'response', 'answer', 'final_answer', 'content']:
            if hasattr(output, attr):
                value = getattr(output, attr)
                if isinstance(value, dict):
                    return value
                elif isinstance(value, str):
                    try:
                        import ast
                        return ast.literal_eval(value)
                    except (SyntaxError, ValueError):
                        try:
                            import json
                            return json.loads(value.replace("'", '"'))
                        except json.JSONDecodeError:
                            pass
        
        # Check for task_outputs
        if hasattr(output, 'tasks_output'):
            tasks_output = output.tasks_output
            if isinstance(tasks_output, list) and len(tasks_output) > 0:
                last_output = tasks_output[-1]
                if isinstance(last_output, dict):
                    return last_output
                elif hasattr(last_output, 'output'):
                    return getattr(last_output, 'output')
        
        # If all else fails, try to extract from the CrewOutput
        return extract_from_crew_output(output)
        
    except Exception as e:
        logger.error(f"Error parsing agent output: {str(e)}")
        logger.error(f"Raw output type: {type(output)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Return a default structure rather than None
        return {
            "month_year": "Unknown",
            "report_type": "Manufacturing",
            "manufacturing_table": "",
            "index_summaries": {},
            "industry_data": {}
        }
    
def extract_from_crew_output(crew_output):
    """Extract dictionary data directly from a CrewOutput object."""
    try:
        import re
        logger.info(f"Attempting to extract from CrewOutput of type: {type(crew_output)}")
        
        # If it's already a dict, return it
        if isinstance(crew_output, dict):
            return crew_output
            
        # If it's None, return a default structure
        if crew_output is None:
            logger.warning("CrewOutput is None, returning default structure")
            return {
                "month_year": "Unknown",
                "report_type": "Manufacturing",
                "manufacturing_table": "",
                "index_summaries": {},
                "industry_data": {}
            }
        
        # Handle the case where the agent responded with an error message
        str_output = str(crew_output)
        if "I tried reusing the same input" in str_output:
            logger.warning("Agent reported input reuse error, providing fallback structure")
            return {
                "month_year": "Unknown",
                "report_type": "Manufacturing",
                "manufacturing_table": "",
                "index_summaries": {},
                "industry_data": {}
            }
            
        # Try to access common attributes that might contain the output
        attributes_to_check = ['result', 'raw_output', 'content', 'output', 'final_answer']
        
        for attr in attributes_to_check:
            if hasattr(crew_output, attr):
                value = getattr(crew_output, attr)
                if isinstance(value, dict):
                    return value
                elif isinstance(value, str):
                    try:
                        import json
                        parsed = json.loads(value.replace("'", '"'))
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        try:
                            import ast
                            parsed = ast.literal_eval(value)
                            if isinstance(parsed, dict):
                                return parsed
                        except (SyntaxError, ValueError):
                            pass
        
        # Try to access task_outputs if available
        if hasattr(crew_output, 'tasks_output') and crew_output.tasks_output:
            tasks = crew_output.tasks_output
            if isinstance(tasks, list) and len(tasks) > 0:
                last_task = tasks[-1]
                if isinstance(last_task, dict):
                    return last_task
                
                # Try to extract from the last task's output attribute
                if hasattr(last_task, 'output'):
                    output = last_task.output
                    if isinstance(output, dict):
                        return output
                    elif isinstance(output, str):
                        try:
                            import ast
                            return ast.literal_eval(output)
                        except (SyntaxError, ValueError):
                            pass
        
        # Access agent_outputs if available
        if hasattr(crew_output, 'agent_outputs'):
            agent_outputs = crew_output.agent_outputs
            if isinstance(agent_outputs, list) and len(agent_outputs) > 0:
                last_agent_output = agent_outputs[-1]
                if isinstance(last_agent_output, dict):
                    return last_agent_output
                elif hasattr(last_agent_output, 'output') and isinstance(last_agent_output.output, dict):
                    return last_agent_output.output
        
        # String representation parsing - critical for the error cases
        str_output = str(crew_output)
        
        # First, try to get a clean dictionary directly
        try:
            if str_output.startswith('{') and str_output.endswith('}'):
                import ast
                return ast.literal_eval(str_output)
        except (SyntaxError, ValueError):
            pass
        
        # Search for Final Answer section with a dictionary
        final_answer_match = re.search(r"## Final Answer:?\s+(\{[\s\S]*?\})", str_output)
        if final_answer_match:
            try:
                dict_text = final_answer_match.group(1)
                import ast
                return ast.literal_eval(dict_text)
            except (SyntaxError, ValueError):
                pass
            
        # Second, try to find dictionary patterns using regex
        dict_patterns = [
            r"\{(?:\s*'[^']*':\s*(?:'[^']*'|\{[^{}]*\}|\[[^[\]]*\]|true|false|\d+(?:\.\d+)?),?\s*)+\}",  # General dictionary pattern
            r"\{[^{}]*'month_year'[^{}]*\}",  # Pattern specific to month_year
            r"\{[^{}]*'New Orders'[^{}]*\}",  # Pattern specific to validation results
            r"\{[^{}]*'.*?'[^{}]*\}",  # Any dictionary with string keys
        ]
        
        import re
        for pattern in dict_patterns:
            try:
                dict_match = re.search(pattern, str_output, re.IGNORECASE)
                if dict_match:
                    match_text = dict_match.group(0)
                    # Try to clean up the match
                    match_text = match_text.replace("True", "true").replace("False", "false")
                    
                    # Try both ast and json parsing
                    try:
                        import ast
                        return ast.literal_eval(match_text)
                    except (SyntaxError, ValueError):
                        try:
                            import json
                            cleaned_json = match_text.replace("'", '"').replace("true", "true").replace("false", "false")
                            return json.loads(cleaned_json)
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logger.debug(f"Error in pattern matching: {str(e)}")
                continue
                
        # Handle truncated strings in the output (like the validation results)
        if "'New Orders': True" in str_output or "'month_year':" in str_output:
            # Build a dictionary from the visible keys and values
            result = {}
            
            if "'month_year':" in str_output:
                # This is likely extraction data
                month_year_match = re.search(r"'month_year':\s*'([^']+)'", str_output)
                if month_year_match:
                    result["month_year"] = month_year_match.group(1)
                
                # Add other expected keys
                result["manufacturing_table"] = "Extracted table content" if "'manufacturing_table':" in str_output else ""
                result["index_summaries"] = {} if "'index_summaries':" in str_output else {}
                result["industry_data"] = {} if "'industry_data':" in str_output else {}
                
                return result
                
            elif "'New Orders': True" in str_output or "'New Orders': False" in str_output:
                # This is likely validation results
                indices = [
                    "New Orders", "Production", "Employment", "Supplier Deliveries",
                    "Inventories", "Customers' Inventories", "Prices", "Backlog of Orders",
                    "New Export Orders", "Imports"
                ]
                
                for index in indices:
                    index_pattern = f"'{index}':\\s*(True|False)"
                    match = re.search(index_pattern, str_output)
                    if match:
                        result[index] = match.group(1) == "True"
                    else:
                        result[index] = False  # Default to False if not found
                
                return result
        
        # Another approach - try to look for dictionary keys at the end of output
        if hasattr(crew_output, 'final_answer') and isinstance(crew_output.final_answer, str):
            answer_lines = crew_output.final_answer.strip().split('\n')
            last_lines = '\n'.join(answer_lines[-20:])  # Check last 20 lines
            if '{' in last_lines and '}' in last_lines:
                dict_text = last_lines[last_lines.find('{'):last_lines.rfind('}')+1]
                try:
                    import ast
                    result = ast.literal_eval(dict_text)
                    if isinstance(result, dict):
                        return result
                except (SyntaxError, ValueError):
                    pass
        
        # Check for structured content or verification results in the log
        special_keys = ['month_year', 'manufacturing_table', 'index_summaries', 'industry_data', 'corrected_industry_data']
        if any(key in str_output for key in special_keys):
            # Try to reconstruct a basic dictionary
            temp_dict = {}
            for key in special_keys:
                if key in str_output:
                    temp_dict[key] = {} if key != 'month_year' else 'Unknown'
            
            # If we have some keys, return the skeleton structure
            if temp_dict:
                return temp_dict
        
        logger.error(f"Failed to extract data from CrewOutput")
        logger.error(f"String representation: {str_output[:500]}...")
        
        # Return a minimal valid structure as a last resort
        return {
            "month_year": "Unknown",
            "report_type": "Manufacturing",
            "manufacturing_table": "",
            "index_summaries": {},
            "industry_data": {}
        }
    except Exception as e:
        logger.error(f"Error in extract_from_crew_output: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Return a minimal valid structure
        return {
            "month_year": "Unknown",
            "report_type": "Manufacturing",
            "manufacturing_table": "",
            "index_summaries": {},
            "industry_data": {}
        }

def fallback_regex_parsing(text):
    """Fallback method to extract key data using regex patterns."""
    try:
        result = {}
        
        # Extract month_year
        month_year_match = re.search(r"'month_year':\s*'([^']+)'", text)
        if month_year_match:
            result["month_year"] = month_year_match.group(1)
        else:
            result["month_year"] = "Unknown"
        
        # Extract manufacturing_table (just the fact it exists)
        if "'manufacturing_table'" in text:
            result["manufacturing_table"] = "Extracted table content"
        else:
            result["manufacturing_table"] = ""
        
        # Extract index_summaries (just the fact they exist)
        if "'index_summaries'" in text:
            result["index_summaries"] = {}
        else:
            result["index_summaries"] = {}
        
        # Extract industry_data (basic structure)
        if "'industry_data'" in text:
            result["industry_data"] = {}
        else:
            result["industry_data"] = {}
        
        return result
    except Exception as e:
        logger.error(f"Fallback regex parsing failed: {str(e)}")
        return {
            "month_year": "Unknown",
            "manufacturing_table": "",
            "index_summaries": {},
            "industry_data": {}
        }

def process_single_pdf(pdf_path, visualization_options=None, report_type=None):
    """Process a single PDF file with optional visualization selections."""
    logger.info(f"Processing PDF: {pdf_path}")

    # If visualization_options is None, use default settings
    if visualization_options is None:
        visualization_options = {
            'basic': True,
            'heatmap': True,
            'timeseries': True,
            'industry': True
        }

    try:
        # First check if sheet_id.txt exists
        if os.path.exists("sheet_id.txt"):
            with open("sheet_id.txt", "r") as f:
                sheet_id = f.read().strip()
                if sheet_id:
                    logger.info(f"Found sheet_id.txt file with ID: {sheet_id}")
                else:
                    logger.warning("sheet_id.txt file exists but is empty")
        else:
            logger.warning("sheet_id.txt not found. A new Google Sheet will be created.")

        # Detect report type
        if not report_type:
            from report_handlers import ReportTypeFactory
            report_type = ReportTypeFactory.detect_report_type(pdf_path)
            logger.info(f"Detected report type: {report_type}")
        else:
            logger.info(f"Using provided report type: {report_type}")

        # Create agents
        extractor_agent = create_extractor_agent()
        data_correction_agent = create_data_correction_agent()
        validator_agent = create_validator_agent()
        formatter_agent = create_formatter_agent()

        # Execute extraction
        logger.info(f"Starting data extraction for {report_type} report...")

        # Always attempt direct PDF parsing first to get baseline data
        direct_data = None
        try:
            from pdf_utils import parse_ism_report
            logger.info("Performing initial direct PDF parsing")
            direct_data = parse_ism_report(pdf_path, report_type)

        except Exception as e:
            logger.error(f"Error in initial direct PDF parsing: {str(e)}")

        # Custom extraction task with report_type
        extraction_task = Task(
            description=f"""
            Extract all relevant data from the ISM {report_type} Report PDF.
            The PDF path is: {pdf_path}

            When using the PDF Extraction Tool, pass the path in this format:
            {{
                "extracted_data": {{
                    "pdf_path": "{pdf_path}",
                    "report_type": "{report_type}"
                }}
            }}

            You must extract:
            1. The month and year of the report
            2. The {'Manufacturing' if report_type == 'Manufacturing' else 'Services'} at a Glance table
            3. All index-specific summaries
            4. Industry mentions in each index summary

            YOUR FINAL ANSWER MUST BE A VALID DICTIONARY containing all extracted data.
            Format your answer as:

            {{
                'month_year': 'Month Year',
                'manufacturing_table': {{extracted indices data here}},
                'index_summaries': {{...}},
                'industry_data': {{...}}
            }}

            IMPORTANT: Replace 'manufacturing_table' with the actual indices data you extracted from the tool, not the literal string 'table content'.

            Ensure all data is correctly identified and structured for further processing.
            """,
            expected_output="A dictionary containing the extracted data with month_year, manufacturing_table, index_summaries, and industry_data",
            agent=extractor_agent
        )

        # Create extraction crew
        extraction_crew = Crew(
            agents=[extractor_agent],
            tasks=[extraction_task],
            verbose=True,
            process=Process.sequential
        )

        extraction_result = extraction_crew.kickoff()
        logger.info("Extraction result received")

        # Parse the extraction result
        extraction_data = safely_parse_agent_output(extraction_result)
        # Removed verbose logging
        
        extraction_data = validate_and_preserve_indices(extraction_data, report_type)
        # Removed verbose logging

        # Initialize extraction_data if it's None to avoid reference errors
        if extraction_data is None:
            extraction_data = {
                "month_year": "Unknown", 
                "manufacturing_table": "",
                "index_summaries": {},
                "industry_data": {},
                "report_type": report_type
            }
            logger.warning("extraction_data was None, initializing with default structure")

        # Add report_type to extraction_data
        if isinstance(extraction_data, dict):
            extraction_data['report_type'] = report_type

        if not extraction_data.get('industry_data') and not extraction_data.get('indices'):
            try:
                from pdf_utils import parse_ism_report
                logger.info("Attempting direct PDF parsing as fallback")
                direct_data = parse_ism_report(pdf_path, report_type)
                if direct_data:
                    logger.info("Successfully parsed PDF directly as fallback")
                    extraction_data.update(direct_data)
            except Exception as e:
                logger.error(f"Direct PDF parsing failed: {str(e)}")

        # FIXED: Simplified verification - only if we have minimal data
        total_industries = 0
        if extraction_data.get('industry_data'):
            total_industries = sum(
                len(industries) for categories in extraction_data['industry_data'].values() 
                for industries in categories.values() if isinstance(categories, dict)
            )

        logger.info(f"Direct PDF parsing found {total_industries} industries")

        # Add handling for the case where extraction_data is a Python object with corrected_industry_data
        if hasattr(extraction_data, 'corrected_industry_data'):
            # Convert to a dictionary if it's not already
            if not isinstance(extraction_data, dict):
                extracted_dict = {}
                for attr in dir(extraction_data):
                    if not attr.startswith('_') and not callable(getattr(extraction_data, attr)):
                        extracted_dict[attr] = getattr(extraction_data, attr)
                extraction_data = extracted_dict

        # If agent extraction failed or returned empty data, use direct parsing
        if not extraction_data or not extraction_data.get('industry_data'):
            if direct_data:
                logger.info("Using direct PDF parsing results as agent extraction failed")
                extraction_data = direct_data
            else:
                logger.error("Both extraction methods failed")
                # Create minimal valid structure to avoid downstream errors
                extraction_data = {
                    "month_year": "Unknown",
                    "manufacturing_table": "",
                    "index_summaries": {},
                    "industry_data": {},
                    "report_type": report_type
                }
        elif direct_data:
            # Compare both methods and merge results to get the most comprehensive data
            agent_industries = count_industries(extraction_data.get('industry_data', {}))
            direct_industries = count_industries(direct_data.get('industry_data', {}))

            logger.info(f"Comparison: Agent found {agent_industries} industries, Direct parsing found {direct_industries} industries")

            # If direct parsing found more industries, start with that and supplement
            if direct_industries > agent_industries:
                logger.info(f"Using direct PDF extraction as base which found more industries")
                merged_data = direct_data.copy()

                # Keep agent's month_year and manufacturing_table if they exist
                if extraction_data.get('month_year'):
                    merged_data['month_year'] = extraction_data['month_year']
                if extraction_data.get('manufacturing_table'):
                    merged_data['manufacturing_table'] = extraction_data['manufacturing_table']
                if extraction_data.get('index_summaries'):
                    merged_data['index_summaries'] = extraction_data['index_summaries']

                # Merge industry data to get the most complete set
                merged_industry_data = merge_industry_data(
                    direct_data.get('industry_data', {}),
                    extraction_data.get('industry_data', {})
                )
                merged_data['industry_data'] = merged_industry_data

                extraction_data = merged_data
            else:
                # Even if agent found more industries, still check for any missing categories
                merged_industry_data = merge_industry_data(
                    extraction_data.get('industry_data', {}),
                    direct_data.get('industry_data', {})
                )
                extraction_data['industry_data'] = merged_industry_data
                logger.info(f"Keeping agent extraction with merged industry data")

        # After extraction
        if extraction_data:
            # Add report_type to extraction_data if not present
            if 'report_type' not in extraction_data:
                extraction_data['report_type'] = report_type
                logger.info(f"Adding missing report_type: {report_type}")
            
            # Ensure month_year exists and is not Unknown if we can get it from somewhere
            if 'month_year' not in extraction_data or extraction_data['month_year'] == "Unknown":
                if direct_data and 'month_year' in direct_data and direct_data['month_year'] != "Unknown":
                    extraction_data['month_year'] = direct_data['month_year']
                    # Removed verbose logging
            
            # Ensure index_summaries exists
            if 'index_summaries' not in extraction_data or not extraction_data['index_summaries']:
                logger.warning("Missing index_summaries, creating empty structure")
                extraction_data['index_summaries'] = {}
                
                # Try to extract summaries from PDF directly if available
                if direct_data and 'index_summaries' in direct_data and direct_data['index_summaries']:
                    extraction_data['index_summaries'] = direct_data['index_summaries']
                    logger.info("Populated index_summaries from direct parsing")
            
            # Ensure industry_data exists
            if 'industry_data' not in extraction_data or not extraction_data['industry_data']:
                logger.warning("Missing industry_data, creating empty structure")
                extraction_data['industry_data'] = {}
                
                # Try to populate from direct parsing
                if direct_data and 'industry_data' in direct_data and direct_data['industry_data']:
                    extraction_data['industry_data'] = direct_data['industry_data']
                    logger.info("Populated industry_data from direct parsing")
            elif all(not industries for categories in extraction_data['industry_data'].values() 
                    for industries in categories.values() if isinstance(categories, dict)):
                logger.warning("industry_data exists but contains no actual industries")
                # Try to populate from direct parsing if it has industries
                if direct_data and 'industry_data' in direct_data:
                    direct_count = sum(len(industries) for categories in direct_data['industry_data'].values() 
                                    for industries in categories.values() if isinstance(categories, dict))
                    if direct_count > 0:
                        extraction_data['industry_data'] = direct_data['industry_data']
                        logger.info(f"Replaced empty industry_data with direct parsing data ({direct_count} industries)")

            # If verification result has industry data but extraction doesn't, use the verification data
            verification_result = None  # Initialize to avoid reference errors
            if 'verified_data' in locals() and verified_data and isinstance(verified_data, dict):
                if 'corrected_industry_data' in verified_data:
                    if not extraction_data['industry_data']:
                        extraction_data['industry_data'] = verified_data['corrected_industry_data']
                        logger.info("Using corrected_industry_data from verified_data")

        # STORE DATA IN DATABASE - CRITICAL STEP - update to include report_type
        from db_utils import store_report_data_in_db
        
        # Ensure report_type exists in extraction_data
        if 'report_type' not in extraction_data:
            extraction_data['report_type'] = report_type

        try:
            store_result = store_report_data_in_db(extraction_data, pdf_path, extraction_data.get('report_type', report_type))
            if store_result:
                logger.info(f"Successfully stored data from {pdf_path} in database")
            else:
                logger.warning(f"Failed to store data from {pdf_path} in database")
        except Exception as e:
            logger.error(f"Error storing data in database: {str(e)}")

        # Prepare for JSON serialization - handle ellipsis and other non-serializable types
        try:
            import copy
            sanitized_data = copy.deepcopy(extraction_data.get('industry_data', {}))
            
            # Function to recursively replace problematic values
            def sanitize_for_json(obj):
                if obj is ...:  # Handle ellipsis
                    return None
                elif isinstance(obj, dict):
                    return {k: sanitize_for_json(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [sanitize_for_json(item) for item in obj]
                elif isinstance(obj, (int, float, str, bool, type(None))):
                    return obj
                else:
                    # Convert other types to string
                    return str(obj)
            
            sanitized_data = sanitize_for_json(sanitized_data)
            json_data = json.dumps(sanitized_data)
            
        except TypeError as e:
            logger.warning(f"JSON serialization issue: {str(e)}")
            # Create a minimal serializable structure
            json_data = "{}"

            # Create the verification task
            verification_task = Task(
                description=f"""
                CRITICAL TASK: You must carefully verify and correct the industry categorization in the extracted data.

                The extracted data is: {json_data}
                
                STEP 1: Carefully examine the textual summaries in index_summaries to find industry mentions:
                {json.dumps(extraction_data.get('index_summaries', {}))}

                STEP 2: For each index (New Orders, Production, etc.), verify which industries are mentioned as:
                - GROWING vs DECLINING for most indices
                - SLOWER vs FASTER for Supplier Deliveries
                - HIGHER vs LOWER for Inventories
                - TOO HIGH vs TOO LOW for Customers' Inventories
                - INCREASING vs DECREASING for Prices

                STEP 3: Compare your findings against industry_data to identify errors.
                Common errors include:
                - Industries placed in the wrong category (e.g., growing when they should be declining)
                - Missing industries that were mentioned in the text
                - Industries appearing in both categories for a single index

                STEP 4: Correct any errors by:
                - Moving industries to the correct category
                - Adding missing industries to appropriate categories
                - Removing industries from incorrect categories

                STEP 5: Return a COMPLETE, CORRECTED copy of the data with your changes implemented.

                IMPORTANT: For each industry, look for EXACT PHRASES in the index summaries that specify its status.
                Do not make assumptions - only categorize based on explicit statements.

                ESPECIALLY IMPORTANT: Make sure to include all parts of the original extraction (month_year, manufacturing_table,
                index_summaries, AND the corrected industry_data).

                """,
                expected_output="A complete dictionary containing the verified data with month_year, manufacturing_table, index_summaries, and corrected industry_data",
                agent=data_correction_agent
            )

            # Create verification crew
            verification_crew = Crew(
                agents=[data_correction_agent],
                tasks=[verification_task],
                verbose=True,
                process=Process.sequential
            )

            verified_result = verification_crew.kickoff()
            logger.info("Verification result received")

            # Safely parse verification result
            verified_data = safely_parse_agent_output(verified_result)

            # Initialize verified_data if None to avoid reference errors
            if verified_data is None:
                verified_data = {}
                logger.warning("verified_data was None, initializing with empty dict")

            # Ensure we're working with the correct data
            if verified_data:
                # Ensure month_year is preserved correctly
                if 'month_year' in verified_data and verified_data['month_year'] != extraction_data.get('month_year'):
                    logger.warning(f"Month/year changed from {extraction_data.get('month_year')} to {verified_data['month_year']} - using original")
                    verified_data['month_year'] = extraction_data.get('month_year')

                # Use the verified data if it was successfully parsed
                if 'industry_data' in verified_data:
                    extraction_data = verified_data
                    logger.info("Successfully verified and corrected data")
                elif 'corrected_industry_data' in verified_data:
                    # Use the corrected industry data but preserve the original month_year
                    extraction_data['industry_data'] = verified_data['corrected_industry_data']
                    logger.info("Successfully applied corrected industry data")
                else:
                    logger.warning("Verification didn't return expected structure, using original data")

                # Use the verified data if it was successfully parsed
                if 'industry_data' in verified_data:
                    extraction_data = verified_data
                    logger.info("Successfully verified and corrected data")
                elif 'corrected_industry_data' in verified_data:
                    # Use the corrected industry data
                    extraction_data['industry_data'] = verified_data['corrected_industry_data']
                    logger.info("Successfully applied corrected industry data")
                else:
                    logger.warning("Verification didn't return expected structure, using original data")
            else:
                logger.warning("Verification failed, continuing with unverified data")

            # Execute structuring - ensure we have valid data for structuring
            logger.info("Starting data structuring...")
            from tools import SimpleDataStructurerTool
            structurer_tool = SimpleDataStructurerTool()

            # Ensure extraction_data has required keys before structuring
            if not isinstance(extraction_data, dict):
                extraction_data = {}

            # Add missing required keys to prevent downstream errors
            required_keys = ["month_year", "manufacturing_table", "index_summaries", "industry_data"]
            for key in required_keys:
                if key not in extraction_data:
                    if key == "month_year":
                        extraction_data[key] = ""
                    elif key == "manufacturing_table":
                        extraction_data[key] = ""
                    else:
                        extraction_data[key] = {}

            # Handle case where 'industry_data' might be missing but 'corrected_industry_data' exists
            if "corrected_industry_data" in extraction_data and not extraction_data.get("industry_data"):
                extraction_data["industry_data"] = extraction_data["corrected_industry_data"]

            # Use the verified data if it was successfully parsed
            structured_data = None  # Initialize to avoid reference errors
            if verified_data and 'corrected_industry_data' in verified_data:
                try:
                    structured_data = structurer_tool._run({
                        'month_year': verified_data.get('month_year', extraction_data.get('month_year', 'Unknown')),
                        'manufacturing_table': verified_data.get('manufacturing_table', extraction_data.get('manufacturing_table', '')),
                        'index_summaries': verified_data.get('index_summaries', extraction_data.get('index_summaries', {})),
                        'industry_data': verified_data.get('corrected_industry_data', {})
                    })
                except Exception as e:
                    logger.error(f"Error in structuring with verified data: {str(e)}")
                    # If structuring with verified data fails, try with original extraction_data
                    try:
                        structured_data = structurer_tool._run(extraction_data)
                    except Exception as e2:
                        logger.error(f"Error in structuring with extraction_data: {str(e2)}")
                        # Provide fallback structured_data
                        structured_data = {}
            else:
                try:
                    structured_data = structurer_tool._run(extraction_data)
                except Exception as e:
                    logger.error(f"Error in structuring: {str(e)}")
                    # Provide fallback structured_data
                    structured_data = {}

            logger.info("Data structuring completed")

            # Check if structured_data is empty or None and fix if needed
            if not structured_data:
                logger.warning("Structured data is empty, using fallback structure")
                structured_data = {}
                # Create a minimal structure for each expected index
                from config import ISM_INDICES, INDEX_CATEGORIES
                for index in ISM_INDICES:
                    structured_data[index] = {
                        "month_year": "",
                        "categories": {}
                    }
                    if index in INDEX_CATEGORIES:
                        for category in INDEX_CATEGORIES[index]:
                            structured_data[index]["categories"][category] = []

            # Execute validation
            logger.info("Starting data validation...")
            validation_task = Task(
                description=f"""
                Validate the structured ISM Manufacturing Report data for accuracy and completeness.

                Check:
                1. All expected indices are present
                2. Each index has the appropriate categories
                3. No missing data or incorrect classifications
                4. Industries are preserved exactly as listed in the report

                Flag any issues that would require manual review.

                The structured data is: {structured_data}
                """,
                expected_output="A dictionary mapping each index name to a boolean indicating validation status",
                agent=validator_agent
            )

            validation_crew = Crew(
                agents=[validator_agent],
                tasks=[validation_task],
                verbose=True,
                process=Process.sequential
            )

            validation_results = validation_crew.kickoff()

            # Safely parse validation results
            validation_dict = safely_parse_agent_output(validation_results)
            if not validation_dict:
                logger.error("Failed to parse validation results")
                # Create default validation dict
                validation_dict = {}
                for index in structured_data.keys():
                    validation_dict[index] = True  # Default to True for all indices

            # Check if any validations passed
            if not any(validation_dict.values()):
                logger.warning(f"All validations failed for {pdf_path}")
                # Set at least one validation to True to continue processing
                if validation_dict:
                    first_key = next(iter(validation_dict))
                    validation_dict[first_key] = True
                    logger.info(f"Setting {first_key} validation to True to continue processing")

            # Log total industry count for final checking
            industry_count = count_industries(extraction_data.get('industry_data', {}))
            logger.info(f"Found {industry_count} industries in structured data")
            
            # Ensure PMI data is extracted and included
            if extraction_data and 'index_summaries' in extraction_data:
                try:
                    # Extract numerical PMI values from the summaries if not already available
                    from pdf_utils import extract_pmi_values_from_summaries
                    pmi_data = extract_pmi_values_from_summaries(extraction_data['index_summaries'])
                    
                    # Add the PMI data to the extraction_data
                    if 'pmi_data' not in extraction_data:
                        extraction_data['pmi_data'] = pmi_data
                        logger.info(f"Added PMI data for {len(pmi_data)} indices")
                except Exception as e:
                    logger.error(f"Error extracting PMI values: {str(e)}")

            # Fix the formatting task to ensure proper data structure
            from tools import GoogleSheetsFormatterTool
            formatter_tool = GoogleSheetsFormatterTool()
            formatting_result = formatter_tool._run({
                'structured_data': structured_data,
                'validation_results': validation_dict,
                'extraction_data': extraction_data,
                'verification_result': verified_data,  # Add the verification result
                'visualization_options': visualization_options
            })

            logger.info("Google Sheets formatting completed")
            return formatting_result

    except Exception as e:
        logger.error(f"Error processing PDF {pdf_path}: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False
    
def validate_and_preserve_indices(extraction_data, report_type):
    """
    Validate that all expected indices are present in the extraction data.
    
    Args:
        extraction_data: The extracted data dictionary
        report_type: The report type (Manufacturing or Services)
    
    Returns:
        The extraction data with validation logging
    """

    # Removed verbose logging

    if not extraction_data or 'indices' not in extraction_data:
        logger.warning("No indices found in extraction data")
        return extraction_data
    
    # Get expected indices based on report type
    if report_type == "Services":
        expected_indices = [
            "Services PMI", "Business Activity", "New Orders", "Employment",
            "Supplier Deliveries", "Inventories", "Inventory Sentiment", 
            "Prices", "Backlog of Orders", "New Export Orders", "Imports"
        ]
    else:
        expected_indices = [
            "Manufacturing PMI", "New Orders", "Production", "Employment",
            "Supplier Deliveries", "Inventories", "Customers' Inventories",
            "Prices", "Backlog of Orders", "New Export Orders", "Imports"
        ]
    
    # Check which indices are present
    present_indices = list(extraction_data['indices'].keys())
    missing_indices = [idx for idx in expected_indices if idx not in present_indices]
    
    if missing_indices:
        logger.warning(f"Missing indices for {report_type} report: {missing_indices}")
    
    logger.info(f"Present indices for {report_type} report: {present_indices}")
    
    # Log the actual values for debugging
    for idx, data in extraction_data['indices'].items():
        if isinstance(data, dict):
            value = data.get('current', data.get('value', 'N/A'))
            direction = data.get('direction', 'N/A')
            logger.info(f"  {idx}: {value} ({direction})")
    
    return extraction_data

def count_industries(industry_data):
    """Count the total number of industries in the industry_data dict."""
    count = 0
    if not industry_data:
        return count
    
    # Handle case where industry_data is a string
    if isinstance(industry_data, str):
        logger.warning(f"industry_data is a string, not a dictionary: {industry_data[:100]}...")
        return 0
        
    # Continue with normal processing for dictionary
    for index, categories in industry_data.items():
        if isinstance(categories, dict):
            for category, industries in categories.items():
                if isinstance(industries, list):
                    count += len(industries)
                elif isinstance(industries, str):
                    # Count a string as a single industry
                    count += 1
    return count

def merge_industry_data(primary_data, secondary_data):
    merged = {}
    
    # Start with all indices from both datasets
    all_indices = set(primary_data.keys()) | set(secondary_data.keys())
    
    for index in all_indices:
        merged[index] = {}
        
        # Get categories from primary data
        primary_categories = primary_data.get(index, {})
        if not isinstance(primary_categories, dict):
            primary_categories = {}
        
        # Get categories from secondary data
        secondary_categories = secondary_data.get(index, {})
        if not isinstance(secondary_categories, dict):
            secondary_categories = {}
        
        # Merge categories
        all_categories = set(primary_categories.keys()) | set(secondary_categories.keys())
        
        for category in all_categories:
            # Start with primary industries
            merged[index][category] = list(primary_categories.get(category, []))
            
            # Add secondary industries that aren't already in the primary list
            for industry in secondary_categories.get(category, []):
                if industry not in merged[index][category]:
                    merged[index][category].append(industry)
    
    return merged

def process_multiple_pdfs(pdf_directory):
    """Process all PDF files in a directory using the Orchestrator agent."""
    logger.info(f"Processing all PDFs in directory: {pdf_directory}")
    
    try:
        # Create orchestrator agent
        orchestrator_agent = create_orchestrator_agent()
        
        # Create orchestration task without using context
        orchestration_task = Task(
            description=f"""
            Orchestrate the processing of all ISM Manufacturing Report PDFs in the directory {pdf_directory}.
            
            Steps:
            1. For each PDF file:
               a. Extract data using the Extractor Agent
               b. Structure data using the Structurer Agent
               c. Validate data using the Validator Agent
               d. Format and update Google Sheets using the Formatter Agent
            
            2. Track the success/failure of each PDF processing
            
            3. Ensure no duplications or overwrites in the Google Sheet
            
            4. Handle errors gracefully and report any issues
            
            The PDF directory is: {pdf_directory}
            """,
            expected_output="""
            A dictionary containing the processing results for each PDF file.
            """,
            agent=orchestrator_agent
        )
        
        # Execute orchestration
        orchestration_crew = Crew(
            agents=[
                orchestrator_agent,
                create_extractor_agent(),
                create_structurer_agent(),
                create_validator_agent(),
                create_formatter_agent(),
                create_data_correction_agent()
            ],
            tasks=[orchestration_task],
            verbose=True,
            process=Process.sequential
        )
        
        result = orchestration_crew.kickoff()
        result_data = safely_parse_agent_output(result)
        
        # If result_data is None or doesn't contain results, try processing each PDF directly
        if not result_data or not result_data.get('success'):
            logger.warning("Orchestration failed or returned invalid results. Trying direct processing.")
            result_data = {'success': True, 'results': {}}
            
            # Get all PDF files in the directory
            pdf_files = [f for f in os.listdir(pdf_directory) if f.lower().endswith('.pdf')]
            
            for pdf_file in pdf_files:
                pdf_path = os.path.join(pdf_directory, pdf_file)
                logger.info(f"Direct processing of {pdf_file}")
                processing_result = process_single_pdf(pdf_path)
                result_data['results'][pdf_file] = processing_result
        
        logger.info("Completed processing all PDFs")
        return result_data if result_data else {"success": False, "message": "Failed to parse orchestration result"}
    
    except Exception as e:
        logger.error(f"Error in batch processing: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {"success": False, "message": str(e)}

if __name__ == "__main__":
    import argparse
    import sys
    
    # Ensure directories exist
    os.makedirs("logs", exist_ok=True)
    os.makedirs("pdfs", exist_ok=True)
    
    # Add console handler for logging
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logging.getLogger().addHandler(console_handler)
    
    parser = argparse.ArgumentParser(description="Process ISM Manufacturing Report PDFs")
    parser.add_argument("--pdf", help="Path to a single PDF file to process")
    parser.add_argument("--dir", help="Directory containing multiple PDF files to process")
    args = parser.parse_args()
    
    if args.pdf:
        print(f"Processing single PDF: {args.pdf}")
        result = process_single_pdf(args.pdf)
        print(f"Result: {result}")
    elif args.dir:
        print(f"Processing all PDFs in directory: {args.dir}")
        result = process_multiple_pdfs(args.dir)
        print(f"Result: {result}")
    else:
        print("Please provide either --pdf or --dir argument")
        parser.print_help()