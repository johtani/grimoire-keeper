const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const searchSource = fs.readFileSync(
    path.join(__dirname, '..', 'static', 'js', 'search.js'),
    'utf8'
);

function createClassList(initialClasses = []) {
    const classes = new Set(initialClasses);
    return {
        add(className) {
            classes.add(className);
        },
        contains(className) {
            return classes.has(className);
        },
        remove(className) {
            classes.delete(className);
        }
    };
}

function createElement(value = '') {
    const listeners = {};
    return {
        classList: createClassList(),
        value,
        addEventListener(event, handler) {
            listeners[event] = handler;
        },
        listener(event) {
            return listeners[event];
        }
    };
}

function createSearchPage(searchResponse) {
    const documentListeners = {};
    let expandableTexts = [];
    let resultsHtml = '';
    const searchCalls = [];
    const elements = {
        dateFrom: createElement(),
        dateTo: createElement(),
        excludeKeywords: createElement(),
        keywordsFilter: createElement(),
        limit: createElement('10'),
        query: createElement('test query'),
        results: createElement(),
        searchForm: createElement(),
        searchSpinner: createElement(),
        urlFilter: createElement(),
        vectorName: createElement('content_vector')
    };

    Object.defineProperty(elements.results, 'innerHTML', {
        get() {
            return resultsHtml;
        },
        set(html) {
            resultsHtml = html;
            const matches = html.match(/class="expandable-text text-truncate-2 cursor-pointer"/g) || [];
            expandableTexts = matches.map(() => {
                const element = createElement();
                element.classList = createClassList([
                    'expandable-text',
                    'text-truncate-2',
                    'cursor-pointer'
                ]);
                return element;
            });
        }
    });

    const document = {
        addEventListener(event, handler) {
            documentListeners[event] = handler;
        },
        createElement() {
            let escapedText = '';
            return {
                set textContent(text) {
                    escapedText = text;
                },
                get innerHTML() {
                    return escapedText;
                }
            };
        },
        getElementById(id) {
            return elements[id];
        },
        querySelectorAll(selector) {
            assert.equal(selector, '.expandable-text');
            return expandableTexts;
        }
    };
    const context = {
        console: { error() {} },
        document,
        window: {
            api: {
                async search(...args) {
                    searchCalls.push(args);
                    return searchResponse;
                }
            }
        }
    };

    vm.createContext(context);
    vm.runInContext(searchSource, context);
    documentListeners.DOMContentLoaded();

    return {
        elements,
        searchCalls,
        getExpandableTexts: () => expandableTexts
    };
}

test('renders expandable summary and content without data-full-text', async () => {
    const page = createSearchPage({
        query: 'test query',
        results: [{
            chunk_id: 2,
            content: 'Full content',
            created_at: '2025-01-01T00:00:00Z',
            page_id: 1,
            score: 0.9,
            summary: 'Full summary',
            title: 'Test title',
            url: 'https://example.com'
        }]
    });

    await page.elements.searchForm.listener('submit')({ preventDefault() {} });

    assert.match(page.elements.results.innerHTML, /Full summary/);
    assert.match(page.elements.results.innerHTML, /Full content/);
    assert.doesNotMatch(page.elements.results.innerHTML, /data-full-text/);

    const expandableTexts = page.getExpandableTexts();
    assert.equal(expandableTexts.length, 2);
    for (const element of expandableTexts) {
        assert.equal(element.classList.contains('text-truncate-2'), true);
        element.listener('click')();
        assert.equal(element.classList.contains('text-truncate-2'), false);
        element.listener('click')();
        assert.equal(element.classList.contains('text-truncate-2'), true);
    }
});

for (const results of [[], [{ page_id: 1, title: 'title', url: 'https://example.com', score: 0.9 }]]) {
    test(`shows truncated search warning with ${results.length} results`, async () => {
        const page = createSearchPage({ query: 'test', results, truncated: true });
        await page.elements.searchForm.listener('submit')({ preventDefault() {} });
        assert.match(page.elements.results.innerHTML, /Results may be incomplete/);
        assert.doesNotMatch(page.elements.results.innerHTML, /No results found/);
    });
}

test('ordinary empty search does not show truncation warning', async () => {
    const page = createSearchPage({ results: [], truncated: false });
    await page.elements.searchForm.listener('submit')({ preventDefault() {} });
    assert.match(page.elements.results.innerHTML, /No results found/);
    assert.doesNotMatch(page.elements.results.innerHTML, /Results may be incomplete/);
});

for (const [zone, date, start, end] of [
    ['UTC', '2026-09-07', '2026-09-07T00:00:00.000Z', '2026-09-08T00:00:00.000Z'],
    ['Asia/Tokyo', '2026-09-07', '2026-09-06T15:00:00.000Z', '2026-09-07T15:00:00.000Z'],
    ['Asia/Tokyo', '2026-01-31', '2026-01-30T15:00:00.000Z', '2026-01-31T15:00:00.000Z'],
    ['Asia/Tokyo', '2026-12-31', '2026-12-30T15:00:00.000Z', '2026-12-31T15:00:00.000Z'],
    ['UTC', '2024-02-29', '2024-02-29T00:00:00.000Z', '2024-03-01T00:00:00.000Z'],
    ['America/New_York', '2026-03-08', '2026-03-08T05:00:00.000Z', '2026-03-09T04:00:00.000Z'],
    ['America/New_York', '2026-11-01', '2026-11-01T04:00:00.000Z', '2026-11-02T05:00:00.000Z']
]) {
    test(`sends inclusive calendar day ${date} in ${zone}`, async () => {
        const previousTZ = process.env.TZ;
        process.env.TZ = zone;
        try {
            const page = createSearchPage({ results: [] });
            page.elements.dateFrom.value = date;
            page.elements.dateTo.value = date;
            await page.elements.searchForm.listener('submit')({ preventDefault() {} });
            const filters = page.searchCalls[0][3];
            assert.equal(filters.date_from, start);
            assert.equal(filters.date_before, end);
            assert.equal(filters.date_to, undefined);
        } finally {
            if (previousTZ === undefined) delete process.env.TZ;
            else process.env.TZ = previousTZ;
        }
    });
}

for (const field of [null, 'dateFrom', 'dateTo']) {
    test(`supports optional date filter ${field}`, async () => {
        const page = createSearchPage({ results: [] });
        if (field) page.elements[field].value = '2026-09-07';
        await page.elements.searchForm.listener('submit')({ preventDefault() {} });
        const filters = page.searchCalls[0][3];
        assert.equal('date_from' in filters, field === 'dateFrom');
        assert.equal('date_before' in filters, field === 'dateTo');
    });
}

test('rejects reversed calendar dates before sending search', async () => {
    const page = createSearchPage({ results: [] });
    page.elements.dateFrom.value = '2026-09-08';
    page.elements.dateTo.value = '2026-09-07';
    await page.elements.searchForm.listener('submit')({ preventDefault() {} });
    assert.equal(page.searchCalls.length, 0);
    assert.match(page.elements.results.innerHTML, /Date From must not be later/);
    assert.equal(page.elements.searchSpinner.classList.contains('d-none'), true);
});
