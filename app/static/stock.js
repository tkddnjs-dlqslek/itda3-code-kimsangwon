const STATUS = { expired: "기한 지남", imminent: "할인 대상", ok: "여유", unknown: "날짜 불완전" };
const $ = (id) => document.getElementById(id);
const cell = (text, cls) => Object.assign(document.createElement("td"), { textContent: text, className: cls || "" });
let discountOnly = true;

async function markMoved(id) {
  try {
    const res = await fetch(`/api/items/${id}/moved`, { method: "POST" });
    if (!res.ok) throw new Error(`서버 오류 ${res.status}`);
    load();
  } catch (e) { $("rule").textContent = `처리 실패: ${e.message}`; }
}

async function load() {
  try {
    const [items, stats] = await Promise.all([
      fetch(`/api/items${discountOnly ? "?discount=1" : ""}`).then((r) => r.json()),
      fetch("/api/stats").then((r) => r.json())]);
    $("rows").replaceChildren(...items.map((it) => {
      const tr = document.createElement("tr");
      if (it.moved) tr.className = "moved";
      const act = document.createElement("td");
      if ((it.status === "imminent" || it.status === "expired") && !it.moved) {
        const b = Object.assign(document.createElement("button"), { textContent: "옮김" });
        b.onclick = () => markMoved(it.id);
        act.append(b);
      } else if (it.moved) act.textContent = "옮김 완료";
      tr.append(
        cell(STATUS[it.status], it.status), cell(it.final_date),
        cell(it.days_left === null ? "" : `${it.days_left}일 (기준 ${it.discount_days}일)`),
        cell(it.product_name || "(이름 없음)"), cell(it.barcode),
        cell(it.confidence === null ? "" : `${Math.round(it.confidence * 100)}%${it.edited ? " (수정됨)" : ""}`),
        cell(it.mode === "manual" ? "수기" : (it.stage === "gs1" ? "바코드" : "촬영")), act);
      return tr;
    }));
    $("rule").textContent = discountOnly
      ? `소비기한까지 남은 일수가 분류별 기준 이하인 상품입니다 (신선 3일, 유제품 5일, 가공식품과 음료 21일, 의약품과 화장품 90일). 옮긴 뒤 "옮김"을 누르면 목록에서 빠집니다. ${items.length}건`
      : `전체 ${items.length}건, 소비기한 빠른 순`;
    const scan = stats.modes.scan, manual = stats.modes.manual;
    const lines = [
      scan ? `촬영 ${scan.n}건, 건당 평균 ${scan.avg_seconds}초` : "촬영 기록 없음",
      manual ? `수기 ${manual.n}건, 건당 평균 ${manual.avg_seconds}초` : "",
      scan && manual && manual.avg_seconds > 0 ? `건당 ${(manual.avg_seconds - scan.avg_seconds).toFixed(1)}초 단축 (${Math.round((1 - scan.avg_seconds / manual.avg_seconds) * 100)}%)` : "",
      stats.review_rate === null ? "" : `사람 확인이 필요했던 비율 ${Math.round(stats.review_rate * 100)}%, 실제로 고친 비율 ${Math.round(stats.edit_rate * 100)}%`,
      stats.second_shot_rate == null ? "" : `전체 재시도까지 간 비율 ${Math.round(stats.second_shot_rate * 100)}%`,
    ].filter(Boolean);
    $("stats").replaceChildren(...lines.map((t) => Object.assign(document.createElement("div"), { textContent: t })));
  } catch (e) {
    $("stats").textContent = `목록을 불러오지 못했습니다: ${e.message}`;
  }
}

function tab(d) {
  discountOnly = d;
  $("tabDiscount").classList.toggle("on", d); $("tabAll").classList.toggle("on", !d);
  $("csv").href = d ? "/api/items.csv?discount=1" : "/api/items.csv";
  load();
}
$("tabDiscount").onclick = () => tab(true);
$("tabAll").onclick = () => tab(false);
load();
