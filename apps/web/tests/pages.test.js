const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const pagesSource = fs.readFileSync(
    path.join(__dirname, '..', 'static', 'js', 'pages.js'),
    'utf8'
);

function createElement() {
    return {
        addEventListener() {},
        classList: { add() {}, remove() {} },
        dataset: {},
        innerHTML: '',
        value: 'all'
    };
}

function createPagesContext(confirmResult) {
    const elements = Object.fromEntries([
        'statusFilter', 'sortBy', 'sortOrder', 'refreshBtn', 'refreshSpinner',
        'pagesTable', 'pagination', 'repairsTable', 'repairStatusFilter',
        'importRepairsBtn', 'scanRepairsBtn', 'retryAllBtn', 'pageDetailModal',
        'pageDetailContent'
    ].map(id => [id, createElement()]));
    elements.pageDetailModal.dataset.pageUrl = 'https://example.com/article';

    const deleteCalls = [];
    const confirmations = [];
    let modalHidden = false;
    const context = {
        alert() {},
        bootstrap: {
            Modal: {
                getOrCreateInstance() {
                    return { hide() { modalHidden = true; }, show() {} };
                }
            }
        },
        clearInterval() {},
        confirm(message) {
            confirmations.push(message);
            return confirmResult;
        },
        document: {
            addEventListener(event, callback) {
                if (event === 'DOMContentLoaded') callback();
            },
            getElementById(id) { return elements[id]; }
        },
        setInterval() { return 1; },
        window: {
            api: {
                async deletePage(pageId) { deleteCalls.push(pageId); },
                async getPages() { return { pages: [], total: 0 }; },
                async getRepairs() { return { repairs: [] }; }
            }
        }
    };
    vm.createContext(context);
    vm.runInContext(pagesSource, context);
    return { elements, confirmations, context, deleteCalls, get modalHidden() { return modalHidden; } };
}

test('confirms URL and all affected stores before deleting a page', async () => {
    const state = createPagesContext(true);

    await state.context.window.deletePage(267);

    assert.deepEqual(state.deleteCalls, [267]);
    assert.equal(state.modalHidden, true);
    assert.match(state.confirmations[0], /https:\/\/example\.com\/article/);
    assert.match(state.confirmations[0], /SQLite/);
    assert.match(state.confirmations[0], /stored JSON/);
    assert.match(state.confirmations[0], /Weaviate/);
    assert.match(state.confirmations[0], /cannot be undone/);
});

test('does not call the deletion API when confirmation is cancelled', async () => {
    const state = createPagesContext(false);

    await state.context.window.deletePage(267);

    assert.deepEqual(state.deleteCalls, []);
    assert.equal(state.modalHidden, false);
});


for (const [status, jobStatus, disabled] of [
    ['queued', null, true],
    ['processing', null, true],
    ['deleting', null, true],
    ['failed', 'queued', true],
    ['failed', 'running', true],
    ['failed', 'failed', false],
    ['succeeded', 'succeeded', false],
]) {
    test(`URL editing for page ${status} and job ${jobStatus}`, async () => {
        const state = createPagesContext(true);
        state.context.window.api.getPageDetail = async () => ({
            id: 1, url: 'https://example.com/old', status, keywords: []
        });
        state.context.window.api.getPageRepair = async () => ({
            json_validation: { valid: true }, reasons: [],
            latest_job: jobStatus ? { id: 1, status: jobStatus } : null
        });
        await state.context.window.showRepairDetail(1);
        const html = state.elements.pageDetailContent.innerHTML;
        assert.equal(/id="repairUrlInput" disabled/.test(html), disabled);
        assert.equal(/onclick="saveRepairUrl\(1\)" disabled/.test(html), disabled);
        const updates = [];
        state.context.window.api.updatePageUrl = async (...args) => updates.push(args);
        state.elements.repairUrlInput = {
            disabled,
            dataset: { currentUrl: encodeURIComponent('https://example.com/old') },
            value: 'https://example.com/new'
        };
        await state.context.window.saveRepairUrl(1);
        assert.equal(updates.length, disabled ? 0 : 1);
        if (!disabled) assert.deepEqual(updates[0], [
            1, 'https://example.com/old', 'https://example.com/new'
        ]);
    });
}
