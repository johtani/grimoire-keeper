// Pages management functionality

document.addEventListener('DOMContentLoaded', function() {
    const statusFilter = document.getElementById('statusFilter');
    const sortBy = document.getElementById('sortBy');
    const sortOrder = document.getElementById('sortOrder');
    const refreshBtn = document.getElementById('refreshBtn');
    const refreshSpinner = document.getElementById('refreshSpinner');
    const pagesTable = document.getElementById('pagesTable');
    const pagination = document.getElementById('pagination');
    const repairsTable = document.getElementById('repairsTable');
    const repairStatusFilter = document.getElementById('repairStatusFilter');

    let currentPage = 0;
    const pageSize = 20;

    // Event listeners
    statusFilter.addEventListener('change', loadPages);
    sortBy.addEventListener('change', loadPages);
    sortOrder.addEventListener('change', loadPages);
    refreshBtn.addEventListener('click', loadPages);
    repairStatusFilter.addEventListener('change', loadRepairs);
    document.getElementById('importRepairsBtn').addEventListener('click', async () => {
        try {
            const result = await window.api.importRepairs();
            alert(`Imported ${result.imported} repair cases (${result.missing_pages} missing pages).`);
            await loadRepairs();
        } catch (error) { alert('Import failed: ' + error.message); }
    });
    document.getElementById('scanRepairsBtn').addEventListener('click', async () => {
        try {
            const result = await window.api.scanRepairs();
            alert(`Scanned ${result.scanned} pages; ${result.pending} pending.`);
            await loadRepairs();
        } catch (error) { alert('Scan failed: ' + error.message); }
    });
    
    // Retry all failed button
    const retryAllBtn = document.getElementById('retryAllBtn');
    if (retryAllBtn) {
        retryAllBtn.addEventListener('click', retryAllFailed);
    }

    // Initial load
    loadPages();
    loadRepairs();

    async function loadRepairs() {
        try {
            const response = await window.api.getRepairs(repairStatusFilter.value);
            repairsTable.innerHTML = response.repairs.length ? `
                <div class="table-responsive"><table class="table table-sm table-hover">
                <thead><tr><th>ID</th><th>URL</th><th>Status</th><th>Reasons</th><th></th></tr></thead>
                <tbody>${response.repairs.map(item => `<tr>
                    <td>${item.page_id}</td><td>${escapeHtml(item.url || 'Missing page')}</td>
                    <td><span class="badge ${item.repair_status === 'resolved' ? 'bg-success' : 'bg-warning text-dark'}">${escapeHtml(item.repair_status)}</span></td>
                    <td>${item.reasons.map(reason => `<span class="badge bg-warning text-dark me-1" title="${escapeHtml(reason.detail)}">${escapeHtml(reason.code)}</span>`).join('')}</td>
                    <td><button class="btn btn-sm btn-outline-primary" onclick="showRepairDetail(${item.page_id})">Repair</button></td>
                </tr>`).join('')}</tbody></table></div>` : '<div class="alert alert-success mb-0">No pending repairs.</div>';
        } catch (error) {
            repairsTable.innerHTML = `<div class="alert alert-danger mb-0">${escapeHtml(error.message)}</div>`;
        }
    }

    async function loadPages() {
        showLoading();

        try {
            const params = {
                limit: pageSize,
                offset: currentPage * pageSize,
                status: statusFilter.value,
                sort: sortBy.value,
                order: sortOrder.value
            };

            const response = await window.api.getPages(params);
            displayPages(response);
            displayPagination(response);

        } catch (error) {
            displayError(error.message);
        } finally {
            hideLoading();
        }
    }

    function showLoading() {
        refreshSpinner.classList.remove('d-none');
        pagesTable.classList.add('loading');
    }

    function hideLoading() {
        refreshSpinner.classList.add('d-none');
        pagesTable.classList.remove('loading');
    }

    function displayPages(response) {
        if (!response.pages || response.pages.length === 0) {
            pagesTable.innerHTML = `
                <div class="alert alert-info">
                    <h6>No pages found</h6>
                    <p class="mb-0">No pages match the current filter criteria.</p>
                </div>
            `;
            return;
        }

        const tableHtml = `
            <div class="table-responsive">
                <table class="table table-hover pages-table">
                    <thead class="table-light">
                        <tr>
                            <th>ID</th>
                            <th>URL</th>
                            <th>Title</th>
                            <th>Status</th>
                            <th>Created</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${response.pages.map(page => createPageRowHtml(page)).join('')}
                    </tbody>
                </table>
            </div>
        `;

        pagesTable.innerHTML = tableHtml;
    }

    function createPageRowHtml(page) {
        const statusClass = `status-${page.status}`;
        const statusText = page.status.charAt(0).toUpperCase() + page.status.slice(1);

        return `
            <tr>
                <td>${page.id}</td>
                <td>
                    <a href="${escapeHtml(page.url)}" target="_blank" class="page-url" title="${escapeHtml(page.url)}">
                        ${escapeHtml(page.url)}
                    </a>
                </td>
                <td class="page-title" title="${escapeHtml(page.title || 'Untitled')}">
                    ${escapeHtml(page.title || 'Untitled')}
                </td>
                <td>
                    <span class="badge status-badge ${statusClass}">
                        ${statusText}
                    </span>
                </td>
                <td>${formatDate(page.created_at)}</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary me-1" onclick="showPageDetail(${page.id})">
                        View
                    </button>
                    ${page.status === 'failed' ? `
                        <button class="btn btn-sm btn-outline-warning me-1" onclick="retryPage(${page.id})">
                            Retry
                        </button>
                    ` : ''}
                    ${page.has_json_file ? `
                        <button class="btn btn-sm btn-outline-info" onclick="window.api.openJsonInNewWindow(${page.id})" title="View JSON Data">
                            📄
                        </button>
                    ` : ''}
                </td>
            </tr>
        `;
    }

    function displayPagination(response) {
        const totalPages = Math.ceil(response.total / pageSize);
        
        if (totalPages <= 1) {
            pagination.innerHTML = '';
            return;
        }

        let paginationHtml = '<nav><ul class="pagination justify-content-center">';

        // Previous button
        paginationHtml += `
            <li class="page-item ${currentPage === 0 ? 'disabled' : ''}">
                <button class="page-link" onclick="changePage(${currentPage - 1})" ${currentPage === 0 ? 'disabled' : ''}>
                    Previous
                </button>
            </li>
        `;

        // Page numbers
        const startPage = Math.max(0, currentPage - 2);
        const endPage = Math.min(totalPages - 1, currentPage + 2);

        for (let i = startPage; i <= endPage; i++) {
            paginationHtml += `
                <li class="page-item ${i === currentPage ? 'active' : ''}">
                    <button class="page-link" onclick="changePage(${i})">${i + 1}</button>
                </li>
            `;
        }

        // Next button
        paginationHtml += `
            <li class="page-item ${currentPage >= totalPages - 1 ? 'disabled' : ''}">
                <button class="page-link" onclick="changePage(${currentPage + 1})" ${currentPage >= totalPages - 1 ? 'disabled' : ''}>
                    Next
                </button>
            </li>
        `;

        paginationHtml += '</ul></nav>';
        pagination.innerHTML = paginationHtml;
    }

    function displayError(message) {
        pagesTable.innerHTML = `
            <div class="alert alert-danger">
                <h6>Error Loading Pages</h6>
                <p class="mb-0">${escapeHtml(message)}</p>
            </div>
        `;
    }

    // Global functions for pagination and page details
    window.changePage = function(page) {
        currentPage = page;
        loadPages();
    };

    window.showPageDetail = async function(pageId) {
        try {
            const page = await window.api.getPageDetail(pageId);
            displayPageDetailModal(page);
        } catch (error) {
            alert('Error loading page details: ' + error.message);
        }
    };
    
    window.retryPage = async function(pageId) {
        if (!confirm('Are you sure you want to retry processing this page?')) {
            return;
        }
        
        try {
            const result = await window.api.retryPage(pageId);
            alert(`Retry started: ${result.message}`);
            loadPages(); // Refresh the page list
        } catch (error) {
            alert('Error retrying page: ' + error.message);
        }
    };

    window.showRepairDetail = async function(pageId) {
        try {
            const [page, repair] = await Promise.all([
                window.api.getPageDetail(pageId), window.api.getPageRepair(pageId)
            ]);
            displayPageDetailModal(page, repair);
        } catch (error) { alert('Error loading repair details: ' + error.message); }
    };

    window.saveRepairUrl = async function(pageId) {
        const input = document.getElementById('repairUrlInput');
        const currentUrl = decodeURIComponent(input.dataset.currentUrl);
        const newUrl = input.value.trim();
        if (newUrl === currentUrl) return;
        if (!confirm(`Change URL?\nBefore: ${currentUrl}\nAfter: ${newUrl}\n\nThis does not start reprocessing.`)) return;
        try {
            await window.api.updatePageUrl(pageId, currentUrl, newUrl);
            await window.showRepairDetail(pageId);
            await Promise.all([loadPages(), loadRepairs()]);
        } catch (error) { alert('URL update failed: ' + error.message); }
    };

    window.startRepair = async function(pageId) {
        const step = document.getElementById('repairStartStep').value;
        if (!confirm(`Start reprocessing from ${step}?`)) return;
        try {
            await window.api.reprocessPage(pageId, step);
            pollRepair(pageId);
        } catch (error) { alert('Reprocessing failed: ' + error.message); }
    };

    async function pollRepair(pageId) {
        const timer = setInterval(async () => {
            try {
                const repair = await window.api.getPageRepair(pageId);
                if (!repair.latest_job || ['succeeded', 'failed'].includes(repair.latest_job.status)) {
                    clearInterval(timer);
                    await Promise.all([loadPages(), loadRepairs()]);
                }
                if (repair.latest_job && ['succeeded', 'failed'].includes(repair.latest_job.status)) {
                    await window.showRepairDetail(pageId);
                }
            } catch (_) { clearInterval(timer); }
        }, 2000);
    }
    
    async function retryAllFailed() {
        if (!confirm('Are you sure you want to retry all failed pages?')) {
            return;
        }
        
        try {
            const result = await window.api.retryAllFailed();
            alert(`Batch retry started: ${result.message}`);
            loadPages(); // Refresh the page list
        } catch (error) {
            alert('Error retrying failed pages: ' + error.message);
        }
    }

    function displayPageDetailModal(page, repair = null) {
        const keywords = Array.isArray(page.keywords) ? page.keywords : 
                        (typeof page.keywords === 'string' ? JSON.parse(page.keywords || '[]') : []);
        
        const keywordBadges = keywords.map(keyword => 
            `<span class="badge bg-secondary me-1 mb-1">${escapeHtml(keyword)}</span>`
        ).join('');

        const modalContent = `
            <div class="row">
                <div class="col-12">
                    <h6>Basic Information</h6>
                    <table class="table table-sm">
                        <tr><th width="120">ID:</th><td>${page.id}</td></tr>
                        <tr><th>URL:</th><td><a href="${escapeHtml(page.url)}" target="_blank">${escapeHtml(page.url)}</a></td></tr>
                        <tr><th>Title:</th><td>${escapeHtml(page.title || 'Untitled')}</td></tr>
                        <tr><th>Status:</th><td><span class="badge status-${page.status}">${page.status}</span></td></tr>
                        <tr><th>Created:</th><td>${formatDate(page.created_at)}</td></tr>
                        <tr><th>Updated:</th><td>${formatDate(page.updated_at)}</td></tr>
                        ${page.has_json_file ? `
                            <tr><th>Raw Data:</th><td>
                                <button class="btn btn-sm btn-outline-info" onclick="window.api.openJsonInNewWindow(${page.id})">
                                    📄 View JSON Data
                                </button>
                            </td></tr>
                        ` : ''}
                    </table>
                </div>
            </div>
            
            ${page.memo ? `
                <div class="row mt-3">
                    <div class="col-12">
                        <h6>Memo</h6>
                        <div class="alert alert-info">
                            ${escapeHtml(page.memo)}
                        </div>
                    </div>
                </div>
            ` : ''}
            
            ${page.error_message ? `
                <div class="row mt-3">
                    <div class="col-12">
                        <h6>Error Details</h6>
                        <div class="alert alert-danger">
                            ${escapeHtml(page.error_message)}
                            ${page.last_success_step ? `
                                <hr class="my-2">
                                <small><strong>Last Success Step:</strong> ${escapeHtml(page.last_success_step)}</small>
                            ` : ''}
                        </div>
                    </div>
                </div>
            ` : ''}
            
            ${page.summary ? `
                <div class="row mt-3">
                    <div class="col-12">
                        <h6>Summary</h6>
                        <p>${escapeHtml(page.summary)}</p>
                    </div>
                </div>
            ` : ''}
            
            ${keywords.length > 0 ? `
                <div class="row mt-3">
                    <div class="col-12">
                        <h6>Keywords</h6>
                        <div>${keywordBadges}</div>
                    </div>
                </div>
            ` : ''}
            
            ${page.has_json_file ? `
                <div class="row mt-3">
                    <div class="col-12">
                        <h6>Actions</h6>
                        <button class="btn btn-outline-info" onclick="window.api.openJsonInNewWindow(${page.id})">
                            📄 View Raw JSON Data
                        </button>
                    </div>
                </div>
            ` : ''}

            ${repair ? `<div class="row mt-3"><div class="col-12">
                <h6>Repair</h6>
                <div class="mb-2"><label class="form-label">URL</label>
                    <div class="input-group"><input id="repairUrlInput" class="form-control" data-current-url="${encodeURIComponent(page.url)}" value="${escapeHtml(page.url)}">
                    <button class="btn btn-outline-warning" onclick="saveRepairUrl(${page.id})">Review & Save</button></div>
                </div>
                <p><strong>Stored JSON:</strong> ${repair.json_validation.valid ? 'Valid' : 'Invalid'} ·
                   <strong>Weaviate:</strong> ${repair.weaviate_registered === null ? 'Unavailable' : (repair.weaviate_registered ? 'Registered' : 'Missing')}</p>
                <div class="mb-2">${repair.reasons.map(reason => `<div class="alert alert-warning py-1 mb-1"><strong>${escapeHtml(reason.code)}</strong>: ${escapeHtml(reason.detail)}</div>`).join('')}</div>
                <div class="input-group"><select class="form-select" id="repairStartStep">
                    <option value="download">Jina download</option><option value="llm">LLM processing</option><option value="vectorize">Weaviate registration</option>
                </select><button class="btn btn-warning" onclick="startRepair(${page.id})">Start Repair</button></div>
                ${repair.latest_job ? `<small class="d-block mt-2">Job #${repair.latest_job.id}: ${escapeHtml(repair.latest_job.status)}${repair.latest_job.error_message ? ' — ' + escapeHtml(repair.latest_job.error_message) : ''}</small>` : ''}
            </div></div>` : ''}
        `;

        document.getElementById('pageDetailContent').innerHTML = modalContent;
        const modalElement = document.getElementById('pageDetailModal');
        bootstrap.Modal.getOrCreateInstance(modalElement).show();
    }

    function escapeHtml(text) {
        return String(text).replace(/[&<>"']/g, character => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        })[character]);
    }

    function formatDate(dateString) {
        if (!dateString) return 'Unknown';
        try {
            const date = new Date(dateString);
            return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
        } catch {
            return dateString;
        }
    }
});
