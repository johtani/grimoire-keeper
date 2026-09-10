const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const staticDirectory = path.join(__dirname, '..', 'static');
const htmlFiles = fs.readdirSync(staticDirectory)
    .filter(file => file.endsWith('.html'));

function assetReferences(html) {
    return [
        ...html.matchAll(/<link\b[^>]*\bhref=["']([^"']+)["']/gi),
        ...html.matchAll(/<script\b[^>]*\bsrc=["']([^"']+)["']/gi)
    ].map(match => match[1]);
}

test('HTML pages load stylesheets and scripts only from local assets', () => {
    for (const htmlFile of htmlFiles) {
        const html = fs.readFileSync(path.join(staticDirectory, htmlFile), 'utf8');
        for (const reference of assetReferences(html)) {
            assert.doesNotMatch(reference, /^https?:\/\//i, `${htmlFile}: ${reference}`);
            assert.ok(
                fs.existsSync(path.resolve(staticDirectory, reference)),
                `${htmlFile}: missing ${reference}`
            );
        }
    }
});

test('Bootstrap 5.3.0 distribution and license are vendored together', () => {
    const bootstrapDirectory = path.join(staticDirectory, 'vendor', 'bootstrap-5.3.0');
    const expectedFiles = [
        'css/bootstrap.min.css',
        'js/bootstrap.bundle.min.js',
        'LICENSE'
    ];

    for (const file of expectedFiles) {
        assert.ok(fs.existsSync(path.join(bootstrapDirectory, file)), `missing ${file}`);
    }

    const css = fs.readFileSync(path.join(bootstrapDirectory, expectedFiles[0]), 'utf8');
    const javascript = fs.readFileSync(path.join(bootstrapDirectory, expectedFiles[1]), 'utf8');
    assert.match(css, /Bootstrap\s+v5\.3\.0/);
    assert.match(javascript, /Bootstrap\s+v5\.3\.0/);
});
