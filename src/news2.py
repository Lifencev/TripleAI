def score_resp_rate(rr):
    if rr <= 8:  return 3
    if rr <= 11: return 1
    if rr <= 20: return 0
    if rr <= 24: return 2
    return 3

def score_spo2(spo2):
    if spo2 <= 91: return 3
    if spo2 <= 93: return 2
    if spo2 <= 95: return 1
    return 0

def score_air_or_o2(on_oxygen: bool):
    return 2 if on_oxygen else 0

def score_sbp(sbp):
    if sbp <= 90:  return 3
    if sbp <= 100: return 2
    if sbp <= 110: return 1
    if sbp <= 219: return 0
    return 3

def score_hr(hr):
    if hr <= 40:  return 3
    if hr <= 50:  return 1
    if hr <= 90:  return 0
    if hr <= 110: return 1
    if hr <= 130: return 2
    return 3

def score_temp(t):
    if t <= 35.0: return 3
    if t <= 36.0: return 1
    if t <= 38.0: return 0
    if t <= 39.0: return 1
    return 2

def score_consciousness(alert: bool):
    # alert == True -> 0 ; any new confusion / not-alert -> 3
    return 0 if alert else 3

def news2(rr, spo2, on_oxygen, sbp, hr, temp, alert):
    parts = {
        "resp":          score_resp_rate(rr),
        "spo2":          score_spo2(spo2),
        "o2":            score_air_or_o2(on_oxygen),
        "sbp":           score_sbp(sbp),
        "hr":            score_hr(hr),
        "temp":          score_temp(temp),
        "consciousness": score_consciousness(alert),
    }
    aggregate = sum(parts.values())
    max_param = max(parts.values())
    return {
        "aggregate": aggregate,
        "max_single_param": max_param,   # feeds the interval logic + single-3 rule
        "components": parts,             # your audit trail — shows WHICH param drove it
    }