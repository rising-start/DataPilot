import threading
from contextlib import contextmanager

class CancellationError(BaseException):
    pass
_local = threading.local()

def current_cancel_event() -> 'threading.Event | None':
    return getattr(_local, 'cancel_event', None)

@contextmanager
def cancel_context(event: 'threading.Event | None'):
    prev = getattr(_local, 'cancel_event', None)
    _local.cancel_event = event
    try:
        yield
    finally:
        _local.cancel_event = prev

def is_cancelled() -> bool:
    event = current_cancel_event()
    return event is not None and event.is_set()

def run_blocking_with_cancel(fn, *args, poll: float=0.2):
    holder: dict = {}
    err: dict = {}

    def target() -> None:
        try:
            holder['v'] = fn(*args)
        except BaseException as e:
            err['e'] = e
    t = threading.Thread(target=target, daemon=True)
    t.start()
    event = current_cancel_event()
    while t.is_alive():
        if event is not None and event.is_set():
            raise CancellationError('任务已取消')
        t.join(poll)
    if 'e' in err:
        raise err['e']
    return holder['v']