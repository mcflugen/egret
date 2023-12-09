# egret

The *egret* utility searches directory trees for input files, selecting lines
that match a pattern.  By default, a pattern matches an input line if the
regular expression in the pattern matches the input line without its
trailing newline.  An empty expression matches every line.  Each input line that
matches at least one of the patterns is written to the standard output.
