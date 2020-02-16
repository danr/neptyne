
const DEBUG = window.location.hash == '#debug'

// eighties
const NAMED_COLOURS = {
  'black':          '#2d2d2d',
  'bright-green':   '#393939',
  'bright-yellow':  '#515151',
  'bright-black':   '#747369',
  'bright-blue':    '#a09f93',
  'white':          '#d3d0c8',
  'bright-magenta': '#e8e6df',
  'bright-white':   '#f2f0ec',
  'red':            '#f2777a',
  'bright-red':     '#f99157',
  'yellow':         '#ffcc66',
  'green':          '#99cc99',
  'cyan':           '#66cccc',
  'blue':           '#6699cc',
  'magenta':        '#cc99cc',
  'bright-cyan':    '#d27b53',
}

function color_to_css(name, fallback) {
  // use class cache?
  if (fallback && (name == 'default' || name == '')) {
    return color_to_css(fallback)
  } else if (name in NAMED_COLOURS) {
    return NAMED_COLOURS[name]
  } else {
    return name
  }
}

function activate(domdiff, root, websocket, state) {

  const {div, span, pre, style, cls, id, class_cache, mousewheel, scroll} = domdiff

  const {css, generate_class} = class_cache()

  const Left = css`
          position: absolute;
          left: 0;
          bottom: 0;
        `
  const Right = css`
          position: absolute;
          right: 0;
          bottom: 0;
        `
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
  const WideChildren = css`
          & * {
            width: 100%;
          }
        `

  css`
    html, body, #root, #root > pre {
      width: 100wh;
    }
    pre {
      white-space: pre-wrap;
      // width: 100vw;
      overflow: auto;
    }
    * {
      box-sizing: border-box;
    }
    pre {
      margin: 0;
    }
    pre, body {
      font-size: 18px;
      letter-spacing: -1px;
      font-family: 'Consolas';
      font-weight: 400 !important;
      background: ${color_to_css('black')};
      // background: linear-gradient(to bottom right, ${color_to_css('bright-green')} 20%, ${color_to_css('black')});
    }
    body {
      margin: 0;
      // overflow: hidden;
    }
    table {
      color: inherit;
    }
  `

  let rAF = k => window.requestAnimationFrame(k)

  window.schedule_refresh = function schedule_refresh() {
    rAF(actual_refresh)
    rAF = x => 0
  }

  if (state.obs) {
    state.obs.disconnect()
  }

  function actual_refresh() {

    rAF = k => window.requestAnimationFrame(k)

    if (!state.cells) {
      return
    }

    const right_inline = node => [
      FlexRowTop,
      css`justify-content: space-between`,
      css`& > .${ContentBlock} { flex-grow: 1 }`,
      node
    ]

    console.log(state.cells)

    const morph = div(
      id`root`,
      css`
        // height: 100%;
        // width: 100%;
        // overflow: hidden;
      `,
      css`
       & > * {
         margin-bottom: 10px;
       }
      `,
      ...state.cells.flatMap(cell_to_dom),
    )

    morph(root)

    const executing = document.querySelector('#executing')
    if (executing) {
      if (state.obs) {
        state.obs.disconnect()
      }
      state.obs = new IntersectionObserver(
        e => {
          const r = e[0].intersectionRatio
          const {y} = executing.getBoundingClientRect()

          const indicator = document.querySelector('#indicator')
          indicator && indicator.setAttribute('data-loc',
            r > 0 ? 'inside' :
            y < 25 ? 'below' : 'above'
          )
        },
        {
          root: null,
          rootMargin: "-25px 0px 0px 0px",
          threshold: [0],
        }
      )
      state.obs.observe(executing)
    }
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
    function make_cells(cursor, cancelled) {
      console.warn('DEBUG', {cursor, cancelled})
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

  schedule_refresh()

  function prioritize_images(msgs0) {
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
      cancelled: 'yellow',
      scheduled: 'bright-yellow',
    }
    let border_colour = colours[status] || colours.default
    const nothing_yet = cell.status == 'executing' && msgs.length == 0 // msgs.filter(m => m.msg_type != 'execute_result').length == 0
      || cell.status == 'scheduled'

    if (nothing_yet && status == 'executing') {
      border_colour = colours['scheduled']
    }

    const is_image = msg => 'image/png' in msg.data || 'image/svg+xml' in msg.data
    const prev_msgs = prioritize_images(cell.prev_msgs)
    const prev_some_img = prev_msgs.some(is_image)
    // console.log({nothing_yet, prev_some_img, prev_msgs, msgs})
    // console.log({nothing_yet, prev_msgs, msgs})
    if (prev_msgs.length > 0 && nothing_yet) {
      msgs = prev_msgs
    }
    if (msgs.length || true) {
      return [
        cell.status == 'executing' &&
          div(
            div(
              '...',
              id`indicator`,
              css`&[data-loc=inside]::before {
                content: "<"
              }`,
              css`&[data-loc=above]::before {
                content: "v"
              }`,
              css`&[data-loc=below]::before {
                content: "^"
              }`,
              css`
                position: absolute;
                right: 2px;
                color:${color_to_css('white')};
                background:${color_to_css('bright-green')};
                border: 2px ${color_to_css('black')} solid;
                padding: 2px;
                margin: 2px 4px 0px 4px;
                border-radius: 2px;
              `),
            css`
              position: sticky;
              top: 1px;
              bottom: 2em;
            `),
        pre(
          cell.status == 'executing' && id`executing`,
          // FlexColumnLeft,
          ...msgs.map(msg_to_dom),
          // pre(css`display:none;color:white;font-size:0.8em`, JSON.stringify(cell, 2, 2)),
          css`
            color:${color_to_css('white')};
            background: ${color_to_css('bright-green')};
            // background: linear-gradient(
            //   to bottom,
            //   ${color_to_css('bright-green')} 20%,
            //   ${color_to_css('black')}
            // );
            padding:0.4em;
            padding-left:0.5em;
            // margin-bottom: -0.5em;
            // margin-top: 0.1em;
            // margin-left: 0.2em;
            border-left: 0.1em ${color_to_css(border_colour)} solid;
            // overflow: visible;
            // font-size: 0.9em;
        `),
      ]
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
        div.foreign = true
        div.innerHTML = html || svg
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

main()

