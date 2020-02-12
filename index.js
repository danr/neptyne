
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
    pre {
      margin: 0;
    }
    pre, body {
      font-size: 22px;
      // font-family: 'Source Serif Pro';
      font-family: 'Consolas';
      letter-spacing: -0.04em;
      font-weight: 400 !important;
      background: linear-gradient(to bottom right, ${color_to_css('bright-green')} 20%, ${color_to_css('black')});
    }
    body {
      margin: 0;
      // overflow: hidden;
    }
    span {
      white-space: pre;
    }
  `

  let rAF = k => window.requestAnimationFrame(k)

  window.schedule_refresh = function schedule_refresh() {
    rAF(actual_refresh)
    rAF = x => 0
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
        height: 100vh;
        width: 100vw;
        // overflow: hidden;
      `,
      css`
       & > * {
         margin-bottom: 10px;
       }
      `,
      ...state.cells.map(cell_to_dom),
    )

    morph(root)
  }

  state.cells = state.cells || []

  function update_cell_data(msg) {
    state.cells = msg
    // console.log(state.cells)
  }

  // console.log(state.cells)

  websocket.onmessage = function on_message(msg) {
    // console.log({msg})
    update_cell_data(JSON.parse(msg.data))
    schedule_refresh()
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
      executing: 'green',
      scheduled: 'bright-yellow',
    }
    const border_colour = colours[status] || colours.default
    const nothing_yet = cell.status == 'executing' && msgs.filter(m => m.msg_type != 'execute_result').length == 0
      || cell.status == 'scheduled'
    const is_image = msg => 'image/png' in msg.data || 'image/svg+xml' in msg.data
    const prev_msgs = prioritize_images(cell.prev_msgs)
    const prev_some_img = prev_msgs.some(is_image)
    // console.log({nothing_yet, prev_some_img, prev_msgs, msgs})
    // console.log({nothing_yet, prev_msgs, msgs})
    if (prev_msgs.length > 0 && nothing_yet) {
      msgs = prev_msgs
    }
    if (msgs.length) {
      return pre(
        FlexColumnLeft,
        ...msgs.map(msg_to_dom),
        // pre(css`display:none;color:white;font-size:0.8em`, JSON.stringify(cell, 2, 2)),
        css`
          color:${color_to_css('white')};
          background: linear-gradient(to bottom right, ${color_to_css('bright-green')} 20%, ${color_to_css('black')});
          padding:0.4em;
          padding-left:0.5em;
          // margin-bottom: -0.5em;
          // margin-top: 0.1em;
          // margin-left: 0.2em;
          // z-index: 1;
          border-left: 0.1em ${color_to_css(border_colour)} solid;
          // overflow: overlay;
          // max-height: 50vh;
          // font-size: 0.9em;
          // order:-1;
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
        div.style.background = 'white'
        div.style.display = 'inline-block'
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

