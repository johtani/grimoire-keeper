document.addEventListener('DOMContentLoaded', loadSystemInfo);

async function loadSystemInfo() {
    const container = document.getElementById('systemInfo');
    try {
        const info = await window.api.getSystemInfo();
        container.innerHTML = renderSystemInfo(info);
    } catch (error) {
        container.innerHTML = `
            <div class="alert alert-danger">
                システム情報を取得できませんでした: ${escapeHtml(error.message)}
            </div>`;
    }
}

function renderSystemInfo(info) {
    const services = Array.isArray(info.services) ? info.services : [];
    const serviceRows = services.map(service => `
        <tr>
            <th scope="row">${escapeHtml(service.name)}</th>
            <td>${escapeHtml(service.purpose)}</td>
            <td>${service.model ? `<code>${escapeHtml(service.model)}</code>` : '—'}</td>
        </tr>`).join('');

    return `
        <div class="card mb-4">
            <div class="card-header"><h2 class="h5 mb-0">外部サービス / LLM</h2></div>
            <div class="card-body table-responsive">
                <table class="table mb-0">
                    <thead><tr><th>サービス</th><th>用途</th><th>モデル</th></tr></thead>
                    <tbody>${serviceRows}</tbody>
                </table>
            </div>
        </div>
        ${renderWeaviate(info.weaviate)}`;
}

function renderWeaviate(weaviate) {
    if (!weaviate || weaviate.status !== 'available') {
        const message = weaviate ? weaviate.message : 'Weaviate schema is unavailable';
        return `
            <div class="card">
                <div class="card-header"><h2 class="h5 mb-0">Weaviate Vectorizer</h2></div>
                <div class="card-body">
                    <div class="alert alert-warning mb-0">${escapeHtml(message)}</div>
                </div>
            </div>`;
    }

    const collections = weaviate.collections.map(collection => `
        <section class="mb-4">
            <h3 class="h6"><code>${escapeHtml(collection.name)}</code></h3>
            <div class="table-responsive">
                <table class="table table-sm mb-0">
                    <thead><tr><th>Named vector</th><th>Vectorizer</th><th>モデル設定</th></tr></thead>
                    <tbody>${collection.vectors.map(vector => `
                        <tr>
                            <th scope="row"><code>${escapeHtml(vector.name)}</code></th>
                            <td><code>${escapeHtml(vector.vectorizer)}</code></td>
                            <td>${renderModel(vector)}</td>
                        </tr>`).join('')}</tbody>
                </table>
            </div>
        </section>`).join('');

    return `
        <div class="card">
            <div class="card-header d-flex justify-content-between align-items-center">
                <h2 class="h5 mb-0">Weaviate Vectorizer</h2>
                <span class="badge bg-success">available</span>
            </div>
            <div class="card-body">${collections}</div>
        </div>`;
}

function renderModel(vector) {
    if (vector.uses_module_default) {
        return '<span class="text-muted">Weaviate / モジュール既定値</span>';
    }
    return `<code>${escapeHtml(JSON.stringify(vector.model))}</code>`;
}

function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = String(value ?? '');
    return div.innerHTML;
}
