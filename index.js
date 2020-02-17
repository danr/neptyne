
const DEBUG = window.location.hash == '#debug'

// eighties
const colors = {
  'black':       '#2d2d2d',
  'grey90':      '#393939',
  'grey80':      '#515151',
  'grey70':      '#747369',
  'grey60':      '#a09f93',
  'white':       '#d3d0c8',
  'whiter':      '#e8e6df',
  'whitest':     '#f2f0ec',
  'red':         '#f2777a',
  'orange':      '#f99157',
  'yellow':      '#ffcc66',
  'green':       '#99cc99',
  'cyan':        '#66cccc',
  'blue':        '#6699cc',
  'magenta':     '#cc99cc',
  'brown': '#d27b53',
}

function activate(domdiff, root, websocket, state) {

  const {div, span, pre, style, cls, id, class_cache, mousewheel, scroll} = domdiff

  const {css, generate_class} = class_cache()

  const FlexColumnRight = css`
          display: flex;
          flex-direction: column;
          align-items: flex-end;
        `
  const FlexColumnLeft = css`
          display: flex;
          flex-direction: column;
          align-items: flex-start;
        `
  const InlineFlexRowTop = css`
          display: inline-flex;
          flex-direction: row;
          align-items: flex-start;
        `
  const FlexRowTop = css`
          display: flex;
          flex-direction: row;
          align-items: flex-start;
        `

  css`
    * {
      box-sizing: border-box;
    }
    pre {
      white-space: pre-wrap;
      overflow: auto;
    }
    body {
      font-size: 18px;
      letter-spacing: -1px;
      font-family: 'Consolas';
      font-weight: 400 !important;
      background: ${colors.black};
    }
    body {
      margin: 0;
    }
    table {
      color: inherit;
      font-size: unset;
      background: ${colors.grey80};
    }
    td, th {
      background: ${colors.grey90};
      padding: 2px 5px;
    }
  `

  let rAF = k => window.requestAnimationFrame(k)

  window.schedule_refresh = function schedule_refresh() {
    rAF(actual_refresh)
    rAF = x => 0
  }

  function actual_refresh() {

    {
      const any_canc = state.cells.some(c => c.status == 'cancelled')
      const any_errd = state.cells.some(c => c.status == 'errored')
      if (any_canc && !any_errd) {
        for (const c of state.cells) {
          if (c.status == 'cancelled') {
            c.status = 'errored'
            break
          }
        }
      }
    }


    rAF = k => window.requestAnimationFrame(k)

    if (!state.cells) {
      return
    }

    // console.log(state.cells)

    const exec_ix = state.cells.findIndex(c => c.status == 'executing')
    const errd_ix = state.cells.findIndex(c => c.status == 'errored')
    const N = state.cells.length

    let status_bar

    if (exec_ix != -1) {
      status_bar = span('running cell ', 1 + exec_ix, '/', N, css`color: ${colors.yellow}`)
    } else if (errd_ix != -1) {
      status_bar = span('errored on cell ', 1 + errd_ix, css`color: ${colors.brown}`)
    } else {
      status_bar = span('ready', css`color: ${colors.green}`)
    }

    const rix = (xs, f) => {
      const i = xs.slice().reverse().findIndex(f)
      console.log({i})
      if (i == -1) {
        return i
      } else {
        return xs.length - i - 1
      }
    }

    let cells = state.cells

    const clear = rix(
      cells,
      c =>
        c.msgs &&
        c.msgs.length == 1 &&
        c.status == 'done' &&
        (
          c.msgs[0].data['text/plain'] == "'clear'" ||
          c.msgs[0].data['text/plain'] == '"clear"'
        ))

    if (clear != -1) {
      cells = cells.slice(clear + 1)
    }

    const morph = div(
      id`root`,
      css`
       & > pre {
         color: ${colors.white};
         background: ${colors.grey90};
         margin: 8px;
         margin-bottom: 12px;
         padding: 4px;
         padding-left: 6px;
         // min-height: 8px;
       }
      `,
      ...cells.map(cell_to_dom),
      div(
        status_bar,
        css`
          display: inline-block;
          height: 22px;
          position: fixed;
          bottom: 0px;
          right: 0px;
          margin: 4px;
          border: 2px ${colors.black} solid;
          padding: 2px 4px;
          padding-bottom: 3px;
          color: ${colors.white};
          background: ${colors.grey90};
        `)
    )

    morph(root)
  }

  state.cells = state.cells || []

  function update_cell_data(msg) {
    state.cells = msg
    // console.log(state.cells)
  }

  // console.log(state.cells)

  if (!DEBUG) {
    websocket.onmessage = function on_message(msg) {
      // console.log({msg})
      update_cell_data(JSON.parse(msg.data))
      schedule_refresh()
    }
  }

  if (DEBUG) {
    debug_functionality(state)
  }

  schedule_refresh()

  function prioritize_images(msgs0) {
    // const is_image = msg => 'image/png' in msg.data || 'image/svg+xml' in msg.data
    const msgs = msgs0 || []
    if (msgs.some(m => m.msg_type == 'display_data')) {
      return msgs.filter(m => m.msg_type != 'execute_result')
    } else {
      return msgs
    }
  }

  function cell_to_dom(cell) {
    const {status} = cell
    let msgs = prioritize_images(cell.msgs)
    const colours = {
      default: 'blue',
      executing: 'yellow',
      errored: 'brown',
      cancelled: 'grey80',
      scheduled: 'grey80',
    }
    let border_colour = colours[status] || colours.default
    let grad_bottom = null
    const prev_msgs = prioritize_images(cell.prev_msgs)
    const nothing_yet = (status == 'executing' && msgs.length == 0 && prev_msgs.length > 0)
      || status == 'scheduled'

    if (nothing_yet && status == 'executing') {
      grad_bottom = colours['scheduled']
    }
    if (prev_msgs.length > 0 && nothing_yet || status == 'cancelled') {
      msgs = prev_msgs
    }
    if (msgs.length) {
      return pre(
        // FlexColumnLeft,
        ...msgs.map(msg_to_dom),
        // pre(css`display:none;color:white;font-size:0.8em`, JSON.stringify(cell, 2, 2)),
        grad_bottom
        ? css`
          border-image: linear-gradient(to bottom,
            ${colors[border_colour]} 0%,
            ${colors[grad_bottom]} 25%
          );
          border-image-slice: 1;
          border-left: 2px solid;
        `
        : css`
          border-left: 2px ${colors[border_colour]} solid;
        `)
    }
  }

  function msg_to_dom(msg) {
    // console.log(blob)
    const mimes = msg.data
    if (mimes) {
      // console.log(mimes)
      const html = mimes['text/html']
      const svg = mimes['image/svg+xml']
      const png = mimes['image/png']
      const plain = mimes['text/plain']
      if (html || svg) {
        const div = document.createElement('div')
        // div.style.background = 'white'
        // div.style.display = 'inline-block'
        div.style['white-space'] = 'normal'
        div.foreign = true
        div.innerHTML = (html || svg).replace(/<table border="\d*"/g, '<table')
        return div
      } else if (png) {
        const img = document.createElement('img')
        img.style.background = 'white'
        img.foreign = true
        img.src = 'data:image/png;base64,' + png
        return img
      } else if (plain) {
        return plain.replace(/\u001b\[[0-9;]*m/g, '')
        // const s = plain.replace(/\u001b\[[0-9;]*m/g, '')
        // const from_A = s.lastIndexOf('\u001b\[A')
        // const from_r = s.lastIndexOf(/\r[^\n]/)
        // if (from_A != -1) {
        //   line.text = s.slice(from_A+3)
        // } else if (from_r != -1) {
        //   line.text = s.slice(from_r+1) + '\n'
        // } else {
        //   line.text += s
        // }
      }
    }
  }
}

async function main() {
  const domdiff = await reimport('./domdiff.js')
  if (typeof websocket == 'undefined' || websocket.readyState != websocket.OPEN) {
    try {
      if (typeof websocket != 'undefined') {
        websocket.close()
      }
    } catch { }
    window.websocket = new WebSocket('ws://' + window.location.host + '/ws')
  }
  const root = document.getElementById('root') || document.body.appendChild(document.createElement('div'))
  root.id = 'root'
  window.state = (window.state || {})
  activate(domdiff, root, window.websocket, window.state)
}

function debug_functionality(state) {
  function make_cells(cursor, cancelled) {
    const new_msg = s => ({
      data: {'text/plain': s + '\n'},
      msg_type: 'execute_result',
    })
    const new_cell = status => ({
      status,
      msgs: [],
      prev_msgs: [],
    })
    const status = {}
    const messages = []
    for (let i = 0; i <= 20; ++i) {
      const id = Math.floor(i / 3) + ''
      messages.push({
        id,
        cat: 'prev_msgs',
        // msg: '.\n\.\nold 1234567891011121314151617181920212223242526272829303132333435363738394041424344454647484950515253545556575859606162636465666768697071727374757677787980' + i,
        msg: '.\n\.\nold 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48 49 50 51 52 53 54 55 56 57 58 59 60 61 62 63 64 65 66 67 68 69 70 71 72 73 74 75 76 77 78 79 80 ' + i,
        // msg: '.\n\.\nold ' + i,
      })
    }
    messages.push({
      id: '1.quiet',
      cat: 'prev_msgs',
      msg: ''
    })
    messages.push({
      id: '2.quiet',
      cat: 'prev_msgs',
      msg: ''
    })
    messages.sort((a, b) => a.id > b.id ? 1 : a.id == b.id ? 0 : -1)
    const N = messages.length
    for (let i = 0; i < N; ++i) {
      const msg = {...messages[i]}
      const id = msg.id
      if (i < cursor) {
        status[id] = 'done'
        msg.cat = 'msgs'
        msg.msg = msg.msg.replace('old', 'new')
        messages.push(msg)
      } else if (i == cursor) {
        status[id] = cancelled ? 'cancelled' : 'executing'
      } else if (i > cursor && !status[id]) {
        status[id] = cancelled ? 'cancelled' : 'scheduled'
      }
    }
    console.log(messages)
    let cells = {}
    for (const m of messages) {
      if (!(m.id in cells)) {
        cells[m.id] = new_cell(status[m.id])
      }
      if (m.msg.length) {
        cells[m.id][m.cat].push(new_msg(m.msg))
      }
    }
    return Object.keys(cells).sort().map(k => cells[k])
  }
  if (!(
    'cursor' in state &&
    'cancelled' in state
  )) {
    state.cursor = 5
    state.cancelled = false
  }
  state.cells = make_cells(state.cursor, state.cancelled)
  window.onkeydown = e => {
    let act = true
    if (e.key == 'ArrowUp') state.cursor -= 1
    else if (e.key == 'ArrowDown') state.cursor += 1
    else if (e.key == 'ArrowLeft') state.cancelled = !state.cancelled
    else if (e.key == 'ArrowRight') state.cancelled = !state.cancelled
    else act = false
    if (act) {
      e.preventDefault()
      state.cursor = Math.max(0, state.cursor) // Math.min(N, state.cursor)
      state.cells = make_cells(state.cursor, state.cancelled)
      schedule_refresh()
    }
  }
}

main()

