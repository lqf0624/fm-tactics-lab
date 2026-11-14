"""Desktop document leases that keep active batch work alive."""
import threading
import time


class DesktopPresence:
    """One lease per app document; reloads get a grace period.

    Browsers may suspend JavaScript timers in a background window. An active
    batch therefore owns a service lease independently of page heartbeats.
    """
    def __init__(self, busy, clock=time.monotonic):
        self.busy=busy;self.clock=clock
        self.lock=threading.Lock();self.pages={};self.seen=False;self.empty_since=None

    def update(self,data):
        key=data.get('page');action=data.get('action')
        if not isinstance(key,str)or not 1<=len(key)<=100 or action not in('open','close'):
            raise ValueError('Invalid desktop presence')
        with self.lock:
            if action=='open':self.pages[key]=self.clock();self.seen=True;self.empty_since=None
            else:self.pages.pop(key,None)
        return self.status()

    def status(self):
        with self.lock:
            now=self.clock()
            # Chromium aggressively throttles or fully suspends timers in an
            # app window while long native batches run or the window is in the
            # background. A stale heartbeat therefore does not mean the user
            # closed the window. Only the explicit pagehide lease release may
            # remove a page; the tray menu remains the crash-recovery exit.
            if self.pages:self.empty_since=None
            elif self.seen and self.empty_since is None:self.empty_since=now
            active=bool(self.busy())
            close_ready=(not active and self.empty_since is not None and now-self.empty_since>=8)
            return {'pages':len(self.pages),'seen':self.seen,'busy':active,'close_ready':close_ready}
