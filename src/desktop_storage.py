"""Storage limits for rebuildable save research and desktop preparation."""
from pathlib import Path
import shutil
import json
import os
import tempfile
import time

GIB = 1024**3
RESERVE_BYTES = 20 * GIB
SAVE_RESERVE_BYTES = 2 * GIB

def require_space(path, additional_bytes=0, *, reserve_bytes=RESERVE_BYTES):
    target = Path(path).resolve()
    p = target
    while not p.exists():p=p.parent
    free=shutil.disk_usage(p).free
    needed = reserve_bytes + additional_bytes
    if free < needed:
        raise ValueError(f'数据目录磁盘空间不足。{p.anchor} 剩余 {free/GIB:.1f} GiB，本操作需要 {needed/GIB:.1f} GiB。'
                         f'写入目录：{target}。可在桌面版设置中更改数据目录，或用 --data-dir 指定。')

def bounded_output(path,limit_bytes=256*1024**2):
    folder=Path(path)
    size=sum(p.stat().st_size for p in folder.rglob('*')if p.is_file())if folder.exists()else 0
    if size>limit_bytes:raise ValueError('本次准备目录超过256 MB上限，请先核查中间文件')
    require_space(folder, limit_bytes-size, reserve_bytes=SAVE_RESERVE_BYTES)

def windows_file_busy(error):
    return isinstance(error, PermissionError) and getattr(error, 'winerror', None) in (5, 32, 33)


def replace_file(source, target, timeout=2):
    deadline = time.monotonic() + timeout
    delay = .015
    while True:
        try:
            os.replace(source, target)
            return
        except PermissionError as error:
            if not windows_file_busy(error) or time.monotonic() >= deadline:
                raise
            time.sleep(delay)
            delay = min(.15, delay * 2)


def write_json_atomic(path, data):
    stream = tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name+'.', suffix='.tmp',
                                         delete=False, mode='w', encoding='utf8')
    temporary = Path(stream.name)
    try:
        with stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
        replace_file(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def publish_summary(directory):
    pending = directory / 'summary.pending.json'
    try:
        replace_file(pending, directory / 'summary.json', timeout=.12)
    except FileNotFoundError:
        return True
    except PermissionError as error:
        if windows_file_busy(error):
            return False
        raise
    return True
