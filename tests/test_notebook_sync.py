# -*- coding: utf-8 -*-
"""predict.ipynb 에 넣은 모듈 원문이 src/ 와 한 글자도 다르지 않은지 검사한다.
다르면 tools/build_notebook.py 를 다시 돌려야 한다."""
import ast
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _embedded_sources():
    with open(os.path.join(REPO, "predict.ipynb"), encoding="utf-8") as f:
        nb = json.load(f)
    found = {}
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        for node in ast.walk(ast.parse("".join(cell["source"]))):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_register_module"):
                found[node.args[0].value] = node.args[1].value
    return found


def test_notebook_embeds_every_module_verbatim():
    embedded = _embedded_sources()
    assert set(embedded) == {"dateparse", "ocr", "pipeline"}
    for name, source in embedded.items():
        with open(os.path.join(REPO, "src", f"{name}.py"), encoding="utf-8", newline="") as f:
            assert source == f.read(), f"{name}: 노트북과 src/ 가 다름. tools/build_notebook.py 재실행 필요"


def test_first_code_cell_is_config_and_no_src_path_dependency():
    with open(os.path.join(REPO, "predict.ipynb"), encoding="utf-8") as f:
        nb = json.load(f)
    code = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    assert code[0].startswith("# ===== CONFIG =====")
    assert 'os.environ.get("ITDA_INPUT_DIR",  "./val_images")' in code[0]
    assert not any("sys.path.insert" in c for c in code), "노트북이 src/ 경로에 의존하면 안 됨"
    assert code[-1].strip().startswith("df.to_csv(OUTPUT_PATH, index=False)")
