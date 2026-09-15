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

    # 이미지 목록 셀부터 끝까지는 그대로 두고, 그 앞(sys.path import 또는 이전에 생성한 모듈 셀)은 새로 만든다.
    # 위치가 아니라 내용으로 찾으므로 원본 노트북과 이미 변환된 노트북 모두에서 다시 돌릴 수 있다.
    # (모듈 원문 셀에도 "list_images" 정의가 있으므로 노트북 셀에만 있는 호출문으로 찾는다)
    starts = [i for i, c in enumerate(code) if "pipeline.list_images(INPUT_DIR)" in "".join(c["source"])]
    assert len(starts) == 1, "이미지 목록 셀(pipeline.list_images(INPUT_DIR))이 정확히 하나여야 함"
    tail = code[starts[0]:]

    helper = code_cell(
        "# 노트북 하나만으로 실행되도록 src/ 코드를 셀 안에 넣고 모듈로 등록한다 (저장소의 src/ 폴더가 없어도 동작).\n"
        "import os, sys, time, types\n"
        "\n"
        "def _register_module(name, source):\n"
        "    mod = types.ModuleType(name)\n"
        "    # ocr.py 는 가중치 폴더를 이 파일 위치 기준 ../weights 로 찾는다. 리눅스는 '..' 앞 폴더가 실제로\n"
        "    # 있어야 경로를 풀므로(src/ 가 없으면 실패), 항상 존재하는 weights/ 안을 파일 위치로 둔다.\n"
        "    # -> weights/../weights == 저장소 루트의 weights/\n"
        "    mod.__file__ = os.path.join(os.path.abspath(\"weights\"), name + \".py\")\n"
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
