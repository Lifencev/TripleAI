"""Loads the real triage dataset into a waiting-room cohort.

Source: data/raw/triage_features_control.csv — one row per ED visit, carrying
identity, timestamps, vitals at two timepoints, ESI level, arrival mode, chief
complaints and comorbidity history.

Where the two NEWS2 readings come from:

    triage_time       -> triage_*  vitals -> "At triage" score
    measurement_time  -> last_*    vitals -> "Latest" score

Both are scored here by src/news2.py from the raw vitals, never read from the
dataset's precomputed columns, so the number on screen always comes from our
own engine. The gap between the two is a genuine observed change, and it is
what feeds the "rose by >= 2" rule. It is two recorded observations, not a
live feed — nothing recomputes between them.

The dataset's own `last_news2` column is used only as a cheap pre-filter to
find candidate rows before our engine scores them. Most ED visits are benign
(around 55% score zero), so an unstratified sample gives a worklist of zeroes.
"""

from pathlib import Path

import pandas as pd

from news2 import news2

_COLUMNS = [
    "patient_id", "stay_id", "esi_level", "age", "gender", "arrival_mode",
    "chief_complaints", "relevant_history", "alert",
    "arrival_time", "triage_time", "measurement_time", "next_reassessment_due",
    "triage_hr", "triage_sbp", "triage_rr", "triage_spo2", "triage_on_oxygen", "triage_temp_c",
    "last_hr", "last_sbp", "last_rr", "last_spo2", "last_on_oxygen", "last_temp_c",
    "last_news2", "triage_news2", "disposition", "low_acuity_admitted_label",
]

_TIME_COLUMNS = ["arrival_time", "triage_time", "measurement_time", "next_reassessment_due"]

_VITALS = ["hr", "sbp", "rr", "spo2", "temp_c", "on_oxygen"]

# The dataset stores complaints and history as machine tokens joined by a pipe.
# Expanded here so a nurse reads words, and so the pipe never reaches the UI.
_TERMS = {
    "abdominalpain": "abdominal pain", "chestpain": "chest pain", "backpain": "back pain",
    "shortnessofbreath": "shortness of breath", "breathingdifficulty": "breathing difficulty",
    "dyspnea": "dyspnoea", "cough": "cough", "fall": "fall", "fall>65": "fall over 65",
    "motorvehiclecrash": "motor vehicle crash", "dizziness": "dizziness", "legpain": "leg pain",
    "alcoholintoxication": "alcohol intoxication", "emesis": "vomiting", "nausea": "nausea",
    "flankpain": "flank pain", "headache-newonsetornewsymptoms": "new-onset headache",
    "headachere-evaluation": "headache re-evaluation", "headache": "headache",
    "headache-recurrentorknowndxmigraines": "recurrent migraine", "suicidal": "suicidal ideation",
    "kneepain": "knee pain", "sorethroat": "sore throat", "fever-9weeksto74years": "fever",
    "fever": "fever", "weakness": "weakness", "psychiatricevaluation": "psychiatric evaluation",
    "rash": "rash", "medicalproblem": "medical problem", "footpain": "foot pain",
    "legswelling": "leg swelling", "alteredmentalstatus": "altered mental status",
    "shoulderpain": "shoulder pain", "diarrhea": "diarrhoea", "armpain": "arm pain",
    "neckpain": "neck pain", "abscess": "abscess", "coldlikesymptoms": "cold-like symptoms",
    "laceration": "laceration", "extremitylaceration": "extremity laceration",
    "dentalpain": "dental pain", "hypertension": "hypertension", "fatigue": "fatigue",
    "earpain": "ear pain", "abnormallab": "abnormal lab result", "femaleguproblem": "GU problem",
    "maleguproblem": "GU problem", "vaginalbleeding": "vaginal bleeding", "syncope": "syncope",
    "handpain": "hand pain", "anklepain": "ankle pain", "ankleinjury": "ankle injury",
    "allergicreaction": "allergic reaction", "hippain": "hip pain", "woundcheck": "wound check",
    "neurologicproblem": "neurological problem", "assaultvictim": "assault",
    "palpitations": "palpitations", "generalizedbodyaches": "generalised body aches",
    "eyeproblem": "eye problem", "eyepain": "eye pain", "fingerinjury": "finger injury",
    "gibleeding": "GI bleeding", "anxiety": "anxiety", "drugproblem": "drug problem",
    "headinjury": "head injury", "seizure-priorhxof": "seizure, prior history",
    "seizure": "seizure", "urinarytractinfection": "urinary tract infection",
    "constipation": "constipation", "dysuria": "dysuria", "facialswelling": "facial swelling",
    "hematuria": "haematuria", "leginjury": "leg injury", "confusion": "confusion",
    "lethargy": "lethargy", "unresponsive": "unresponsive", "other": "other",
    # comorbidity history
    "htn": "hypertension", "diabmelnoc": "diabetes", "diabmelwcm": "diabetes with complications",
    "asthma": "asthma", "copd": "COPD", "chfnonhp": "heart failure",
    "chrkidneydisease": "chronic kidney disease", "acutemi": "prior MI",
    "coronathero": "coronary atherosclerosis", "adltrespfl": "respiratory failure",
    "respdistres": "respiratory distress",
}


def _humanise(raw: object) -> str:
    """'asthma|htn' -> 'Asthma, hypertension'. Never returns a pipe."""
    if not isinstance(raw, str) or not raw.strip():
        return ""
    parts = [_TERMS.get(p.strip().lower(), p.strip().replace("_", " ")) for p in raw.split("|")]
    parts = [p for p in parts if p]
    if not parts:
        return ""
    joined = ", ".join(dict.fromkeys(parts))
    return joined[0].upper() + joined[1:]


def _score(row: pd.Series, prefix: str) -> dict:
    return news2(
        rr=float(row[f"{prefix}_rr"]),
        spo2=float(row[f"{prefix}_spo2"]),
        on_oxygen=bool(row[f"{prefix}_on_oxygen"]),
        sbp=float(row[f"{prefix}_sbp"]),
        hr=float(row[f"{prefix}_hr"]),
        temp=float(row[f"{prefix}_temp_c"]),
        alert=bool(row["alert"]),
    )


# (label, predicate on the eligible frame, relative weight)
#
# Deliberately bottom-heavy. A real waiting room is mostly fine, and the whole
# point of the monitor is catching the few who are not — if half the worklist
# is red, red stops meaning anything. Weights hold the mix at roughly three
# alerting in twelve whatever size is requested.
#
# "rising" is drawn on the observed change rather than the absolute score: a
# patient who went 1 -> 4 is exactly the under-triaged deterioration this tool
# exists to surface, and without this stratum the delta rule never fires.
_STRATA = [
    ("rising", lambda d: (d["last_news2"] - d["triage_news2"]) >= 2, 2),
    ("high",   lambda d: d["last_news2"] >= 5, 1),
    ("watch",  lambda d: (d["last_news2"] >= 3) & (d["last_news2"] < 5), 2),
    ("low",    lambda d: (d["last_news2"] >= 1) & (d["last_news2"] < 3), 3),
    ("stable", lambda d: d["last_news2"] == 0, 4),
]

DATASET_DIRS = ("raw", "processed")


def dataset_path() -> Path:
    """Locate the intake CSV.

    The file is gitignored and lives outside version control, and it has been
    kept under both data/raw and data/processed at different points, so accept
    either rather than hard-coding one.
    """
    root = Path(__file__).resolve().parents[1] / "data"
    for sub in DATASET_DIRS:
        candidate = root / sub / "triage_features_control.csv"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "triage_features_control.csv not found under "
        + " or ".join(f"data/{d}/" for d in DATASET_DIRS)
        + ". It is gitignored — copy it in locally."
    )


def _to_records(picked: pd.DataFrame) -> pd.DataFrame:
    """Score rows with our own engine and shape them for the UI.

    Shared by the initial cohort and by sequential intake so a patient
    admitted later is identical in schema to one loaded at startup.
    """
    triage = picked.apply(lambda r: _score(r, "triage"), axis=1)
    last = picked.apply(lambda r: _score(r, "last"), axis=1)

    out = pd.DataFrame({
        # The dataset carries its own identity; do not fabricate one.
        "ID": picked["patient_id"].astype(str),
        "Stay": picked["stay_id"].astype(str),
        "Age": picked["age"].astype(int),
        "Sex": picked["gender"].fillna("Unknown"),
        "ESI": picked["esi_level"].astype(int),
        "Arrival": picked["arrival_mode"].fillna("Unknown").str.capitalize(),
        "Complaint": picked["chief_complaints"].map(_humanise),
        "History": picked["relevant_history"].map(_humanise),
        "ArrivedAt": picked["arrival_time"],
        "TriagedAt": picked["triage_time"],
        "MeasuredAt": picked["measurement_time"],
        "DueAt": picked["next_reassessment_due"],
        "NEWS2_Prev": [s["aggregate"] for s in triage],
        "NEWS2_Score": [s["aggregate"] for s in last],
        "Max_Single_Param": [s["max_single_param"] for s in last],
        "Components": [s["components"] for s in last],
        "HR": picked["last_hr"].astype(int),
        "SBP": picked["last_sbp"].astype(int),
        "RR": picked["last_rr"].astype(int),
        "SpO2": picked["last_spo2"].astype(int),
        "Temp": picked["last_temp_c"].astype(float).round(1),
        "O2_supp": picked["last_on_oxygen"].astype(bool),
        "Alert": picked["alert"].astype(bool),
        "Disposition": picked["disposition"].fillna("Unknown"),
    }).reset_index(drop=True)

    out["Delta"] = out["NEWS2_Score"] - out["NEWS2_Prev"]
    out["Complaint"] = out["Complaint"].replace("", "Not recorded")
    out["History"] = out["History"].replace("", "None recorded")

    # Minutes between the two scored observations — the span the delta covers.
    gap = (out["MeasuredAt"] - out["TriagedAt"]).dt.total_seconds() / 60
    out["ObsGapMin"] = gap.fillna(0).round().astype(int)
    out["WaitMin"] = (
        (out["MeasuredAt"] - out["ArrivedAt"]).dt.total_seconds() / 60
    ).fillna(0).round().astype(int)
    return out


def _eligible(scan_rows: int) -> pd.DataFrame:
    """Rows with a complete second set of vitals — the only monitorable ones."""
    df = pd.read_csv(
        dataset_path(), usecols=_COLUMNS, nrows=scan_rows, parse_dates=_TIME_COLUMNS
    )
    needed = [f"{p}_{c}" for p in ("triage", "last") for c in _VITALS] + [
        "esi_level", "alert", "last_news2", "triage_news2",
    ]
    df = df.dropna(subset=needed)
    if df.empty:
        raise ValueError("No rows with a complete second set of vitals.")
    return df


def load_pool(size: int = 60, scan_rows: int = 250_000, seed: int = 11) -> pd.DataFrame:
    """A stratified pool of patients spanning the full acuity range.

    The first N form the opening waiting room; the remainder are the intake
    queue that sequential admission draws from, so an arriving patient has the
    same acuity mix as the starting cohort rather than whatever the CSV
    happens to list next.
    """
    df = _eligible(scan_rows)

    total_weight = sum(w for _, _, w in _STRATA)
    picked = []
    used = set()
    for _, predicate, weight in _STRATA:
        n = max(1, round(size * weight / total_weight))
        # Strata overlap (a rising patient may also be high), so exclude rows
        # already taken rather than showing the same visit twice.
        stratum = df[predicate(df) & ~df.index.isin(used)]
        if len(stratum):
            chosen = stratum.sample(min(len(stratum), n), random_state=seed)
            used.update(chosen.index)
            picked.append(chosen)
    picked = pd.concat(picked)

    if len(picked) < size:  # top up if a stratum was short
        rest = df.drop(picked.index)
        picked = pd.concat(
            [picked, rest.sample(min(len(rest), size - len(picked)), random_state=seed)]
        )

    # Shuffle so admissions are not ordered worst-first.
    picked = picked.sample(frac=1, random_state=seed)
    return _to_records(picked)


def load_cohort(size: int = 12, scan_rows: int = 250_000, seed: int = 11) -> pd.DataFrame:
    """The waiting room as it stands when the shift starts."""
    return load_pool(size=size, scan_rows=scan_rows, seed=seed).head(size).reset_index(drop=True)
