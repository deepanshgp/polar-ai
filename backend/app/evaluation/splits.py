from dataclasses import dataclass
from datetime import date, timedelta
import numpy as np

@dataclass(frozen=True)
class TimeSplit:
    train: tuple[date,date]; val: tuple[date,date]; test: tuple[date,date]; gap_days: int

def make_time_split(dates, val_frac=.2, test_frac=.2, gap_days=0):
    ds=sorted(set(d.date() if hasattr(d,'date') else d for d in dates)); n=len(ds)
    if n < 3: raise ValueError("at least three dates required")
    test_start=max(1,int(n*(1-test_frac))); val_start=max(1,int(n*(1-test_frac-val_frac)))
    gap=timedelta(days=gap_days)
    return TimeSplit((ds[0],ds[val_start-1]),(ds[val_start]+gap,ds[test_start-1]),(ds[test_start]+gap,ds[-1]),gap_days)

def assert_no_leakage(split: TimeSplit, max_lead: int):
    if split.train[1] + timedelta(days=max_lead) >= split.val[0]: raise AssertionError("train target window overlaps validation block")
    if split.val[1] + timedelta(days=max_lead) >= split.test[0]: raise AssertionError("validation target window overlaps test block")

def make_berg_split(records, val_frac=.2, test_frac=.2):
    ids=sorted({r["berg_id"] for r in records}); n=len(ids)
    if n < 3: raise ValueError("at least three bergs required")
    a=max(1,int(n*(1-test_frac-val_frac))); b=max(a+1,int(n*(1-test_frac)))
    return {"train":ids[:a],"val":ids[a:b],"test":ids[b:]}
