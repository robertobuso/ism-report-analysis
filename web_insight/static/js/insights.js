document.addEventListener('DOMContentLoaded', function() {
    // Set up event listeners
    const refreshTrendsBtn = document.getElementById('refreshTrendsBtn');
    if (refreshTrendsBtn) {
        refreshTrendsBtn.addEventListener('click', loadTrends);
    }
    
    const generateInsightBtn = document.getElementById('generateInsightBtn');
    if (generateInsightBtn) {
        generateInsightBtn.addEventListener('click', function() {
            generateInsight();
        });
    }
    
    // Load initial data
    loadTrends();
    loadInsights();
    
    // Initialize modal
    const insightDetailModal = new bootstrap.Modal(document.getElementById('insightDetailModal'));
});

/**
 * Load significant trends from the API
 */
function loadTrends() {
    const trendsContainer = document.getElementById('trendsContainer');
    const loadingIndicator = document.getElementById('trendsLoadingIndicator');
    
    if (!trendsContainer) return;
    
    // Show loading state
    trendsContainer.innerHTML = `
        <div class="text-center">
            <div class="spinner-border text-primary"></div>
            <p class="mt-2">Loading trends...</p>
        </div>
    `;
    
    if (loadingIndicator) {
        loadingIndicator.classList.remove('d-none');
    }
    
    // Fetch trends from API
    fetch('/web_insight/api/significant_trends')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(trends => {
            if (loadingIndicator) {
                loadingIndicator.classList.add('d-none');
            }
            
            // Handle empty trends
            if (!trends || trends.length === 0) {
                trendsContainer.innerHTML = `
                    <div class="alert alert-info">
                        <i class="bi bi-info-circle"></i> No significant trends found in recent ISM data.
                    </div>
                `;
                return;
            }
            
            // Render trends
            trendsContainer.innerHTML = '';
            
            trends.forEach((trend, index) => {
                const isPositive = trend.change > 0;
                const cardClass = isPositive ? 'positive' : 'negative';
                const changeClass = isPositive ? 'positive' : 'negative';
                const changePrefix = isPositive ? '+' : '';
                
                const trendCard = document.createElement('div');
                trendCard.className = `trend-card ${cardClass}`;
                trendCard.innerHTML = `
                    <div class="trend-title">${trend.index_name}</div>
                    <div class="trend-description">${trend.description}</div>
                    <div class="trend-change ${changeClass}">
                        Change: ${changePrefix}${trend.change.toFixed(1)} points
                    </div>
                    <button class="btn btn-sm btn-outline-primary analyze-trend" data-index="${index}">
                        <i class="bi bi-search"></i> Analyze with Web Data
                    </button>
                `;
                
                trendsContainer.appendChild(trendCard);
            });
            
            // Add event listeners to analyze buttons
            document.querySelectorAll('.analyze-trend').forEach(button => {
                button.addEventListener('click', function() {
                    const trendIndex = parseInt(this.getAttribute('data-index'));
                    generateInsight(trendIndex);
                });
            });
        })
        .catch(error => {
            if (loadingIndicator) {
                loadingIndicator.classList.add('d-none');
            }
            
            trendsContainer.innerHTML = `
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle"></i> Error loading trends: ${error.message}
                </div>
            `;
            console.error('Error loading trends:', error);
        });
}

/**
 * Load insights from the API
 */
function loadInsights() {
    const insightsContainer = document.getElementById('insightsContainer');
    
    if (!insightsContainer) return;
    
    // Show loading state
    insightsContainer.innerHTML = `
        <div class="text-center">
            <div class="spinner-border text-primary"></div>
            <p class="mt-2">Loading insights...</p>
        </div>
    `;
    
    // Fetch insights from API
    fetch('/web_insight/api/insights')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(insights => {
            // Handle empty insights
            if (!insights || insights.length === 0) {
                insightsContainer.innerHTML = `
                    <div class="alert alert-info">
                        <i class="bi bi-info-circle"></i> No insights generated yet. Click "Generate New Insight" to create one.
                    </div>
                `;
                return;
            }
            
            // Render insights
            insightsContainer.innerHTML = '';
            
            insights.forEach(insight => {
                const card = document.createElement('div');
                card.className = 'insight-card';
                
                // Format date
                const date = new Date(insight.created_at);
                const formattedDate = date.toLocaleDateString('en-US', {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric'
                });
                
                // Get a preview of the analysis (first 150 chars)
                const analysisPreview = insight.analysis.substring(0, 150) + 
                    (insight.analysis.length > 150 ? '...' : '');
                
                card.innerHTML = `
                    <div class="insight-header">
                        <h3 class="insight-title">${insight.index_name} Analysis</h3>
                        <span class="insight-date">${formattedDate}</span>
                    </div>
                    <div class="insight-description">
                        ${insight.trend_description}
                    </div>
                    <div class="insight-analysis">
                        <h6>Analysis Preview:</h6>
                        <p>${analysisPreview}</p>
                    </div>
                    <div class="implications-section">
                        <h6>Investment Implications:</h6>
                        ${formatImplicationsPreview(insight.investment_implications)}
                    </div>
                    <div class="insight-button mt-3">
                        <button class="btn btn-outline-primary btn-sm view-insight" data-insight-id="${insight.insight_id}">
                            <i class="bi bi-eye"></i> View Full Analysis
                        </button>
                    </div>
                `;
                
                insightsContainer.appendChild(card);
            });
            
            // Add event listeners to view buttons
            document.querySelectorAll('.view-insight').forEach(button => {
                button.addEventListener('click', function() {
                    const insightId = this.getAttribute('data-insight-id');
                    showInsightDetail(insightId);
                });
            });
        })
        .catch(error => {
            insightsContainer.innerHTML = `
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle"></i> Error loading insights: ${error.message}
                </div>
            `;
            console.error('Error loading insights:', error);
        });
}

/**
 * Generate a new insight based on a trend
 */
function generateInsight(trendIndex = 0) {
    const generateBtn = document.getElementById('generateInsightBtn');
    const loadingIndicator = document.getElementById('insightLoadingIndicator');
    
    // Disable button and show loading state
    if (generateBtn) {
        generateBtn.disabled = true;
    }
    
    if (loadingIndicator) {
        loadingIndicator.classList.remove('d-none');
    }
    
    // Show a notification at top of insights container
    const insightsContainer = document.getElementById('insightsContainer');
    if (insightsContainer) {
        const notification = document.createElement('div');
        notification.className = 'alert alert-info generating-notification';
        notification.innerHTML = `
            <div class="d-flex align-items-center">
                <div class="spinner-border spinner-border-sm me-2" role="status"></div>
                <div>
                    <strong>Generating insight...</strong>
                    <p class="mb-0 small">This may take up to a minute as we search the web and analyze the data.</p>
                </div>
            </div>
        `;
        insightsContainer.prepend(notification);
    }
    
    // Make the API call
    fetch('/web_insight/api/generate_insight', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ trend_index: trendIndex })
    })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(insight => {
            // Re-enable button and hide loading indicator
            if (generateBtn) {
                generateBtn.disabled = false;
            }
            
            if (loadingIndicator) {
                loadingIndicator.classList.add('d-none');
            }
            
            // Remove generation notification
            document.querySelectorAll('.generating-notification').forEach(el => el.remove());
            
            // Reload insights to show the new one
            loadInsights();
            
            // Show success notification
            if (insightsContainer) {
                const successNotification = document.createElement('div');
                successNotification.className = 'alert alert-success';
                successNotification.innerHTML = `
                    <i class="bi bi-check-circle"></i> New insight generated successfully!
                `;
                insightsContainer.prepend(successNotification);
                
                // Auto-hide the notification after 5 seconds
                setTimeout(() => {
                    successNotification.classList.add('fade');
                    setTimeout(() => successNotification.remove(), 500);
                }, 5000);
            }
        })
        .catch(error => {
            // Re-enable button and hide loading indicator
            if (generateBtn) {
                generateBtn.disabled = false;
            }
            
            if (loadingIndicator) {
                loadingIndicator.classList.add('d-none');
            }
            
            // Remove generation notification
            document.querySelectorAll('.generating-notification').forEach(el => el.remove());
            
            // Show error notification
            if (insightsContainer) {
                const errorNotification = document.createElement('div');
                errorNotification.className = 'alert alert-danger';
                errorNotification.innerHTML = `
                    <i class="bi bi-exclamation-triangle"></i> Error generating insight: ${error.message}
                `;
                insightsContainer.prepend(errorNotification);
            }
            
            console.error('Error generating insight:', error);
        });
}

/**
 * Show the detailed view of an insight
 */
function showInsightDetail(insightId) {
    const modalBody = document.getElementById('insightDetailModalBody');
    if (!modalBody) return;
    
    // Show loading state in modal
    modalBody.innerHTML = `
        <div class="text-center p-4">
            <div class="spinner-border text-primary"></div>
            <p class="mt-2">Loading insight details...</p>
        </div>
    `;
    
    // Show the modal
    const modal = new bootstrap.Modal(document.getElementById('insightDetailModal'));
    modal.show();
    
    // Fetch the insight details
    fetch(`/web_insight/api/insight/${insightId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(insight => {
            // Format date
            const date = new Date(insight.created_at);
            const formattedDate = date.toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
            
            // Set the modal title
            document.getElementById('insightDetailModalLabel').innerText = `${insight.index_name} Analysis`;
            
            // Format the analysis text
            const formattedAnalysis = formatAnalysisText(insight.analysis);
            
            // Create the modal content
            modalBody.innerHTML = `
                <div class="insight-detail">
                    <div class="alert ${insight.change > 0 ? 'alert-success' : 'alert-danger'} mb-4">
                        <h5 class="alert-heading">${insight.trend_description}</h5>
                        <div class="d-flex justify-content-between">
                            <div>
                                <span class="badge ${(insight.change || 0) > 0 ? 'bg-success' : 'bg-danger'}">
                                    Change: ${(insight.change || 0) > 0 ? '+' : ''}${typeof insight.change === 'number' ? insight.change.toFixed(1) : '0.0'} points
                                </span>
                                <span class="badge bg-secondary ms-2">
                                    Current: ${typeof insight.current_value === 'number' ? insight.current_value.toFixed(1) : '0.0'}
                                </span>
                            </div>
                            <div class="text-muted small">
                                Generated: ${formattedDate}
                            </div>
                        </div>
                    </div>
                    
                    <div class="card mb-4">
                        <div class="card-header bg-light">
                            <h5 class="card-title mb-0">Analysis</h5>
                        </div>
                        <div class="card-body">
                            ${formattedAnalysis}
                        </div>
                    </div>
                    
                    <div class="card mb-4">
                        <div class="card-header bg-light">
                            <h5 class="card-title mb-0">Investment Implications</h5>
                        </div>
                        <div class="card-body">
                            ${formatDetailedImplications(insight.investment_implications)}
                        </div>
                    </div>
                    
                    <div class="card">
                        <div class="card-header bg-light">
                            <h5 class="card-title mb-0">Evidence from Web</h5>
                        </div>
                        <div class="card-body p-0">
                            <ul class="list-group list-group-flush">
                                ${formatEvidence(insight.evidence)}
                            </ul>
                            <div class="p-3 bg-light border-top">
                                <small class="text-muted">
                                    <i class="bi bi-info-circle"></i> 
                                    Search queries used: ${formatSearchQueries(insight.search_queries)}
                                </small>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        })
        .catch(error => {
            modalBody.innerHTML = `
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle"></i> Error loading insight details: ${error.message}
                </div>
            `;
            console.error('Error loading insight details:', error);
        });
}

/**
 * Format analysis text for better readability
 */
function formatAnalysisText(text) {
    if (!text) return '';
    
    // Replace numbered points with styled headers
    let formatted = text.replace(/(\d+\.\s+)([^\n]+)/g, '<h6 class="mt-3">$1$2</h6>');
    
    // Replace paragraphs
    formatted = formatted.replace(/\n\n/g, '</p><p>');
    
    // Replace single line breaks
    formatted = formatted.replace(/\n/g, '<br>');
    
    // Wrap in paragraph tags if not already
    if (!formatted.startsWith('<p>')) {
        formatted = '<p>' + formatted;
    }
    if (!formatted.endsWith('</p>')) {
        formatted += '</p>';
    }
    
    // Highlight bullish and bearish mentions
    formatted = formatted.replace(/\b(bullish)\b/gi, '<span class="text-bullish">$1</span>');
    formatted = formatted.replace(/\b(bearish)\b/gi, '<span class="text-bearish">$1</span>');
    
    return formatted;
}

/**
 * Format investment implications for preview
 */
function formatImplicationsPreview(implications) {
    if (!implications || !implications.sectors || !implications.companies) {
        return '<p class="text-muted">No specific investment implications identified.</p>';
    }
    
    let html = '';
    
    // Add sectors
    if (implications.sectors.length > 0) {
        const sectors = implications.sectors.slice(0, 2);
        html += '<div class="mb-2">';
        sectors.forEach(sector => {
            const impactClass = sector.impact === 'bullish' ? 'text-bullish' : 'text-bearish';
            html += `<span class="badge bg-light text-dark me-2">${sector.name} <span class="${impactClass}">(${sector.impact})</span></span>`;
        });
        if (implications.sectors.length > 2) {
            html += `<span class="badge bg-secondary">+${implications.sectors.length - 2} more</span>`;
        }
        html += '</div>';
    }
    
    // Add companies
    if (implications.companies.length > 0) {
        const companies = implications.companies.slice(0, 2);
        html += '<div>';
        companies.forEach(company => {
            const impactClass = company.impact === 'bullish' ? 'text-bullish' : 'text-bearish';
            html += `<span class="badge bg-light text-dark me-2">${company.name} <span class="${impactClass}">(${company.impact})</span></span>`;
        });
        if (implications.companies.length > 2) {
            html += `<span class="badge bg-secondary">+${implications.companies.length - 2} more</span>`;
        }
        html += '</div>';
    }
    
    return html || '<p class="text-muted">No specific investment implications identified.</p>';
}

/**
 * Format detailed investment implications
 */
function formatDetailedImplications(implications) {
    if (!implications || !implications.sectors || !implications.companies) {
        return '<p class="text-muted">No specific investment implications identified.</p>';
    }
    
    let html = '';
    
    // Add sectors
    if (implications.sectors.length > 0) {
        html += '<h6 class="mt-3">Sectors</h6>';
        html += '<div class="list-group mb-3">';
        implications.sectors.forEach(sector => {
            const impactClass = sector.impact === 'bullish' ? 'text-bullish' : 'text-bearish';
            html += `
                <div class="list-group-item">
                    <div class="d-flex justify-content-between align-items-center">
                        <strong>${sector.name}</strong>
                        <span class="badge ${sector.impact === 'bullish' ? 'bg-success' : 'bg-danger'}">${sector.impact}</span>
                    </div>
                    ${sector.reasoning ? `<p class="mb-0 mt-1 small">${sector.reasoning}</p>` : ''}
                </div>
            `;
        });
        html += '</div>';
    }
    
    // Add companies
    if (implications.companies.length > 0) {
        html += '<h6 class="mt-3">Companies</h6>';
        html += '<div class="list-group mb-3">';
        implications.companies.forEach(company => {
            const impactClass = company.impact === 'bullish' ? 'text-bullish' : 'text-bearish';
            html += `
                <div class="list-group-item">
                    <div class="d-flex justify-content-between align-items-center">
                        <strong>${company.name} ${company.ticker ? `(${company.ticker})` : ''}</strong>
                        <span class="badge ${company.impact === 'bullish' ? 'bg-success' : 'bg-danger'}">${company.impact}</span>
                    </div>
                    ${company.reasoning ? `<p class="mb-0 mt-1 small">${company.reasoning}</p>` : ''}
                </div>
            `;
        });
        html += '</div>';
    }
    
    // Add timing considerations
    if (implications.timing) {
        html += `
            <h6 class="mt-3">Timing Considerations</h6>
            <div class="alert alert-secondary">
                ${implications.timing}
            </div>
        `;
    }
    
    return html || '<p class="text-muted">No specific investment implications identified.</p>';
}

/**
 * Format evidence sources
 */
function formatEvidence(evidence) {
    if (!evidence || evidence.length === 0) {
        return '<li class="list-group-item text-muted">No evidence sources found.</li>';
    }
    
    let html = '';
    
    evidence.forEach((item, index) => {
        html += `
            <li class="list-group-item">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <h6 class="mb-0">${item.title}</h6>
                    <span class="badge bg-secondary">${item.source}</span>
                </div>
                <p class="small text-muted mb-2 evidence-excerpt">
                    ${item.content ? (item.content.substring(0, 200) + '...') : 'No content available'}
                </p>
                <a href="${item.url}" target="_blank" class="btn btn-sm btn-outline-primary">
                    <i class="bi bi-box-arrow-up-right"></i> View Source
                </a>
            </li>
        `;
    });
    
    return html;
}

/**
 * Format search queries
 */
function formatSearchQueries(queries) {
    if (!queries || queries.length === 0) {
        return 'None';
    }
    
    // Show first 2 queries and "and X more" if there are more
    if (queries.length <= 2) {
        return queries.join(', ');
    } else {
        return `${queries[0]}, ${queries[1]} and ${queries.length - 2} more`;
    }
}