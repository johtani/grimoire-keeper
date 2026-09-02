const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const registerSource = fs.readFileSync(
    path.join(__dirname, '..', 'static', 'js', 'register.js'),
    'utf8'
);

function createClassList(initialClasses = []) {
    const classes = new Set(initialClasses);
    return {
        add(...classNames) { classNames.forEach((name) => classes.add(name)); },
        contains(className) { return classes.has(className); },
        remove(...classNames) { classNames.forEach((name) => classes.delete(name)); }
    };
}

function createElement(value = '') {
    const attributes = {};
    const listeners = {};
    return {
        classList: createClassList(),
        className: '',
        disabled: false,
        innerHTML: '',
        style: {},
        textContent: '',
        value,
        addEventListener(event, handler) { listeners[event] = handler; },
        listener(event) { return listeners[event]; },
        reset() {},
        setAttribute(name, value) { attributes[name] = value; },
        getAttribute(name) { return attributes[name]; }
    };
}

function createRegisterManager(apiOverrides = {}) {
    const elements = {
        memo: createElement(),
        processingInfo: createElement(),
        progressBar: createElement(),
        recentPages: createElement(),
        registerForm: createElement(),
        resultAlert: createElement(),
        resultArea: createElement(),
        spinner: createElement(),
        statusText: createElement(),
        submitBtn: createElement(),
        url: createElement('https://example.com/article')
    };
    const intervalCallbacks = new Map();
    let nextIntervalId = 1;
    const api = {
        async getPageDetail() { return { status: 'queued' }; },
        async getPages() { return { pages: [] }; },
        async processUrl() { return { status: 'queued', page_id: 258 }; },
        ...apiOverrides
    };

    class ApiClient {
        constructor() { return api; }
    }

    const document = {
        addEventListener() {},
        createElement() { return createElement(); },
        getElementById(id) { return elements[id]; }
    };
    const context = {
        ApiClient,
        clearInterval(id) { intervalCallbacks.delete(id); },
        console: { error() {} },
        document,
        setInterval(callback) {
            const id = nextIntervalId++;
            intervalCallbacks.set(id, callback);
            return id;
        },
        setTimeout(callback) { callback(); }
    };
    vm.createContext(context);
    vm.runInContext(
        `${registerSource}\nthis.RegisterManagerForTest = RegisterManager;`,
        context
    );

    return {
        api,
        elements,
        intervalCallbacks,
        manager: new context.RegisterManagerForTest()
    };
}

test('starts polling when registration is queued', async () => {
    const { elements, intervalCallbacks, manager } = createRegisterManager();

    await manager.handleSubmit({ preventDefault() {} });

    assert.equal(manager.currentPageId, 258);
    assert.equal(intervalCallbacks.size, 1);
    assert.equal(elements.statusText.textContent, '処理待ちです...');
    assert.equal(elements.progressBar.style.width, '10%');
});

test('continues polling from queued through processing and stops on completion', async () => {
    const responses = [
        { status: 'queued', last_success_step: null },
        { status: 'processing', last_success_step: 'downloaded' },
        { status: 'processing', last_success_step: 'llm_processed' },
        { status: 'completed', last_success_step: 'completed' }
    ];
    const { elements, intervalCallbacks, manager } = createRegisterManager({
        async getPageDetail() { return responses.shift(); }
    });
    manager.currentPageId = 258;
    manager.startStatusCheck();
    const poll = [...intervalCallbacks.values()][0];

    await poll();
    assert.equal(intervalCallbacks.size, 1);
    await poll();
    assert.equal(elements.statusText.textContent, 'AI要約を生成中...');
    await poll();
    assert.equal(elements.statusText.textContent, 'ベクトル化処理中...');
    await poll();

    assert.equal(elements.statusText.textContent, '処理完了！');
    assert.equal(elements.progressBar.style.width, '100%');
    assert.equal(intervalCallbacks.size, 0);
    assert.equal(manager.currentPageId, null);
});

test('shows the failure reason and stops polling', () => {
    const { elements, intervalCallbacks, manager } = createRegisterManager();
    manager.currentPageId = 258;
    manager.startStatusCheck();

    manager.updateProcessingStatus({
        status: 'failed',
        error_message: 'Jina API request failed'
    });

    assert.equal(
        elements.statusText.textContent,
        '処理に失敗しました: Jina API request failed'
    );
    assert.equal(intervalCallbacks.size, 0);
});

for (const [status, expected] of [
    ['cancelled', '処理はキャンセルされました'],
    ['unexpected', '不明な処理状態です: unexpected']
]) {
    test(`stops polling for ${status}`, () => {
        const { elements, intervalCallbacks, manager } = createRegisterManager();
        manager.currentPageId = 258;
        manager.startStatusCheck();

        manager.updateProcessingStatus({ status });

        assert.equal(elements.statusText.textContent, expected);
        assert.equal(intervalCallbacks.size, 0);
    });
}
