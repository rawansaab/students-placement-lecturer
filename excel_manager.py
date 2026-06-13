
# -*- coding: utf-8 -*-
from io import BytesIO
import pandas as pd


def df_to_xlsx_bytes(df: pd.DataFrame, sheet_name: str = "שיבוץ") -> bytes:
    xlsx_io = BytesIO()

    with pd.ExcelWriter(xlsx_io, engine="xlsxwriter") as writer:
        cols = list(df.columns)

        if "אחוז התאמה" in cols:
            cols = [c for c in cols if c != "אחוז התאמה"] + ["אחוז התאמה"]

        df[cols].to_excel(writer, index=False, sheet_name=sheet_name)

        workbook = writer.book
        worksheet = writer.sheets[sheet_name]

        header_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#EEF2FF",
            "border": 1
        })

        for col_idx, col_name in enumerate(cols):
            worksheet.write(0, col_idx, col_name, header_fmt)
            worksheet.set_column(col_idx, col_idx, 18)

        if "אחוז התאמה" in cols:
            score_col = cols.index("אחוז התאמה")
            red_fmt = workbook.add_format({"font_color": "red", "bold": True})
            worksheet.set_column(score_col, score_col, 14, red_fmt)

    xlsx_io.seek(0)
    return xlsx_io.getvalue()
