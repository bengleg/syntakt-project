// The page's build worker: runs core.mjs off the page's thread and sends back the .syx. The user's OS file is
// received, used and dropped here; it is never sent anywhere. Patch packages are checked and merged here; they are
// data and are never run.
import { buildPatched, buildPatchedFromPackages, checkPackage, sha } from './core.mjs'

const build = async (run) => {
  self.postMessage({ type: 'status', text: 'Checking the OS file and applying the patches. Packing takes about a minute.' })
  return run()
}

self.onmessage = async ({ data }) => {
  try {
    if (data.type === 'validate') {
      const { id, title } = checkPackage(data.doc)
      return self.postMessage({ type: 'valid', id, title })
    }
    if (data.type === 'build-packages') {
      const { syx, ids, margin, marginMin } = await build(() => buildPatchedFromPackages(data.packages, data.ids, new Uint8Array(data.stock)))
      return self.postMessage({ type: 'done', syx: syx.buffer, sha256: sha(syx), ids, margin, marginMin }, [syx.buffer])
    }
    const { syx, margin, marginMin } = await build(() => buildPatched(data.doc, new Uint8Array(data.stock)))
    self.postMessage({ type: 'done', syx: syx.buffer, sha256: sha(syx), margin, marginMin }, [syx.buffer])
  } catch (error) {
    self.postMessage({ type: 'error', text: error instanceof Error ? error.message : String(error) })
  }
}
