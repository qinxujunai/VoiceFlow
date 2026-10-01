"""Native workers must never outlive their owning UI process."""

import multiprocessing
import os
import threading
from multiprocessing.connection import wait


def watch_parent_exit():
    parent = multiprocessing.parent_process()
    if parent is None:
        return

    def watch():
        wait([parent.sentinel])
        # Native inference may be stuck: Python cleanup cannot be relied on here.
        os._exit(0)

    threading.Thread(
        target=watch,
        name="voiceflow-parent-exit",
        daemon=True,
    ).start()
