# neptyne
​
[![IRC][IRC Badge]][IRC]

Editor-agnostic jupyter kernel interaction and [kakoune](http://kakoune.org) integration

## Installation and usage

Have the python kernel installed and run

```
python install . --user
```

Now run

```
neptyne FILES...
```

In the directory you want some files to be viewed. Now open your browser and start editing and saving the files:

```
cromium --app=http://localhost:8234
```

## Usage with kakoune

Inside kakoune run

```
source %sh{neptyne kak_source}
```

Now you can use eg `neptyne-enable-process-on-idle` to rerun the kernel on NormalIdle and InsertIdle.
No files need to be listed on the command line, communication goes via a file called `.requests`.

## License

MIT

[IRC]: https://webchat.freenode.net?channels=kakoune
[IRC Badge]: https://img.shields.io/badge/IRC-%23kakoune-blue.svg
