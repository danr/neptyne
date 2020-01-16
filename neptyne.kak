
map global insert <a-c> '<a-;>: neptyne_setup; neptyne_complete<ret>'
map global insert <a-i> '<a-;>: neptyne_setup; neptyne_jedi icomplete<ret>'
map global insert <a-j> '<a-;>: neptyne_setup; neptyne_jedi complete<ret>'
map global insert <a-d> '<a-;>: neptyne_jedi docstring<ret>'
map global insert <a-z> '<a-;>: neptyne_jedi usages<ret>'
map global insert <a-s> '<a-;>: neptyne_jedi sig<ret>'
map global insert <a-g> '<a-;>: neptyne_jedi goto<ret>'
map global insert <a-h> '<a-;>: neptyne_inspect normal<ret>'
map global insert <a-w> '<a-;>: write<ret>'
map global normal <a-h> ': neptyne_inspect normal<ret>'

rmhooks global neptyne
hook -group neptyne global BufWritePost .*(py|go|rb) %{ try neptyne_process }


try %{
    decl -hidden str _neptyne_location %val{source}
    decl -hidden str _neptyne_tmp
    decl completions neptyne_completions
}

def neptyne_setup %{
    set -add window completers option=neptyne_completions
}

def neptyne_jedi -params 1 %{
    eval -draft -no-hooks %{
        set window _neptyne_tmp "%val{cursor_line} %val{cursor_column} neptyne_completions %val{timestamp}"
        exec \%
        echo -to-file .requests "jedi_%arg{1} %val{cursor_byte_offset} %val{client} %val{session} %opt{_neptyne_tmp}
%val{selection}"
    }
}

def neptyne_complete %{
    eval -draft -no-hooks %{
        eval -draft %{
            # first find the completion start
            try %{
                eval -draft %{
                    exec h <a-k> [\w.] <ret> l <a-/> [\w.]* <ret> <a-:> <a-\;> \;
                }
            }
            # set window _neptyne_tmp "set window neptyne_completions %val{cursor_line}.%val{cursor_column}@%val{timestamp}"
            set window _neptyne_tmp "%val{cursor_line} %val{cursor_column} neptyne_completions %val{timestamp}"
        }
        # select everything backwards from the actual cursor position
        exec Gg <a-:>
        echo -to-file .requests "complete %val{cursor_byte_offset} %val{client} %val{session} %opt{_neptyne_tmp}
%val{selection}"
    }
}
def neptyne_inspect -params 1 %{
    eval -draft -no-hooks %{
        try %{
            exec <a-i> w <a-:> ';'
        }
        exec Gg <a-:>
        echo -to-file .requests "inspect %val{cursor_byte_offset} %val{client} %val{session} %arg{1} %val{window_width} %val{window_height}
%val{selection}"
    }
}

def neptyne_process %{
    eval -draft -no-hooks %{
        try %{ decl line-specs neptyne_flags }
        try %{ decl str-list neptyne_prev_flags }
        try %{ addhl window/ flag-lines default neptyne_flags }
        try %{ update-option window neptyne-flags }
        exec \%
        echo -to-file .requests "process %val{cursor_byte_offset} %val{client} %val{session} %val{timestamp} %opt{neptyne_flags} %opt{neptyne_prev_flags}
%val{selection}"
    }
}

def neptyne %{
    nop %sh{
        path=$(dirname $kak_opt__neptyne_location)
        (xterm -ti vt340 -xrm "XTerm*decTerminalID: vt340" -xrm "XTerm*numColorRegisters: 256" -e "(python $path/neptyne.py $kak_buffile; bash)") >/dev/null 2>&1 </dev/null &
    }
}
