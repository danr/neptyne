
map global insert <a-c> '<a-;>: neptyne-complete<ret>'
# map global insert <a-i> '<a-;>: neptyne-jedi icomplete<ret>'
# map global insert <a-j> '<a-;>: neptyne-jedi complete<ret>'
# map global insert <a-d> '<a-;>: neptyne-jedi docstring<ret>'
# map global insert <a-z> '<a-;>: neptyne-jedi usages<ret>'
# map global insert <a-s> '<a-;>: neptyne-jedi sig<ret>'
# map global insert <a-g> '<a-;>: neptyne-jedi goto<ret>'
map global insert <a-h> '<a-;>: neptyne-inspect<ret>'
map global insert <a-w> '<a-;>: write<ret>'
map global insert <a-a> '<a-;>: neptyne-process-on-insert-idle<ret>'
map global normal <a-h> ': neptyne-inspect<ret>'

# rmhooks global neptyne
# hook -group neptyne global BufWritePost .*(py|go|rb) %{ try neptyne-process }

def neptyne-enable-window-process-on-write %{
    neptyne-disable-window-process-on-write
    hook -group neptyne-process-on-write window BufWritePost .* %{ try neptyne-process }
}

def neptyne-disable-window-process-on-write %{
    rmhooks window neptyne-process-on-write
}

def neptyne-process-on-insert-idle %{
    hook -group neptyne-process-on-insert-idle window InsertIdle .* %{ try neptyne-process }
    hook -once window ModeChange pop:.*:normal %{ rmhooks window neptyne-process-on-insert-idle }
}

def neptyne-enable-process-on-idle %{
    hook -group neptyne-process-on-idle window InsertIdle .* %{ try neptyne-process }
    hook -group neptyne-process-on-idle window NormalIdle .* %{ try neptyne-process }
}

def neptyne-disable-process-on-idle %{
    rmhooks window neptyne-process-on-idle
}

def neptyne-enable-inspect-on-idle %{
    hook -group neptyne-inspect-on-idle window InsertIdle .* %{ try neptyne-inspect }
    hook -group neptyne-inspect-on-idle window NormalIdle .* %{ try neptyne-inspect }
}

def neptyne-disable-inspect-on-idle %{
    rmhooks window neptyne-inspect-on-idle
}

def neptyne-enable-window-completer %{
    try %{ decl completions neptyne_completions }
    set -add window completers option=neptyne_completions
}

def neptyne-complete-on -params 1 %{
    try %{ decl str neptyne_complete_on }
    set window neptyne_complete_on %arg{1}
    rmhooks window neptyne-complete-on
    hook -group neptyne-complete-on window InsertIdle .* %{
        try %{
            exec -draft "<esc>hGg<a-:><a-k>(%opt{neptyne_complete_on})\z<ret>"
            echo completing...
            neptyne-complete
        }
    }
}

hook -group neptyne-filetype global WinSetOption filetype=python %{
    neptyne-complete-on [.]|from\s+|import\s+
}

hook -group neptyne-filetype global WinSetOption filetype=r %{
    neptyne-complete-on [$]
}

def neptyne-request -params 1.. %{
    echo -to-file .requests "
type %arg{1}
bufname %val{bufname}
buffile %val{buffile}
cursor_line %val{cursor_line}
cursor_column %val{cursor_column}
cursor_byte_offset %val{cursor_byte_offset}
client %val{client}
session %val{session}
timestamp %val{timestamp}
window_width %val{window_width}
window_height %val{window_height}
args %arg{@}
--- ---
%val{selection}"
}

def neptyne-process %{
    eval -draft -no-hooks %{
        exec '%'
        neptyne-request process
    }
}

def neptyne-complete %{
    neptyne-enable-window-completer
    eval -draft -no-hooks %{
        exec ';Gg<a-;>'
        neptyne-request complete
    }
}

def neptyne-inspect -params 0..1 %{
    eval -draft -no-hooks %{
        exec ';Gg<a-;>'
        neptyne-request inspect %arg{@}
    }
}

def neptyne-restart %{
    neptyne-request restart
}

# def neptyne-jedi -params 1 %{
#     eval -draft -no-hooks %{
#         exec '%'
#         neptyne-request "jedi_%arg{1}"
#     }
# }

