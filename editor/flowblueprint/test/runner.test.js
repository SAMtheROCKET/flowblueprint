'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const path = require('node:path');
const {
    FORMATS, LEVELS, VIEWS, modularizeArguments, runPython, ensureTrusted, isSupportedInput, outputPath, drawArguments,
} = require('../runner');
const manifest = require('../package.json');

test('untrusted workspaces cannot run Python', () => {
    assert.throws(() => ensureTrusted({ workspace: { isTrusted: false } }), /Trust/);
    ensureTrusted({ workspace: { isTrusted: true } });
});

test('runner uses isolated Python, argument arrays and no shell', async () => {
    let actual;
    const source = 'C:\\example space\\$(bad);file.py';
    const result = await runPython('C:\\python path\\python.exe', 'flowblueprint',
        [source, '--output', 'x.svg'], '', (executable, args, options) => {
            actual = { executable, args, options };
            const process = new EventEmitter();
            process.stdout = new EventEmitter(); process.stdout.setEncoding = () => {};
            process.stderr = new EventEmitter(); process.stderr.setEncoding = () => {};
            process.stdin = new EventEmitter();
            process.stdin.end = () => {
                queueMicrotask(() => {
                    process.stdout.emit('data', 'wrote x.svg (4 blocks)');
                    process.emit('close', 0);
                });
            };
            process.kill = () => {};
            return process;
        });
    assert.equal(actual.executable, 'C:\\python path\\python.exe');
    assert.equal(actual.options.shell, false);
    assert.equal(actual.options.windowsHide, true);
    assert.deepEqual(actual.args, ['-I', '-X', 'utf8', '-m', 'flowblueprint', source, '--output', 'x.svg']);
    assert.equal(result.code, 0);
    assert.match(result.output, /wrote x\.svg/);
});

test('only FlowBlueprint can be run', () => {
    assert.throws(() => runPython('python', 'refactrail', []), /Unsupported/);
    assert.throws(() => runPython('python', 'untrusted', []), /Unsupported/);
});

test('scripts, notebooks and folders are drawable', () => {
    assert.ok(isSupportedInput('C:\\work\\report.py', false));
    assert.ok(isSupportedInput('/work/Analysis.IPYNB', false));
    assert.ok(isSupportedInput('/work/project', true));
    assert.ok(!isSupportedInput('/work/notes.txt', false));
    assert.ok(!isSupportedInput('/work/stub.pyi', false));
});

test('output goes next to the file, or into the folder', () => {
    const script = path.join('work space', 'report.v2.py');
    assert.equal(outputPath(script, false, 'drawio'), path.join('work space', 'report.v2.drawio'));
    assert.equal(outputPath(script, false, 'md'), path.join('work space', 'report.v2.md'));
    assert.equal(outputPath('project', true, 'html'), path.join('project', 'architecture.html'));
    assert.equal(outputPath(script, false, 'png'), path.join('work space', 'report.v2.png'));
    assert.equal(outputPath(script, false, 'drawio.png'), path.join('work space', 'report.v2.drawio.png'));
    assert.throws(() => outputPath(script, false, 'pdf'), /Format/);
});

test('an existing output is replaced only when force is given', () => {
    assert.deepEqual(drawArguments('a b.py', 'a b.svg', 'detailed', false),
        ['a b.py', '--output', 'a b.svg', '--level', 'detailed']);
    assert.deepEqual(drawArguments('a.py', 'a.svg', 'summary', true),
        ['a.py', '--output', 'a.svg', '--level', 'summary', '--force']);
    assert.throws(() => drawArguments('a.py', 'a.svg', 'everything', false), /Level/);
});

test('the manifest offers the same formats and levels as the runner', () => {
    const properties = manifest.contributes.configuration.properties;
    assert.deepEqual(properties['flowblueprint.defaultFormat'].enum, FORMATS);
    assert.deepEqual(properties['flowblueprint.level'].enum, LEVELS);
    assert.equal(properties['flowblueprint.level'].default, 'full');
    assert.match(manifest.toolVersion, new RegExp(`^${manifest.version.replace(/\./g, '\\.')}`));
    assert.deepEqual(manifest.contributes.commands.map(item => item.command),
        ['flowblueprint.drawFile', 'flowblueprint.drawFolder',
            'flowblueprint.modularizeFile', 'flowblueprint.modularizeFolder']);
    assert.deepEqual(properties['flowblueprint.view'].enum, VIEWS);
    assert.equal(properties['flowblueprint.view'].default, 'reference');
});

test('reference mode and new-copy workflows use explicit safe arguments', () => {
    assert.deepEqual(drawArguments('a.py', 'a.drawio', 'full', false, 'reference'),
        ['a.py', '--output', 'a.drawio', '--level', 'full', '--view', 'reference']);
    assert.throws(() => drawArguments('a.py', 'a.svg', 'full', false, 'bad'), /view/);
    assert.deepEqual(modularizeArguments('work space/a.py', 'draft space', true, true),
        ['work space/a.py', '--pipeline-to', 'draft space', '--externalize-sql', '--png']);
    assert.deepEqual(modularizeArguments('repo', 'draft', false, false),
        ['repo', '--pipeline-to', 'draft']);
});
