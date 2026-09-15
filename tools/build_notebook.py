"""predict.ipynb 를 노트북 하나만으로 돌도록 만든다.

src/ 의 dateparse.py, ocr.py, pipeline.py 원문을 셀 안에 그대로 넣고, 실행 시 모듈로 등록한다.
코드를 옮겨 적지 않고 원문을 넣기 때문에 동작은 src/ 와 같다. src/ 를 고치면 이 스크립트를 다시 돌린다.
tests/test_notebook_sync.py 가 노트북 속 원문과 src/ 가 같은지 검사한다.

    python tools/build_notebook.py
"""
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NB = os.path.join(REPO, "predict.ipynb")
MODULES = ["dateparse", "ocr", "pipeline"]   # 의존 순서: ocr 은 dateparse 를, pipeline 은 둘 다 import


def code_cell(src: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": src.splitlines(keepends=True)}


def module_cell(name: str) -> dict:
    with open(os.path.join(REPO, "src", f"{name}.py"), encoding="utf-8", newline="") as f:
        source = f.read()
    assert "'''" not in source, f"{name}.py 에 ''' 가 있어 원문 그대로 넣을 수 없음"
    return code_cell(
        f"# ===== 모듈 {name}: src/{name}.py 원문 그대로 =====\n"
        f"_register_module({name!r}, r'''{source}''')\n")


def main() -> None:
    with open(NB, encoding="utf-8") as f:
        nb = json.load(f)
    code = [c for c in nb["cells"] if c["cell_type"] == "code"]
    config = code[0]
    assert "".join(config["source"]).startswith("# ===== CONFIG ====="), "첫 셀이 CONFIG 셀이 아님"

    # 기존 두 번째 셀(src/ 를 sys.path 에 넣고 import)을 모듈 등록 셀들로 바꾼다. 나머지는 그대로
    tail = code[2:]
    assert "list_images" in "".join(tail[0]["source"]), "세 번째 셀 구성이 예상과 다름"

    helper = code_cell(
        "# 노트북 하나만으로 실행되도록 src/ 코드를 셀 안에 넣고 모듈로 등록한다 (저장소의 src/ 폴더가 없어도 동작).\n"
        "import os, sys, time, types\n"
        "\n"
        "def _register_module(name, source):\n"
        "    mod = types.ModuleType(name)\n"
        "    # ocr.py 는 가중치 폴더를 이 파일 위치 기준 ../weights 로 찾는다. 저장소 루트의 weights/ 를 가리키게 둔다\n"
        "    mod.__file__ = os.path.abspath(os.path.join(\"src\", name + \".py\"))\n"
        "    sys.modules[name] = mod          # exec 전에 등록해야 dataclass 와 모듈 간 import 가 동작\n"
        "    exec(compile(source, mod.__file__, \"exec\"), mod.__dict__)\n"
        "    return mod\n")
    imports = code_cell("import pandas as pd\nimport pipeline\n")

    for c in [config, *tail]:
        c["outputs"], c["execution_count"] = [], None
    nb["cells"] = [config, helper, *[module_cell(m) for m in MODULES], imports, *tail]

    with open(NB, "w", encoding="utf-8", newline="\n") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("written", NB, "cells", len(nb["cells"]))


if __name__ == "__main__":
    main()
