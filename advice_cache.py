# advice_cache.py — In-memory & DB caching for AI health advice
import hashlib
from threading import Lock

_memory_cache = {}
_memory_lock = Lock()
_MEMORY_MAX = 256


def _make_hash(systolic, diastolic, pulse, notes):
    raw = f"{systolic}|{diastolic}|{pulse}|{notes or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def get_or_compute(record_obj, compute_fn):
    record_id = getattr(record_obj, "record_id", getattr(record_obj, "id", 1))
    input_hash = _make_hash(
        record_obj.get_systolic(),
        record_obj.get_diastolic(),
        record_obj.get_pulse_rate(),
        record_obj.get_notes(),
    )
    key = (record_id, input_hash)

    with _memory_lock:
        hit = _memory_cache.get(key)
        if hit is not None:
            return hit, True

    advice = compute_fn()

    with _memory_lock:
        if len(_memory_cache) >= _MEMORY_MAX:
            first_key = next(iter(_memory_cache))
            _memory_cache.pop(first_key, None)
        _memory_cache[key] = advice

    return advice, False


def invalidate_record(record_id):
    with _memory_lock:
        for k in list(_memory_cache.keys()):
            if k[0] == record_id:
                _memory_cache.pop(k, None)
