"""Exercise real MPQ tools when native binaries or Docker tool paths are available."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACK = os.environ.get("MPQPACK", str(ROOT / "client-patch/mpqpack"))
READ = os.environ.get("MPQREAD", str(ROOT / "client-patch/mpqread"))


@unittest.skipUnless(shutil.which(PACK) and shutil.which(READ), "MPQ tools unavailable")
class MpqToolsTests(unittest.TestCase):
    def test_archive_growth_preserves_files_and_allows_replacement(self):
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp)
            archive = stage / "patch.mpq"
            source = stage / "source"
            extracted = stage / "extracted"
            expected = {}
            # Exceed the initial archive capacity several times, as addon bundling does.
            for index in range(64):
                internal = f"Interface\\AddOns\\EraTalents\\file-{index}.lua"
                content = f"-- Русский текст {index}\n".encode("utf-8")
                source.write_bytes(content)
                subprocess.run([PACK, str(archive), internal, str(source)],
                               check=True, capture_output=True)
                expected[internal] = content
            first = next(iter(expected))
            expected[first] = b"-- replaced\n"
            source.write_bytes(expected[first])
            subprocess.run([PACK, str(archive), first, str(source)],
                           check=True, capture_output=True)
            for internal, content in expected.items():
                subprocess.run([READ, str(archive), internal, str(extracted)],
                               check=True, capture_output=True)
                self.assertEqual(extracted.read_bytes(), content, internal)


if __name__ == "__main__":
    unittest.main()
