// API Client for Grimoire Keeper

const API_ERROR_MESSAGES = {
    bad_request: 'リクエストを処理できませんでした。',
    unauthorized: '認証が必要です。',
    forbidden: 'この操作は許可されていません。',
    not_found: '対象が見つかりませんでした。',
    method_not_allowed: 'この操作は利用できません。',
    conflict: '現在の状態では操作を実行できません。',
    validation_error: '入力内容を確認してください。',
    service_unavailable: 'サービスを一時的に利用できません。',
    internal_error: 'サーバーでエラーが発生しました。'
};

class ApiError extends Error {
    constructor(code, message, requestId, status) {
        const requestInfo = requestId ? ` (リクエストID: ${requestId})` : '';
        super(`${message}${requestInfo}`);
        this.name = 'ApiError';
        this.code = code;
        this.requestId = requestId;
        this.status = status;
    }
}

class ApiClient {
    constructor() {
        // nginxプロキシ経由でAPIにアクセス
        this.baseUrl = '';
    }

    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const config = {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        };

        try {
            const response = await fetch(url, config);
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                const apiError = errorData?.error || {};
                const errorCode = apiError.code || 'api_error';
                const errorMessage = API_ERROR_MESSAGES[errorCode]
                    || apiError.message
                    || 'APIリクエストに失敗しました。';
                throw new ApiError(
                    errorCode,
                    errorMessage,
                    apiError.request_id,
                    response.status
                );
            }

            // Content-Typeをチェックしてレスポンスを適切に処理
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            } else {
                return await response.text();
            }
        } catch (error) {
            console.error('API Request failed:', error);
            throw error;
        }
    }

    // Search API
    async search(query, vectorName = 'content_vector', limit = 5, filters = {}, excludeKeywords = null) {
        const requestBody = {
            query,
            vector_name: vectorName,
            limit: parseInt(limit),
            filters
        };
        
        if (excludeKeywords && excludeKeywords.length > 0) {
            requestBody.exclude_keywords = excludeKeywords;
        }
        
        return this.request('/api/v1/search', {
            method: 'POST',
            body: JSON.stringify(requestBody)
        });
    }

    // Pages API
    async getPages(params = {}) {
        const queryParams = new URLSearchParams();
        
        if (params.limit) queryParams.append('limit', params.limit);
        if (params.offset) queryParams.append('offset', params.offset);
        if (params.sort) queryParams.append('sort', params.sort);
        if (params.order) queryParams.append('order', params.order);
        if (params.status) queryParams.append('status', params.status);

        const endpoint = `/api/v1/pages${queryParams.toString() ? '?' + queryParams.toString() : ''}`;
        return this.request(endpoint);
    }

    async getPageDetail(pageId) {
        return this.request(`/api/v1/pages/${pageId}`);
    }

    async getRepairs(status = 'pending') {
        return this.request(`/api/v1/repairs?status=${encodeURIComponent(status)}`);
    }

    async importRepairs() {
        return this.request('/api/v1/repairs/import', { method: 'POST' });
    }

    async scanRepairs() {
        return this.request('/api/v1/repairs/scan', { method: 'POST' });
    }

    async getPageRepair(pageId) {
        return this.request(`/api/v1/pages/${pageId}/repair`);
    }

    async updatePageUrl(pageId, currentUrl, newUrl) {
        return this.request(`/api/v1/pages/${pageId}/url`, {
            method: 'PATCH',
            body: JSON.stringify({ current_url: currentUrl, new_url: newUrl })
        });
    }

    async deleteRepairPage(pageId) {
        return this.request(`/api/v1/pages/${pageId}`, { method: 'DELETE' });
    }

    async reprocessPage(pageId, fromStep) {
        return this.request(`/api/v1/reprocess/${pageId}`, {
            method: 'POST', body: JSON.stringify({ from_step: fromStep })
        });
    }
    
    async getPageJson(pageId) {
        return this.request(`/api/v1/pages/${pageId}/json`);
    }
    
    // Retry API
    async retryPage(pageId) {
        return this.request(`/api/v1/retry/${pageId}`, {
            method: 'POST'
        });
    }
    
    async retryAllFailed(options = {}) {
        return this.request('/api/v1/retry-failed', {
            method: 'POST',
            body: JSON.stringify(options)
        });
    }

    // Process URL API
    async processUrl(url, memo = '') {
        return this.request('/api/v1/process-url', {
            method: 'POST',
            body: JSON.stringify({ url, memo })
        });
    }

    async getProcessStatus(pageId) {
        return this.request(`/api/v1/process-status/${pageId}`);
    }
    
    // Health Check
    async healthCheck() {
        try {
            await this.request('/api/v1/health');
            return true;
        } catch {
            return false;
        }
    }

    async getSystemInfo() {
        return this.request('/api/v1/system-info');
    }
    
    // JSON file display helper
    openJsonInNewWindow(pageId) {
        const url = `${this.baseUrl}/api/v1/pages/${pageId}/json`;
        window.open(url, '_blank', 'width=800,height=600,scrollbars=yes,resizable=yes');
    }
}

// Global API client instance
window.api = new ApiClient();
