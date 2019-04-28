
def neptyne_setup %{
    try %{
        decl completions neptyne_completions
    }
    set -add window completers option=neptyne_completions
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
map global insert <a-c> '<a-;>: neptyne_complete<ret>'
map global insert <a-h> '<a-;>: neptyne_inspect<ret>'
map global normal <a-h> ': neptyne_inspect<ret>'

