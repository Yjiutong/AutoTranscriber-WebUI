import threading
from typing import Dict

repo_locks: Dict[str, threading.Lock] = {}

def get_repo_lock(repo_path: str) -> threading.Lock:
    if repo_path not in repo_locks:
        repo_locks[repo_path] = threading.Lock()
    return repo_locks[repo_path]
