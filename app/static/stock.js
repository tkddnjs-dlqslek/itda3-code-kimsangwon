const STATUS = { expired: "기한 지남", imminent: "임박", ok: "여유", unknown: "날짜 불완전" };
const cell = (text, cls) => Object.assign(document.createElement("td"), { textContent: text, className: cls || "" });

async function load() {
  try {
    const [items, stats] = await Promise.all([fetch("/api/items").then((r) => r.json()), fetch("/api/stats").then((r) => r.json())]);
    document.getElementById("rows").replaceChildren(...items.map((it) => {
      const tr = document.createElement("tr");
      tr.append(
        cell(STATUS[it.status], it.status), cell(it.final_date), cell(it.days_left === null ? "" : `${it.days_left}일`),
        cell(it.product_name || "(이름 없음)"), cell(it.barcode),
        cell(it.confidence === null ? "" : `${Math.round(it.confidence * 100)}%${it.edited ? " (수정됨)" : ""}`),
        cell(it.mode === "manual" ? "수기" : "촬영"), cell(it.seconds === null ? "" : `${it.seconds}초`));
      return tr;
    }));
    const scan = stats.modes.scan, manual = stats.modes.manual;
    const lines = [
      scan ? `촬영 ${scan.n}건, 건당 평균 ${scan.avg_seconds}초` : "촬영 기록 없음",
      manual ? `수기 ${manual.n}건, 건당 평균 ${manual.avg_seconds}초` : "수기 기록 없음",
      scan && manual && manual.avg_seconds > 0 ? `건당 ${(manual.avg_seconds - scan.avg_seconds).toFixed(1)}초 단축 (${Math.round((1 - scan.avg_seconds / manual.avg_seconds) * 100)}%)` : "",
      stats.review_rate === null ? "" : `사람 확인이 필요했던 비율 ${Math.round(stats.review_rate * 100)}%, 실제로 고친 비율 ${Math.round(stats.edit_rate * 100)}%`,
      stats.second_shot_rate === null || stats.second_shot_rate === undefined ? "" : `날짜 면을 다시 대야 했던 비율(2차 촬영) ${Math.round(stats.second_shot_rate * 100)}%`,
    ].filter(Boolean);
    document.getElementById("stats").replaceChildren(...lines.map((t) => Object.assign(document.createElement("div"), { textContent: t })));
  } catch (e) {
    document.getElementById("stats").textContent = `목록을 불러오지 못했습니다: ${e.message}`;
  }
}

load();
