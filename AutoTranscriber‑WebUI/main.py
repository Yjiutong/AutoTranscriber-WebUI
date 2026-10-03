from fastapi import FastAPI, UploadFile, File, Query
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import os
import sys
import threading
from typing import List, Dict
import subprocess
import webbrowser
import time

app = FastAPI(title="AutoTranscriber‑WebUI")

repo_locks: Dict[str, threading.Lock] = {}

def get_repo_lock(repo_path: str) -> threading.Lock:
    if repo_path not in repo_locks:
        repo_locks[repo_path] = threading.Lock()
    return repo_locks[repo_path]

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PARENT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
AUTO_TRANSCRIBER_SCRIPT = os.path.join(PARENT_DIR, "AutoTranscriber", "main.py")

FRONTEND_FOLDER = os.path.join(BASE_DIR, "frontend")
INDEX_HTML = os.path.join(FRONTEND_FOLDER, "index.html")

INPUT_DIR = os.path.join(BASE_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("==================================")
print(f"BASE_DIR: {BASE_DIR}")
print(f"AUTO_TRANSCRIBER_SCRIPT: {AUTO_TRANSCRIBER_SCRIPT}")
print(f"script exists: {os.path.exists(AUTO_TRANSCRIBER_SCRIPT)}")
print("==================================")

app.mount("/static", StaticFiles(directory=FRONTEND_FOLDER), name="static")

@app.get("/", response_class=HTMLResponse)
async def index():
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        return f.read()

def scan_files(folder: str) -> List[dict]:
    items = []
    for name in os.listdir(folder):
        full = os.path.join(folder, name)
        if os.path.isfile(full):
            items.append({"name": name})
    return items

@app.get("/api/input/list")
async def list_input():
    return {"files": scan_files(INPUT_DIR)}

@app.get("/api/output/list")
async def list_output():
    return {"files": scan_files(OUTPUT_DIR)}

@app.post("/api/audio/upload")
async def upload(file: UploadFile = File(...)):
    dest = os.path.join(INPUT_DIR, file.filename)
    with open(dest, "wb") as fp:
        fp.write(await file.read())
    return {"input_filename": file.filename}

@app.post("/api/file/delete")
async def delete_file(folder: str = Query(...), filename: str = Query(...)):
    if folder == "input":
        path = os.path.join(INPUT_DIR, filename)
    elif folder == "output":
        path = os.path.join(OUTPUT_DIR, filename)
    else:
        return {"ok": False}
    if os.path.exists(path):
        os.remove(path)
    return {"ok": True}

@app.get("/api/output/download")
async def download(filename: str = Query(...)):
    path = os.path.join(OUTPUT_DIR, filename)
    return FileResponse(path, filename=filename)

@app.get("/api/transcribe/stream")
async def transcribe_stream(input_filename: str = Query(...)):
    input_path = os.path.join(INPUT_DIR, input_filename)
    lock = get_repo_lock(AUTO_TRANSCRIBER_SCRIPT)

    def generator():
        if not os.path.exists(input_path):
            yield ("data:ERROR|输入文件不存在\n\n").encode("utf-8")
            return
        if not os.path.exists(AUTO_TRANSCRIBER_SCRIPT):
            yield ("data:ERROR|找不到AutoTranscriber脚本\n\n").encode("utf-8")
            return

        acquired = lock.acquire(timeout=3)
        if not acquired:
            yield ("data:ERROR|任务正在运行，请稍后再试\n\n").encode("utf-8")
            return
        try:
            base, ext = os.path.splitext(input_filename)
            out_name = f"{base}_result.mid"
            out_path = os.path.join(OUTPUT_DIR, out_name)

            cmd = [
                sys.executable,
                AUTO_TRANSCRIBER_SCRIPT,
                "-i", input_path,
                "-o", out_path
            ]
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env
            )
            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                if line:
                    payload = f"data:STDOUT|{line.rstrip()}\n\n"
                    yield payload.encode("utf-8")

            ret = proc.wait()
            if ret != 0:
                yield ("data:ERROR|扒谱进程异常退出\n\n").encode("utf-8")
                return
            if not os.path.exists(out_path):
                yield ("data:ERROR|未生成输出MIDI文件\n\n").encode("utf-8")
                return
            yield ("data:DONE|\n\n").encode("utf-8")
        finally:
            lock.release()

    return StreamingResponse(generator(), media_type="text/event-stream")


if __name__ == "__main__":
    host = "127.0.0.1"
    port = 8000
    proc = subprocess.Popen([
        sys.executable, "-m", "uvicorn",
        "main:app",
        "--host", host,
        "--port", str(port),
        "--workers", "1"
    ], cwd=BASE_DIR)
    print(f"\nWebUI启动: http://{host}:{port}")
    def open_browser():
        time.sleep(2.2)
        webbrowser.open(f"http://{host}:{port}")
    threading.Thread(target=open_browser, daemon=True).start()
    proc.wait()
