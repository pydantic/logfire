import {opendir} from 'node:fs/promises'
import path from 'path'
import assert from 'assert'
import {loadPyodide} from 'pyodide'

const stdout = []
const stderr = []

function dumpCapturedOutput() {
    console.error('captured stdout:', stdout.join(''))
    console.error('captured stderr:', stderr.join(''))
}

function fail(error) {
    dumpCapturedOutput()
    console.error(error)
    process.exitCode = 1
}

process.on('uncaughtException', fail)
process.on('unhandledRejection', fail)

async function runTest() {
    const wheelPath = await findWheel(path.join(path.resolve(import.meta.dirname, '..'), 'dist'));
    const pyodide = await loadPyodide({

        stdout: (msg) => {
            stdout.push(msg)
        },
        stderr: (msg) => {
            stderr.push(msg)
        }
    })
    await pyodide.loadPackage(['micropip', 'pygments'])
    console.log('Running Pyodide test...\n')
    await pyodide.runPythonAsync(`
import sys
import micropip
from importlib.metadata import version

await micropip.install(['file:${wheelPath}'], reinstall=True)
from packaging.version import Version
api_version = version('opentelemetry-api')
sdk_version = version('opentelemetry-sdk')
assert api_version == sdk_version, (api_version, sdk_version)
instrumentation_version = version('opentelemetry-instrumentation')
assert Version(instrumentation_version) < Version('0.67b0'), instrumentation_version
conventions_version = version('opentelemetry-semantic-conventions')
assert Version(conventions_version) < Version('0.67b0'), conventions_version
import logfire
logfire.configure(token='unknown', inspect_arguments=False)
logfire.info('hello {name}', name='world')
sys.stdout.flush()
sys.stderr.flush()
`)
    let out = stdout.join('')
    let err = stderr.join('')
    console.log('stdout:', out)
    console.log('stderr:', err)
    assert.ok(out.includes('hello world'))

    assert.ok(
        err.includes(
            'UserWarning: Logfire API returned status code 401.'
        ),
    )
    console.log('\n\nLogfire Pyodide tests passed 🎉')
}


async function findWheel(dist_dir) {
    const dir = await opendir(dist_dir);
    for await (const dirent of dir) {
        if (dirent.name.startsWith('logfire-') && dirent.name.endsWith('.whl')) {
            return path.join(dist_dir, dirent.name);
        }
    }
}

runTest().catch(fail)
