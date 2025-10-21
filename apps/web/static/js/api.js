// API Client for Grimoire Keeper

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
                throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
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
            await this.request('/health');
            return true;
        } catch {
            return false;
        }
    }
    
    // JSON file display helper
    openJsonInNewWindow(pageId) {
        const url = `${this.baseUrl}/api/v1/pages/${pageId}/json`;
        window.open(url, '_blank', 'width=800,height=600,scrollbars=yes,resizable=yes');
    }
}

// Global API client instance
window.api = new ApiClient();