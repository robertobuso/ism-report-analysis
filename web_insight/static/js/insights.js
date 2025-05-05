document.addEventListener('DOMContentLoaded', function () {
    // Buttons
    const refreshTrendsBtn = document.getElementById('refreshTrendsBtn');
    if (refreshTrendsBtn) refreshTrendsBtn.addEventListener('click', loadTrends);
  
    const generateInsightBtn = document.getElementById('generateInsightBtn');
    if (generateInsightBtn)
      generateInsightBtn.addEventListener('click', () => generateInsight());
  
    // Initial load
    loadTrends();
    loadInsights();
  
    // Bootstrap modal handle
    new bootstrap.Modal(document.getElementById('insightDetailModal'));
  });
  
  /* -------- API CALLS & RENDERING -------- */
  
  function loadTrends() {
    const trendsContainer = document.getElementById('trendsContainer');
    const loadingIndicator = document.getElementById('trendsLoadingIndicator');
    if (!trendsContainer) return;
  
    trendsContainer.innerHTML = spinnerHTML('Loading trends…');
    loadingIndicator?.classList.remove('d-none');
  
    fetch('/web_insight/api/significant_trends')
      .then((res) => {
        if (!res.ok) throw new Error('Network response was not ok');
        return res.json();
      })
      .then((trends) => {
        loadingIndicator?.classList.add('d-none');
  
        if (!trends || trends.length === 0) {
          trendsContainer.innerHTML = emptyInfo(
            'No significant trends found in recent ISM data.'
          );
          return;
        }
        trendsContainer.innerHTML = '';
        trends.forEach((trend, idx) => trendsContainer.appendChild(trendCard(trend, idx)));
        document.querySelectorAll('.analyze-trend').forEach((btn) =>
          btn.addEventListener('click', function () {
            generateInsight(parseInt(this.dataset.index, 10));
          })
        );
      })
      .catch((err) => {
        loadingIndicator?.classList.add('d-none');
        trendsContainer.innerHTML = errorInfo(`Error loading trends: ${err.message}`);
        console.error(err);
      });
  }
  
  function loadInsights() {
    const insightsContainer = document.getElementById('insightsContainer');
    if (!insightsContainer) return;
  
    insightsContainer.innerHTML = spinnerHTML('Loading insights…');
  
    fetch('/web_insight/api/insights')
      .then((res) => {
        if (!res.ok) throw new Error('Network response was not ok');
        return res.json();
      })
      .then((insights) => {
        if (!insights || insights.length === 0) {
          insightsContainer.innerHTML = emptyInfo(
            'No insights generated yet. Click "Generate New Insight" to create one.'
          );
          return;
        }
        insightsContainer.innerHTML = '';
        insights.forEach((insight) => insightsContainer.appendChild(insightCard(insight)));
  
        document.querySelectorAll('.view-insight').forEach((btn) =>
          btn.addEventListener('click', () => showInsightDetail(btn.dataset.insightId))
        );
      })
      .catch((err) => {
        insightsContainer.innerHTML = errorInfo(`Error loading insights: ${err.message}`);
        console.error(err);
      });
  }
  
  function generateInsight(trendIndex = null) {
    // Default to random trend if none selected
    if (trendIndex === null) trendIndex = Math.floor(Math.random() * 5);
  
    const btn = document.getElementById('generateInsightBtn');
    const loadBadge = document.getElementById('insightLoadingIndicator');
    const insightsContainer = document.getElementById('insightsContainer');
  
    btn && (btn.disabled = true);
    loadBadge && loadBadge.classList.remove('d-none');
    insightsContainer &&
      insightsContainer.prepend(
        notify(
          'info',
          'Generating insight… This may take up to a minute as we search the web and analyse the data.',
          true
        )
      );
  
    fetch('/web_insight/api/generate_insight', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trend_index: trendIndex })
    })
      .then((res) => {
        if (!res.ok) throw new Error('Network response was not ok');
        return res.json();
      })
      .then(() => {
        btn && (btn.disabled = false);
        loadBadge && loadBadge.classList.add('d-none');
        document.querySelectorAll('.generating-notification').forEach((n) => n.remove());
        loadInsights();
        insightsContainer &&
          insightsContainer.prepend(notify('success', 'New insight generated successfully!'));
      })
      .catch((err) => {
        btn && (btn.disabled = false);
        loadBadge && loadBadge.classList.add('d-none');
        document.querySelectorAll('.generating-notification').forEach((n) => n.remove());
        insightsContainer &&
          insightsContainer.prepend(notify('danger', `Error generating insight: ${err.message}`));
        console.error(err);
      });
  }
  
  function showInsightDetail(id) {
    const modalBody = document.getElementById('insightDetailModalBody');
    if (!modalBody) return;
  
    modalBody.innerHTML = spinnerHTML('Loading insight details…');
    new bootstrap.Modal(document.getElementById('insightDetailModal')).show();
  
    fetch(`/web_insight/api/insight/${id}`)
      .then((res) => {
        if (!res.ok) throw new Error('Network response was not ok');
        return res.json();
      })
      .then((insight) => {
        document.getElementById('insightDetailModalLabel').innerText =
          `${insight.index_name} Analysis`;
  
        const date = new Date(insight.created_at).toLocaleString('en-US', {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit'
        });
  
        modalBody.innerHTML = `
          <div class="insight-detail">
            <div class="alert ${insight.change > 0 ? 'alert-success' : 'alert-danger'} mb-4">
              <h5 class="alert-heading">${insight.trend_description}</h5>
              <div class="d-flex justify-content-between">
                <div>
                  <span class="badge ${insight.change > 0 ? 'bg-success' : 'bg-danger'}">
                    Change: ${insight.change > 0 ? '+' : ''}${insight.change.toFixed(1)} pts
                  </span>
                  <span class="badge bg-secondary ms-2">
                    Current: ${insight.current_value.toFixed(1)}
                  </span>
                  <span class="badge bg-secondary ms-2">
                    Previous: ${insight.previous_value.toFixed(1)}
                  </span>
                </div>
                <div class="text-muted small">Generated: ${date}</div>
              </div>
            </div>
  
            ${analysisCard(insight.analysis)}
            ${implicationsCard(insight.investment_implications)}
            ${evidenceCard(insight.evidence, insight.search_queries)}
          </div>
        `;
      })
      .catch((err) => {
        modalBody.innerHTML = errorInfo(`Error loading insight details: ${err.message}`);
        console.error(err);
      });
  }
  
  /* ----------  HTML BUILDERS ---------- */
  
  const spinnerHTML = (msg) => `
    <div class="text-center">
      <div class="spinner-border text-primary"></div>
      <p class="mt-2">${msg}</p>
    </div>`;
  
  const emptyInfo = (msg) =>
    `<div class="alert alert-info"><i class="bi bi-info-circle"></i> ${msg}</div>`;
  
  const errorInfo = (msg) =>
    `<div class="alert alert-danger"><i class="bi bi-exclamation-triangle"></i> ${msg}</div>`;
  
  const notify = (type, msg, generating = false) => {
    const cls =
      type === 'success'
        ? 'alert-success'
        : type === 'info'
        ? 'alert-info generating-notification'
        : 'alert-danger';
    return Object.assign(document.createElement('div'), {
      className: `alert ${cls}`,
      innerHTML: generating
        ? `<div class="d-flex align-items-center">
             <div class="spinner-border spinner-border-sm me-2" role="status"></div>
             <div><strong>${msg}</strong></div>
           </div>`
        : `<i class="bi ${
            type === 'success' ? 'bi-check-circle' : type === 'info' ? 'bi-info-circle' : 'bi-exclamation-triangle'
          }"></i> ${msg}`
    });
  };
  
  const trendCard = (trend, idx) => {
    const isPositive = trend.change > 0;
    const card = document.createElement('div');
    card.className = `trend-card ${isPositive ? 'positive' : 'negative'}`;
    card.innerHTML = `
      <div class="trend-title">${trend.index_name}</div>
      <div class="trend-description">${trend.description}</div>
      <div class="trend-change ${isPositive ? 'positive' : 'negative'}">
        Change: ${isPositive ? '+' : ''}${trend.change.toFixed(1)} points
      </div>
      <button class="btn btn-sm btn-outline-primary analyze-trend" data-index="${idx}">
        <i class="bi bi-search"></i> Analyze with Web Data
      </button>`;
    return card;
  };
  
  const insightCard = (insight) => {
    const card = document.createElement('div');
    card.className = 'insight-card';
  
    const date = new Date(insight.created_at).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
    const preview = insight.analysis.slice(0, 150) + (insight.analysis.length > 150 ? '…' : '');
  
    card.innerHTML = `
      <div class="insight-header">
        <h3 class="insight-title">${insight.index_name} Analysis</h3>
        <span class="insight-date">${date}</span>
      </div>
      <div class="insight-description">${insight.trend_description}</div>
      <div class="insight-analysis">
        <h6>Analysis Preview:</h6><p>${preview}</p>
      </div>
      <div class="implications-section">
        <h6>Investment Implications:</h6>
        ${formatImplicationsPreview(insight.investment_implications)}
      </div>
      <div class="insight-button mt-3">
        <button class="btn btn-outline-primary btn-sm view-insight" data-insight-id="${insight.insight_id}">
          <i class="bi bi-eye"></i> View Full Analysis
        </button>
      </div>`;
    return card;
  };
  
  const analysisCard = (analysis) => `
    <div class="card mb-4">
      <div class="card-header bg-light"><h5 class="mb-0">Analysis</h5></div>
      <div class="card-body">${formatAnalysisText(analysis)}</div>
    </div>`;
  
  const implicationsCard = (impl) => `
    <div class="card mb-4">
      <div class="card-header bg-light"><h5 class="mb-0">Investment Implications</h5></div>
      <div class="card-body">${formatDetailedImplications(impl)}</div>
    </div>`;
  
  const evidenceCard = (ev, q) => `
    <div class="card">
      <div class="card-header bg-light"><h5 class="mb-0">Evidence from Web</h5></div>
      <div class="card-body p-0">
        <ul class="list-group list-group-flush">${formatEvidence(ev)}</ul>
        <div class="p-3 bg-light border-top">
          <small class="text-muted"><i class="bi bi-info-circle"></i>
            Search queries used: ${formatSearchQueries(q)}
          </small>
        </div>
      </div>
    </div>`;
    
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