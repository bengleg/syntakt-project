// The page: pick the features (or the single v2o file) and the OS file, build in the worker, offer the .syx for download.
// The download exists only once the user clicks the link; nothing is saved by the page itself. Patch files are data:
// they are checked in the worker and written into the image only when ticked and built. None is run.
// The build stamp (?v= in index.html) is carried onto the bundle and the worker, so a stale cached copy cannot run with a
// fresh page. Static import of the bundle is replaced by a dynamic one for the same reason.
// Under each mod, and in "Your selection", the page shows what the ticked mods do together (analyze.mjs). These are
// estimates from the checks and the owner's notes (web/patches/info.json); the page measures nothing itself.
const V = new URL(import.meta.url).search
const { resolvePackages } = await import(`./dist/merge.mjs${V}`)
const { analyzeSelection, conflictsIfAdded, noteFor } = await import(`./dist/analyze.mjs${V}`)

const TESTED_V2O = '3df95923db35b0787119b04253e877f62b7c10ee1b7ab3f87340673aa843e3ac'
const V2O_ID = 'delay-control-full'
const V2O_LABEL = 'DelayCtrl v2o (single file, tested baseline)'
const FILE_NOTE = "declared by the file's author, not checked"
const BAND_WORD = { light: 'Light', noticeable: 'Noticeable', heavy: 'Heavy' }
const STATE_WORD = { todo: 'To do', done: 'Done', blocked: 'Problem' }
const COPY_FALLBACK = 'Copying is not available in this browser. Select the code and copy it by hand.'
const $ = id => document.getElementById(id)
const own = (obj, key) => (Object.prototype.hasOwnProperty.call(obj, key) ? obj[key] : undefined)
const worker = new Worker(`dist/worker.mjs${V}`, { type: 'module' })
const packages = {}   // id -> parsed .sypatch: the manifest order, then the files added by the user
const titles = {}     // id -> the title shown
const builtIn = new Set([V2O_ID])
let curated = {}      // the owner's notes: { budget, packages } from patches/info.json (missing file = none)
let v2oDoc = null
let validating = null // resolver for the added file the worker is checking
let pending = null    // 'validate' or 'build' while the worker is busy
let manifestReady = false  // built-in ids are known only after the manifest loads
let lastBuild = null  // { v2o } for the build in progress
let timer = null, started = 0
let copiedTimer = null

const has = id => Object.prototype.hasOwnProperty.call(packages, id)
const featureBoxes = () => [...document.querySelectorAll('.feature')]
const importBoxes = () => [...document.querySelectorAll('.import')]
const selectedIds = () => [...document.querySelectorAll('.feature:checked, .import:checked')].map(b => b.value)
const setStatus = (text, tone = '') => {
  $('status').textContent = text
  $('status').className = tone
  $('status').setAttribute('role', tone === 'err' ? 'alert' : 'status')
}
const stopTimer = () => { clearInterval(timer); timer = null; $('elapsed').textContent = '' }
const getJson = path => fetch(path).then(r => { if (!r.ok) throw new Error(`${path}: ${r.status}`); return r.json() })
const nameOf = id => own(titles, id) ?? id
const curatedPackages = () => (curated.packages && typeof curated.packages === 'object' ? curated.packages : {})
const fileInfoFor = id => own(packages, id)?.info ?? null
const notesOf = id => noteFor(fileInfoFor(id), own(curatedPackages(), id) ?? null)
const sizeText = bytes => (bytes < 1024 ? `${bytes} ${bytes === 1 ? 'byte' : 'bytes'}` : `${(bytes / 1024).toFixed(1)} KB`)
const fileSizeText = bytes => {
  if (bytes < 1024) return `${bytes} bytes`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function budgetOf() {
  const b = curated.budget
  return b && Number.isFinite(b.noticeable) && Number.isFinite(b.heavy) ? { noticeable: b.noticeable, heavy: b.heavy } : undefined
}
const analyse = ids => analyzeSelection(packages, curatedPackages(), ids, budgetOf())

// What will be applied, in order, from the ticks. Empty until the manifest has loaded.
function plan() {
  if ($('v2o').checked) return { lines: [V2O_LABEL], error: '' }
  if (!Object.keys(packages).length) return { lines: [], error: '' }
  const ids = selectedIds()
  if (!ids.length) return { lines: [], error: 'Tick at least one feature.' }
  try {
    return { lines: resolvePackages(packages, ids).map(nameOf), error: '' }
  } catch (e) {
    return { lines: [], error: e.message }
  }
}

// The audio load as a plain sentence (the body after "Audio load: ").
function loadBody(cost) {
  const { band, known, unmeasured, perPackage } = cost
  const measured = Object.values(perPackage).some(v => v !== null)
  if (band === 'none') return 'none, adds no code that runs during sound.'
  if (band === 'unknown') {
    if (!measured) return 'not measured yet. This page cannot tell how heavy this mod is.'
    return `about ${known} processor steps per audio slice, measured in the emulator, for the parts measured so far. `
      + `Not measured yet for: ${unmeasured.map(nameOf).join(', ')}. The total is a minimum.`
  }
  return `${BAND_WORD[band]}, about ${known} processor steps per audio slice, measured in the emulator.`
}

function summaryLine(id, imported) {
  const { note, from } = notesOf(id)
  if (typeof note.summary !== 'string' || !note.summary) return null
  return imported && from.summary === 'file' ? `${note.summary} (${FILE_NOTE})` : note.summary
}

// The pair message already names both mods, so it is shown as it is. Only a mod that cannot be added at all gets a prefix.
function conflictLabel(id, c) {
  const other = c.a === id ? c.b : c.a
  return other ? c.text : `Cannot be added: ${c.text}`
}

// Audio load is shown under a mod only when a number or a band exists (not while it is still unmeasured).
const loadKnown = cost => cost.band !== 'unknown' || Object.values(cost.perPackage).some(v => v !== null)

// The lines under one mod: its summary, its patch memory, its audio load, and (when unticked) what it would conflict with.
function boxLines(id, imported, ticked) {
  const lines = []
  const summary = summaryLine(id, imported)
  if (summary) lines.push({ text: summary })
  const a = analyse([id])
  const used = a.size.totals.areaBytes
  lines.push({ text: used > 0 ? `Uses ${sizeText(used)} of patch memory` : 'Changes only the program, no patch memory' })
  if (loadKnown(a.cost)) {
    const costFromFile = imported && notesOf(id).from.cost === 'file'
    lines.push({ text: `Audio load: ${loadBody(a.cost)}${costFromFile ? ` (${FILE_NOTE})` : ''}` })
  }
  if (!ticked) {
    const shown = new Set()
    for (const c of conflictsIfAdded(packages, curatedPackages(), selectedIds(), id, budgetOf())) {
      if (shown.has(c.text)) continue
      shown.add(c.text)
      lines.push({ text: conflictLabel(id, c), warn: true })
    }
  }
  return lines
}

// The plain reason Build is off, shown under the button. Empty when Build is on.
function whyNotBuilding({ hasStock, loaded, v2oOn, ids, error, lines, blocking }) {
  if (blocking || (error && ids.length)) return 'Build is off: a conflict must be fixed first. Untick one of the mods named above.'
  if (!hasStock) return 'Build is off: no OS 1.41 file chosen yet. Choose it in step 3.'
  if (!lines.length) {
    return !loaded && !v2oOn
      ? 'Build is off: the patch set is still loading.'
      : 'Build is off: nothing is ticked yet. Tick a feature or a mod.'
  }
  return ''
}

// "Your selection": patch memory, program places, audio load and conflicts. Returns true when Build must stay off.
function renderPanel(ids, v2oOn) {
  const panel = $('selection')
  $('conflicts').replaceChildren()
  $('conflict-action').textContent = ''
  if (v2oOn) {
    panel.hidden = false
    $('mem-bar').hidden = true
    $('mem-text').textContent = 'Size: not split into parts, tested baseline.'
    $('places').textContent = ''
    $('load').textContent = 'Audio load: not split into parts, tested baseline.'
    return false
  }
  if (!ids.length) { panel.hidden = true; return false }
  const a = analyse(ids)
  panel.hidden = false
  const { areaBytes, areaSize, areaPercent, osPlaces } = a.size.totals
  const pctText = areaPercent < 0.1 ? 'under 0.1%' : `${areaPercent.toFixed(1)}%`
  $('mem-bar').hidden = areaBytes === 0
  $('mem-text').textContent = areaBytes === 0
    ? 'No patch memory used.'
    : `${sizeText(areaBytes)} of ${areaSize / 1024} KB used (${pctText})`
  $('mem-fill').style.width = `${Math.min(100, areaPercent)}%`
  $('places').textContent = `Changes ${osPlaces} ${osPlaces === 1 ? 'place' : 'places'} in the Syntakt's own program.`
  $('load').textContent = `Audio load: ${loadBody(a.cost)}`
  if (!a.conflicts.length) {
    $('conflicts').append(Object.assign(document.createElement('p'), { className: 'muted', textContent: 'No conflicts found by the checks on this page.' }))
  }
  for (const c of a.conflicts) {
    $('conflicts').append(Object.assign(document.createElement('p'), { className: 'conflict', textContent: c.text }))
  }
  if (a.blocking) $('conflict-action').textContent = 'Untick one of these to continue.'
  return a.blocking
}

// Fills the notes under every mod and the selection panel. Returns true when a conflict blocks the build.
function renderNotes() {
  const v2oOn = $('v2o').checked
  const loaded = Object.keys(packages).length > 0
  const ids = selectedIds()
  const show = loaded && !v2oOn
  document.querySelectorAll('[data-note]').forEach(el => {
    el.replaceChildren()
    if (!show) return
    for (const line of boxLines(el.dataset.note, el.dataset.imported === 'true', ids.includes(el.dataset.note))) {
      el.append(Object.assign(document.createElement('div'), { textContent: line.text, className: line.warn ? 'warn' : '' }))
    }
  })
  return renderPanel(loaded ? ids : [], v2oOn)
}

// The four steps in the top bar and the badge on each section title. Every state comes from the page's own state.
function setStep(key, state, badge, tone) {
  document.querySelector(`[data-step="${key}"]`).dataset.state = state
  $(`state-${key}`).textContent = STATE_WORD[state]
  $(`badge-${key}`).textContent = badge
  $(`badge-${key}`).dataset.tone = tone
}

function renderProgress({ busy, loaded, v2oOn, error, blocking, lines, hasStock, resultShown, buildOn, why }) {
  const addedTicked = importBoxes().some(b => b.checked)
  if (blocking || error) setStep('features', blocking ? 'blocked' : 'todo', blocking ? 'Conflict' : 'Needs input', blocking ? 'err' : 'warn')
  else if (lines.length) setStep('features', 'done', 'Ready', 'ok')
  else setStep('features', 'todo', loaded || v2oOn ? 'Needs input' : 'Loading', loaded || v2oOn ? 'warn' : 'info')

  if (blocking) setStep('mods', 'blocked', 'Conflict', 'err')
  else if (addedTicked) setStep('mods', 'done', 'Ready', 'ok')
  else setStep('mods', 'todo', 'Optional', 'info')

  if (hasStock) setStep('os-file', 'done', 'Ready', 'ok')
  else setStep('os-file', 'todo', 'Needs input', 'warn')

  if (resultShown) setStep('build', 'done', 'Built', 'ok')
  else if (busy) setStep('build', 'todo', 'Building', 'info')
  else if (why && !buildOn) setStep('build', blocking ? 'blocked' : 'todo', blocking ? 'Conflict' : 'Needs input', blocking ? 'err' : 'warn')
  else if (buildOn) setStep('build', 'todo', 'Ready', 'ok')
  else setStep('build', 'todo', 'Needs input', 'warn')
}

function refresh() {
  const busy = pending !== null
  const v2oOn = $('v2o').checked
  const loaded = Object.keys(packages).length > 0
  featureBoxes().forEach(b => { b.disabled = !loaded || v2oOn || busy })
  importBoxes().forEach(b => { b.disabled = v2oOn || busy })
  $('v2o').disabled = !v2oDoc || busy
  $('import').disabled = busy
  $('import-pick').disabled = busy
  $('import-drop').dataset.disabled = String(busy)
  document.querySelectorAll('.remove').forEach(b => { b.disabled = busy })

  const boxes = [...featureBoxes(), ...importBoxes()]
  const tickable = boxes.some(b => !b.disabled)
  $('select-all').disabled = !tickable
  $('select-none').disabled = !tickable
  $('count').textContent = loaded && boxes.length ? `${boxes.filter(b => b.checked).length} of ${boxes.length} selected` : ''
  $('imports-empty').hidden = importBoxes().length > 0

  const { lines, error } = plan()
  $('plan').replaceChildren(...lines.map(text => Object.assign(document.createElement('li'), { textContent: text })))
  $('plan-error').textContent = error
  const blocking = renderNotes()
  const hasStock = !!$('stock').files.length
  const buildOn = !(busy || !hasStock || !!error || !lines.length || blocking)
  $('build').disabled = !buildOn
  $('build').classList.toggle('busy', pending === 'build')
  const why = busy ? '' : whyNotBuilding({
    hasStock, loaded, v2oOn, ids: selectedIds(), error, lines, blocking,
  })
  $('build-why').textContent = why
  renderProgress({ busy, loaded, v2oOn, error, blocking, lines, hasStock, resultShown: !$('result').hidden, buildOn, why })
}

const infoReady = getJson('patches/info.json')
  .then(j => { curated = j && typeof j === 'object' ? j : {} })
  .catch(() => { curated = {} })

Promise.all([getJson('patches/manifest.json'), infoReady])
  .then(([m]) => Promise.all(m.packages.map(p => getJson(`patches/${p.file}`).then(doc => ({ p, doc })))))
  .then(list => {
    for (const { p, doc } of list) {
      packages[p.id] = doc
      titles[p.id] = p.title ?? doc.title ?? p.id
      builtIn.add(p.id)
    }
    manifestReady = true
    refresh()
  })
  .catch(() => setStatus('Could not load the patch set. Serve this folder over HTTP (see web/build.mjs).', 'err'))

getJson('patches/delay-control.sypatch.json')
  .then(d => { v2oDoc = d; $('patchinfo').textContent = `For OS ${d.target.os} only.`; refresh() })
  .catch(() => { $('patchinfo').textContent = 'The single-file v2o set could not be loaded.' })

// Any change to a tick, a mod or the single-file option: the old result no longer matches the ticks.
function selectionChanged() {
  $('result').hidden = true
  if ($('status').className === 'ok') setStatus('')
  refresh()
}

document.addEventListener('change', e => {
  if (e.target.matches('.feature, .import, #v2o')) selectionChanged()
})

function setAllTicks(on) {
  for (const box of [...featureBoxes(), ...importBoxes()]) if (!box.disabled) box.checked = on
  selectionChanged()
}
$('select-all').addEventListener('click', () => setAllTicks(true))
$('select-none').addEventListener('click', () => setAllTicks(false))

// A drop zone: a dragged file is accepted only when the zone is enabled. The browser is kept from opening the file.
function wireDrop(zone, onDrop) {
  zone.addEventListener('dragover', e => {
    if (zone.dataset.disabled === 'true') return
    e.preventDefault()
    zone.classList.add('over')
  })
  zone.addEventListener('dragleave', () => zone.classList.remove('over'))
  zone.addEventListener('drop', e => {
    e.preventDefault()
    zone.classList.remove('over')
    if (zone.dataset.disabled === 'true') return
    onDrop(e.dataTransfer.files)
  })
}

$('import-pick').addEventListener('click', () => $('import').click())
$('import').addEventListener('change', () => {
  const files = [...$('import').files]
  $('import').value = ''
  addFiles(files)
})
wireDrop($('import-drop'), files => {
  const jsonFiles = [...files].filter(f => /\.json$/i.test(f.name))
  if (!jsonFiles.length) return setStatus('Only .json mod files can be added here.', 'err')
  addFiles(jsonFiles)
})

async function addFiles(files) {
  if (!files.length) return
  if (!manifestReady) return setStatus('Wait for the built-in patches to load, then add the file.', 'err')
  setStatus(files.length === 1 ? 'Checking the file...' : `Checking ${files.length} files...`)
  const results = []
  for (const file of files) results.push(await addFile(file))
  setStatus(results.map(r => r.text).join(' '), results.every(r => r.ok) ? 'ok' : 'err')
}

// Checks one added file in the worker. When it passes, it is listed under "Mods you were sent" (not applied yet).
async function addFile(file) {
  const fail = text => ({ ok: false, text: `Not added (${file.name}): ${text}` })
  let doc
  try { doc = JSON.parse(await file.text()) } catch { return fail('the file is not JSON.') }
  const data = await new Promise(resolve => {
    validating = resolve
    pending = 'validate'
    refresh()
    worker.postMessage({ type: 'validate', doc })
  })
  if (data.type === 'error') return fail(data.text)
  const { id, title } = data
  if (builtIn.has(id)) return fail(`the id "${id}" belongs to a built-in patch.`)
  if (has(id)) return fail(`a patch with the id "${id}" is already added.`)
  packages[id] = doc
  titles[id] = title
  const row = document.createElement('div')
  row.className = 'feature-row'
  const label = document.createElement('label')
  label.className = 'check'
  const box = Object.assign(document.createElement('input'), { type: 'checkbox', className: 'import', value: id })
  label.append(box, ` ${title} (${id}), from a file you added`)
  const note = Object.assign(document.createElement('div'), { className: 'note' })
  note.dataset.note = id
  note.dataset.imported = 'true'
  const actions = document.createElement('div')
  actions.className = 'row'
  const remove = Object.assign(document.createElement('button'), { type: 'button', className: 'text danger remove', textContent: 'Remove' })
  remove.setAttribute('aria-label', `Remove ${title}`)
  remove.addEventListener('click', () => removeFile(id, row))
  actions.append(remove)
  row.append(label, note, actions)
  $('imports').append(row)
  refresh()
  return { ok: true, text: `Added ${title}. It is not applied until you tick it.` }
}

// Only mods added from a file can be removed. Built-in mods have no Remove button.
function removeFile(id, row) {
  const title = nameOf(id)
  delete packages[id]
  delete titles[id]
  row.remove()
  $('result').hidden = true
  setStatus(`Removed ${title}.`)
  refresh()
}

$('stock-pick').addEventListener('click', () => $('stock').click())
$('stock').addEventListener('change', stockChanged)
$('stock-clear').addEventListener('click', () => {
  $('stock').value = ''
  stockChanged()
})
wireDrop($('stock-drop'), files => {
  const [file] = [...files]
  if (!file) return
  if (!/\.syx$/i.test(file.name)) return setStatus('Only a .syx file can be used as the OS file.', 'err')
  const transfer = new DataTransfer()
  transfer.items.add(file)
  $('stock').files = transfer.files
  stockChanged()
})

// Shows the chosen file's name and size. Only the name and size are read; the bytes are read by Build only.
function stockChanged() {
  const file = $('stock').files[0]
  $('result').hidden = true
  $('stock-chosen').hidden = !file
  $('stock-empty').hidden = !!file
  if (file) {
    $('stock-name').textContent = file.name
    $('stock-size').textContent = `Â· ${fileSizeText(file.size)}`
  }
  refresh()
}

$('build').addEventListener('click', async () => {
  const file = $('stock').files[0]
  if (!file) return
  const v2o = $('v2o').checked
  lastBuild = { v2o }
  pending = 'build'
  $('result').hidden = true
  refresh()
  const stock = await file.arrayBuffer().catch(() => null)
  if (!stock) {
    pending = null
    refresh()
    return setStatus('Could not read the OS file.', 'err')
  }
  started = Date.now()
  timer = setInterval(() => { $('elapsed').textContent = `${Math.round((Date.now() - started) / 1000)} s` }, 1000)
  setStatus('Starting...')
  if (v2o) worker.postMessage({ type: 'build', doc: v2oDoc, stock }, [stock])
  else worker.postMessage({ type: 'build-packages', packages, ids: selectedIds(), stock }, [stock])
})

$('copy-sha').addEventListener('click', async () => {
  const sha = $('sha').textContent
  if (!sha) return
  const say = text => { $('copy-status').textContent = text }
  if (!navigator.clipboard?.writeText) return say(COPY_FALLBACK)
  try {
    await navigator.clipboard.writeText(sha)
    say('Copied')
    clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => say(''), 2000)
  } catch {
    say(COPY_FALLBACK)
  }
})

function showResult(data) {
  const { v2o } = lastBuild
  const names = v2o ? [V2O_LABEL] : data.ids.map(nameOf)
  $('applied').textContent = `Applied: ${names.join(', ')}.`
  $('sha').textContent = data.sha256
  $('copy-status').textContent = ''
  const url = URL.createObjectURL(new Blob([data.syx], { type: 'application/octet-stream' }))
  if (v2o) {
    const matches = data.sha256 === TESTED_V2O
    $('match').className = matches ? 'ok' : 'warn'
    $('match').textContent = matches
      ? 'This matches the tested DelayCtrl v2o build.'
      : 'This does not match the tested DelayCtrl v2o build. Check the OS file and patch set before using it.'
  } else {
    $('match').className = 'warn'
    $('match').textContent = 'This is not the single-file v2o build, so it is not expected to match the tested v2o build byte for byte.'
  }
  const room = $('boot-room')
  const hasRoom = Number.isFinite(data.margin) && Number.isFinite(data.marginMin)
  room.className = hasRoom ? (data.margin >= data.marginMin ? 'ok' : 'warn') : ''
  room.textContent = hasRoom ? `Boot room: ${data.margin} bytes (at least ${data.marginMin} needed).` : ''
  $('download').href = url
  $('download').download = v2o ? `delay-control-${data.sha256.slice(0, 8)}.syx` : `syntakt-os141-${data.sha256.slice(0, 8)}.syx`
  $('result').hidden = false
  setStatus('Done.', 'ok')
}

worker.onmessage = ({ data }) => {
  if (data.type === 'status') return setStatus(data.text)
  if (pending === 'validate') {
    pending = null
    refresh()
    const done = validating
    validating = null
    return done(data)
  }
  stopTimer()
  pending = null
  refresh()
  if (data.type === 'error') return setStatus(`Not built: ${data.text}`, 'err')
  showResult(data)
}

refresh()
