# -*- coding: utf-8 -*-
import os
from io import BytesIO
from typing import Optional, Tuple

import pandas as pd
from flask import Flask, render_template, request, send_file, jsonify, redirect, url_for
from markupsafe import Markup

from matching_engine import (
    Weights,
    read_any,
    resolve_students,
    resolve_sites,
    greedy_match,
    build_cockpit_rows,
    compute_score_with_explain,
    normalize_text,
)
from excel_manager import df_to_xlsx_bytes

app = Flask(__name__)

last_results_df: Optional[pd.DataFrame] = None
last_summary_df: Optional[pd.DataFrame] = None
last_students_df: Optional[pd.DataFrame] = None
last_sites_df: Optional[pd.DataFrame] = None


@app.after_request
def add_no_cache_headers(response):
    """
    מונע מהדפדפן להציג תוצאות ישנות מה-Cache אחרי יציאה וחזרה למערכת.
    """
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.before_request
def maintenance_mode():
    if os.getenv("MAINTENANCE_MODE", "0") == "1":
        html = """
        <html lang="he" dir="rtl">
        <head>
          <meta charset="utf-8">
          <title>האתר סגור</title>
          <style>
            body{
              font-family:David,Assistant,system-ui;
              background:#f8fafc;
              direction:rtl;
              text-align:center;
              margin:0;
              padding-top:120px;
              color:#111827;
            }
            .box{
              display:inline-block;
              padding:32px 40px;
              border-radius:18px;
              background:#ffffff;
              box-shadow:0 10px 30px rgba(15,23,42,.08);
              border:1px solid #e5e7eb;
            }
            h1{margin:0 0 12px;font-size:26px;}
            p{margin:0;color:#6b7280;}
          </style>
        </head>
        <body>
          <div class="box">
            <h1>⚙️ האתר סגור כרגע</h1>
            <p>הגישה למערכת השיבוץ מוגבלת זמנית.</p>
          </div>
        </body>
        </html>
        """
        return Markup(html), 503


def clear_current_matching_state():
    """
    איפוס מלא של השיבוץ האחרון.
    כל כניסה חדשה למערכת תתחיל נקייה.
    """
    global last_results_df, last_summary_df, last_students_df, last_sites_df

    last_results_df = None
    last_summary_df = None
    last_students_df = None
    last_sites_df = None


def empty_context(error=None, success=None):
    return {
        "results": None,
        "summary": None,
        "capacities": None,
        "explanations": None,
        "cockpit": None,
        "error": error,
        "success": success,
    }


def normalize_id_value(value) -> str:
    text = normalize_text(value)

    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]

    return text


def normalize_id_series(series: pd.Series) -> pd.Series:
    return series.apply(normalize_id_value)


def make_display_results(base_df: pd.DataFrame) -> pd.DataFrame:
    if "התערבות ידנית" in base_df.columns:
        manual_values = base_df["התערבות ידנית"].apply(
            lambda x: "כן" if normalize_text(x) == "כן" else "לא"
        )
    else:
        manual_values = pd.Series(["לא"] * len(base_df), index=base_df.index)

    df = pd.DataFrame({
        "אחוז התאמה": base_df["אחוז התאמה"].fillna(0).astype(int),
        "שם הסטודנט/ית": (
            base_df["שם פרטי"].astype(str) + " " + base_df["שם משפחה"].astype(str)
        ).str.strip(),
        "תעודת זהות": base_df["ת\"ז הסטודנט"].apply(normalize_id_value),
        "תחום התמחות": base_df["תחום ההתמחות במוסד"],
        "עיר המוסד": base_df["עיר המוסד"],
        "שם מקום ההתמחות": base_df["שם מקום ההתמחות"],
        "שם המדריך/ה": base_df["שם המדריך"],
        "עודכן ידנית?": manual_values,
    })

    return df.sort_values("אחוז התאמה", ascending=False)


def make_summary(base_df: pd.DataFrame) -> pd.DataFrame:
    valid = base_df[base_df["שם מקום ההתמחות"] != "לא שובץ"].copy()

    if valid.empty:
        return pd.DataFrame(columns=[
            "שם מקום ההתמחות",
            "תחום ההתמחות במוסד",
            "שם המדריך",
            "כמה סטודנטים",
            "המלצת שיבוץ",
        ])

    summary_df = (
        valid
        .groupby(["שם מקום ההתמחות", "תחום ההתמחות במוסד", "שם המדריך"], dropna=False)
        .agg({
            "ת\"ז הסטודנט": "count",
            "שם פרטי": list,
            "שם משפחה": list,
        })
        .reset_index()
    )

    summary_df.rename(columns={"ת\"ז הסטודנט": "כמה סטודנטים"}, inplace=True)

    summary_df["המלצת שיבוץ"] = summary_df.apply(
        lambda row: " + ".join(
            [f"{f} {l}" for f, l in zip(row["שם פרטי"], row["שם משפחה"])]
        ),
        axis=1,
    )

    return summary_df[[
        "שם מקום ההתמחות",
        "תחום ההתמחות במוסד",
        "שם המדריך",
        "כמה סטודנטים",
        "המלצת שיבוץ",
    ]]


def make_capacities(sites_df: pd.DataFrame, base_df: pd.DataFrame) -> pd.DataFrame:
    caps = sites_df.groupby("site_name")["site_capacity"].sum().to_dict()

    valid = base_df[base_df["שם מקום ההתמחות"] != "לא שובץ"].copy()
    assigned = valid.groupby("שם מקום ההתמחות")["ת\"ז הסטודנט"].count().to_dict()

    cap_rows = []

    for site_name, capacity in caps.items():
        used = int(assigned.get(site_name, 0))
        cap_rows.append({
            "שם מקום ההתמחות": site_name,
            "קיבולת": int(capacity),
            "שובצו בפועל": used,
            "יתרה/חוסר": int(capacity - used),
        })

    return pd.DataFrame(cap_rows).sort_values("שם מקום ההתמחות")


def make_explanations(base_df: pd.DataFrame):
    explanations = []

    for _, r in base_df.iterrows():
        parts = r.get("_expl", {})

        if not isinstance(parts, dict):
            parts = {}

        explanations.append({
            "student": f"{r['שם פרטי']} {r['שם משפחה']}",
            "site": r["שם מקום ההתמחות"],
            "score": int(r["אחוז התאמה"]),
            "parts": parts,
        })

    return explanations


def build_context_from_current(error=None, success=None):
    global last_results_df, last_summary_df, last_students_df, last_sites_df

    context = empty_context(error=error, success=success)

    if last_results_df is None or last_results_df.empty:
        return context

    df_show = make_display_results(last_results_df)

    summary_df = make_summary(last_results_df)
    last_summary_df = summary_df.copy()

    cap_df = pd.DataFrame()
    cockpit = None

    if last_sites_df is not None:
        cap_df = make_capacities(last_sites_df, last_results_df)

    if last_students_df is not None and last_sites_df is not None:
        cockpit = build_cockpit_rows(
            last_students_df,
            last_sites_df,
            last_results_df,
            Weights(),
        )

    context.update({
        "results": df_show.to_dict(orient="records"),
        "summary": summary_df.to_dict(orient="records"),
        "capacities": cap_df.to_dict(orient="records") if not cap_df.empty else None,
        "explanations": make_explanations(last_results_df),
        "cockpit": cockpit,
        "error": error,
        "success": success,
    })

    return context


def perform_override(student_id_raw, target_site_raw) -> Tuple[bool, str, int]:
    global last_results_df, last_summary_df, last_students_df, last_sites_df

    if last_results_df is None or last_students_df is None or last_sites_df is None:
        return False, "אין נתוני שיבוץ פעילים. צריך להעלות קבצים ולבצע שיבוץ קודם.", 0

    student_id = normalize_id_value(student_id_raw)
    target_site = normalize_text(target_site_raw)

    if not student_id or not target_site:
        return False, "חסר סטודנט או מקום התמחות.", 0

    id_series = normalize_id_series(last_results_df["ת\"ז הסטודנט"])
    row_mask = id_series == student_id

    if not row_mask.any():
        return False, "הסטודנט לא נמצא בתוצאות השיבוץ.", 0

    site_rows = last_sites_df[last_sites_df["site_name"].apply(normalize_text) == target_site]

    if site_rows.empty:
        return False, "מקום ההתמחות לא נמצא בקובץ המקומות.", 0

    current_site = last_results_df.loc[row_mask, "שם מקום ההתמחות"].iloc[0]
    current_score = int(last_results_df.loc[row_mask, "אחוז התאמה"].iloc[0])

    if normalize_text(current_site) == target_site:
        return True, "לא בוצע שינוי: זה כבר השיבוץ הנוכחי.", current_score

    assigned_without_student = last_results_df[
        (normalize_id_series(last_results_df["ת\"ז הסטודנט"]) != student_id)
        & (last_results_df["שם מקום ההתמחות"] != "לא שובץ")
    ]

    used_target = int(
        (assigned_without_student["שם מקום ההתמחות"].apply(normalize_text) == target_site).sum()
    )

    target_capacity = int(
        pd.to_numeric(site_rows["site_capacity"], errors="coerce").fillna(1).sum()
    )

    if used_target >= target_capacity:
        return False, "לא ניתן לשבץ: הקיבולת במקום ההתמחות מלאה.", current_score

    stu_rows = last_students_df[last_students_df["stu_id"].apply(normalize_id_value) == student_id]

    if stu_rows.empty:
        return False, "נתוני הסטודנט לא נמצאו.", 0

    stu = stu_rows.iloc[0]
    site = site_rows.iloc[0]

    score, parts = compute_score_with_explain(stu, site, Weights())

    idx = last_results_df[row_mask].index[0]

    last_results_df.at[idx, "שם מקום ההתמחות"] = site.get("site_name", "")
    last_results_df.at[idx, "עיר המוסד"] = site.get("site_city", "")
    last_results_df.at[idx, "תחום ההתמחות במוסד"] = site.get("site_field", "")
    last_results_df.at[idx, "שם המדריך"] = site.get("שם המדריך", "")
    last_results_df.at[idx, "אחוז התאמה"] = int(score)
    last_results_df.at[idx, "התערבות ידנית"] = "כן"
    last_results_df.at[idx, "_expl"] = parts

    last_summary_df = make_summary(last_results_df)

    return True, f"השיבוץ עודכן מ־{current_site} אל {target_site}.", int(score)


@app.route("/", methods=["GET", "POST"])
def index():
    global last_results_df, last_summary_df, last_students_df, last_sites_df

    if request.method == "GET":
        """
        כל כניסה רגילה למערכת השיבוץ מתחילה דף נקי.
        לכן השיבוץ הקודם לא נשמר ולא מוצג שוב.
        """
        clear_current_matching_state()
        return render_template("index.html", **empty_context())

    students_file = request.files.get("students_file")
    sites_file = request.files.get("sites_file")

    if not students_file or not sites_file:
        return render_template(
            "index.html",
            **empty_context("יש להעלות גם קובץ סטודנטים וגם קובץ אתרי התמחות."),
        )

    try:
        df_students_raw = read_any(students_file)
        df_sites_raw = read_any(sites_file)

        students = resolve_students(df_students_raw)
        sites = resolve_sites(df_sites_raw)

        base_df = greedy_match(students, sites.copy(), Weights())

        last_students_df = students.copy()
        last_sites_df = sites.copy()
        last_results_df = base_df.copy()
        last_summary_df = make_summary(last_results_df)

        return render_template(
            "index.html",
            **build_context_from_current(success="השיבוץ בוצע בהצלחה."),
        )

    except Exception as e:
        return render_template(
            "index.html",
            **empty_context(f"שגיאה במהלך השיבוץ: {e}"),
        )


@app.route("/override-form", methods=["POST"])
def override_form():
    student_id = request.form.get("student_id", "")
    site_name = request.form.get("site_name", "")

    ok, message, _score = perform_override(student_id, site_name)

    if ok:
        return render_template("index.html", **build_context_from_current(success=message))

    return render_template("index.html", **build_context_from_current(error=message))


@app.route("/api/override", methods=["POST"])
def apply_override():
    data = request.get_json(silent=True) or {}

    ok, message, score = perform_override(
        data.get("student_id", ""),
        data.get("site_name", ""),
    )

    if not ok:
        return jsonify({"ok": False, "message": message, "score": score}), 400

    return jsonify({"ok": True, "message": message, "score": score})


@app.route("/clear")
def clear_results():
    """
    כפתור/קישור איפוס ידני אם תרצי להשתמש בו בעתיד.
    """
    clear_current_matching_state()
    return redirect(url_for("index"))


@app.route("/download/results")
def download_results():
    global last_results_df

    if last_results_df is None or last_results_df.empty:
        return "אין נתוני שיבוץ להורדה", 400

    df_show = make_display_results(last_results_df)
    data = df_to_xlsx_bytes(df_show, sheet_name="תוצאות")

    return send_file(
        BytesIO(data),
        as_attachment=True,
        download_name="student_site_matching.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/download/summary")
def download_summary():
    global last_summary_df

    if last_summary_df is None or last_summary_df.empty:
        return "אין טבלת סיכום להורדה", 400

    data = df_to_xlsx_bytes(last_summary_df, sheet_name="סיכום")

    return send_file(
        BytesIO(data),
        as_attachment=True,
        download_name="student_site_summary.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
