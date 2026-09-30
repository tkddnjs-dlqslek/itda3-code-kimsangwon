// 중고거래 기한 검증 화면: 사진 1장을 /api/verify 로 보내고 allow, block, review 를 크게 보여 준다.
const $ = (id) => document.getElementById(id);
const TITLE = { allow: "등록 가능", block: "등록 불가", review: "운영자 확인 필요" };

$("photo").onchange = () => {
  const f = $("photo").files[0];
  if (!f) { $("preview").hidden = true; return; }
  $("preview").src = URL.createObjectURL(f); $("preview").hidden = false;
  $("result").hidden = true; $("msg").textContent = "";
};

$("run").onclick = async () => {
  const f = $("photo").files[0];
  if (!f) { $("msg").textContent = "소비기한 표시 부분 사진을 먼저 선택해 주세요."; return; }
  const body = new FormData();
  body.append("image", f, f.name || "photo.jpg");
  body.append("min_months", $("minMonths").value || "0");
  body.append("product_name", $("pname").value.trim());
  $("run").disabled = true; $("msg").textContent = "판독 중";
  try {
    const res = await fetch("/api/verify", { method: "POST", body });
    if (!res.ok) throw new Error(`서버 오류 ${res.status}`);
    show(await res.json());
    $("msg").textContent = "";
  } catch (e) {
    $("msg").textContent = `검증 실패: ${e.message}`;
  } finally {
    $("run").disabled = false;
  }
};

function show(d) {
  const r = $("result");
  r.hidden = false;
  r.className = `card verdict ${d.verdict}`;
  $("title").textContent = `${TITLE[d.verdict] || d.verdict}${d.product_name ? `: ${d.product_name}` : ""}`;
  $("reason").textContent = d.reason;
  const months = d.months_left == null ? "계산 불가" : `${d.months_left}개월`;
  const conf = d.confidence == null ? "" : `, 신뢰도 ${Math.round(d.confidence * 100)}%`;
  $("detail").textContent = `읽은 소비기한 ${d.final_date}, 남은 기간 ${months}, 기준 ${d.min_months}개월${conf}, ${d.elapsed_ms}ms (${d.stage})`;
  $("evidence").replaceChildren(...(d.evidence || []).slice(0, 5).map((t) => Object.assign(document.createElement("li"), { textContent: t })));
}
