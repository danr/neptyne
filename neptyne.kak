
map global insert <a-c> '<a-;>: neptyne_setup; neptyne_complete<ret>'
map global insert <a-h> '<a-;>: neptyne_inspect<ret>'
map global insert <a-w> '<a-;>: write<ret>'
map global normal <a-h> ': neptyne_inspect<ret>'

def neptyne_setup %{
    try %{
        decl completions neptyne_completions
    }
    set -add window completers option=neptyne_completions
    map window insert <a-c> '<a-;>: neptyne_complete<ret>'
}
def neptyne_complete %{
    eval -draft -no-hooks %{
        try %{
            exec h <a-i> w <a-:> '<a-;>;'
        } catch %{
            exec l
        }
        exec Gg <a-:>
        echo -to-file .requests "complete %val{cursor_byte_offset} %val{client} %val{session} set window neptyne_completions %val{cursor_line}.%val{cursor_column}@%val{timestamp}
%val{selection}"
    }
}
def neptyne_inspect %{
    eval -draft -no-hooks %{
        try %{
            exec <a-i> w <a-:> ';'
        }
        exec Gg <a-:>
        echo -to-file .requests "inspect %val{cursor_byte_offset} %val{client} %val{session} %val{window_width} %val{window_height}
%val{selection}"
    }
}
def neptyne %{
    nop %sh{
        (urxvt -e python /home/dan/code/neptyne/neptyne.py $kak_buffile) >/dev/null 2>&1 </dev/null &
    }
}
