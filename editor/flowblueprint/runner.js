'use strict';

const path = require('node:path');
const { spawn } = require('node:child_process');

const FORMATS = ['drawio', 'svg', 'html', 'md'];

function runPython(pythonPath, tool, argumentsList, input = '', spawnProcess = spawn) {
    if (tool !== 'flowblueprint') {
        throw new Error('Unsupported tool');
    }
    return new Promise((resolve, reject) => {
        const process = spawnProcess(pythonPath, ['-I', '-m', tool, ...argumentsList], {
            shell: false,
            windowsHide: true,
            env: { ...global.process.env, PYTHONNOUSERSITE: '1', PYTHONUTF8: '1' },
        });
        let output = '';
        let errors = '';
        let settled = false;
        // Whole projects take longer to draw than a single file.
        const timer = setTimeout(() => finish(new Error('Tool exceeded 180 seconds')), 180000);
        function finish(error, code) {
            if (settled) { return; }
            settled = true;
            clearTimeout(timer);
            if (error) { process.kill(); reject(error); }
            else { resolve({ code, output, errors }); }
        }
        function append(text, stderr) {
            if (stderr) { errors += text; } else { output += text; }
            if (Buffer.byteLength(output + errors, 'utf8') > 8 * 1024 * 1024) {
                finish(new Error('Tool output exceeded 8 MB'));
            }
        }
        process.stdout.setEncoding('utf8');
        process.stderr.setEncoding('utf8');
        process.stdout.on('data', text => append(text, false));
        process.stderr.on('data', text => append(text, true));
        process.on('error', error => finish(error));
        process.on('close', code => finish(null, code));
        process.stdin.on('error', () => {});
        process.stdin.end(input);
    });
}

function ensureTrusted(vscode) {
    if (!vscode.workspace.isTrusted) {
        throw new Error('Trust this workspace before running Python tools.');
    }
}

// A drawable input is a .py script, an .ipynb notebook or a folder.
function isSupportedInput(inputPath, isFolder) {
    return isFolder || ['.py', '.ipynb'].includes(path.extname(inputPath).toLowerCase());
}

// my_script.py -> my_script.drawio next to it; a folder -> FOLDER/architecture.drawio.
function outputPath(inputPath, isFolder, format) {
    if (!FORMATS.includes(format)) {
        throw new Error(`Format must be one of ${FORMATS.join(', ')}.`);
    }
    if (isFolder) { return path.join(inputPath, `architecture.${format}`); }
    const parsed = path.parse(inputPath);
    return path.join(parsed.dir, `${parsed.name}.${format}`);
}

function drawArguments(inputPath, output, level, force) {
    if (!['detailed', 'summary'].includes(level)) {
        throw new Error('Level must be "detailed" or "summary".');
    }
    const args = [inputPath, '--output', output, '--level', level];
    if (force) { args.push('--force'); }
    return args;
}

module.exports = {
    FORMATS, runPython, ensureTrusted, isSupportedInput, outputPath, drawArguments,
};
