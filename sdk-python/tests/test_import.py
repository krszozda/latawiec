"""What a first `import latawiec` says for itself."""

import os
import subprocess
import sys
from pathlib import Path

# The warning knobs of whoever runs the suite would change the answer, and the
# reader this is about has neither set.
INHERITED_FILTERS = ("PYTHONWARNINGS", "PYTHONDEVMODE")


def test_a_first_import_prints_nothing(tmp_path: Path) -> None:
    """Python compiles a dependency once per install and reports its
    questionable docstrings while doing it, so only a cold bytecode cache
    shows what someone installing this package sees. Anything printed under
    the default filters is something they would have to read, so the
    assertion is the whole of stderr rather than one category.
    """
    env = {name: value for name, value in os.environ.items() if name not in INHERITED_FILTERS}
    env["PYTHONPYCACHEPREFIX"] = str(tmp_path)

    done = subprocess.run(
        [sys.executable, "-c", "import latawiec"], capture_output=True, text=True, env=env
    )

    assert done.returncode == 0, done.stderr
    assert done.stderr == ""
