import {opendir} from 'node:fs/promises'
import path from 'path'
import assert from 'assert'
import { loadPyodide } from 'pyodide'


async function runTest() {
  const wheelPath = await findWheel(path.join(path.resolve(import.meta.dirname, '..'), 'dist'));
  const stdout = []
  const stderr = []
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

await micropip.install(['file:${wheelPath}'])
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
    if (dirent.name.endsWith('.whl')) {
      return path.join(dist_dir, dirent.name);
    }
  }
}

runTest()
