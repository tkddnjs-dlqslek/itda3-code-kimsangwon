// 중고거래 기한 검증 화면: 게시글 사진 최대 5장을 /api/verify_listing 으로 보내고 allow, block, review 를 보여 준다.
const $ = (id) => document.getElementById(id);
const TITLE = { allow: "등록 가능", block: "등록 불가", review: "운영자 확인 필요" };
const MAX_PHOTOS = 5;
let selected = [];

$("photoFiles").onchange = () => {
  const files = Array.from($("photoFiles").files || []);
  if (files.length > MAX_PHOTOS) {
    $("msg").textContent = "최대 5장까지 올릴 수 있습니다";
    selected = files.slice(0, MAX_PHOTOS);
  } else {
    $("msg").textContent = "";
    selected = files;
  }
  $("thumbs").replaceChildren(...selected.map((f) => {
    const img = document.createElement("img");
    img.src = URL.createObjectURL(f);
    img.alt = f.name;
    return img;
  }));
  $("result").hidden = true;
};

$("run").onclick = async () => {
  if (selected.length === 0) {
    $("msg").textContent = "소비기한 표시 부분이 보이는 사진을 먼저 선택해 주세요.";
    return;
  }
  const body = new FormData();
  selected.forEach((f, i) => body.append("images", f, f.name || `photo${i}.jpg`));
  body.append("product_name", $("pname").value.trim());
  // 진행 표시: 버튼 글자와 안내 줄에 경과 초를 1초마다 찍는다 (서버는 사진당 1~8초, 2단계 판독)
  const n = selected.length, t0 = performance.now();
  $("run").disabled = true; $("result").hidden = true;
  const tickMsg = () => {
    const sec = Math.round((performance.now() - t0) / 1000);
    $("run").textContent = `판독 중 ${sec}초`;
    $("msg").textContent = `사진 ${n}장 판독 중입니다. 1차는 빠르게 훑고 날짜가 없는 사진만 정밀 판독합니다. 최대 ${n * 8 + n * 2}초`;
  };
  tickMsg(); const timer = setInterval(tickMsg, 1000);
  try {
    const res = await fetch("/api/verify_listing", { method: "POST", body });
    if (!res.ok) throw new Error(`서버 오류 ${res.status}`);
    show(await res.json());
    $("msg").textContent = "";
  } catch (e) {
    $("msg").textContent = `검증 실패: ${e.message}`;
  } finally {
    clearInterval(timer); $("run").textContent = "검증"; $("run").disabled = false;
  }
};

$("modalClose").onclick = () => { $("modal").hidden = true; };

function openModal(text) {
  $("modalText").textContent = text;
  $("modal").hidden = false;
}

function show(d) {
  const r = $("result");
  r.hidden = false;
  r.className = `card verdict ${d.verdict}`;
  $("title").textContent = `${TITLE[d.verdict] || d.verdict}${d.product_name ? `: ${d.product_name}` : ""}`;
  $("reason").textContent = d.reason;
  if (d.min_photo != null && d.deadline != null) {
    $("detail").textContent = `가장 빠른 소비기한 ${d.deadline} (사진 ${d.min_photo + 1}), 남은 기간 ${d.months_left}개월, 소요 ${d.elapsed_ms}ms`;
  } else {
    $("detail").textContent = `소요 ${d.elapsed_ms}ms`;
  }
  $("photos").replaceChildren(...(d.photos || []).map((p) => {
    const text = p.final_date === "NONE"
      ? `사진 ${p.index + 1}: 소비기한 없음`
      : `사진 ${p.index + 1}: ${p.final_date} (신뢰도 ${p.confidence == null ? "확인 불가" : `${Math.round(p.confidence * 100)}%`})`;
    return Object.assign(document.createElement("li"), { textContent: text });
  }));
  if (d.verdict === "block") {
    openModal(`소비기한(유통기한)이 ${d.min_months}개월 이상 남을 때만 업로드 가능합니다`);
  } else if (d.verdict === "review" && d.min_photo == null) {
    openModal("소비기한 표시 부분이 보이는 사진을 추가해 주십시오");
  }
}
