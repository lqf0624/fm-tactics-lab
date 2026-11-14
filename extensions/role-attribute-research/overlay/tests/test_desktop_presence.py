from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from desktop_presence import DesktopPresence


class DesktopPresenceTests(unittest.TestCase):
    def test_suspended_page_does_not_close_after_batch_finishes(self):
        now=[0.0];busy=[False]
        presence=DesktopPresence(lambda:busy[0],lambda:now[0])
        presence.update({'page':'one','action':'open'})
        busy[0]=True;now[0]=400
        self.assertEqual(presence.status(),
            {'pages':1,'seen':True,'busy':True,'close_ready':False})
        now[0]=1000
        self.assertFalse(presence.status()['close_ready'])
        busy[0]=False
        self.assertFalse(presence.status()['close_ready'])

    def test_closed_idle_page_uses_grace_period(self):
        now=[0.0]
        presence=DesktopPresence(lambda:False,lambda:now[0])
        presence.update({'page':'one','action':'open'})
        presence.update({'page':'one','action':'close'})
        now[0]=7.9;self.assertFalse(presence.status()['close_ready'])
        now[0]=8.0;self.assertTrue(presence.status()['close_ready'])

    def test_invalid_lease_is_rejected(self):
        presence=DesktopPresence(lambda:False)
        with self.assertRaises(ValueError):presence.update({'page':'','action':'open'})
