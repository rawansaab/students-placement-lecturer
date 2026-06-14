# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple, Dict
import pandas as pd
import numpy as np


@dataclass
class Weights:
    w_field: float = 0.50
    w_city: float = 0.05
    w_special: float = 0.45


STU_COLS = {
    "id": ["מספר תעודת זהות", "תעודת זהות", "ת\"ז", "תז", "תעודת זהות הסטודנט"],
    "first": ["שם פרטי"],
    "last": ["שם משפחה"],
    "address": ["כתובת", "כתובת מלאה", "כתובת הסטודנט"],
    "city": ["עיר מגורים", "עיר"],
    "phone": ["טלפון", "מספר טלפון"],
    "email": ["דוא\"ל", "דוא״ל", "אימייל", "כתובת אימייל", "כתובת מייל"],
    "preferred_field": ["תחום מועדף", "תחומים מועדפים"],
    "special_req": ["בקשה מיוחדת", "בקשות מיוחדות"],
    "partner": ["בן/בת זוג להכשרה", "בן\\בת זוג להכשרה", "בן/בת זוג", "בן\\בת זוג"],
}

SITE_COLS = {
    "name": ["מוסד / שירות הכשרה", "מוסד", "שם מוסד ההתמחות", "שם המוסד", "מוסד ההכשרה"],
    "field": ["תחום ההתמחות", "תחום התמחות"],
    "street": ["רחוב"],
    "city": ["עיר"],
    "capacity": ["מספר סטודנטים שניתן לקלוט השנה", "מספר סטודנטים שניתן לקלוט", "קיבולת"],
    "sup_first": ["שם פרטי"],
    "sup_last": ["שם משפחה"],
    "phone": ["טלפון"],
    "email": ["אימייל", "כתובת מייל", "דוא\"ל", "דוא״ל"],
    "review": ["חוות דעת מדריך"],
}


def pick_col(df: pd.DataFrame, options: List[str]) -> Optional[str]:
    for opt in options:
        if opt in df.columns:
            return opt
    return None


def require_col(df: pd.DataFrame, options: List[str], label: str) -> str:
    col = pick_col(df, options)
    if not col:
        raise ValueError(f"חסרה עמודה נדרשת: {label}. שמות אפשריים: {', '.join(options)}")
    return col


def read_any(uploaded) -> pd.DataFrame:
    name = (uploaded.filename or "").lower()

    if name.endswith(".csv"):
        try:
            return pd.read_csv(uploaded, encoding="utf-8-sig")
        except UnicodeDecodeError:
            uploaded.stream.seek(0)
            return pd.read_csv(uploaded, encoding="cp1255")

    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded)

    return pd.read_csv(uploaded, encoding="utf-8-sig")


def normalize_text(x: Any) -> str:
    if x is None:
        return ""

    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass

    if isinstance(x, (int, np.integer)):
        return str(int(x)).strip()

    if isinstance(x, (float, np.floating)):
        if float(x).is_integer():
            return str(int(x)).strip()
        return str(x).strip()

    text = str(x).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def split_tokens(text: str) -> List[str]:
    text = normalize_text(text).replace(";", ",").replace("|", ",")
    return [t.strip().lower() for t in text.split(",") if t.strip()]


def resolve_students(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    id_col = require_col(out, STU_COLS["id"], "תעודת זהות")
    first_col = require_col(out, STU_COLS["first"], "שם פרטי")
    last_col = require_col(out, STU_COLS["last"], "שם משפחה")

    out["stu_id"] = out[id_col]
    out["stu_first"] = out[first_col]
    out["stu_last"] = out[last_col]

    city_col = pick_col(out, STU_COLS["city"])
    if city_col:
        out["stu_city"] = out[city_col]
    else:
        addr_col = pick_col(out, STU_COLS.get("address", []))
        if addr_col:
            out["stu_city"] = out[addr_col].apply(
                lambda x: str(x).split(",")[-1].strip()
                if isinstance(x, str) and "," in x else ""
            )
        else:
            out["stu_city"] = ""

    pref_col = pick_col(out, STU_COLS["preferred_field"])
    out["stu_pref"] = out[pref_col] if pref_col else ""

    req_col = pick_col(out, STU_COLS["special_req"])
    out["stu_req"] = out[req_col] if req_col else ""

    for c in ["stu_id", "stu_first", "stu_last", "stu_city", "stu_pref", "stu_req"]:
        out[c] = out[c].apply(normalize_text)

    return out


def resolve_sites(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    name_col = require_col(out, SITE_COLS["name"], "שם מוסד / שירות הכשרה")
    field_col = require_col(out, SITE_COLS["field"], "תחום התמחות")
    city_col = require_col(out, SITE_COLS["city"], "עיר")

    out["site_name"] = out[name_col]
    out["site_field"] = out[field_col]
    out["site_city"] = out[city_col]

    cap_col = pick_col(out, SITE_COLS["capacity"])
    if cap_col:
        out["site_capacity"] = pd.to_numeric(out[cap_col], errors="coerce").fillna(1).astype(int)
    else:
        out["site_capacity"] = 1

    out["site_capacity"] = out["site_capacity"].clip(lower=1)
    out["capacity_left"] = out["site_capacity"].astype(int)

    sup_first = pick_col(out, SITE_COLS["sup_first"])
    sup_last = pick_col(out, SITE_COLS["sup_last"])

    out["שם המדריך"] = ""
    if sup_first or sup_last:
        ff = out[sup_first] if sup_first else ""
        ll = out[sup_last] if sup_last else ""
        out["שם המדריך"] = (ff.astype(str) + " " + ll.astype(str)).str.strip()

    for c in ["site_name", "site_field", "site_city", "שם המדריך"]:
        out[c] = out[c].apply(normalize_text)

    return out


def compute_score_with_explain(stu: pd.Series, site: pd.Series, W: Weights) -> Tuple[int, Dict[str, int]]:
    stu_city = normalize_text(stu.get("stu_city", "")).lower()
    site_city = normalize_text(site.get("site_city", "")).lower()
    stu_pref = normalize_text(stu.get("stu_pref", "")).lower()
    site_field = normalize_text(site.get("site_field", "")).lower()
    stu_req = normalize_text(stu.get("stu_req", ""))

    if stu_pref:
        tokens = split_tokens(stu_pref)
        field_component = 100 if any(tok in site_field for tok in tokens) else 0
    else:
        field_component = 70

    if stu_city and site_city:
        city_component = 100 if stu_city == site_city else 0
    else:
        city_component = 50

    stu_req_lower = stu_req.lower()

    if "קרוב" in stu_req_lower:
        if stu_city and site_city:
            special_component = 100 if stu_city == site_city else 0
        else:
            special_component = 50
    elif "צפון" in stu_req_lower:
        north_cities = [
            "צפת", "כרמיאל", "נהריה", "עכו", "קריית שמונה",
            "קרית שמונה", "טבריה", "חורפיש", "מעלות", "סחנין",
        ]
        north_cities = [c.lower() for c in north_cities]
        special_component = 75 if site_city in north_cities else 50
    elif stu_req:
        special_component = 60
    else:
        special_component = 50

    parts = {
        "התאמת תחום": round(W.w_field * field_component),
        "מרחק/גיאוגרפיה": round(W.w_city * city_component),
        "בקשות מיוחדות": round(W.w_special * special_component),
        "עדיפויות הסטודנט/ית": 0,
    }

    score = int(np.clip(sum(parts.values()), 0, 100))
    return score, parts


def candidate_scores_for_student(stu: pd.Series, sites_df: pd.DataFrame, W: Weights) -> List[Dict[str, Any]]:
    candidates = []

    for _, site in sites_df.iterrows():
        score, parts = compute_score_with_explain(stu, site, W)

        candidates.append({
            "site_name": site.get("site_name", ""),
            "site_city": site.get("site_city", ""),
            "site_field": site.get("site_field", ""),
            "supervisor": site.get("שם המדריך", ""),
            "capacity": int(site.get("site_capacity", 1)),
            "score": int(score),
            "parts": parts,
        })

    return sorted(candidates, key=lambda x: x["score"], reverse=True)


def greedy_match(students_df: pd.DataFrame, sites_df: pd.DataFrame, W: Weights) -> pd.DataFrame:
    results = []
    supervisor_count = {}

    for _, s in students_df.iterrows():
        cand = sites_df[sites_df["capacity_left"] > 0].copy()

        if cand.empty:
            results.append({
                "ת\"ז הסטודנט": s["stu_id"],
                "שם פרטי": s["stu_first"],
                "שם משפחה": s["stu_last"],
                "שם מקום ההתמחות": "לא שובץ",
                "עיר המוסד": "",
                "תחום ההתמחות במוסד": "",
                "שם המדריך": "",
                "אחוז התאמה": 0,
                "התערבות ידנית": "",
                "_expl": {
                    "התאמת תחום": 0,
                    "מרחק/גיאוגרפיה": 0,
                    "בקשות מיוחדות": 0,
                    "עדיפויות הסטודנט/ית": 0,
                },
            })
            continue

        def score_row(r):
            sc, parts = compute_score_with_explain(s, r, W)
            return pd.Series({"score": sc, "_parts": parts})

        cand[["score", "_parts"]] = cand.apply(score_row, axis=1)

        def allowed_supervisor(r):
            sup = r.get("שם המדריך", "")
            if not sup:
                return True
            return supervisor_count.get(sup, 0) < 2

        filtered = cand[cand.apply(allowed_supervisor, axis=1)]

        if filtered.empty:
            filtered = cand.sort_values("score", ascending=False)
        else:
            filtered = filtered.sort_values("score", ascending=False)

        chosen = filtered.iloc[0]
        idx = chosen.name

        sites_df.at[idx, "capacity_left"] -= 1

        sup_name = chosen.get("שם המדריך", "")
        if sup_name:
            supervisor_count[sup_name] = supervisor_count.get(sup_name, 0) + 1

        results.append({
            "ת\"ז הסטודנט": s["stu_id"],
            "שם פרטי": s["stu_first"],
            "שם משפחה": s["stu_last"],
            "שם מקום ההתמחות": chosen["site_name"],
            "עיר המוסד": chosen.get("site_city", ""),
            "תחום ההתמחות במוסד": chosen["site_field"],
            "שם המדריך": sup_name,
            "אחוז התאמה": int(chosen["score"]),
            "התערבות ידנית": "",
            "_expl": chosen["_parts"],
        })

    return pd.DataFrame(results)


def score_class(score: int) -> str:
    if score >= 80:
        return "high"
    if score >= 60:
        return "medium"
    return "low"


def build_cockpit_rows(
    students_df: pd.DataFrame,
    sites_df: pd.DataFrame,
    base_df: pd.DataFrame,
    W: Weights,
) -> List[Dict[str, Any]]:
    rows = []

    for _, stu in students_df.iterrows():
        stu_id = normalize_text(stu.get("stu_id", ""))
        current_rows = base_df[base_df["ת\"ז הסטודנט"].apply(normalize_text) == stu_id]

        if current_rows.empty:
            current_site = "לא שובץ"
            current_score = 0
        else:
            current = current_rows.iloc[0]
            current_site = current.get("שם מקום ההתמחות", "לא שובץ")
            current_score = int(current.get("אחוז התאמה", 0))

        candidates = candidate_scores_for_student(stu, sites_df, W)
        top_candidates = candidates[:5]

        flags = []

        if current_site == "לא שובץ":
            flags.append("לא שובץ")
        if current_score < 60:
            flags.append("התאמה נמוכה")
        elif current_score < 75:
            flags.append("דורש בדיקה")
        if normalize_text(stu.get("stu_req", "")):
            flags.append("בקשה מיוחדת")
        if len(top_candidates) >= 2 and abs(top_candidates[0]["score"] - top_candidates[1]["score"]) <= 5:
            flags.append("כמה חלופות דומות")

        action = "אישור מומלץ" if not flags else "בדיקה ידנית מומלצת"

        rows.append({
            "student_id": stu_id,
            "student_name": f"{stu.get('stu_first', '')} {stu.get('stu_last', '')}".strip(),
            "student_city": stu.get("stu_city", ""),
            "student_pref": stu.get("stu_pref", ""),
            "student_req": stu.get("stu_req", ""),
            "current_site": current_site,
            "score": current_score,
            "score_class": score_class(current_score),
            "flags": flags,
            "action": action,
            "alternatives": candidates,
        })

    return rows
