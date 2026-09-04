from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CleanupBytecodeTests(unittest.TestCase):
    def test_standard_invocation_does_not_create_local_bytecode_cache(self) -> None:
        temp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp, True)
        scripts = temp / "scripts"
        scripts.mkdir()

        for name in ("post_merge_cleanup.py", "closeout_state.py"):
            shutil.copy2(ROOT / "scripts" / name, scripts / name)

        env = os.environ.copy()
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        env.pop("PYTHONPYCACHEPREFIX", None)

        result = subprocess.run(
            [sys.executable, str(scripts / "post_merge_cleanup.py"), "--help"],
            cwd=temp,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(
            (scripts / "__pycache__").exists(),
            "standard cleanup invocation created ignored bytecode residue",
        )


if __name__ == "__main__":
    unittest.main()
