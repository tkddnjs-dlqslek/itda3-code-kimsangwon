# -*- coding: utf-8 -*-
"""키워드 변형 표.xlsx (시트 '변형', 채택 == 'O') -> dateparse.KEYWORD_DICT 리터럴 출력.
사전을 다시 만들어야 할 때: python tools/export_keyword_dict.py > 붙여넣을 내용 확인
"""
import sys

import pandas as pd

XLSX = r"C:\Users\user\Desktop\ITDA 공모전\키워드 변형 표.xlsx"


def build_dict() -> dict:
    df = pd.read_excel(XLSX, sheet_name="변형")
    df = df[df["채택"] == "O"]
    out = {}
    for _, r in df.iterrows():
        fixed = r.get("고친 키워드")
        target = fixed if isinstance(fixed, str) and fixed.strip() else r["추정 키워드"]
        out[r["변형"]] = target
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    d = build_dict()
    print(f"# {len(d)} rows")
    print("KEYWORD_DICT = {")
    for k, v in d.items():
        print(f"    {k!r}: {v!r},")
    print("}")
