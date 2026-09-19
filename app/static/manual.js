const $ = (id) => document.getElementById(id);
const part = (id, width) => { const v = $(id).value.trim(); return v ? v.padStart(width, "0") : "NONE"; };
let startedAt = 0, timer = null;

$("mstart").onclick = () => {
  startedAt = performance.now();
  $("mfields").hidden = false;
  ["mbarcode", "mpname", "myear", "mmonth", "mday"].forEach((id) => { $(id).value = ""; });
  clearInterval(timer);
  timer = setInterval(() => { $("mtimer").textContent = `${((performance.now() - startedAt) / 1000).toFixed(1)}초`; }, 100);
  $("mbarcode").focus();
};

$("msave").onclick = async () => {
  const item = { barcode: $("mbarcode").value.trim(), product_name: $("mpname").value.trim(),
    year: part("myear", 4), month: part("mmonth", 2), day: part("mday", 2),
    mode: "manual", seconds: Math.round((performance.now() - startedAt) / 100) / 10 };
  const res = await fetch("/api/items", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(item) });
  if (!res.ok) { $("mtimer").textContent = "날짜 형식을 확인해 주세요"; return; }
  clearInterval(timer);
  $("mfields").hidden = true;
  $("mtimer").textContent = `저장했습니다 (${item.seconds}초)`;
};
