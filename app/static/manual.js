const $ = (id) => document.getElementById(id);
const part = (id, width) => { const v = $(id).value.trim(); return v ? v.padStart(width, "0") : "NONE"; };
const year_part = () => { const v = $("myear").value.trim(); return v ? v : "NONE"; };
let startedAt = 0, timer = null;

$("mstart").onclick = () => {
  startedAt = performance.now();
  $("mfields").hidden = false;
  ["mbarcode", "mpname", "myear", "mmonth", "mday"].forEach((id) => { $(id).value = ""; });
  $("mmsg").textContent = "";
  clearInterval(timer);
  timer = setInterval(() => { $("mtimer").textContent = `${((performance.now() - startedAt) / 1000).toFixed(1)}초`; }, 100);
  $("mbarcode").focus();
};

$("msave").onclick = async () => {
  const item = { barcode: $("mbarcode").value.trim(), product_name: $("mpname").value.trim(),
    year: year_part(), month: part("mmonth", 2), day: part("mday", 2),
    mode: "manual", seconds: Math.round((performance.now() - startedAt) / 100) / 10 };
  $("msave").disabled = true;
  try {
    const res = await fetch("/api/items", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(item) });
    if (res.status === 422) { $("mmsg").textContent = "날짜 형식을 확인해 주세요"; return; }   // 타이머는 계속 돈다: 시간 측정을 이어간다
    if (!res.ok) { $("mmsg").textContent = `저장 실패: 서버 오류 ${res.status}`; return; }
    clearInterval(timer);
    $("mfields").hidden = true;
    $("mmsg").textContent = `저장했습니다 (${item.seconds}초)`;
  } catch (e) {
    $("mmsg").textContent = "저장 실패: 서버에 연결할 수 없습니다";   // 타이머는 계속 돈다
  } finally {
    $("msave").disabled = false;
  }
};
