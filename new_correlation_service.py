# correlation_service.py
import logging
import numpy as np
import sqlite3
from typing import Dict, List, Tuple, Optional, Union
import pandas as pd
from db_utils import get_db_connection
import traceback

logger = logging.getLogger(__name__)

class CorrelationAnalysisService:
    """Service for analyzing correlations between ISM indices."""
    
    def __init__(self):
        """Initialize the correlation analysis service."""
        self.cache = {}  # Simple in-memory cache
    
    def get_correlation_between_indices(self, index1: str, index2: str, 
                                        months: int = 36, 
                                        report_type1: Optional[str] = None,
                                        report_type2: Optional[str] = None) -> Dict:
        """
        Calculate correlation between two indices.
        
        Args:
            index1: Name of the first index
            index2: Name of the second index
            months: Number of months to include in analysis
            report_type1: Report type for the first index (optional)
            report_type2: Report type for the second index (optional)
            
        Returns:
            Dictionary with correlation results
        """
        # Check cache first
        cache_key = f"{index1}_{report_type1}_{index2}_{report_type2}_{months}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            # Get time series data for both indices
            series1 = self._get_index_time_series(index1, months, report_type1)
            series2 = self._get_index_time_series(index2, months, report_type2)
            
            if not series1 or not series2:
                return {
                    'correlation': None,
                    'p_value': None,
                    'error': 'Insufficient data'
                }
            
            # Align the time series by date
            aligned_series = self._align_time_series(series1, series2)
            
            if not aligned_series or len(aligned_series) < 3:
                return {
                    'correlation': None,
                    'p_value': None,
                    'error': 'Insufficient overlapping data points'
                }
            
            # Calculate Pearson correlation
            correlation, p_value = self._calculate_correlation(
                aligned_series['values1'],
                aligned_series['values2']
            )
            
            # Calculate lagged correlations for potential leading indicators
            lagged_correlations = self._calculate_lagged_correlations(
                aligned_series['values1'],
                aligned_series['values2'],
                max_lag=3
            )
            
            result = {
                'correlation': correlation,
                'p_value': p_value,
                'dates': aligned_series['dates'],
                'values1': aligned_series['values1'],
                'values2': aligned_series['values2'],
                'lagged_correlations': lagged_correlations,
                'index1': index1,
                'index2': index2,
                'report_type1': report_type1,
                'report_type2': report_type2,
                'n': len(aligned_series['dates'])
            }
            
            # Cache the result
            self.cache[cache_key] = result
            
            return result
        except Exception as e:
            logger.error(f"Error calculating correlation: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                'correlation': None,
                'p_value': None,
                'error': str(e)
            }
    
    def get_cross_report_correlations(self, months: int = 36) -> Dict:
        """
        Calculate correlations between Manufacturing and Services indices.
        
        Args:
            months: Number of months to include in analysis
            
        Returns:
            Dictionary mapping index pairs to their correlation statistics
        """
        try:
            # Get all Manufacturing indices
            mfg_indices = self._get_indices('Manufacturing')
            
            # Get all Services indices
            svc_indices = self._get_indices('Services')
            
            results = {}
            
            # Calculate correlations between each pair
            for mfg_index in mfg_indices:
                for svc_index in svc_indices:
                    # Skip comparing unlike indices
                    if not self._are_comparable_indices(mfg_index, svc_index):
                        continue
                        
                    key = f"{mfg_index}-{svc_index}"
                    results[key] = self.get_correlation_between_indices(
                        mfg_index, svc_index, months, 
                        report_type1='Manufacturing', 
                        report_type2='Services'
                    )
            
            return results
        except Exception as e:
            logger.error(f"Error calculating cross-report correlations: {str(e)}")
            logger.error(traceback.format_exc())
            return {}
    
    def get_all_correlations_for_index(self, index_name: str, 
                                      report_type: Optional[str] = None,
                                      months: int = 36,
                                      min_correlation: float = 0.5) -> Dict:
        """
        Find all significant correlations for a given index.
        
        Args:
            index_name: Name of the index to analyze
            report_type: Report type for the index (optional)
            months: Number of months to include in analysis
            min_correlation: Minimum absolute correlation coefficient to include
            
        Returns:
            Dictionary with correlation results
        """
        try:
            # Get all indices
            all_indices = self._get_indices()
            
            results = {}
            
            # Calculate correlations with all other indices
            for other_index in all_indices:
                # Skip self-correlation
                if other_index == index_name:
                    continue
                
                # Get correlation
                correlation = self.get_correlation_between_indices(
                    index_name, other_index, months, report_type
                )
                
                # Only include significant correlations
                if correlation.get('correlation') is not None and \
                   abs(correlation['correlation']) >= min_correlation:
                    results[other_index] = correlation
            
            # Sort by absolute correlation (highest first)
            sorted_results = dict(sorted(
                results.items(),
                key=lambda item: abs(item[1]['correlation']),
                reverse=True
            ))
            
            return sorted_results
        except Exception as e:
            logger.error(f"Error calculating correlations for {index_name}: {str(e)}")
            return {}
    
    def _get_index_time_series(self, index_name: str, 
                             months: int = 36, 
                             report_type: Optional[str] = None) -> List[Dict]:
        """
        Get time series data for an index.
        
        Args:
            index_name: Name of the index
            months: Number of months to include
            report_type: Report type (optional)
            
        Returns:
            List of dictionaries with date, value pairs
        """
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Build query based on whether report_type is provided
            query = """
                SELECT r.report_date, p.index_value
                FROM pmi_indices p
                JOIN reports r ON p.report_date = r.report_date
                WHERE p.index_name = ?
                {}
                ORDER BY r.report_date DESC
                LIMIT ?
            """
            
            params = []
            if report_type:
                query = query.format("AND r.report_type = ?")
                params = [index_name, report_type, months]
            else:
                query = query.format("")
                params = [index_name, months]
                
            cursor.execute(query, params)
            
            # Convert to list of dictionaries
            result = [
                {'date': row['report_date'], 'value': row['index_value']}
                for row in cursor.fetchall()
            ]
            
            return result
        except Exception as e:
            logger.error(f"Error getting time series for {index_name}: {str(e)}")
            return []
        finally:
            if conn:
                conn.close()
    
    def _align_time_series(self, series1: List[Dict], series2: List[Dict]) -> Dict:
        """
        Align two time series by date.
        
        Args:
            series1: First time series
            series2: Second time series
            
        Returns:
            Dictionary with aligned dates and values
        """
        try:
            # Create dictionaries mapping dates to values
            dict1 = {item['date']: item['value'] for item in series1}
            dict2 = {item['date']: item['value'] for item in series2}
            
            # Find common dates
            common_dates = sorted(set(dict1.keys()) & set(dict2.keys()))
            
            if not common_dates:
                return None
            
            # Extract aligned values
            aligned_values1 = [dict1[date] for date in common_dates]
            aligned_values2 = [dict2[date] for date in common_dates]
            
            return {
                'dates': common_dates,
                'values1': aligned_values1,
                'values2': aligned_values2
            }
        except Exception as e:
            logger.error(f"Error aligning time series: {str(e)}")
            return None
    
    def _calculate_correlation(self, values1: List[float], values2: List[float]) -> Tuple[float, float]:
        """
        Calculate Pearson correlation coefficient and p-value.
        
        Args:
            values1: First array of values
            values2: Second array of values
            
        Returns:
            Tuple of (correlation, p_value)
        """
        try:
            import scipy.stats as stats
            
            if len(values1) < 3 or len(values2) < 3:
                return None, None
                
            correlation, p_value = stats.pearsonr(values1, values2)
            
            return round(correlation, 3), round(p_value, 4)
        except Exception as e:
            logger.error(f"Error calculating correlation: {str(e)}")
            return None, None
    
     def _calculate_lagged_correlations(self, values1: List[float], values2: List[float], max_lag: int = 3) -> Dict:
        """
        Calculate correlations with lags to detect leading indicators.
        
        Args:
            values1: First array of values
            values2: Second array of values
            max_lag: Maximum lag to consider (in months)
            
        Returns:
            Dictionary mapping lags to correlation coefficients
        """
        try:
            import scipy.stats as stats
            
            results = {}
            
            # Add zero lag (standard correlation)
            results[0] = stats.pearsonr(values1, values2)[0]
            
            # Check positive lags (series1 leading series2)
            for lag in range(1, min(max_lag + 1, len(values1))):
                # Ensure we have enough data points
                if len(values1) - lag < 3:
                    break
                    
                correlation = stats.pearsonr(
                    values1[:-lag],  # Earlier values of series1
                    values2[lag:]    # Later values of series2
                )[0]
                
                results[lag] = round(correlation, 3)
            
            # Check negative lags (series2 leading series1)
            for lag in range(1, min(max_lag + 1, len(values1))):
                # Ensure we have enough data points
                if len(values2) - lag < 3:
                    break
                    
                correlation = stats.pearsonr(
                    values1[lag:],   # Later values of series1
                    values2[:-lag]   # Earlier values of series2
                )[0]
                
                results[-lag] = round(correlation, 3)
            
            return results
        except Exception as e:
            logger.error(f"Error calculating lagged correlations: {str(e)}")
            return {0: None}
    
    def _get_indices(self, report_type: Optional[str] = None) -> List[str]:
        """
        Get all indices for a report type.
        
        Args:
            report_type: Report type (optional)
            
        Returns:
            List of index names
        """
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            if report_type:
                query = """
                    SELECT DISTINCT i.index_name 
                    FROM pmi_indices i
                    JOIN reports r ON i.report_date = r.report_date
                    WHERE r.report_type = ?
                    ORDER BY i.index_name
                """
                cursor.execute(query, (report_type,))
            else:
                query = """
                    SELECT DISTINCT index_name 
                    FROM pmi_indices 
                    ORDER BY index_name
                """
                cursor.execute(query)
            
            return [row['index_name'] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting indices: {str(e)}")
            return []
        finally:
            if conn:
                conn.close()
    
    def _are_comparable_indices(self, index1: str, index2: str) -> bool:
        """
        Determine if two indices are comparable across report types.
        
        Args:
            index1: First index name
            index2: Second index name
            
        Returns:
            Boolean indicating if indices are comparable
        """
        # Map of equivalent indices between Manufacturing and Services
        equivalence_map = {
            'Manufacturing PMI': 'Services PMI',
            'Production': 'Business Activity',
            'New Orders': 'New Orders',
            'Employment': 'Employment',
            'Supplier Deliveries': 'Supplier Deliveries',
            'Inventories': 'Inventories',
            "Customers' Inventories": 'Inventory Sentiment',
            'Prices': 'Prices',
            'Backlog of Orders': 'Backlog of Orders',
            'New Export Orders': 'New Export Orders',
            'Imports': 'Imports'
        }
        
        # Check if indices are direct equivalents
        if index1 == index2:
            return True
            
        # Check the mapping in both directions
        if index1 in equivalence_map and equivalence_map[index1] == index2:
            return True
            
        if index2 in equivalence_map and equivalence_map[index2] == index1:
            return True
            
        return False
    

    # Add imports at the top of app.py
from correlation_service import CorrelationAnalysisService

# Create a singleton instance of the correlation service
correlation_service = CorrelationAnalysisService()

# Add correlation analysis endpoints
@app.route('/api/correlations/between_indices')
def get_correlation_between_indices():
    """Get correlation between two indices."""
    try:
        # Get parameters
        index1 = request.args.get('index1')
        index2 = request.args.get('index2')
        report_type1 = request.args.get('report_type1')
        report_type2 = request.args.get('report_type2')
        months = request.args.get('months', 36, type=int)
        
        if not index1 or not index2:
            return jsonify({"error": "Both index1 and index2 are required"}), 400
            
        # Get correlation
        result = correlation_service.get_c<!-- templates/correlations.html -->
<!DOCTYPE html>
<html>
<head>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <title>ISM Report Correlations</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --primary-color: midnightblue;
            --primary-hover: #10104D;
            --secondary-color: #f8f9fa;
            --accent-color: #28a745;
            --text-color: #333;
            --light-text: #6c757d;
            --bg-color: #f8fafc;
            --card-shadow: rgba(0, 0, 0, 0.05);

            /* Chart specific colors */
            --color-growing: #34A853;
            --color-contracting: #EA4335;
            --color-neutral-heatmap: #F5F5F5;
        }
        
        body {
            font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            line-height: 1.6;
            letter-spacing: -0.01em;
        }
        
        .container-fluid {
            padding: 0;
        }
        
        .content-container {
            padding: 2rem;
            max-width: 1900px;
            margin: 0 auto;
        }
        
        /* Navbar styling */
        .navbar {
            padding: 1rem 2rem;
            background-color: white !important;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
        }
        
        .navbar-brand {
            font-weight: 700;
            font-size: 1.4rem;
            color: var(--primary-color) !important;
        }
        
        .nav-link {
            font-weight: 500;
            color: var(--text-color);
            position: relative;
            padding: 0.5rem 1rem;
            margin: 0 0.25rem;
        }
        
        .nav-link:hover {
            color: var(--primary-color);
        }
        
        .nav-link.active {
            color: var(--primary-color);
        }
        
        .nav-link.active::after {
            content: '';
            position: absolute;
            bottom: 0;
            left: 1rem;
            right: 1rem;
            height: 2px;
            background-color: var(--primary-color);
        }
        
        /* Header styling */
        .dashboard-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
        }

        .dashboard-header h1 {
            font-weight: 700;
            font-size: 1.75rem;
            margin: 0;
            color: #0f172a;
            letter-spacing: -0.02em;
        }
        
        /* KPI Cards styling */
        .correlation-card {
            background: white;
            border-radius: 16px;
            box-shadow: 0 4px 20px var(--card-shadow);
            padding: 1.75rem;
            height: 100%;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }

        .correlation-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.1);
        }
    
        .correlation-title {
            color: var(--light-text);
            font-size: 0.875rem;
            font-weight: 600;
            margin-bottom: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.03em;
            display: flex;
            align-items: center;
        }
        
        .correlation-title i {
            margin-left: 0.5rem;
            font-size: 0.85rem;
            color: var(--primary-color);
        }

        .correlation-value {
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
            color: #0f172a;
            letter-spacing: -0.03em;
            font-feature-settings: "tnum";
            font-variant-numeric: tabular-nums;
        }

        .correlation-info {
            font-size: 1rem;
            font-weight: 600;
        }
        
        /* Tab navigation */
        .correlation-tabs {
            background: white;
            border-radius: 16px;
            box-shadow: 0 4px 20px var(--card-shadow);
            margin-bottom: 2rem;
            overflow: hidden;
        }
        
        .nav-tabs {
            border-bottom: 1px solid rgba(0, 0, 0, 0.05);
            padding: 0 1rem;
            background-color: white;
        }

        .nav-tabs .nav-link {
            border: none;
            border-bottom: 3px solid transparent;
            color: var(--light-text);
            font-weight: 600;
            padding: 1rem 1.5rem;
            transition: color 0.2s ease, border-color 0.2s ease;
        }

        .nav-tabs .nav-link:hover {
            border-color: #cbd5e1;
            color: #334155;
        }

        .nav-tabs .nav-link.active {
            color: var(--primary-color);
            border-color: var(--primary-color);
            background-color: transparent;
        }
        
        .tab-content {
            padding: 2rem;
        }
        
        /* Content card styling */
        .content-card {
            background: white;
            border-radius: 16px;
            box-shadow: 0 4px 20px var(--card-shadow);
            margin-bottom: 2rem;
            overflow: hidden;
        }
        
        .content-card-header {
            padding: 1.5rem 2rem;
            border-bottom: 1px solid rgba(0, 0, 0, 0.05);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .content-card-header h5 {
            margin: 0;
            font-weight: 600;
            color: var(--primary-color);
            font-size: 1.2rem;
        }
        
        .content-card-body {
            padding: 2rem;
        }
        
        /* Filter selectors */
        .filter-container {
            display: flex;
            flex-wrap: wrap;
            gap: 1rem;
            margin-bottom: 1.5rem;
        }

        .filter-container label {
            font-size: 0.875rem;
            font-weight: 600;
            color: var(--light-text);
            margin-bottom: 0.35rem;
        }
        
        .form-select {
            border-radius: 8px;
            border: 1px solid #e2e8f0;
            padding: 0.6rem 1rem;
            font-size: 0.95rem;
            background-color: white;
            min-width: 200px;
            font-weight: 500;
        }
        
        .form-select:focus {
            border-color: var(--primary-color);
            box-shadow: 0 0 0 3px rgba(0, 86, 179, 0.1);
        }
        
        /* Heatmap styling */
        .heatmap-cell {
            padding: 0.5rem;
            text-align: center;
            border: 1px solid #dee2e6;
        }
        
        .correlation-positive {
            background-color: rgba(52, 168, 83, 0.1);
        }
        
        .correlation-positive-strong {
            background-color: rgba(52, 168, 83, 0.3);
        }
        
        .correlation-positive-very-strong {
            background-color: rgba(52, 168, 83, 0.5);
        }
        
        .correlation-negative {
            background-color: rgba(234, 67, 53, 0.1);
        }
        
        .correlation-negative-strong {
            background-color: rgba(234, 67, 53, 0.3);
        }
        
        .correlation-negative-very-strong {
            background-color: rgba(234, 67, 53, 0.5);
        }
        
        /* Footer */
        .footer {
            background-color: white;
            border-top: 1px solid rgba(0, 0, 0, 0.05);
            padding: 1.5rem 0;
            text-align: center;
            color: var(--light-text);
            margin-top: 2rem;
        }
        
        /* Responsive adjustments */
        @media (max-width: 768px) {
            .content-container {
                padding: 1rem;
            }
            
            .correlation-card {
                margin-bottom: 1rem;
            }
            
            .dashboard-header {
                flex-direction: column;
                align-items: flex-start;
            }
            
            .dashboard-header h1 {
                margin-bottom: 1rem;
            }
            
            .nav-tabs .nav-link {
                padding: 0.75rem 1rem;
            }
            
            .content-card-header, .content-card-body {
                padding: 1.25rem;
            }
        }
    </style>
</head>
<body>
    <div class="container-fluid">
        <nav class="navbar navbar-expand-lg navbar-light">
            <div class="container-fluid">
                <a class="navbar-brand" href="#">Envoy LLC</a>
                <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                    <span class="navbar-toggler-icon"></span>
                </button>
                <div class="collapse navbar-collapse" id="navbarNav">
                    <ul class="navbar-nav me-auto">
                        <li class="nav-item">
                            <a class="nav-link" href="{{ url_for('dashboard') }}">Dashboard</a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="{{ url_for('upload_view') }}">Upload Reports</a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link active" href="{{ url_for('correlations') }}">Correlations</a>
                        </li>
                    </ul>
                    <div class="d-flex">
                        <a href="{{ url_for('logout') }}" class="btn btn-outline-secondary">
                            <i class="bi bi-box-arrow-right me-2"></i>Logout
                        </a>
                    </div>
                </div>
            </div>
        </nav>

        <div class="content-container">
            <!-- Dashboard Header -->
            <div class="dashboard-header">
                <h1>ISM Report Correlation Analysis</h1>
                <div class="d-flex">
                    <button id="refreshBtn" class="btn btn-primary">
                        <i class="bi bi-arrow-repeat me-2"></i>Refresh Analysis
                    </button>
                </div>
            </div>
            
            <!-- Correlation Tabs -->
            <div class="correlation-tabs">
                <!-- Navigation Tabs -->
                <ul class="nav nav-tabs" id="correlationTabs" role="tablist">
                    <li class="nav-item" role="presentation">
                        <button class="nav-link active" id="cross-report-tab" data-bs-toggle="tab" data-bs-target="#cross-report">
                            <i class="bi bi-graph-up-arrow me-2"></i>Manufacturing vs. Services
                        </button>
                    </li>
                    <li class="nav-item" role="presentation">
                        <button class="nav-link" id="index-correlations-tab" data-bs-toggle="tab" data-bs-target="#index-correlations">
                            <i class="bi bi-search me-2"></i>Index Correlations
                        </button>
                    </li>
                    <li class="nav-item" role="presentation">
                        <button class="nav-link" id="lagged-correlations-tab" data-bs-toggle="tab" data-bs-target="#lagged-correlations">
                            <i class="bi bi-clock-history me-2"></i>Lagged Correlations
                        </button>
                    </li>
                </ul>
        
                <!-- Tab Content -->
                <div class="tab-content" id="correlationTabsContent">
                    <!-- Cross-Report Tab -->
                    <div class="tab-pane fade show active" id="cross-report" role="tabpanel">
                        <div class="content-card">
                            <div class="content-card-header">
                                <h5>Manufacturing vs. Services Correlations</h5>
                                <div class="d-flex align-items-center">
                                    <select id="monthsSelect" class="form-select form-select-sm me-2" style="width: auto;">
                                        <option value="12">Last 12 Months</option>
                                        <option value="24">Last 24 Months</option>
                                        <option value="36" selected>Last 36 Months</option>
                                        <option value="48">Last 48 Months</option>
                                    </select>
                                    <button id="exportCrossCorrelationBtn" class="btn btn-sm btn-outline-secondary">
                                        <i class="bi bi-download"></i> Export
                                    </button>
                                </div>
                            </div>
                            <div class="content-card-body">
                                <div class="row mb-4">
                                    <div class="col-md-4 mb-3">
                                        <div class="correlation-card">
                                            <div class="correlation-title">
                                                Strongest Positive Correlation
                                                <i class="bi bi-info-circle-fill" data-bs-toggle="tooltip" data-bs-placement="top" title="The two indices that show the strongest positive correlation, indicating they tend to move in the same direction."></i>
                                            </div>
                                            <div class="correlation-value" id="strongestPositiveValue">--</div>
                                            <div class="correlation-info" id="strongestPositiveInfo">--</div>
                                        </div>
                                    </div>
                                    <div class="col-md-4 mb-3">
                                        <div class="correlation-card">
                                            <div class="correlation-title">
                                                Strongest Negative Correlation
                                                <i class="bi bi-info-circle-fill" data-bs-toggle="tooltip" data-bs-placement="top" title="The two indices that show the strongest negative correlation, indicating they tend to move in opposite directions."></i>
                                            </div>
                                            <div class="correlation-value" id="strongestNegativeValue">--</div>
                                            <div class="correlation-info" id="strongestNegativeInfo">--</div>
                                        </div>
                                    </div>
                                    <div class="col-md-4 mb-3">
                                        <div class="correlation-card">
                                            <div class="correlation-title">
                                                Best Leading Indicator
                                                <i class="bi bi-info-circle-fill" data-bs-toggle="tooltip" data-bs-placement="top" title="The index that best predicts future movements in another index based on lagged correlation analysis."></i>
                                            </div>
                                            <div class="correlation-value" id="leadingIndicatorValue">--</div>
                                            <div class="correlation-info" id="leadingIndicatorInfo">--</div>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="table-responsive">
                                    <table class="table table-bordered" id="crossCorrelationTable">
                                        <thead>
                                            <tr>
                                                <th>Manufacturing Index</th>
                                                <th>Services Index</th>
                                                <th>Correlation</th>
                                                <th>P-Value</th>
                                                <th>Significance</th>
                                            </tr>
                                        </thead>
                                        <tbody id="crossCorrelationBody">
                                            <!-- Will be populated by JavaScript -->
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Index Correlations Tab -->
                    <div class="tab-pane fade" id="index-correlations" role="tabpanel">
                        <div class="content-card">
                            <div class="content-card-header">
                                <h5>Index Correlation Search</h5>
                                <div class="d-flex align-items-center">
                                    <button id="exportIndexCorrelationBtn" class="btn btn-sm btn-outline-secondary">
                                        <i class="bi bi-download"></i> Export
                                    </button>
                                </div>
                            </div>
                            <div class="content-card-body">
                                <div class="filter-container">
                                    <div>
                                        <label for="indexSelect">Select Index</label>
                                        <select id="indexSelect" class="form-select">
                                            <!-- Will be populated by JavaScript -->
                                        </select>
                                    </div>
                                    <div>
                                        <label for="reportTypeSelect">Report Type</label>
                                        <select id="reportTypeSelect" class="form-select">
                                            <option value="">All</option>
                                            <option value="Manufacturing">Manufacturing</option>
                                            <option value="Services">Services</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label for="minCorrelationSelect">Minimum Correlation</label>
                                        <select id="minCorrelationSelect" class="form-select">
                                            <option value="0.3">0.3</option>
                                            <option value="0.5" selected>0.5</option>
                                            <option value="0.7">0.7</option>
                                            <option value="0.9">0.9</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label for="indexMonthsSelect">Time Range</label>
                                        <select id="indexMonthsSelect" class="form-select">
                                            <option value="12">Last 12 Months</option>
                                            <option value="24">Last 24 Months</option>
                                            <option value="36" selected>Last 36 Months</option>
                                            <option value="48">Last 48 Months</option>
                                        </select>
                                    </div>
                                </div>
                                
                                <div id="indexCorrelationResults">
                                    <p class="text-center text-muted">Select an index to see correlations</p>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Lagged Correlations Tab -->
                    <div class="tab-pane fade" id="lagged-correlations" role="tabpanel">
                        <div class="content-card">
                            <div class="content-card-header">
                                <h5>Lagged Correlation Analysis</h5>
                                <div class="d-flex align-items-center">
                                    <button id="exportLaggedBtn" class="btn btn-sm btn-outline-secondary">
                                        <i class="bi bi-download"></i> Export
                                    </button>
                                </div>
                            </div>
                            <div class="content-card-body">
                                <div class="filter-container">
                                    <div>
                                        <label for="laggedIndex1">First Index</label>
                                        <select id="laggedIndex1" class="form-select">
                                            <!-- Will be populated by JavaScript -->
                                        </select>
                                    </div>
                                    <div>
                                        <label for="laggedReport1">Report Type</label>
                                        <select id="laggedReport1" class="form-select">
                                            <option value="Manufacturing">Manufacturing</option>
                                            <option value="Services">Services</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label for="laggedIndex2">Second Index</label>
                                        <select id="laggedIndex2" class="form-select">
                                            <!-- Will be populated by JavaScript -->
                                        </select>
                                    </div>
                                    <div>
                                        <label for="laggedReport2">Report Type</label>
                                        <select id="laggedReport2" class="form-select">
                                            <option value="Manufacturing">Manufacturing</option>
                                            <option value="Services">Services</option>
                                        </select>
                                    </div>
                                </div>
                                
                                <div class="row mt-4">
                                    <div class="col-md-6">
                                        <div id="laggedCorrelationChart" style="height: 400px;">
                                            <canvas id="laggedChart"></canvas>
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <div id="scatterChart" style="height: 400px;">
                                            <canvas id="indexScatterChart"></canvas>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="mt-4">
                                    <h6>Interpretation</h6>
                                    <div id="laggedInterpretation">
                                        <p class="text-muted">Select two indices to analyze their relationship</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <footer class="footer">
        <div class="container">
            <p>© 2025 Envoy LLC. All rights reserved.</p>
        </div>
    </footer>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Initialize tooltips
        document.addEventListener('DOMContentLoaded', function() {
            const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
            const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));
            
            // Initialize tabs
            loadCrossReportCorrelations();
            loadIndices();
            
            // Set up event listeners
            document.getElementById('monthsSelect').addEventListener('change', loadCrossReportCorrelations);
            document.getElementById('indexSelect').addEventListener('change', loadIndexCorrelations);
            document.getElementById('reportTypeSelect').addEventListener('change', loadIndexCorrelations);
            document.getElementById('minCorrelationSelect').addEventListener('change', loadIndexCorrelations);
            document.getElementById('indexMonthorrelation_between_indices(
            index1, index2, months, report_type1, report_type2
        )
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting correlation: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/correlations/cross_report')
def get_cross_report_correlations():
    """Get correlations between Manufacturing and Services indices."""
    try:
        # Get parameters
        months = request.args.get('months', 36, type=int)
        
        # Get cross-report correlations
        results = correlation_service.get_cross_report_correlations(months)
        
        return jsonify(results)
    except Exception as e:
        logger.error(f"Error getting cross-report correlations: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/correlations/for_index/<index_name>')
def get_correlations_for_index(index_name):
    """Get all significant correlations for an index."""
    try:
        # Get parameters
        report_type = request.args.get('report_type')
        months = request.args.get('months', 36, type=int)
        min_correlation = request.args.get('min_correlation', 0.5, type=float)
        
        # Get correlations
        results = correlation_service.get_all_correlations_for_index(
            index_name, report_type, months, min_correlation
        )
        
        return jsonify(results)
    except Exception as e:
        logger.error(f"Error getting correlations for index: {str(e)}")
        return jsonify({"error": str(e)}), 500

document.getElementById('indexMonthsSelect').addEventListener('change', loadIndexCorrelations);
            
            // Set up lagged correlation events
            document.getElementById('laggedIndex1').addEventListener('change', loadLaggedCorrelations);
            document.getElementById('laggedReport1').addEventListener('change', loadLaggedCorrelations);
            document.getElementById('laggedIndex2').addEventListener('change', loadLaggedCorrelations);
            document.getElementById('laggedReport2').addEventListener('change', loadLaggedCorrelations);
            
            // Export buttons
            document.getElementById('exportCrossCorrelationBtn').addEventListener('click', exportCrossCorrelationData);
            document.getElementById('exportIndexCorrelationBtn').addEventListener('click', exportIndexCorrelationData);
            document.getElementById('exportLaggedBtn').addEventListener('click', exportLaggedCorrelationData);
            
            // Refresh button
            document.getElementById('refreshBtn').addEventListener('click', refreshAllAnalyses);
        });
        
        // Cross-Report Correlations
        function loadCrossReportCorrelations() {
            const months = document.getElementById('monthsSelect').value;
            const tableBody = document.getElementById('crossCorrelationBody');
            
            // Show loading indicator
            tableBody.innerHTML = '<tr><td colspan="5" class="text-center">Loading correlation data...</td></tr>';
            
            // Reset KPI cards
            document.getElementById('strongestPositiveValue').textContent = '--';
            document.getElementById('strongestPositiveInfo').textContent = '--';
            document.getElementById('strongestNegativeValue').textContent = '--';
            document.getElementById('strongestNegativeInfo').textContent = '--';
            document.getElementById('leadingIndicatorValue').textContent = '--';
            document.getElementById('leadingIndicatorInfo').textContent = '--';
            
            // Fetch cross-report correlations
            fetch(`/api/correlations/cross_report?months=${months}`)
                .then(response => response.json())
                .then(data => {
                    // Update KPI cards with strongest correlations
                    updateCorrelationKPIs(data);
                    
                    // Populate table
                    tableBody.innerHTML = '';
                    
                    // Sort by absolute correlation (highest first)
                    const sortedPairs = Object.entries(data)
                        .filter(([key, value]) => value.correlation !== null) // Skip null correlations
                        .sort((a, b) => Math.abs(b[1].correlation) - Math.abs(a[1].correlation));
                    
                    sortedPairs.forEach(([key, value]) => {
                        const [mfgIndex, svcIndex] = key.split('-');
                        const correlation = value.correlation;
                        const pValue = value.p_value;
                        
                        const row = document.createElement('tr');
                        
                        // Apply color coding based on correlation strength
                        let correlationClass = '';
                        let significance = '';
                        
                        if (correlation > 0.7) {
                            correlationClass = 'correlation-positive-very-strong';
                            significance = 'Very strong positive';
                        } else if (correlation > 0.5) {
                            correlationClass = 'correlation-positive-strong';
                            significance = 'Strong positive';
                        } else if (correlation > 0.3) {
                            correlationClass = 'correlation-positive';
                            significance = 'Moderate positive';
                        } else if (correlation < -0.7) {
                            correlationClass = 'correlation-negative-very-strong';
                            significance = 'Very strong negative';
                        } else if (correlation < -0.5) {
                            correlationClass = 'correlation-negative-strong';
                            significance = 'Strong negative';
                        } else if (correlation < -0.3) {
                            correlationClass = 'correlation-negative';
                            significance = 'Moderate negative';
                        } else {
                            significance = 'Weak or no correlation';
                        }
                        
                        // Add statistical significance based on p-value
                        let pValueText = pValue;
                        if (pValue !== null) {
                            if (pValue < 0.01) {
                                pValueText = `${pValue} ***`;
                            } else if (pValue < 0.05) {
                                pValueText = `${pValue} **`;
                            } else if (pValue < 0.1) {
                                pValueText = `${pValue} *`;
                            }
                        }
                        
                        row.innerHTML = `
                            <td>${mfgIndex}</td>
                            <td>${svcIndex}</td>
                            <td class="${correlationClass}">${correlation}</td>
                            <td>${pValueText || 'N/A'}</td>
                            <td>${significance}</td>
                        `;
                        
                        tableBody.appendChild(row);
                    });
                })
                .catch(error => {
                    console.error('Error fetching cross-report correlations:', error);
                    tableBody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">Error loading correlation data</td></tr>';
                });
        }
        
        function updateCorrelationKPIs(data) {
            // Find strongest positive correlation
            let strongestPositive = null;
            let strongestPositiveIndices = '';
            
            // Find strongest negative correlation
            let strongestNegative = null;
            let strongestNegativeIndices = '';
            
            // Find best leading indicator (from lagged correlations)
            let bestLeadingIndicator = null;
            let bestLeadingIndicatorInfo = '';
            
            // Process all correlations
            Object.entries(data).forEach(([key, value]) => {
                if (value.correlation === null) return;
                
                const correlation = value.correlation;
                const [mfgIndex, svcIndex] = key.split('-');
                
                // Check for strongest positive
                if (correlation > 0 && (strongestPositive === null || correlation > strongestPositive)) {
                    strongestPositive = correlation;
                    strongestPositiveIndices = `${mfgIndex} & ${svcIndex}`;
                }
                
                // Check for strongest negative
                if (correlation < 0 && (strongestNegative === null || correlation < strongestNegative)) {
                    strongestNegative = correlation;
                    strongestNegativeIndices = `${mfgIndex} & ${svcIndex}`;
                }
                
                // Check for leading indicators (lagged correlations)
                if (value.lagged_correlations) {
                    Object.entries(value.lagged_correlations).forEach(([lag, lagCorrelation]) => {
                        if (lagCorrelation === null) return;
                        if (lag === '0') return; // Skip zero lag (already covered by regular correlation)
                        
                        const lagInt = parseInt(lag);
                        
                        // We're looking for strong correlations with non-zero lag
                        // Positive lag means mfgIndex leads svcIndex, negative means svcIndex leads mfgIndex
                        if (Math.abs(lagCorrelation) > 0.7 && (bestLeadingIndicator === null || Math.abs(lagCorrelation) > Math.abs(bestLeadingIndicator))) {
                            bestLeadingIndicator = lagCorrelation;
                            
                            if (lagInt > 0) {
                                bestLeadingIndicatorInfo = `${mfgIndex} leads ${svcIndex} by ${lagInt} month(s)`;
                            } else {
                                bestLeadingIndicatorInfo = `${svcIndex} leads ${mfgIndex} by ${Math.abs(lagInt)} month(s)`;
                            }
                        }
                    });
                }
            });
            
            // Update KPI cards
            if (strongestPositive !== null) {
                document.getElementById('strongestPositiveValue').textContent = strongestPositive.toFixed(2);
                document.getElementById('strongestPositiveInfo').textContent = strongestPositiveIndices;
            }
            
            if (strongestNegative !== null) {
                document.getElementById('strongestNegativeValue').textContent = strongestNegative.toFixed(2);
                document.getElementById('strongestNegativeInfo').textContent = strongestNegativeIndices;
            }
            
            if (bestLeadingIndicator !== null) {
                document.getElementById('leadingIndicatorValue').textContent = bestLeadingIndicator.toFixed(2);
                document.getElementById('leadingIndicatorInfo').textContent = bestLeadingIndicatorInfo;
            }
        }
        
        // Index Correlations
        function loadIndices() {
            // Fetch all available indices
            fetch('/api/all_indices')
                .then(response => response.json())
                .then(indices => {
                    // Populate index selects
                    populateIndexSelects(indices);
                })
                .catch(error => {
                    console.error('Error fetching indices:', error);
                });
        }
        
        function populateIndexSelects(indices) {
            // Sort indices alphabetically
            indices.sort();
            
            // Populate the index select for the Index Correlations tab
            const indexSelect = document.getElementById('indexSelect');
            indexSelect.innerHTML = ''; // Clear existing options
            
            indices.forEach(index => {
                const option = document.createElement('option');
                option.value = index;
                option.textContent = index;
                indexSelect.appendChild(option);
            });
            
            // Populate the lagged correlation selects
            const laggedIndex1 = document.getElementById('laggedIndex1');
            const laggedIndex2 = document.getElementById('laggedIndex2');
            
            laggedIndex1.innerHTML = ''; // Clear existing options
            laggedIndex2.innerHTML = ''; // Clear existing options
            
            indices.forEach(index => {
                // Add to first select
                const option1 = document.createElement('option');
                option1.value = index;
                option1.textContent = index;
                laggedIndex1.appendChild(option1);
                
                // Add to second select
                const option2 = document.createElement('option');
                option2.value = index;
                option2.textContent = index;
                laggedIndex2.appendChild(option2);
            });
            
            // Set default values for lagged correlations
            if (indices.includes('Manufacturing PMI')) {
                laggedIndex1.value = 'Manufacturing PMI';
            }
            
            if (indices.includes('New Orders')) {
                laggedIndex2.value = 'New Orders';
            }
            
            // Trigger initial load of lagged correlations
            loadLaggedCorrelations();
        }
        
        function loadIndexCorrelations() {
            const indexName = document.getElementById('indexSelect').value;
            if (!indexName) return;
            
            const reportType = document.getElementById('reportTypeSelect').value;
            const minCorrelation = document.getElementById('minCorrelationSelect').value;
            const months = document.getElementById('indexMonthsSelect').value;
            
            const resultsContainer = document.getElementById('indexCorrelationResults');
            
            // Show loading indicator
            resultsContainer.innerHTML = '<p class="text-center">Loading correlations...</p>';
            
            // Build URL with parameters
            let url = `/api/correlations/for_index/${encodeURIComponent(indexName)}?min_correlation=${minCorrelation}&months=${months}`;
            if (reportType) {
                url += `&report_type=${encodeURIComponent(reportType)}`;
            }
            
            // Fetch correlations
            fetch(url)
                .then(response => response.json())
                .then(correlations => {
                    if (Object.keys(correlations).length === 0) {
                        resultsContainer.innerHTML = '<p class="text-center text-muted">No significant correlations found</p>';
                        return;
                    }
                    
                    // Build table of correlations
                    let html = `
                        <table class="table table-bordered">
                            <thead>
                                <tr>
                                    <th>Correlated Index</th>
                                    <th>Report Type</th>
                                    <th>Correlation</th>
                                    <th>P-Value</th>
                                    <th>Data Points</th>
                                </tr>
                            </thead>
                            <tbody>
                    `;
                    
                    // Add rows for each correlation
                    Object.entries(correlations).forEach(([otherIndex, data]) => {
                        const correlation = data.correlation;
                        const pValue = data.p_value;
                        const n = data.n || 'N/A';
                        const otherReportType = data.report_type2 || 'N/A';
                        
                        // Apply color coding based on correlation strength
                        let correlationClass = '';
                        
                        if (correlation > 0.7) {
                            correlationClass = 'correlation-positive-very-strong';
                        } else if (correlation > 0.5) {
                            correlationClass = 'correlation-positive-strong';
                        } else if (correlation > 0.3) {
                            correlationClass = 'correlation-positive';
                        } else if (correlation < -0.7) {
                            correlationClass = 'correlation-negative-very-strong';
                        } else if (correlation < -0.5) {
                            correlationClass = 'correlation-negative-strong';
                        } else if (correlation < -0.3) {
                            correlationClass = 'correlation-negative';
                        }
                        
                        html += `
                            <tr>
                                <td>${otherIndex}</td>
                                <td>${otherReportType}</td>
                                <td class="${correlationClass}">${correlation}</td>
                                <td>${pValue || 'N/A'}</td>
                                <td>${n}</td>
                            </tr>
                        `;
                    });
                    
                    html += `
                            </tbody>
                        </table>
                    `;
                    
                    resultsContainer.innerHTML = html;
                })
                .catch(error => {
                    console.error('Error fetching index correlations:', error);
                    resultsContainer.innerHTML = '<p class="text-center text-danger">Error loading correlations</p>';
                });
        }
        
        // Lagged Correlations
        function loadLaggedCorrelations() {
            const index1 = document.getElementById('laggedIndex1').value;
            const report1 = document.getElementById('laggedReport1').value;
            const index2 = document.getElementById('laggedIndex2').value;
            const report2 = document.getElementById('laggedReport2').value;
            
            if (!index1 || !index2) return;
            
            // Show loading
            document.getElementById('laggedInterpretation').innerHTML = '<p class="text-center">Loading correlation data...</p>';
            
            // Fetch correlation data
            fetch(`/api/correlations/between_indices?index1=${encodeURIComponent(index1)}&index2=${encodeURIComponent(index2)}&report_type1=${encodeURIComponent(report1)}&report_type2=${encodeURIComponent(report2)}&months=36`)
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        document.getElementById('laggedInterpretation').innerHTML = `<p class="text-danger">${data.error}</p>`;
                        return;
                    }
                    
                    // Create lagged correlation chart
                    createLaggedCorrelationChart(data);
                    
                    // Create scatter plot
                    createScatterPlot(data);
                    
                    // Generate interpretation
                    document.getElementById('laggedInterpretation').innerHTML = generateInterpretation(data);
                })
                .catch(error => {
                    console.error('Error fetching lagged correlations:', error);
                    document.getElementById('laggedInterpretation').innerHTML = '<p class="text-danger">Error loading correlation data</p>';
                });
        }
        
        function createLaggedCorrelationChart(data) {
            // Get the lagged correlations
            const laggedCorrelations = data.lagged_correlations || {};
            
            // Convert to arrays for chart.js
            const lags = Object.keys(laggedCorrelations).map(Number).sort((a, b) => a - b);
            const correlations = lags.map(lag => laggedCorrelations[lag]);
            
            // Chart configuration
            const chartCanvas = document.getElementById('laggedChart');
            
            // Destroy existing chart if it exists
            if (window.laggedChart) {
                window.laggedChart.destroy();
            }
            
            // Create new chart
            window.laggedChart = new Chart(chartCanvas, {
                type: 'bar',
                data: {
                    labels: lags.map(lag => `${lag < 0 ? '' : '+'}${lag} ${Math.abs(lag) === 1 ? 'month' : 'months'}`),
                    datasets: [{
                        label: 'Correlation',
                        data: correlations,
                        backgroundColor: correlations.map(val => val > 0 ? 'rgba(52, 168, 83, 0.6)' : 'rgba(234, 67, 53, 0.6)'),
                        borderColor: correlations.map(val => val > 0 ? 'rgba(52, 168, 83, 1)' : 'rgba(234, 67, 53, 1)'),
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        title: {
                            display: true,
                            text: `Lagged Correlations between ${data.index1} and ${data.index2}`,
                            font: {
                                size: 14,
                                weight: 'bold'
                            }
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    const lag = lags[context.dataIndex];
                                    const correlation = context.raw;
                                    
                                    if (lag === 0) {
                                        return `Correlation: ${correlation.toFixed(2)}`;
                                    } else if (lag > 0) {
                                        return `${data.index1} leads ${data.index2} by ${lag} month(s): ${correlation.toFixed(2)}`;
                                    } else {
                                        return `${data.index2} leads ${data.index1} by ${Math.abs(lag)} month(s): ${correlation.toFixed(2)}`;
                                    }
                                }
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: false,
                            min: -1,
                            max: 1,
                            title: {
                                display: true,
                                text: 'Correlation Coefficient'
                            }
                        },
                        x: {
                            title: {
                                display: true,
                                text: 'Lag (months)'
                            }
                        }
                    }
                }
            });
        }
        
        function createScatterPlot(data) {
            // Create scatter plot of the actual data points
            const chartCanvas = document.getElementById('indexScatterChart');
            
            // Destroy existing chart if it exists
            if (window.scatterChart) {
                window.scatterChart.destroy();
            }
            
            // Get values for both indices
            const values1 = data.values1 || [];
            const values2 = data.values2 || [];
            
            if (values1.length === 0 || values2.length === 0) {
                return;
            }
            
            // Create data for scatter plot
            const scatterData = values1.map((val, i) => ({
                x: val,
                y: values2[i]
            }));
            
            // Create scatter plot
            window.scatterChart = new Chart(chartCanvas, {
                type: 'scatter',
                data: {
                    datasets: [{
                        label: 'Data Points',
                        data: scatterData,
                        backgroundColor: 'rgba(0, 48, 143, 0.6)',
                        borderColor: 'rgba(0, 48, 143, 1)',
                        pointRadius: 5,
                        pointHoverRadius: 7
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        title: {
                            display: true,
                            text: `${data.index1} vs ${data.index2}`,
                            font: {
                                size: 14,
                                weight: 'bold'
                            }
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    return `${data.index1}: ${context.raw.x.toFixed(1)}, ${data.index2}: ${context.raw.y.toFixed(1)}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            title: {
                                display: true,
                                text: data.index1
                            }
                        },
                        y: {
                            title: {
                                display: true,
                                text: data.index2
                            }
                        }
                    }
                }
            });
        }
        
        function generateInterpretation(data) {
            // Generate a human-readable interpretation of the correlation analysis
            const correlation = data.correlation;
            const pValue = data.p_value;
            const n = data.n || 0;
            const laggedCorrelations = data.lagged_correlations || {};
            
            let interpretation = '';
            
            // Interpret main correlation
            interpretation += '<h6>Current Correlation</h6>';
            if (correlation === null || n < 3) {
                interpretation += '<p>Insufficient data to calculate correlation.</p>';
            } else {
                // Describe correlation strength
                let strengthDesc = '';
                if (Math.abs(correlation) > 0.8) {
                    strengthDesc = 'very strong';
                } else if (Math.abs(correlation) > 0.6) {
                    strengthDesc = 'strong';
                } else if (Math.abs(correlation) > 0.4) {
                    strengthDesc = 'moderate';
                } else if (Math.abs(correlation) > 0.2) {
                    strengthDesc = 'weak';
                } else {
                    strengthDesc = 'very weak or no';
                }
                
                // Describe direction
                const directionDesc = correlation > 0 ? 'positive' : 'negative';
                
                // Describe statistical significance
                let significanceDesc = '';
                if (pValue < 0.01) {
                    significanceDesc = 'highly statistically significant';
                } else if (pValue < 0.05) {
                    significanceDesc = 'statistically significant';
                } else if (pValue < 0.1) {
                    significanceDesc = 'marginally significant';
                } else {
                    significanceDesc = 'not statistically significant';
                }
                
                interpretation += `<p>There is a ${strengthDesc} ${directionDesc} correlation (r = ${correlation.toFixed(2)}) between ${data.index1} (${data.report_type1}) and ${data.index2} (${data.report_type2}), which is ${significanceDesc} (p = ${pValue.toFixed(4)}).</p>`;
                
                if (correlation > 0) {
                    interpretation += `<p>This suggests that when ${data.index1} increases, ${data.index2} tends to increase as well.</p>`;
                } else {
                    interpretation += `<p>This suggests that when ${data.index1} increases, ${data.index2} tends to decrease.</p>`;
                }
            }
            
            // Interpret lagged correlations
            if (Object.keys(laggedCorrelations).length > 1) {
                interpretation += '<h6>Time-Lagged Relationship</h6>';
                
                // Find best lag (highest absolute correlation)
                let bestLag = 0;
                let bestCorrelation = 0;
                
                Object.entries(laggedCorrelations).forEach(([lag, corr]) => {
                    if (Math.abs(corr) > Math.abs(bestCorrelation) && lag !== '0') {
                        bestLag = parseInt(lag);
                        bestCorrelation = corr;
                    }
                });
                
                if (bestLag !== 0 && Math.abs(bestCorrelation) > Math.abs(correlation)) {
                    if (bestLag > 0) {
                        interpretation += `<p>The strongest correlation (${bestCorrelation.toFixed(2)}) occurs when ${data.index1} leads ${data.index2} by ${bestLag} month${bestLag > 1 ? 's' : ''}. This suggests that changes in ${data.index1} may be predictive of future changes in ${data.index2}.</p>`;
                    } else {
                        interpretation += `<p>The strongest correlation (${bestCorrelation.toFixed(2)}) occurs when ${data.index2} leads ${data.index1} by ${Math.abs(bestLag)} month${Math.abs(bestLag) > 1 ? 's' : ''}. This suggests that changes in ${data.index2} may be predictive of future changes in ${data.index1}.</p>`;
                    }
                } else {
                    interpretation += `<p>The correlation is strongest without any time lag, suggesting that these indices tend to move together in the same time period.</p>`;
                }
            }
            
            return interpretation;
        }
        
        // Utility functions for exporting
        function exportCrossCorrelationData() {
            // Get table data
            const table = document.getElementById('crossCorrelationTable');
            exportTableToCSV(table, 'cross_report_correlations.csv');
        }
        
        function exportIndexCorrelationData() {
            // Get table data from the tab
            const resultsContainer = document.getElementById('indexCorrelationResults');
            const table = resultsContainer.querySelector('table');
            
            if (!table) {
                alert('No correlation data to export');
                return;
            }
            
            const indexName = document.getElementById('indexSelect').value;
            exportTableToCSV(table, `${indexName}_correlations.csv`);
        }
        
        function exportLaggedCorrelationData() {
            // Get data from the lagged correlation charts
            const index1 = document.getElementById('laggedIndex1').value;
            const index2 = document.getElementById('laggedIndex2').value;
            
            // Create a temporary table
            const tempTable = document.createElement('table');
            const thead = document.createElement('thead');
            const tbody = document.createElement('tbody');
            
            // Add header row
            const headerRow = document.createElement('tr');
            headerRow.innerHTML = `
                <th>Lag (months)</th>
                <th>Correlation</th>
            `;
            thead.appendChild(headerRow);
            
            // Get data from the chart
            if (window.laggedChart) {
                const labels = window.laggedChart.data.labels;
                const data = window.laggedChart.data.datasets[0].data;
                
                // Add data rows
                for (let i = 0; i < labels.length; i++) {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${labels[i]}</td>
                        <td>${data[i]}</td>
                    `;
                    tbody.appendChild(row);
                }
            }
            
            tempTable.appendChild(thead);
            tempTable.appendChild(tbody);
            document.body.appendChild(tempTable);
            tempTable.style.display = 'none';
            
            exportTableToCSV(tempTable, `${index1}_${index2}_lagged_correlations.csv`);
            
            // Remove temporary table
            document.body.removeChild(tempTable);
        }
        
        function exportTableToCSV(table, filename) {
            const rows = table.querySelectorAll('tr');
            let csv = [];
            
            for (let i = 0; i < rows.length; i++) {
                const row = [], cols = rows[i].querySelectorAll('td, th');
                
                for (let j = 0; j < cols.length; j++) {
                    // Replace HTML entities and quotes
                    let data = cols[j].innerText.replace(/(\r\n|\n|\r)/gm, '').replace(/(\s\s)/gm, ' ');
                    data = data.replace(/"/g, '""');
                    row.push('"' + data + '"');
                }
                
                csv.push(row.join(','));
            }
            
            // Download CSV file
            downloadCSV(csv.join('\n'), filename);
        }
        
        function downloadCSV(csv, filename) {
            const csvFile = new Blob([csv], {type: 'text/csv'});
            const downloadLink = document.createElement('a');
            
            downloadLink.download = filename;
            downloadLink.href = window.URL.createObjectURL(csvFile);
            downloadLink.style.display = 'none';
            
            document.body.appendChild(downloadLink);
            downloadLink.click();
            document.body.removeChild(downloadLink);
        }
        
        function refreshAllAnalyses() {
            // Refresh all analyses
            loadCrossReportCorrelations();
            loadIndexCorrelations();
            loadLaggedCorrelations();
        }
    </script>
</body>
</html>


@app.route('/correlations')
@login_required
def correlations():
    """Display the correlation analysis page."""
    return render_template('correlations.html')