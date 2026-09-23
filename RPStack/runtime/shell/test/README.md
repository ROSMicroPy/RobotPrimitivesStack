# Shell tests

Run from the repository root:

```sh
python3 -m unittest discover -s RPStack/runtime/shell/test -v
```

Tests cover lazy discovery, command precedence, external registration, script
startup, shared dispatch, JSON preservation, node task cancellation, filesystem
operations, optional waits alongside stop, and installation of the two mip
packages into an isolated tree. Hardware commands are not executed.
