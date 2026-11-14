"""Multiplex editor requests over the desktop parent's anonymous pipes."""

from concurrent.futures import ThreadPoolExecutor
import ctypes
from ctypes import wintypes
import json
import msvcrt
import os
import sys
import threading
import traceback


MAX_REQUEST_FRAME = 16_100_000
MAX_IN_FLIGHT = 24


def take_pipes():
    """Keep protocol handles private when Windows launches native or Python workers."""
    reader = os.fdopen(os.dup(sys.stdin.fileno()), 'rb')
    writer = os.fdopen(os.dup(sys.stdout.fileno()), 'wb')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
    kernel.SetStdHandle.restype = wintypes.BOOL
    with open(os.devnull, 'rb') as null:
        for number, fd, replacement in (
            (-10, sys.stdin.fileno(), null.fileno()),
            (-11, sys.stdout.fileno(), sys.stderr.fileno()),
        ):
            os.dup2(replacement, fd)
            if not kernel.SetStdHandle(number, msvcrt.get_osfhandle(fd)):
                raise ctypes.WinError(ctypes.get_last_error())
    return reader, writer


def serve(api, request_size_limit):
    reader, writer = take_pipes()
    write_lock = threading.Lock()
    slots = threading.BoundedSemaphore(MAX_IN_FLIGHT)
    pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix='desktop-request')

    def error_message(chinese, english):
        return chinese if os.environ.get('FM27_UI_LANGUAGE', '').startswith('zh') else english

    def send(frame):
        encoded = json.dumps(frame, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf8')
        with write_lock:
            try:
                writer.write(encoded + b'\n')
                writer.flush()
            except OSError:
                os._exit(0)

    def request(frame):
        try:
            target, method = frame['target'], frame['method']
            if not isinstance(target, str) or not target.startswith('/api/') or '#' in target:
                raise ValueError(error_message('请求路径无效', 'Invalid API path'))
            if method == 'GET':
                value, status, _ = api(target).get()
            elif method == 'POST':
                body = frame.get('body')
                if not isinstance(body, str) or not 0 < len(body.encode('utf8')) <= request_size_limit(target):
                    raise ValueError(error_message('请求大小无效', 'Invalid request size'))
                value, status, _ = api(target).post(json.loads(body))
            else:
                raise ValueError(error_message('请求方法无效', 'Invalid request method'))
            if isinstance(value, bytes):
                value = value.decode('utf8')
            send({'id':frame['id'], 'status':status, 'data':value})
        except (KeyError, ValueError) as error:
            send({'id':frame['id'], 'status':400, 'data':{'error':str(error)}})
        except Exception:
            traceback.print_exc()
            send({'id':frame['id'], 'status':500, 'data':{'error':error_message(
                '后台请求失败，请查看启动日志。', 'Backend request failed. See the startup log.')}})
        finally:
            slots.release()

    send({'ready':1, 'pid':os.getpid()})
    while True:
        line = reader.readline(MAX_REQUEST_FRAME + 1)
        if not line:
            # Windows closes the service's job object here and terminates its native children.
            os._exit(0)
        if len(line) > MAX_REQUEST_FRAME:
            print('IPC request frame exceeded the transport limit.', file=sys.stderr)
            os._exit(2)
        try:
            frame = json.loads(line)
            if not isinstance(frame, dict) or type(frame.get('id')) is not int:
                raise ValueError('IPC request has no numeric ID')
        except ValueError as error:
            print(error, file=sys.stderr)
            os._exit(2)
        if not slots.acquire(blocking=False):
            send({'id':frame['id'], 'status':503, 'data':{'error':error_message(
                '后台请求过多，请稍后重试。', 'Backend is busy. Try again shortly.')}})
            continue
        pool.submit(request, frame)
