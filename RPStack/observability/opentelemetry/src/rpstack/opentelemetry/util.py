
# This copyright notice must be included 
# in all distributions of this code
#
# Copyright (c) 2026 John Gentilin
# Author: John Gentilin
# All rights reserved unless otherwise stated.
#
#
try:
    import utime as _time
except ImportError:
    import time as _time

try:
    import urandom as _random
except ImportError:
    import random as _random


_UNIX_EPOCH_OFFSET_SECONDS = 946684800


# Detect platforms whose clock epoch starts in 2000 and supply the Unix offset.
def _unix_epoch_offset_seconds():
    try:
        if hasattr(_time, "gmtime") and _time.gmtime(0)[0] == 2000:
            return _UNIX_EPOCH_OFFSET_SECONDS
    except (AttributeError, IndexError, TypeError):
        pass
    return 0


_EPOCH_OFFSET_SECONDS = _unix_epoch_offset_seconds()


# Return wall-clock nanoseconds normalized to the Unix epoch across supported platforms.
def now_unix_nanos():
    if hasattr(_time, "time_ns"):
        return int(_time.time_ns()) + (_EPOCH_OFFSET_SECONDS * 1_000_000_000)
    return int((_time.time() + _EPOCH_OFFSET_SECONDS) * 1_000_000_000)


# Combine two random 32-bit values when supported, otherwise retaining the zero fallback.
def _random_u64():
    random_64bit = 0
    if hasattr(_random, "getrandbits"):
        # Combine two 32-bit chunks into one 64-bit number
        random_64bit = \
            (_random.getrandbits(32) << 32) | \
             _random.getrandbits(32)

    return random_64bit


# Format two generated 64-bit values as a 32-character trace identifier.
def random_trace_id():
    hi = _random_u64()
    lo = _random_u64()
    return "{:016x}{:016x}".format(hi, lo)


# Format a generated 64-bit value as a 16-character span identifier.
def random_span_id():
    return "{:016x}".format(_random_u64())
