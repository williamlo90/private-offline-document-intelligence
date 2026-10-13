"""Read-only host memory guard; never stops unrelated processes."""
import os

def available_memory_bytes():
    if os.name=='nt':
        import ctypes
        class MemoryStatus(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(name,ctypes.c_ulonglong) for name in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
        value=MemoryStatus();value.length=ctypes.sizeof(value)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
            raise RuntimeError('memory_inventory_unavailable')
        return value.available
    from pathlib import Path
    values=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    return int(values['MemAvailable'].split()[0])*1024

def require_memory(gib):
    available=available_memory_bytes()
    if available < gib*1024**3:
        raise RuntimeError('resource_budget_unavailable')
    return available
