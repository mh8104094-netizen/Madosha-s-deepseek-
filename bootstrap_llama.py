from __future__ import annotations

import ctypes.util
import os
import pathlib
import subprocess
import sys
import tarfile
import urllib.request

RUNTIME_DIR = pathlib.Path("/tmp/xmind-llama")
MODEL_DIR = pathlib.Path("/tmp/xmind-models")
ARCHIVE = pathlib.Path("/tmp/llama-linux-x64.tar.gz")
MODEL = MODEL_DIR / "Qwen3-0.6B-Q4_0.gguf"

LLAMA_URL = os.getenv(
    "XMIND_LLAMA_BINARY_URL",
    "https://github.com/ggml-org/llama.cpp/releases/download/b10964/llama-b10964-bin-ubuntu-x64.tar.gz",
)
MODEL_URL = os.getenv(
    "XMIND_MODEL_URL",
    "https://huggingface.co/ggml-org/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_0.gguf?download=true",
)
CTX = os.getenv("XMIND_LOCAL_CONTEXT", "1024")
THREADS = os.getenv("XMIND_LOCAL_THREADS", "2")
PORT = os.getenv("XMIND_LLAMA_PORT", "11435")


def log(msg: str) -> None:
    print(f"[LLAMA-BOOT] {msg}", flush=True)


def ensure_openmp() -> None:
    if ctypes.util.find_library("gomp"):
        log("GNU OpenMP runtime already available")
        return
    apt = pathlib.Path("/usr/bin/apt-get")
    if not apt.exists():
        raise RuntimeError("libgomp.so.1 is missing and apt-get is unavailable")
    log("libgomp.so.1 missing; installing Debian libgomp1...")
    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"
    subprocess.run([str(apt), "update", "-qq"], check=True, env=env)
    subprocess.run(
        [str(apt), "install", "-y", "--no-install-recommends", "libgomp1"],
        check=True,
        env=env,
    )
    if not ctypes.util.find_library("gomp"):
        raise RuntimeError("libgomp1 installation completed but libgomp is still unavailable")
    log("libgomp1 installed successfully")


def download(url: str, dest: pathlib.Path, label: str) -> None:
    if dest.exists() and dest.stat().st_size > 1024 * 1024:
        log(f"{label} already present: {dest.stat().st_size / 1_000_000:.1f} MB")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "X-MIND/0.5"})
    log(f"downloading {label}...")
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        next_report = 50 * 1024 * 1024
        while True:
            chunk = r.read(4 * 1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if got >= next_report:
                if total:
                    log(f"{label}: {got / 1_000_000:.0f}/{total / 1_000_000:.0f} MB")
                else:
                    log(f"{label}: {got / 1_000_000:.0f} MB")
                next_report += 50 * 1024 * 1024
    tmp.replace(dest)
    log(f"{label} downloaded: {dest.stat().st_size / 1_000_000:.1f} MB")


def find_server() -> pathlib.Path:
    candidates = list(RUNTIME_DIR.rglob("llama-server")) or list(RUNTIME_DIR.rglob("llama-server*"))
    for p in candidates:
        if p.is_file():
            p.chmod(p.stat().st_mode | 0o111)
            return p
    raise FileNotFoundError("llama-server not found in extracted archive")


def main() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    ensure_openmp()
    download(LLAMA_URL, ARCHIVE, "llama.cpp runtime")
    if not any(RUNTIME_DIR.iterdir()):
        log("extracting llama.cpp runtime...")
        with tarfile.open(ARCHIVE, "r:gz") as tf:
            tf.extractall(RUNTIME_DIR, filter="data")
        log("llama.cpp runtime extracted")

    download(MODEL_URL, MODEL, "Qwen3-0.6B Q4_0")
    server = find_server()
    log(f"llama-server: {server}")

    lib_dirs = {str(server.parent), str(RUNTIME_DIR)}
    for lib in RUNTIME_DIR.rglob("*.so*"):
        lib_dirs.add(str(lib.parent))
    env = os.environ.copy()
    existing = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = ":".join(sorted(lib_dirs)) + (":" + existing if existing else "")

    args = [
        str(server),
        "-m", str(MODEL),
        "--host", "127.0.0.1",
        "--port", PORT,
        "-c", CTX,
        "-t", THREADS,
        "-np", "1",
        "--cache-ram", "0",
        "--no-warmup",
        "--jinja",
        "--reasoning-budget", "0",
    ]
    log("starting local llama.cpp cortex: " + " ".join(args))
    os.execvpe(str(server), args, env)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {type(e).__name__}: {e}")
        sys.exit(1)
