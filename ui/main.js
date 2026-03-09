const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let mainWindow;
let pythonProcess;

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 400,
        height: 500,
        transparent: false,
        frame: false,       // Frameless
        resizable: true,
        backgroundColor: '#050505',
        alwaysOnTop: true,  // Keep Jarvis on top
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false
        }
    });

    mainWindow.loadFile(path.join(__dirname, 'index.html'));

    // Start Python Backend
    startPythonBackend();

    mainWindow.on('closed', () => {
        mainWindow = null;
        if (pythonProcess) {
            pythonProcess.kill();
        }
    });
}

function startPythonBackend() {
    console.log('Starting Python backend...');

    // Spawn the Jarvis script, passing a flag so it knows to emit JSON for the UI
    pythonProcess = spawn('python', ['-u', 'main.py', '--json-ui'], {
        cwd: path.join(__dirname, '..') // Root project dir
    });

    pythonProcess.stdout.on('data', (data) => {
        const output = data.toString();
        // In stdout we might have normal logs AND our special JSON packets.
        // Let's parse line by line.
        const lines = output.split('\n');

        for (const line of lines) {
            const t = line.trim();
            if (!t) continue;

            // Look for our specific IPC tag
            if (t.startsWith('{"jarvis_ipc":')) {
                try {
                    const parsed = JSON.parse(t);
                    if (mainWindow) {
                        mainWindow.webContents.send('jarvis-event', parsed.jarvis_ipc);
                    }
                } catch (e) {
                    console.error("Failed to parse IPC JSON:", t);
                }
            } else {
                // Normal log
                console.log(`[PYTHON]: ${t}`);
            }
        }
    });

    pythonProcess.stderr.on('data', (data) => {
        console.error(`[PYTHON ERR]: ${data.toString()}`);
    });

    pythonProcess.on('close', (code) => {
        console.log(`Python process exited with code ${code}`);
    });
}

app.whenReady().then(() => {
    createWindow();

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
