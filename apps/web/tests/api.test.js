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

for (const [status, code, expected] of [
    [404, 'not_found', '対象が見つかりませんでした。'],
    [409, 'conflict', '現在の状態では操作を実行できません。'],
    [422, 'validation_error', '入力内容を確認してください。']
]) {
    test(`uses the error code mapping for HTTP ${status}`, async () => {
        const client = createApiClient(async () => errorResponse(
            status,
            'Error',
            async () => ({
                error: { code, message: `API message ${status}` }
            })
        ));

        await assert.rejects(
            client.request('/api/v1/test'),
            { code, message: expected, status }
        );
    });
}

test('includes the request ID without exposing legacy detail', async () => {
    const client = createApiClient(async () => errorResponse(
        409,
        'Conflict',
        async () => ({
            error: {
                code: 'conflict',
                message: 'Common error message',
                request_id: 'request-1234'
            },
            detail: 'secret internal detail'
        })
    ));

    await assert.rejects(
        client.request('/api/v1/test'),
        {
            code: 'conflict',
            requestId: 'request-1234',
            message: '現在の状態では操作を実行できません。 (リクエストID: request-1234)'
        }
    );
});

test('does not display a legacy FastAPI detail', async () => {
    const client = createApiClient(async () => errorResponse(
        503,
        'Service Unavailable',
        async () => ({ detail: 'Weaviate is not available' })
    ));

    await assert.rejects(
        client.request('/api/v1/test'),
        { code: 'api_error', message: 'APIリクエストに失敗しました。' }
    );
});

test('uses a safe message for a non-JSON response', async () => {
    const client = createApiClient(async () => errorResponse(
        502,
        'Bad Gateway',
        async () => { throw new SyntaxError('Unexpected token'); }
    ));

    await assert.rejects(
        client.request('/api/v1/test'),
        { code: 'api_error', message: 'APIリクエストに失敗しました。' }
    );
});
