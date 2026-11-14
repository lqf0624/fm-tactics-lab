from copy import deepcopy
from pathlib import Path
import hashlib
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from generate_profile import verify_release_profile


class ReleaseProfileTests(unittest.TestCase):
    def test_range_bytes_and_all_other_metadata_must_match(self):
        profile={'reference_sha256':'example','ranges':[{'rva':16,'purpose':'entry','hex':'0102'}]}
        metadata={'reference_sha256':'example','ranges':[{'rva':16,'purpose':'entry','size':2,
            'sha256':hashlib.sha256(bytes([1,2])).hexdigest()}]}
        verify_release_profile(profile,metadata)
        for key,value in [('hex','0103'),('rva',17)]:
            changed=deepcopy(profile);changed['ranges'][0][key]=value
            with self.assertRaises(ValueError):verify_release_profile(changed,metadata)
        changed=deepcopy(profile);changed['reference_sha256']='wrong'
        with self.assertRaises(ValueError):verify_release_profile(changed,metadata)
