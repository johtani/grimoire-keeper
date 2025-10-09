// API Client for Grimoire Keeper

class ApiClient {
    constructor() {
        this.baseUrl = 'http://localhost:8000';
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

            return await response.json();
        } catch (error) {
            console.error('API Request failed:', error);
            throw error;
        }
    }

    // Search API
    async search(query, vectorName = 'content_vector', limit = 5, filters = {}) {
        return this.request('/api/v1/search', {
            method: 'POST',
            body: JSON.stringify({
                query,
                vector_name: vectorName,
                limit: parseInt(limit),
                filters
            })
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

    // Health Check
    async healthCheck() {
        try {
            await this.request('/health');
            return true;
        } catch {
            return false;
        }
    }
}

// Global API client instance
window.api = new ApiClient();