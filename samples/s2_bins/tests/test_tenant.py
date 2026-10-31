"""The sample's door into the shop (service/tenant.py): an answer cut short is an error the service already handles.

    python3 -m unittest discover -s samples/s2_bins/tests -p 'test_*.py'
"""
import http.client
import pathlib
import sys
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "service"))
import tenant  # noqa: E402


def cut_answer(*args, **kwargs):
    """What ``urlopen`` gives back when the answer starts and the connection closes before its end: reading it raises
    ``http.client.IncompleteRead``, an ``HTTPException`` that is not an ``OSError``."""
    class Answer:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, *n):
            raise http.client.IncompleteRead(b"")
    return Answer()


class AnswerCutShort(unittest.TestCase):
    def test_an_answer_cut_short_is_a_tenant_error_never_a_crash(self):
        t = tenant.Tenant("https://shop.example", "k", "s")
        with mock.patch.object(tenant.urllib.request, "urlopen", cut_answer):
            with self.assertRaises(tenant.TenantError) as e:
                t.get("Item", "X")
        self.assertIn("IncompleteRead", str(e.exception))


if __name__ == "__main__":
    unittest.main()
