const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const apiSource = fs.readFileSync(
    path.join(__dirname, '..', 'static', 'js', 'api.js'),
    'utf8'
);

function createApiClient(fetch) {
    const context = {
        console: { error() {} },
        fetch,
        URLSearchParams,
        window: {}
    };
    vm.createContext(context);
    vm.runInContext(`${apiSource}\nthis.ApiClientForTest = ApiClient;`, context);
    return new context.ApiClientForTest();
}

function errorResponse(status, statusText, json) {
    return {
        ok: false,
        status,
        statusText,
        json
    };
}

for (const status of [404, 409, 422]) {
    test(`uses the common API error message for HTTP ${status}`, async () => {
        const client = createApiClient(async () => errorResponse(
            status,
            'Error',
            async () => ({
                error: { code: 'api_error', message: `API message ${status}` }
            })
        ));

        await assert.rejects(
            client.request('/api/v1/test'),
            { message: `API message ${status}` }
        );
    });
}

test('prefers the common API error message over FastAPI detail', async () => {
    const client = createApiClient(async () => errorResponse(
        409,
        'Conflict',
        async () => ({
            error: { code: 'conflict', message: 'Common error message' },
            detail: 'Legacy detail'
        })
    ));

    await assert.rejects(
        client.request('/api/v1/test'),
        { message: 'Common error message' }
    );
});

test('falls back to FastAPI detail', async () => {
    const client = createApiClient(async () => errorResponse(
        503,
        'Service Unavailable',
        async () => ({ detail: 'Weaviate is not available' })
    ));

    await assert.rejects(
        client.request('/api/v1/test'),
        { message: 'Weaviate is not available' }
    );
});

test('falls back to the HTTP status for a non-JSON response', async () => {
    const client = createApiClient(async () => errorResponse(
        502,
        'Bad Gateway',
        async () => { throw new SyntaxError('Unexpected token'); }
    ));

    await assert.rejects(
        client.request('/api/v1/test'),
        { message: 'HTTP 502: Bad Gateway' }
    );
});
