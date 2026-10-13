"""Summarize bounded Docker/GPU samples from the Phase 7 load window."""
from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'local/phase-7/load-final-resources.jsonl'
OUTPUT = ROOT / 'local/phase-7/final-resource-summary.json'


def mib(value: str) -> float:
    match = re.fullmatch(r'([0-9.]+)(KiB|MiB|GiB)', value)
    if not match:
        raise ValueError(value)
    scale = {'KiB': 1 / 1024, 'MiB': 1, 'GiB': 1024}[match.group(2)]
    return float(match.group(1)) * scale


def main() -> None:
    rows = [json.loads(line) for line in SOURCE.read_text().splitlines() if line.strip()]
    if not rows:
        raise RuntimeError('No resource samples')
    peaks: dict[str, float] = {}
    gpu = []
    for row in rows:
        gpu.append(int(row['gpu'].split(',')[0].strip()))
        for container in row['containers']:
            used = mib(container['MemUsage'].split('/')[0].strip())
            name = container['Name']
            peaks[name] = max(peaks.get(name, 0), used)
    api = peaks['private-documents-phase7-api-1']
    ollama = peaks['private-documents-phase7-ollama-1']
    result = {
        'status': 'passed' if api <= 1536 and ollama <= 4096 and max(gpu) <= 4608 else 'failed',
        'samples': len(rows), 'first_utc': rows[0]['utc'], 'last_utc': rows[-1]['utc'],
        'container_peak_mib_sampled': {key: round(value, 2) for key, value in peaks.items()},
        'host_gpu_used_peak_mib_sampled': max(gpu),
        'budgets_mib': {'api': 1536, 'ollama': 4096, 'gpu': 4608},
        'observation_limit': 'Sampling, not continuous maxima. GPU number is whole-host used VRAM, including unrelated processes; it is a conservative upper bound for this lab.'
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
