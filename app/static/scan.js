import { DEFAULTS, initial, step, toGray, meanAbsDiff } from "./motion.js";

const $ = (id) => document.getElementById(id);
const PHASE = { empty: "대기 중: 상품을 대 주세요", present: "상품 감지: 잠시 멈춰 주세요", captured: "촬영 완료: 상품을 치워 주세요" };
const video = $("video"), small = $("small"), full = $("full");
const sctx = small.getContext("2d", { willReadFrequently: true });
const reader = new ZXingBrowser.BrowserMultiFormatReader();

let state = initial();
let prev = null, base = null;   // 직전 프레임, 빈 배경 (흑백 64x48)
let busy = false;               // 판독 중이거나 확인 화면이 열려 있으면 새로 찍지 않는다
let presentAt = 0;              // 상품이 화면에 들어온 시각 (자동 촬영의 ROI 시작점)
let capturedAt = 0;             // 촬영 시각. 저장까지 걸린 시간을 잰다 (ROI 실측)
let ocr = null;                 // 서버 판독값. 사람이 고쳤는지 비교하는 기준

async function start() {
  try {
    video.srcObject = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
    await video.play();
    setInterval(tick, 200);
  } catch (e) {
    $("phase").textContent = "카메라를 열 수 없습니다";
    $("msg").textContent = e.message;
  }
}

function tick() {
  if (busy || video.readyState < 2) return;
  sctx.drawImage(video, 0, 0, small.width, small.height);
  const gray = toGray(sctx.getImageData(0, 0, small.width, small.height).data);
  if (!base) { base = gray; prev = gray; return; }
  const diff = meanAbsDiff(gray, prev), scene = meanAbsDiff(gray, base);
  prev = gray;
  const prevPhase = state.phase;
  const r = step(state, diff, scene);
  state = r.state;
  if (prevPhase === "empty" && state.phase === "present") presentAt = performance.now();   // ROI 시작점: 상품이 화면에 들어온 순간
  if (state.phase === "empty" && diff < DEFAULTS.stillT) {
    for (let i = 0; i < base.length; i += 1) base[i] = (base[i] * 9 + gray[i]) / 10;   // 조명 변화에 배경을 천천히 맞춘다
  }
  $("phase").textContent = PHASE[state.phase];
  if (r.capture) capture(false);
}

function readBarcode() {
  if (video.readyState < 2) return "";
  try {
    full.width = video.videoWidth;
    full.height = video.videoHeight;
    full.getContext("2d").drawImage(video, 0, 0);
    return reader.decodeFromCanvas(full).getText();
  } catch (e) { return ""; }   // 못 찾으면 예외
}

async function capture(manual) {
  if (video.readyState < 2) return;   // 프레임이 아직 없으면 찍지 않는다 (busy 를 세우기 전에 확인)
  busy = true;
  capturedAt = manual ? performance.now() : presentAt;   // 자동 촬영은 상품이 들어온 순간부터, 수동 촬영은 누른 순간부터
  $("phase").textContent = "판독 중";
  try {
    const barcode = readBarcode();
    const blob = await new Promise((resolve) => full.toBlob(resolve, "image/jpeg", 0.92));
    if (!blob) throw new Error("이미지를 만들지 못했습니다");
    const body = new FormData();
    body.append("image", blob, "frame.jpg");
    body.append("barcode", barcode);
    const res = await fetch("/api/scan", { method: "POST", body });
    if (!res.ok) throw new Error(`서버 오류 ${res.status}`);
    showForm(await res.json(), barcode);
  } catch (e) {
    $("msg").textContent = `판독 실패: ${e.message}`;
    busy = false;
  }
}

const blank = (v) => (v === "NONE" ? "" : v);
const part = (id, width) => { const v = $(id).value.trim(); return v ? v.padStart(width, "0") : "NONE"; };

function showForm(data, barcode) {
  ocr = data;
  $("form").hidden = false;
  $("form").classList.toggle("review", data.needs_review);
  $("badge").textContent = `${data.needs_review ? "확인 필요" : "자동 통과"} ${Math.round(data.confidence * 100)}%`;
  $("save").textContent = data.needs_review ? "확인하고 저장" : "저장";
  $("barcode").value = barcode;
  $("pname").value = data.product ? data.product.name : "";
  $("year").value = blank(data.year);
  $("month").value = blank(data.month);
  $("day").value = blank(data.day);
  $("evidence").replaceChildren(...data.evidence.map((t) => Object.assign(document.createElement("li"), { textContent: t })));
  $("msg").textContent = `판독 ${data.elapsed_ms}ms, 시도 단계 ${data.stage}`;
}

function closeForm(message) {
  $("form").hidden = true;
  $("msg").textContent = message;
  ocr = null;
  busy = false;      // 상태 기계는 captured 에 머물러 있어 물건을 치울 때까지 다시 찍지 않는다
}

async function save() {
  const year = $("year").value.trim() || "NONE", month = part("month", 2), day = part("day", 2);
  const item = {
    barcode: $("barcode").value.trim(), product_name: $("pname").value.trim(), year, month, day,
    confidence: ocr.confidence, needs_review: ocr.needs_review, stage: ocr.stage, evidence: ocr.evidence,
    edited: year !== ocr.year || month !== ocr.month || day !== ocr.day,
    mode: "scan", seconds: Math.round((performance.now() - capturedAt) / 100) / 10,
  };
  $("save").disabled = true;
  try {
    const res = await fetch("/api/items", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(item) });
    if (res.status === 422) { $("msg").textContent = "저장 실패: 날짜 형식을 확인해 주세요 (연 4자리, 월과 일 2자리)"; return; }
    if (!res.ok) { $("msg").textContent = `저장 실패: 서버 오류 ${res.status}`; return; }
    closeForm(`저장했습니다 (${item.seconds}초). 상품을 치우고 다음 상품을 대 주세요.`);
  } catch (e) {
    $("msg").textContent = "저장 실패: 서버에 연결할 수 없습니다";   // 폼은 열어 둔다: 재시도할 수 있게
  } finally {
    $("save").disabled = false;
  }
}

async function findProduct() {
  try {
    const res = await fetch(`/api/product/${encodeURIComponent($("barcode").value.trim())}`);
    $("pname").value = res.ok ? (await res.json()).name : "";
    if (!res.ok) $("msg").textContent = "등록되지 않은 바코드입니다. 상품명을 직접 적어 주세요.";
  } catch (e) {
    $("msg").textContent = "상품 조회 실패: 서버에 연결할 수 없습니다";
  }
}

$("shoot").onclick = () => { if (!busy) capture(true); };
$("rebase").onclick = () => { base = null; state = initial(); $("msg").textContent = "빈 배경을 다시 잡았습니다."; };
$("rescan").onclick = () => { const code = readBarcode(); if (code) { $("barcode").value = code; findProduct(); } else $("msg").textContent = "바코드를 찾지 못했습니다."; };
$("find").onclick = findProduct;
$("save").onclick = save;
$("skip").onclick = () => closeForm("버렸습니다. 상품을 치우고 다시 대 주세요.");
start();
