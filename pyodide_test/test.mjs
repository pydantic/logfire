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
  await pyodide.runPythonAsync(`
import sys
import micropip

await micropip.install(['file:${wheelPath}'])
import logfire
logfire.configure(token='unknown', inspect_arguments=False)
logfire.info('hello {name}', name='world')
`)
  let out = stdout.join('')
  assert.ok(out.includes('hello world'), `stdout did not include message, stdout: "${out}"`)

  let err = stderr.join('')
  assert.ok(
    err.includes(
      'UserWarning: Logfire API returned status code 401.'
    ),
    `stderr did not include warning, stderr: "${err}"`
  )
}


async function findWheel(dist_dir) {
  const dir = await opendir(dist_dir);
  for await (const dirent of dir) {
    if (dirent.name.endsWith('.whl')) {
      return path.join(dist_dir, dirent.name);
    }
  }
}

runTest().catch(console.error)
