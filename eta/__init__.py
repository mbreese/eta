'''
Displays a progress meter and an ETA calculation based upon either a user supplied number (out of a total)
or based upon a file and it's size.  In the case of a file, the position information is calculated from the
tell() method.  The ETA is calculated by taking the average of the last 50 ETA calculations so that the numbers
can be smoothed out.  Additionally, you can set a 'modulo' parameter that will only display a message every
N iterations (thus relieving you from having to calculate it).

Marcus R Breese <marcus@breese.com>
Created: Jan 2010
Last update: Oct 2012

'''
import sys
import datetime
import os

import threading
import socket


def eta_open_iter(fname, callback=None):
    f = open(fname)  # not using with to support 2.4
    _eta = ETA(os.stat(fname).st_size, fileobj=f)
    extra = ''
    for line in f:
        if callback:
            extra = callback()
        _eta.print_status(extra=extra)
        yield line
    _eta.done()
    f.close()


class _NoopETA(object):
    def __init__(self, *args, **kwargs):
        pass

    def done(self):
        pass

    def print_status(self, *args, **kwargs):
        pass


class _SocketETA(object):
    def __init__(self, total, modulo=None, fileobj=None, *args, **kwargs):
        self.total = total
        self.started = 0
        self.elapsed = 0
        self.extra = ''
        self.current = 0
        self.last_step = 0
        self.end = False

        try:
            fileobj.fileobj.tell()
            self.fileobj = fileobj.fileobj
        except:
            self.fileobj = fileobj

        self._sock = None
        self._t = None
        self.start()

    def start(self):
        if not self._t and not self._sock:
            self._t = threading.Thread(target=self._start_listener, args = ())
            self._t.daemon = True
            self._t.start()

            self._shutdown = False

    def _start_listener(self):
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        socket_fname = "/tmp/eta-%s" % os.getpid()
        try:
            os.remove(socket_fname)
        except OSError:
            pass
        
        self._sock.bind(socket_fname)
        self._sock.listen(1)

        try:
            while not self._shutdown:
                conn, addr = self._sock.accept()
                conn.sendall(self.get_status())
                conn.close()
        except:
            pass

        try:
            os.remove(socket_fname)
        except OSError:
            pass

    def done(self):
        self._shutdown = True
        if self._sock:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except:
                pass
            self._sock.close()
            self._sock = None
        if self._t:
            self._t.join(30)
            self._t = None

    def print_status(self, current=None, extra='', *args, **kwargs):
        self.current = current
        self.extra = extra

        if self.started == 0:
            now = datetime.datetime.now()
            self.started = now
            self.elapsed = 0

        if self.current is None and not self.fileobj:
            self.current = self.last_step + self.step
            self.last_step = self.current

    def get_status(self):
        now = datetime.datetime.now()
        td = now - self.started
        elapsed_sec = (td.days * 86400) + td.seconds

        if elapsed_sec < 0:
            elapsed_sec = 0

        elapsed_time = pretty_time(elapsed_sec)

        if self.current is None and self.fileobj:
            current = self.fileobj.tell()
        else:
            current = self.current

        pct = float(current) / self.total
        if pct > 1.0:
            pct = 1.0
        
        if pct < 0:
            est_remaining = 'Unknown'
        else:
            est_remaining = pretty_time((elapsed_sec / pct) - elapsed_sec)

        if 'JOB_ID' in os.environ:
            jobid = 'Job ID   : %s\n' % os.environ['JOB_ID']
        else:
            jobid = None

        return """\
%sCommand  : %s

Started  : %s
Elapsed  : %s
Remaining: %s

Total    : %s
Current  : %s (%.2f%%)
%s
""" % (jobid if jobid else '', ' '.join(sys.argv), self.started, elapsed_time, est_remaining, self.total, self.current, pct*100, '\n%s' % self.extra if self.extra else '')


class _ETA(object):
    def __init__(self, total, modulo=None, fileobj=None, window=50, step=1, prog_bar_length=20, min_ms_between_updates=None):
        self.started = datetime.datetime.now()
        self.last = []
        self.total = total
        self.spinner = "|/-\\"
        self.spinner_pos = 0
        self.i = 0
        self.modulo = modulo

        try:
            fileobj.fileobj.tell()
            self.fileobj = fileobj.fileobj
        except:
            self.fileobj = fileobj

        self.last_len = 0
        self.step = step
        self.last_step = 0
        self.window = window
        self.prog_bar_length = prog_bar_length
        
        if min_ms_between_updates is not None:
            self.min_ms_between_updates = min_ms_between_updates  # in milliseconds
        elif sys.stderr.isatty():
            self.min_ms_between_updates = 200
        else:
            self.min_ms_between_updates = 10000

        self._last_update = 0
        self._started = 0

    def pct(self, current):
        if current < self.total:
            return float(current) / self.total
        return 1

    def ave_remaining(self, current, elapsed_sec):
        if len(self.last) > self.window:
            self.last = self.last[-self.window:]
        rem = self.remaining(current, elapsed_sec)
        if rem:
            self.last.append(rem)

        acc = 0.0
        for p in self.last:
            acc += p

        if len(self.last) > 0:
            return acc / len(self.last)
        else:
            return None

    def remaining(self, current, elapsed_sec):
        # elapsed = (datetime.datetime.now() - self.started).seconds
        pct = self.pct(current)
        if pct > 0:
            eta = elapsed_sec / self.pct(current)
        else:
            return None

        remaining = eta - elapsed_sec
        return remaining

    def done(self, overwrite=True):
        if overwrite:
            sys.stderr.write('\r')
            sys.stderr.write(' ' * self.last_len)
            sys.stderr.write('\b' * self.last_len)

        elapsed = (datetime.datetime.now() - self.started).seconds
        sys.stderr.write("Done! (%s)\n" % pretty_time(elapsed))
        sys.stderr.flush()

    def print_status(self, current=None, extra='', overwrite=True):
        self.i += 1
        if self.modulo and self.i % self.modulo > 0:
            return

        now = datetime.datetime.now()

        if self._last_update:
            elapsed = (now - self._last_update)
            millis = (elapsed.seconds * 1000) + (elapsed.microseconds / 1000)
            if millis < self.min_ms_between_updates:
                return

        self._last_update = now

        if not self._started:
            self._started = now
            elapsed_sec = 0
        else:
            td = now - self.started
            elapsed_sec = (td.days * 86400) + td.seconds

        if current is None:
            if self.fileobj:
                current = self.fileobj.tell()
            else:
                current = self.last_step + self.step

        self.last_step = current

        if overwrite:
            sys.stderr.write("\r")
            if self.last_len:
                sys.stderr.write(' ' * self.last_len)
            sys.stderr.write("\r")

        if extra:
            extra = " | %s" % extra

        if self.prog_bar_length > 0:
            pct_current = self.pct(current)
            completed = int(self.prog_bar_length * pct_current)
            remaining = self.prog_bar_length - completed
            prog_bar = '[%s>%s] ' % ('=' * completed, ' ' * (remaining - 1))
        else:
            prog_bar = ''

        line = "%6.1f%% %s %s %sETA: %s%s" % (pct_current * 100,
                                         self.spinner[self.spinner_pos],
                                         pretty_time(elapsed_sec),
                                         prog_bar,
                                         pretty_time(self.ave_remaining(current, elapsed_sec)),
                                         extra)
        width, height = getTerminalSize()
        if len(line) > width:
            line = line[:width]
        sys.stderr.write(line)

        if not overwrite:
            sys.stderr.write('\n')
        else:
            self.last_len = len(line)

        self.spinner_pos += 1
        if self.spinner_pos > 3:
            self.spinner_pos = 0
        sys.stderr.flush()


def pretty_time(secs):
    if secs is None:
        return ""

    if secs > 60:
        mins, secs = divmod(secs, 60)
        if mins > 60:
            hours, mins = divmod(mins, 60)
        else:
            hours = 0
    else:
        mins = 0
        hours = 0

    if hours:
        s = "%d:%02d:%02d" % (hours, mins, secs)
    elif mins:
        s = "%d:%02d" % (mins, secs)
    else:
        s = "0:%02d" % secs

    return s




#
# getTerminalSize from StackOverflow:
# http://stackoverflow.com/questions/566746/how-to-get-console-window-width-in-python


def getTerminalSize():
    def ioctl_GWINSZ(fd):
        try:
            import fcntl
            import termios
            import struct
            cr = struct.unpack('hh', fcntl.ioctl(fd, termios.TIOCGWINSZ,
        '1234'))
        except:
            return None
        return cr
    cr = ioctl_GWINSZ(0) or ioctl_GWINSZ(1) or ioctl_GWINSZ(2)

    if not cr:
        try:
            fd = os.open(os.ctermid(), os.O_RDONLY)
            cr = ioctl_GWINSZ(fd)
            os.close(fd)
        except:
            pass

    if not cr:
        try:
            cr = (os.environ['LINES'], os.environ['COLUMNS'])
        except:
            cr = (25, 80)

    return int(cr[1]), int(cr[0])


if 'HIDE_ETA' in os.environ:
    ETA = _NoopETA
elif 'SOCKET_ETA' in os.environ:
    ETA = _SocketETA
elif not sys.stderr.isatty() and 'SHOW_ETA' not in os.environ:
    ETA = _NoopETA
else:
    ETA = _ETA
