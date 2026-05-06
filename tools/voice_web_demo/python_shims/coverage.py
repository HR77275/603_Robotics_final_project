"""Hide incompatible system coverage.py from numba during Whisper subprocesses.

Ubuntu 22.04 may provide an older ``coverage`` package while user-site
``openai-whisper`` installs a newer ``numba``. Some Numba versions import
``coverage.types`` at module import time if any coverage package is present.
Raising ImportError makes Numba take its normal no-coverage path.
"""

raise ImportError("coverage disabled for CS603 Whisper subprocess")
