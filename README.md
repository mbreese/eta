ETA
===

This is a python package that will create progress bars for command-line programs.

Example usage:

    from eta import ETA
    eta = ETA(ticks)
    for foo in bar:
        eta.print_status()
    eta.done()

Or, file based usage (calls tell() to get progress)

    fobj = open(fname)
    eta = ETA(os.stat(fname).st_size, fileobj=fobj)

    for line in fobj:
        eta.print_status(extra="extra message")
        ...
    eta.done()

The output is something similar to:

    20.0% - 0:04 [====>               ] ETA: 0:17 (Optional messages go here)

