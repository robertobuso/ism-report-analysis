import json
import sqlite3
import logging
import os
from datetime import datetime
import openai
from . import config
from . import search_utils

# Configure OpenAI
openai.api_key = config.OPENAI_API_KEY

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebEnhancedInsightGenerator:
    """Class to generate enhanced insights from ISM data with web evidence."""
    
    def __init__(self, db_path=None):
        """Initialize the insight generator with database connection."""
        if db_path is None:
            db_path = config.ISM_DB_PATH
            
        self.db_path = db_path
        self.conn = self._get_db_connection()
        
        # Create insights table if it doesn't exist
        self._create_insights_table()
    
    def _get_db_connection(self):
        """Create a connection to the SQLite database."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        return conn
    
    def _create_insights_table(self):
        """Create the insights table if it doesn't exist."""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS web_insights (
                insight_id TEXT PRIMARY KEY,
                report_date DATE NOT NULL,
                index_name TEXT NOT NULL,
                trend_description TEXT NOT NULL,
                search_queries TEXT NOT NULL,
                evidence TEXT NOT NULL,
                analysis TEXT NOT NULL,
                investment_implications TEXT NOT NULL,
                created_at DATETIME NOT NULL
            )
            ''')
            
            # Create index
            cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_web_insights_date 
            ON web_insights(report_date)
            ''')
            
            self.conn.commit()
            logger.info("Web insights table initialized")
        except Exception as e:
            logger.error(f"Error creating insights table: {str(e)}")
    
    def identify_significant_trends(self, months_to_analyze=2):
        """Identify significant trends in the ISM data."""
        try:
            cursor = self.conn.cursor()
            
            # Get most recent report dates
            cursor.execute('''
            SELECT report_date, month_year 
            FROM reports 
            ORDER BY report_date DESC 
            LIMIT ?
            ''', (months_to_analyze,))
            
            report_dates = [dict(row) for row in cursor.fetchall()]
            
            if len(report_dates) < 2:
                logger.warning("Need at least 2 months of data to identify trends")
                return []
            
            # Get PMI data for these dates
            current_month = report_dates[0]
            previous_month = report_dates[1]
            
            # Get indices for the current month
            cursor.execute('''
            SELECT index_name, index_value, direction
            FROM pmi_indices
            WHERE report_date = ?
            ''', (current_month['report_date'],))
            
            current_indices = {row['index_name']: {
                'value': row['index_value'],
                'direction': row['direction']
            } for row in cursor.fetchall()}
            
            # Get indices for the previous month
            cursor.execute('''
            SELECT index_name, index_value, direction
            FROM pmi_indices
            WHERE report_date = ?
            ''', (previous_month['report_date'],))
            
            previous_indices = {row['index_name']: {
                'value': row['index_value'],
                'direction': row['direction']
            } for row in cursor.fetchall()}
            
            # Compare indices to find significant changes
            trends = []
            
            for index_name, current_data in current_indices.items():
                if index_name in previous_indices:
                    previous_data = previous_indices[index_name]
                    
                    # Get current and previous values
                    current_value = float(current_data['value'])
                    previous_value = float(previous_data['value'])
                    
                    # Calculate the change
                    change = current_value - previous_value
                    
                    # If the change is significant
                    if abs(change) >= config.SIGNIFICANT_CHANGE_THRESHOLD:
                        trend = {
                            "index_name": index_name,
                            "current_value": current_value,
                            "previous_value": previous_value,
                            "change": change,
                            "direction": current_data['direction'],
                            "month_year": current_month['month_year'],
                            "report_date": current_month['report_date']
                        }
                        
                        # Add a description
                        if change > 0:
                            trend["description"] = f"{index_name} rose {abs(change):.1f} points to {current_value:.1f} in {current_month['month_year']}"
                        else:
                            trend["description"] = f"{index_name} fell {abs(change):.1f} points to {current_value:.1f} in {current_month['month_year']}"
                        
                        trends.append(trend)
            
            # Sort trends by absolute change (most significant first)
            return sorted(trends, key=lambda x: abs(x['change']), reverse=True)
        
        except Exception as e:
            logger.error(f"Error identifying trends: {str(e)}")
            return []
    
    def generate_search_queries(self, trend):
        """Generate search queries based on a trend."""
        index_name = trend['index_name']
        direction = "increase" if trend['change'] > 0 else "decrease"
        month_year = trend['month_year']
        
        # Get the current month and year
        current_month = datetime.now().strftime("%B")
        current_year = datetime.now().year
        
        # Generate different query variations
        queries = [
            f"manufacturing {index_name.lower()} {direction} impact {current_month} {current_year}",
            f"economic impact of {direction} in manufacturing {index_name.lower()} today",
            f"{index_name} {direction} manufacturing sector implications {current_month}",
            f"why {index_name.lower()} {direction}d in manufacturing this month"
        ]
        
        # If it's a specific index, add more targeted queries
        if index_name == "New Orders":
            queries.append(f"manufacturing demand {direction} {current_month} impact")
            queries.append(f"factory orders {direction} economic implications this week")
        elif index_name == "Production":
            queries.append(f"manufacturing output {direction} {current_month} implications")
            queries.append(f"factory production {direction} impact today")
        elif index_name == "Employment":
            queries.append(f"manufacturing jobs {direction} {current_month} analysis")
            queries.append(f"manufacturing employment {direction} impact this week")
        elif index_name == "Prices":
            queries.append(f"manufacturing inflation {direction} {current_month} impact")
            queries.append(f"factory input costs {direction} implications today")
        elif index_name == "Manufacturing PMI":
            queries.append(f"manufacturing PMI {direction} economic outlook {current_month}")
            queries.append(f"PMI {direction} impact on economy this week")
            
        return queries
    
    def analyze_with_llm(self, trend, evidence, model=None):
        """Analyze trend and evidence using OpenAI's LLM."""
        if model is None:
            model = config.OPENAI_MODEL
            
        # Format evidence for the prompt
        evidence_text = ""
        for i, item in enumerate(evidence, 1):
            evidence_text += f"SOURCE {i}: {item['source']} - {item['title']}\n"
            evidence_text += f"EXCERPT: {item['content'][:500]}...\n\n"
        
        prompt = f"""
        I am analyzing a trend from the ISM Manufacturing Report, and I need to provide context and investment implications.

        THE TREND:
        {trend['description']}
        Current value: {trend['current_value']} ({trend['direction']})
        Previous value: {trend['previous_value']}
        Change: {trend['change']} points

        EVIDENCE FROM NEWS AND ANALYSIS:
        {evidence_text}

        Please provide:
        1. A brief explanation of why this trend is occurring (based on the evidence)
        2. The broader economic implications of this trend
        3. 2-3 specific companies or sectors that might be affected (positively or negatively)
        4. Any predictions for the next 3-6 months based on this trend

        Format your response clearly with numbered sections. For the investment implications, indicate if they are bullish or bearish.
        
        Keep your analysis concise but insightful.
        """
        
        client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert economic analyst and investment strategist."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        
        return response.choices[0].message.content
    
    def extract_investment_implications(self, analysis):
        """Extract investment implications from the analysis."""
        client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
        
        prompt = f"""
        Based on the following analysis, extract just the investment implications in a structured format.
        
        {analysis}
        
        Format your response as a JSON object with the following structure:
        {{
            "sectors": [
                {{
                    "name": "Sector name",
                    "impact": "bullish/bearish",
                    "reasoning": "Brief explanation"
                }}
            ],
            "companies": [
                {{
                    "name": "Company name",
                    "ticker": "Stock ticker if mentioned",
                    "impact": "bullish/bearish",
                    "reasoning": "Brief explanation"
                }}
            ],
            "timing": "Timing considerations if mentioned"
        }}
        
        Return only the JSON without any other text.
        """
        
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You extract investment implications from analysis into structured data."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        
        try:
            # Extract JSON string from response
            json_str = response.choices[0].message.content
            
            # If it's wrapped in ```json blocks, extract just the JSON part
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()
                
            return json.loads(json_str)
        except Exception as e:
            logger.error(f"Error parsing investment implications: {str(e)}")
            return {"sectors": [], "companies": [], "timing": ""}
    
    def generate_insight(self, trend_index=0):
        """Generate a complete insight for a significant trend."""
        # Get significant trends
        trends = self.identify_significant_trends()
        
        if not trends:
            return {"error": "No significant trends identified"}
        
        # Select the trend to analyze (default to most significant)
        if trend_index >= len(trends):
            trend_index = 0
            
        trend = trends[trend_index]
        
        # Generate search queries
        queries = self.generate_search_queries(trend)
        
        # Search the web for each query
        all_results = []
        for query in queries[:2]:  # Limit to 2 queries for the demo
            results = search_utils.search_web(query, num_results=3)
            all_results.extend(results)
        
        # Remove duplicate URLs
        unique_urls = set()
        unique_results = []
        for result in all_results:
            if result['url'] not in unique_urls:
                unique_urls.add(result['url'])
                unique_results.append(result)
        
        # Fetch content from top results
        evidence = []
        for result in unique_results[:config.MAX_SEARCH_RESULTS]:
            content = search_utils.fetch_article_content(result['url'])
            evidence.append({
                "source": result['source'],
                "title": result['title'],
                "url": result['url'],
                "content": content
            })
        
        # Analyze with LLM
        analysis = self.analyze_with_llm(trend, evidence)
        
        # Extract investment implications
        investment_implications = self.extract_investment_implications(analysis)
        
        # Structure the complete insight
        insight = {
            "insight_id": f"INS-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "report_date": trend['report_date'],
            "index_name": trend['index_name'],
            "trend_description": trend['description'],
            "current_value": trend['current_value'],
            "previous_value": trend['previous_value'],
            "change": trend['change'],
            "direction": trend['direction'],
            "month_year": trend['month_year'],
            "search_queries": queries,
            "evidence": evidence,
            "analysis": analysis,
            "investment_implications": investment_implications
        }
        
        # Store in database
        self.store_insight(insight)
        
        return insight
    
    def store_insight(self, insight):
        """Store an insight in the database."""
        try:
            cursor = self.conn.cursor()
            
            # Insert the insight
            cursor.execute('''
            INSERT INTO web_insights (
                insight_id, report_date, index_name, trend_description, 
                search_queries, evidence, analysis, investment_implications, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                insight['insight_id'],
                insight['report_date'],
                insight['index_name'],
                insight['trend_description'],
                json.dumps(insight['search_queries']),
                json.dumps(insight['evidence']),
                insight['analysis'],
                json.dumps(insight['investment_implications']),
                datetime.now().isoformat()
            ))
            
            self.conn.commit()
            logger.info(f"Insight stored: {insight['insight_id']}")
            return True
        except Exception as e:
            logger.error(f"Error storing insight: {str(e)}")
            return False
    
    def get_insight(self, insight_id):
        """Get a specific insight by ID."""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute('''
            SELECT * FROM web_insights WHERE insight_id = ?
            ''', (insight_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
                
            insight = dict(row)
            
            # Parse JSON fields
            insight['search_queries'] = json.loads(insight['search_queries'])
            insight['evidence'] = json.loads(insight['evidence'])
            insight['investment_implications'] = json.loads(insight['investment_implications'])
            
            return insight
        except Exception as e:
            logger.error(f"Error retrieving insight: {str(e)}")
            return None
    
    def get_all_insights(self, limit=10):
        """Get all insights from the database."""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute('''
            SELECT * FROM web_insights ORDER BY created_at DESC LIMIT ?
            ''', (limit,))
            
            insights = []
            for row in cursor.fetchall():
                insight = dict(row)
                
                # Parse JSON fields
                insight['search_queries'] = json.loads(insight['search_queries'])
                insight['evidence'] = json.loads(insight['evidence'])
                insight['investment_implications'] = json.loads(insight['investment_implications'])
                
                insights.append(insight)
                
            return insights
        except Exception as e:
            logger.error(f"Error retrieving insights: {str(e)}")
            return []
    
    def delete_insight(self, insight_id):
        """Delete an insight by ID."""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute('''
            DELETE FROM web_insights WHERE insight_id = ?
            ''', (insight_id,))
            
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting insight: {str(e)}")
            return False