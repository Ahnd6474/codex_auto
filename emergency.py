import os
import signal
import psutil

def kill_all_child_processes():
    parent = psutil.Process(os.getpid())
    children = parent.children(recursive=True)

    # 먼저 terminate
    for child in children:
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass

    gone, alive = psutil.wait_procs(children, timeout=3)

    # 남아 있으면 kill
    for child in alive:
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass