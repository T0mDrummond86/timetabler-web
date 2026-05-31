"""Shared constants for the timetabling app.

The slot grid mirrors the Joondalup `Overall` spreadsheet: 30-minute slots
from 08:00 to 22:30 (29 slots), Monday through Friday (5 days).
"""
from datetime import time

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
NUM_DAYS = len(DAYS)

SLOT_MINUTES = 30
FIRST_SLOT_TIME = time(8, 0)
NUM_SLOTS = 28  # 08:00 start through 21:30 start (last slot ends 22:00)


def slot_to_time(slot: int) -> time:
    minutes = FIRST_SLOT_TIME.hour * 60 + FIRST_SLOT_TIME.minute + slot * SLOT_MINUTES
    return time(minutes // 60, minutes % 60)


def time_to_slot(t: time) -> int:
    minutes = t.hour * 60 + t.minute - (FIRST_SLOT_TIME.hour * 60 + FIRST_SLOT_TIME.minute)
    if minutes < 0 or minutes % SLOT_MINUTES != 0:
        raise ValueError(f"time {t} is not aligned to a {SLOT_MINUTES}-minute slot")
    return minutes // SLOT_MINUTES


