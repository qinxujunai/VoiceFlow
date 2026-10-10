"""Native workers must never outlive their owning UI process."""

import multiprocessing
import os
import threading
from multiprocessing.connection import wait


def watch_parent_exit(on_exit=None, *, grace_seconds=2.0):
    parent = multiprocessing.parent_process()
    if parent is None:
        return

    def watch():
        wait([parent.sentinel])
        if on_exit is not None:
            finished = threading.Event()

            def flush():
                try:
                    on_exit()
                finally:
                    finished.set()

            threading.Thread(target=flush, daemon=True).start()
            finished.wait(timeout=max(0.0, float(grace_seconds)))
        # Native inference may be stuck: Python cleanup cannot be relied on here.
        os._exit(0)

    threading.Thread(
        target=watch,
        name="voiceflow-parent-exit",
        daemon=True,
    ).start()
