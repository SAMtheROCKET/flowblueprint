'use strict';

const fs = require('node:fs');
const {
    FORMATS, runPython, ensureTrusted, isSupportedInput, outputPath, drawArguments,
} = require('./runner');
const { resolvePythonPath, ensureTool } = require('./setup');
const manifest = require('./package.json');

const FORMAT_LABELS = {
    drawio: 'draw.io diagram (editable)',
    svg: 'SVG image',
    html: 'Web page',
    md: 'Markdown with a Mermaid flowchart',
};

function activate(context) {
    const vscode = require('vscode');
    const tool = manifest.name;
    const output = vscode.window.createOutputChannel(manifest.displayName);
    context.subscriptions.push(output);

    // The file a command applies to: the explorer item, else the active editor.
    function activeFileUri(clicked) {
        if (clicked) { return clicked; }
        const editor = vscode.window.activeTextEditor;
        const notebook = vscode.window.activeNotebookEditor;
        const uri = editor?.document.uri.scheme === 'vscode-notebook-cell'
            ? notebook?.notebook.uri : (editor?.document.uri || notebook?.notebook.uri);
        if (!uri) { throw new Error('Open a Python file or notebook first.'); }
        if (editor?.document.isDirty || notebook?.notebook.isDirty) {
            throw new Error('Save the file before drawing it.');
        }
        return uri;
    }

    async function activeFolderUri(clicked) {
        if (clicked) { return clicked; }
        const folders = vscode.workspace.workspaceFolders || [];
        if (folders.length === 0) { throw new Error('Open a project folder first.'); }
        if (folders.length === 1) { return folders[0].uri; }
        const picked = await vscode.window.showWorkspaceFolderPick({ placeHolder: 'Folder to draw' });
        return picked?.uri;
    }

    async function chooseFormat(config) {
        const preferred = config.get('defaultFormat', 'drawio');
        const ordered = [preferred, ...FORMATS.filter(format => format !== preferred)];
        const picked = await vscode.window.showQuickPick(
            ordered.filter(format => FORMATS.includes(format)).map(format => ({
                label: `.${format}`, description: FORMAT_LABELS[format], format,
            })), { title: 'FlowBlueprint output format' });
        return picked?.format;
    }

    async function openResult(file, format) {
        const uri = vscode.Uri.file(file);
        if (format === 'html') {
            await vscode.env.openExternal(uri);
        } else if (format === 'md') {
            await vscode.commands.executeCommand('markdown.showPreview', uri);
        } else {
            // .drawio opens in a draw.io editor extension when one is installed.
            await vscode.commands.executeCommand('vscode.open', uri);
        }
    }

    async function draw(isFolder, clicked) {
        ensureTrusted(vscode);
        const uri = isFolder ? await activeFolderUri(clicked) : activeFileUri(clicked);
        if (!uri) { return; }
        if (uri.scheme !== 'file') { throw new Error('This command requires a local saved file.'); }
        if (!isSupportedInput(uri.fsPath, isFolder)) {
            throw new Error('Use a saved .py script or .ipynb notebook.');
        }
        const config = vscode.workspace.getConfiguration(tool, uri);
        const format = await chooseFormat(config);
        if (!format) { return; }
        const target = outputPath(uri.fsPath, isFolder, format);
        let force = false;
        if (fs.existsSync(target)) {
            const answer = await vscode.window.showWarningMessage(
                `${target} exists. Replace it?`, { modal: true }, 'Replace');
            if (answer !== 'Replace') { return; }
            force = true;
        }
        const pythonPath = await resolvePythonPath(vscode, uri, config.get('pythonPath', ''));
        await ensureTool(vscode, {
            pythonPath, tool, displayName: manifest.displayName,
            version: manifest.toolVersion, runPython,
        });
        const args = drawArguments(uri.fsPath, target, config.get('level', 'full'), force);
        const result = await vscode.window.withProgress(
            { location: vscode.ProgressLocation.Notification, title: 'Drawing the architecture...' },
            () => runPython(pythonPath, tool, args));
        output.clear();
        output.appendLine(result.output);
        if (result.errors) { output.appendLine(result.errors); }
        if (result.code !== 0 || !fs.existsSync(target)) {
            output.show(true);
            throw new Error(result.errors.trim() || result.output.trim() || 'The tool failed.');
        }
        await openResult(target, format);
    }

    const handlers = {
        drawFile: clicked => draw(false, clicked),
        drawFolder: clicked => draw(true, clicked),
    };
    for (const contribution of manifest.contributes.commands) {
        const command = contribution.command.split('.').at(-1);
        context.subscriptions.push(vscode.commands.registerCommand(contribution.command,
            clicked => handlers[command](clicked?.fsPath ? clicked : undefined)
                .catch(error => vscode.window.showErrorMessage(error.message))));
    }
}

module.exports = { activate };
