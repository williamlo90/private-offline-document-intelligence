"""Run frozen Phase 6 splits under one dedicated, offline Linux Ollama daemon."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

import psutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "local/phase-6" / (sys.argv[1] if len(sys.argv) > 1 else "attempt-1")
PROFILE = json.loads((ROOT / "config/ollama-profile.json").read_text(encoding="utf-8"))
DAEMON = Path("/home/william/project07-lab-runtime/ollama/bin/ollama")
MODEL_ROOT = Path("/home/william/project07-phase6-models")


def gpu_free_mib() -> int | None:
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                                capture_output=True, text=True, timeout=4, check=True)
        return int(result.stdout.strip().splitlines()[0])
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def main() -> None:
    if OUT.name not in {"attempt-1", "attempt-2", "attempt-3", "repair-probe", "invalid-probe", "final", "final-2", "final-3", "final-4", "final-5", "final-6", "final-7", "final-8"}:
        raise RuntimeError("Invalid evidence run name")
    if sys.platform != "linux" or sorted(name for _, name in socket.if_nameindex()) != ["lo"]:
        raise RuntimeError("Run in Linux loopback-only user/network namespace")
    if not DAEMON.is_file():
        raise RuntimeError("Pinned Linux Ollama runtime missing")
    lock=json.loads((ROOT/"config/ollama-runtime-lock.json").read_text(encoding="utf-8"))
    manifest=MODEL_ROOT/"manifests/registry.ollama.ai/library/qwen3/4b-instruct-2507-q4_K_M"
    blob=MODEL_ROOT/"blobs"/("sha256-"+lock["model"]["gguf_sha256"])
    if (not manifest.is_file() or not blob.is_file()
        or hashlib.sha256(manifest.read_bytes()).hexdigest()!=lock["model"]["manifest_sha256"]):
        raise RuntimeError("Local Linux model manifest pin mismatch")
    digest=hashlib.sha256()
    with blob.open('rb') as stream:
        while chunk:=stream.read(1024*1024):digest.update(chunk)
    if digest.hexdigest()!=lock["model"]["gguf_sha256"]:
        raise RuntimeError("Local Linux GGUF pin mismatch")
    if psutil.virtual_memory().available < 3 * 1024**3:
        raise RuntimeError("Insufficient free Linux RAM before model load")
    free_vram = gpu_free_mib()
    if free_vram is not None and free_vram < 4000:
        raise RuntimeError("Insufficient GPU free VRAM before model load")
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("development-native.json", "heldout-native.json", "supervisor.json"):
        if (OUT / name).exists():
            raise RuntimeError(f"Refusing to overwrite prior Phase 6 evidence: {name}")
    env = {**os.environ, "PYTHONPATH": str(ROOT), "OLLAMA_HOST": f"127.0.0.1:{PROFILE['port']}",
           "OLLAMA_MODELS": str(MODEL_ROOT), "OLLAMA_NO_CLOUD": "1",
           "OLLAMA_MAX_LOADED_MODELS": "1", "OLLAMA_NUM_PARALLEL": "1", "OLLAMA_KEEP_ALIVE": "0"}
    env["PRIVATE_TESSERACT"] = "/home/william/project07-lab-runtime/usr/bin/tesseract"
    env["PRIVATE_TESSDATA"] = str(ROOT / "local/ocr/tessdata")
    env["LD_LIBRARY_PATH"] = "/home/william/project07-lab-runtime/usr/lib/x86_64-linux-gnu:" + env.get("LD_LIBRARY_PATH", "")
    opener = build_opener(ProxyHandler({}))
    started = time.monotonic()
    peak_rss = 0
    min_free_ram = psutil.virtual_memory().available
    min_free_vram = free_vram
    error = None
    daemon = subprocess.Popen([str(DAEMON), "serve"], cwd=DAEMON.parent, env=env,
                              stdout=(OUT / "ollama.log").open("w"), stderr=subprocess.STDOUT)
    try:
        for _ in range(100):
            if daemon.poll() is not None:
                raise RuntimeError("Ollama daemon exited during startup")
            try:
                with opener.open(f"http://127.0.0.1:{PROFILE['port']}/api/version", timeout=1) as response:
                    version = json.load(response)["version"]
                break
            except (URLError, TimeoutError):
                time.sleep(.1)
        else:
            raise RuntimeError("Ollama daemon startup timeout")
        if version != "0.40.3":
            raise RuntimeError(f"Ollama runtime version drift: {version}")
        for split in (("repair",) if OUT.name in {"repair-probe","invalid-probe"} else ("development", "regression-v1", "regression-v2", "regression-v3", "regression-v4", "regression-v5", "heldout-v6")):
            report = OUT / f"{split}-native.json"
            command = ([sys.executable, "-m", "scripts.probe_phase6_invalid" if OUT.name == "invalid-probe" else "scripts.probe_phase6_repair", str(report)]
                       if split == "repair" else [sys.executable, "-m", "scripts.evaluate_phase6", split, str(report)])
            with (OUT / f"{split}-worker.log").open("w", encoding="utf-8") as log:
                worker = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
                while worker.poll() is None:
                    total_rss = 0
                    sampled_pids = set()
                    for process in (daemon, worker):
                        try:
                            process_info = psutil.Process(process.pid)
                            for member in [process_info, *process_info.children(recursive=True)]:
                                if member.pid not in sampled_pids and member.is_running():
                                    sampled_pids.add(member.pid)
                                    total_rss += member.memory_info().rss
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    peak_rss = max(peak_rss, total_rss)
                    min_free_ram = min(min_free_ram, psutil.virtual_memory().available)
                    sample_vram = gpu_free_mib()
                    if sample_vram is not None:
                        min_free_vram = sample_vram if min_free_vram is None else min(min_free_vram, sample_vram)
                    if min_free_ram < 1024**3:
                        worker.kill()
                        error = "Linux RAM reserve below 1 GiB"
                        break
                    if time.monotonic() - started > 1800:
                        worker.kill()
                        error = "Phase 6 lab timeout"
                        break
                    time.sleep(.5)
                worker.wait()
                if worker.returncode or error:
                    raise RuntimeError(f"{split} evaluation failed: {error or worker.returncode}; see {log.name}")
            if split != "repair" and not json.loads(report.read_text(encoding="utf-8"))["gate_passed"]:
                raise RuntimeError(f"{split} quality gate failed; later split remains sealed")
            print(f"{split} report: {report}", flush=True)
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        try:
            children = psutil.Process(daemon.pid).children(recursive=True) if daemon.poll() is None else []
        except psutil.NoSuchProcess:
            children = []
        if daemon.poll() is None:
            daemon.terminate()
            try:
                daemon.wait(timeout=10)
            except subprocess.TimeoutExpired:
                daemon.kill()
                daemon.wait(timeout=10)
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(children, timeout=5)
        for child in alive:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        summary = {"status": "passed" if error is None else "failed", "error": error,
                   "runtime": "Ollama 0.40.3", "model": PROFILE["model"],
                   "model_asset_root": str(MODEL_ROOT), "model_asset_sha256_verified": lock["model"]["gguf_sha256"],
                   "boundary": "Linux loopback-only user/network namespace; no host network interruption",
                   "sampled_peak_process_tree_rss_gib": round(peak_rss / 1024**3, 3),
                   "minimum_linux_free_ram_gib": round(min_free_ram / 1024**3, 3),
                   "minimum_gpu_free_mib": min_free_vram,
                   "seconds": round(time.monotonic() - started, 3),
                   "sampling_limits": "0.5-second process-tree RSS and GPU snapshots; not a hard peak bound"}
        (OUT / "supervisor.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
