// Search functionality

document.addEventListener('DOMContentLoaded', function() {
    const searchForm = document.getElementById('searchForm');
    const resultsContainer = document.getElementById('results');
    const searchSpinner = document.getElementById('searchSpinner');

    searchForm.addEventListener('submit', handleSearch);

    async function handleSearch(event) {
        event.preventDefault();
        
        const query = document.getElementById('query').value.trim();
        if (!query) return;

        // Show loading state
        searchSpinner.classList.remove('d-none');
        resultsContainer.innerHTML = '';

        try {
            // Collect form data
            const vectorName = document.getElementById('vectorName').value;
            const limit = document.getElementById('limit').value;
            
            // Collect filters
            const filters = {};
            const dateFrom = document.getElementById('dateFrom').value;
            const dateTo = document.getElementById('dateTo').value;
            const urlFilter = document.getElementById('urlFilter').value.trim();
            const keywordsFilter = document.getElementById('keywordsFilter').value.trim();
            const excludeKeywords = document.getElementById('excludeKeywords').value.trim();

            if (dateFrom) filters.date_from = dateFrom;
            if (dateTo) filters.date_to = dateTo;
            if (urlFilter) filters.url = urlFilter;
            if (keywordsFilter) {
                filters.keywords = keywordsFilter.split(',').map(k => k.trim()).filter(k => k);
            }
            
            // 除外キーワードを処理
            const excludeKeywordsList = excludeKeywords ? 
                excludeKeywords.split(',').map(k => k.trim()).filter(k => k) : null;

            // Perform search
            const response = await window.api.search(query, vectorName, limit, filters, excludeKeywordsList);
            
            // Display results
            displayResults(response);

        } catch (error) {
            displayError(error.message);
        } finally {
            searchSpinner.classList.add('d-none');
        }
    }

    function displayResults(response) {
        if (!response.results || response.results.length === 0) {
            resultsContainer.innerHTML = `
                <div class="alert alert-info">
                    <h6>No results found</h6>
                    <p class="mb-0">Try adjusting your search query or filters.</p>
                </div>
            `;
            return;
        }

        const resultsHtml = `
            <div class="card fade-in">
                <div class="card-header">
                    <h6 class="mb-0">Search Results (${response.results.length} of ${response.total || response.results.length})</h6>
                    <small class="text-muted">Query: "${response.query}"</small>
                </div>
                <div class="card-body p-0">
                    ${response.results.map(result => createResultHtml(result)).join('')}
                </div>
            </div>
        `;

        resultsContainer.innerHTML = resultsHtml;
        
        // Add click handlers for expandable text
        addExpandableTextHandlers();
    }

    function createResultHtml(result) {
        const keywords = Array.isArray(result.keywords) ? result.keywords : [];
        const keywordBadges = keywords.slice(0, 5).map(keyword => 
            `<span class="badge bg-secondary keyword-badge">${escapeHtml(keyword)}</span>`
        ).join('');

        const memoHtml = result.memo ? `
            <div class="search-result-memo">
                <strong>Memo:</strong> ${escapeHtml(result.memo)}
            </div>
        ` : '';

        const scoreColor = result.score >= 0.8 ? 'text-success' : 
                          result.score >= 0.6 ? 'text-warning' : 'text-secondary';

        // content_vectorの場合はコンテンツも表示
        const vectorName = document.getElementById('vectorName').value;
        const contentHtml = (vectorName === 'content_vector' && result.content) ? `
            <div class="search-result-content mt-2">
                <strong>Content:</strong>
                <div class="expandable-text text-truncate-2 cursor-pointer" data-full-text="${escapeHtml(result.content)}">
                    ${escapeHtml(result.content)}
                </div>
            </div>
        ` : '';

        return `
            <div class="search-result">
                <a href="${escapeHtml(result.url)}" target="_blank" class="search-result-title">
                    ${escapeHtml(result.display_title || result.title || 'Untitled')}
                </a>
                <div class="search-result-url">${escapeHtml(result.url)}</div>
                <div class="search-result-score ${scoreColor}">
                    Score: ${result.score.toFixed(3)}
                </div>
                ${result.summary ? `
                    <div class="search-result-summary">
                        <strong>Summary:</strong>
                        <div class="expandable-text text-truncate-2 cursor-pointer" data-full-text="${escapeHtml(result.summary)}">
                            ${escapeHtml(result.summary)}
                        </div>
                    </div>
                ` : ''}
                ${contentHtml}
                ${keywordBadges ? `
                    <div class="search-result-keywords">
                        ${keywordBadges}
                    </div>
                ` : ''}
                ${memoHtml}
                <div class="text-muted small mt-2">
                    ${formatDate(result.created_at)}
                </div>
            </div>
        `;
    }

    function displayError(message) {
        resultsContainer.innerHTML = `
            <div class="alert alert-danger">
                <h6>Search Error</h6>
                <p class="mb-0">${escapeHtml(message)}</p>
            </div>
        `;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function formatDate(dateString) {
        if (!dateString) return 'Unknown date';
        try {
            const date = new Date(dateString);
            return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
        } catch {
            return dateString;
        }
    }

    function addExpandableTextHandlers() {
        const expandableTexts = document.querySelectorAll('.expandable-text');
        expandableTexts.forEach(element => {
            element.addEventListener('click', function() {
                const isExpanded = !element.classList.contains('text-truncate-2');
                
                if (isExpanded) {
                    // Collapse: restore truncated view
                    element.classList.add('text-truncate-2');
                } else {
                    // Expand: show full text
                    element.classList.remove('text-truncate-2');
                }
            });
        });
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', function(event) {
        if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
            event.preventDefault();
            document.getElementById('query').focus();
        }
        if (event.key === 'Escape') {
            resultsContainer.innerHTML = '';
        }
    });
});