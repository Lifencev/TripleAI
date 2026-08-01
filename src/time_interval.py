def news2_interval(aggregate: int, max_single_param: int) -> int:
    """Recommended max minutes to next check, from NEWS2 alone.
    Needs the aggregate AND the highest single-parameter score,
    because a lone '3' escalates independently of the total."""
    if aggregate >= 7:
        return 15          # 'continuous' — 15 is a demo-friendly stand-in
    if aggregate >= 5 or max_single_param == 3:
        return 60          # urgent / hourly band
    if aggregate >= 1:     # 1–4
        return 240
    return 240             # aggregate 0; CTAS will almost always floor this

# ESI 1-5 -> reassessment interval (minutes).
# NOTE: unlike CTAS, ESI publishes NO official reassessment intervals.
# This mapping is our approximation, ordered by acuity. Stated as such.
ESI_INTERVALS = {1: 15, 2: 15, 3: 30, 4: 60, 5: 120}

def next_eval_interval(news2_aggregate: int,
                       news2_max_param: int,
                       esi_level: int) -> dict:
    """Take the stricter (shorter) of the NEWS2-derived interval
    and the ESI acuity floor."""
    n = news2_interval(news2_aggregate, news2_max_param)
    e = ESI_INTERVALS[esi_level]
    chosen = min(n, e)
    return {
        "interval_min": chosen,
        "news2_says": n,
        "esi_says": e,
        "driver": "NEWS2" if n < e else "ESI" if e < n else "both",
    }
