
map global insert <a-c> '<a-;>: neptyne-enable-window-completer; neptyne-complete<ret>'
map global insert <a-i> '<a-;>: neptyne-enable-window-completer; neptyne-jedi icomplete<ret>'
map global insert <a-j> '<a-;>: neptyne-enable-window-completer; neptyne-jedi complete<ret>'
map global insert <a-d> '<a-;>: neptyne-jedi docstring<ret>'
map global insert <a-z> '<a-;>: neptyne-jedi usages<ret>'
map global insert <a-s> '<a-;>: neptyne-jedi sig<ret>'
map global insert <a-g> '<a-;>: neptyne-jedi goto<ret>'
map global insert <a-h> '<a-;>: neptyne-inspect normal<ret>'
map global insert <a-w> '<a-;>: write<ret>'
map global insert <a-a> '<a-;>: neptyne-process-on-insert-idle<ret>'
map global normal <a-h> ': neptyne-inspect normal<ret>'

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
    hook -once window ModeChange pop:.*:normal %{ rmhooks window neptyne-insert-idle }
}

def neptyne-enable-process-on-idle %{
    hook -group neptyne-process-on-idle window InsertIdle .* %{ try neptyne-process }
    hook -group neptyne-process-on-idle window NormalIdle .* %{ try neptyne-process }
}

def neptyne-disable-process-on-idle %{
    rmhooks window neptyne-process-on-idle
}

def neptyne-enable-window-completer %{
    try %{ decl completions neptyne_completions }
    set -add window completers option=neptyne_completions
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

def neptyne-jedi -params 1 %{
    eval -draft -no-hooks %{
        exec '%'
        neptyne-request "jedi_%arg{1}"
    }
}

def neptyne-complete %{
    eval -draft -no-hooks %{
        exec ';Gg<a-;>'
        neptyne-request complete
    }
}

def neptyne-inspect %{
    eval -draft -no-hooks %{
        exec ';Gg<a-;>'
        neptyne-request inspect
    }
}

