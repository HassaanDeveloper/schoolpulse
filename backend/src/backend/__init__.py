"""SchoolPulse backend package.

Ensures this package's parent directory (``src/``) is importable before any
sibling ``backend.*`` import runs.

Vercel resolves the entrypoint as ``src.backend.main`` (a namespace package,
because ``src/`` has no ``__init__.py``), so ``src/`` itself is never placed on
``sys.path`` by the host.  Without this bootstrap, ``from backend.core...``
inside ``main.py`` raises ``ModuleNotFoundError`` at cold start.  Locally the
same import is satisfied by the editable-install ``.pth`` file, which is why the
failure only shows up after deploying.
"""

import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent.parent)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
