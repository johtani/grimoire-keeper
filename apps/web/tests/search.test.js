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
                async search() {
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
