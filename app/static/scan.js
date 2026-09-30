import { DEFAULTS, initial, step, toGray, meanAbsDiff } from "./motion.js";
import { parseGS1, productKey } from "./gs1.js";

// 연속 스캔 (09-30): 검수원이 상품을 카메라 앞에서 돌리는 동안
//   바코드는 브라우저가 0.5초마다 찾고 (GS1 2D 바코드에 유효기한이 있으면 그걸로 끝),
//   소비기한은 1.2초마다 서버 싼 모드(1단계, 2단계, 검출기 교체)로 판독한다.
// 둘 다 잡히고 신뢰도가 기준 이상이면 완료음과 함께 자동 저장, 낮으면 그때만 확인 화면을 연다.
// 싼 모드로 3번 못 읽으면 전체 재시도 1번, 그래도 없으면 확인 화면에서 직접 입력.

const $ = (id) => document.getElementById(id);
const video = $("video"), small = $("small"), full = $("full");
const sctx = small.getContext("2d", { willReadFrequently: true });
const reader = new ZXingBrowser.BrowserMultiFormatReader();
const OCR_EVERY_MS = 1200, CHEAP_TRIES = 3;

let state = initial(), prev = null, base = null;
let formOpen = false, inflight = false, cooldown = false, ticks = 0;
let cur = null;                      // 지금 들고 있는 상품
let lastSaved = "";                  // 방금 저장한 바코드 (치우기 전 같은 상품 중복 저장 방지)
let audio = null;

const newItem = () => ({ barcode: "", productName: "", date: null, source: "", ocr: null,
  tries: 0, fullTried: false, failed: false, startedAt: performance.now(), lastOcr: 0 });

function beep() {
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    const o = audio.createOscillator(), g = audio.createGain();
    o.frequency.value = 1760; g.gain.value = 0.15;
    o.connect(g); g.connect(audio.destination); o.start(); o.stop(audio.currentTime + 0.12);
  } catch (e) { /* 소리 없이 진행 */ }
  if (navigator.vibrate) navigator.vibrate(80);
}

async function start() {
  $("start").hidden = true;
  beep();                             // 휴대폰은 사용자 동작 뒤에만 소리를 허용한다
  try {
    video.srcObject = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
    await video.play();
    setInterval(tick, 250);
    $("phase").textContent = "상품을 카메라 앞에서 돌려 주세요";
  } catch (e) {
    $("phase").textContent = "카메라를 열 수 없습니다";
    $("msg").textContent = `${e.message}. 휴대폰은 https 주소로 접속해야 카메라가 열립니다.`;
    $("start").hidden = false;
  }
}

function grabFull() {
  full.width = video.videoWidth; full.height = video.videoHeight;
  full.getContext("2d").drawImage(video, 0, 0);
}

function readBarcodeText() {
  try { grabFull(); return reader.decodeFromCanvas(full).getText(); } catch (e) { return ""; }
}

async function setBarcode(text) {
  const key = productKey(text);
  if (!key) return;
  cur.barcode = key;
  const g = parseGS1(text);
  if (g && g.expiry) { cur.date = g.expiry; cur.source = "barcode"; }   // 의약품 2D 바코드: 유효기한을 바코드에서
  try {
    const res = await fetch(`/api/product/${encodeURIComponent(key)}`);
    if (res.ok) cur && cur.barcode === key && (cur.productName = (await res.json()).name);
  } catch (e) { /* 상품명 없이 진행 */ }
  render();
}

async function ocrFrame(shot) {
  if (inflight || !cur) return;
  inflight = true;
  const item = cur;
  item.lastOcr = performance.now();
  if (!shot) shot = item.tries >= CHEAP_TRIES && !item.fullTried ? "second" : "first";
  if (shot !== "first") item.fullTried = true;
  try {
    grabFull();
    const blob = await new Promise((resolve) => full.toBlob(resolve, "image/jpeg", 0.9));
    if (!blob) throw new Error("이미지를 만들지 못했습니다");
    const body = new FormData();
    body.append("image", blob, "frame.jpg"); body.append("barcode", item.barcode); body.append("shot", shot);
    const res = await fetch("/api/scan", { method: "POST", body });
    if (!res.ok) throw new Error(`서버 오류 ${res.status}`);
    const data = await res.json();
    if (data.final_date !== "NONE") {
      if (!item.date) { item.date = { year: data.year, month: data.month, day: data.day }; item.source = "ocr"; item.ocr = data; }
    } else {
      item.tries += 1;
      if (item.fullTried && shot !== "first") item.failed = true;
    }
    $("msg").textContent = `판독 ${data.elapsed_ms}ms (${data.stage})`;
  } catch (e) {
    $("msg").textContent = `판독 실패: ${e.message}`;
  } finally {
    inflight = false;
  }
}

function tick() {
  if (formOpen || video.readyState < 2) return;
  sctx.drawImage(video, 0, 0, small.width, small.height);
  const gray = toGray(sctx.getImageData(0, 0, small.width, small.height).data);
  if (!base) { base = gray; prev = gray; return; }
  const diff = meanAbsDiff(gray, prev), scene = meanAbsDiff(gray, base);
  prev = gray;
  state = step(state, diff, scene);
  if (state.phase === "empty") {
    if (diff < DEFAULTS.stillT) for (let i = 0; i < base.length; i += 1) base[i] = (base[i] * 9 + gray[i]) / 10;
    if (cur || cooldown) { cur = null; cooldown = false; lastSaved = ""; render(); }
    return;
  }
  ticks += 1;
  if (cooldown) {                     // 저장 직후: 상품을 치우거나 다른 바코드가 보일 때까지 쉰다
    if (ticks % 2 === 0) {
      const text = readBarcodeText();
      if (text && productKey(text) !== lastSaved) { cooldown = false; cur = newItem(); setBarcode(text); }
    }
    return;
  }
  if (!cur) cur = newItem();
  if (!cur.barcode && ticks % 2 === 0) { const text = readBarcodeText(); if (text) setBarcode(text); }
  if (!cur.date && !cur.failed && performance.now() - cur.lastOcr > OCR_EVERY_MS) ocrFrame();
  render();
  maybeComplete();
}

function render() {
  const b = $("chipBarcode"), d = $("chipDate");
  b.classList.toggle("ok", !!(cur && cur.barcode));
  d.classList.toggle("ok", !!(cur && cur.date));
  b.textContent = cur && cur.barcode ? `바코드 ${cur.productName || cur.barcode}` : "바코드";
  d.textContent = cur && cur.date ? `소비기한 ${cur.date.year}-${cur.date.month}-${cur.date.day}${cur.source === "barcode" ? " (바코드)" : ""}` : "소비기한";
  $("phase").textContent = cooldown ? "저장 완료: 다음 상품을 대 주세요"
    : !cur ? "상품을 카메라 앞에서 돌려 주세요"
    : !cur.barcode && !cur.date ? "바코드와 소비기한을 찾는 중"
    : !cur.barcode ? "바코드 면을 보여 주세요" : !cur.date ? "소비기한 면을 보여 주세요" : "확인 중";
}

function maybeComplete() {
  if (!cur || formOpen) return;
  if (cur.date && cur.barcode) {
    if (cur.source === "barcode" || (cur.ocr && !cur.ocr.needs_review)) autoSave();
    else openForm();
  } else if (cur.failed) {
    openForm();                       // 소비기한을 끝내 못 읽음: 직접 입력
  }
}

const seconds = () => Math.round((performance.now() - cur.startedAt) / 100) / 10;

function itemFrom(date, edited) {
  const o = cur.ocr;
  return {
    barcode: cur.barcode, product_name: cur.productName, year: date.year, month: date.month, day: date.day,
    confidence: cur.source === "barcode" ? 1 : (o ? o.confidence : null),
    needs_review: cur.source === "barcode" ? false : (o ? o.needs_review : true),
    edited, second_shot: cur.fullTried, stage: cur.source === "barcode" ? "gs1" : (o ? o.stage : ""),
    evidence: cur.source === "barcode" ? ["GS1 바코드 유효기한"] : (o ? o.evidence : []),
    mode: "scan", seconds: seconds(),
  };
}

async function post(item) {
  const res = await fetch("/api/items", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(item) });
  if (res.status === 422) throw new Error("날짜 형식을 확인해 주세요 (연 4자리, 월과 일 2자리)");
  if (!res.ok) throw new Error(`서버 오류 ${res.status}`);
}

function done(item) {
  beep();
  $("flash").hidden = false; setTimeout(() => { $("flash").hidden = true; }, 350);
  $("msg").textContent = `저장: ${item.product_name || item.barcode || "(바코드 없음)"} ${item.year}-${item.month}-${item.day} (${item.seconds}초)`;
  lastSaved = item.barcode; cooldown = true; cur = null; render();
}

async function autoSave() {
  const item = itemFrom(cur.date, false);
  formOpen = true;                    // 저장 중 중복 방지
  try { await post(item); done(item); } catch (e) { $("msg").textContent = `저장 실패: ${e.message}`; }
  finally { formOpen = false; }
}

// ---- 확인 화면: 신뢰도가 낮거나 못 읽었거나 바코드 없이 저장할 때
const blank = (v) => (!v || v === "NONE" ? "" : v);
const part = (id, width) => { const v = $(id).value.trim(); return v ? v.padStart(width, "0") : "NONE"; };

function openForm() {
  if (!cur) cur = newItem();
  formOpen = true;
  const o = cur.ocr;
  $("form").hidden = false;
  $("form").classList.toggle("review", true);
  $("badge").textContent = o ? `확인 필요 ${Math.round(o.confidence * 100)}%` : "직접 입력";
  $("barcode").value = cur.barcode;
  $("pname").value = cur.productName;
  $("year").value = blank(cur.date && cur.date.year);
  $("month").value = blank(cur.date && cur.date.month);
  $("day").value = blank(cur.date && cur.date.day);
  $("evidence").replaceChildren(...(o ? o.evidence : []).map((t) => Object.assign(document.createElement("li"), { textContent: t })));
}

function closeForm(message) {
  $("form").hidden = true; formOpen = false;
  if (message) $("msg").textContent = message;
}

async function saveForm() {
  const date = { year: $("year").value.trim() || "NONE", month: part("month", 2), day: part("day", 2) };
  cur.barcode = $("barcode").value.trim(); cur.productName = $("pname").value.trim();
  const before = cur.date || { year: "NONE", month: "NONE", day: "NONE" };
  const item = itemFrom(date, date.year !== before.year || date.month !== before.month || date.day !== before.day);
  $("save").disabled = true;
  try { await post(item); closeForm(); done(item); }
  catch (e) { $("msg").textContent = `저장 실패: ${e.message}`; }
  finally { $("save").disabled = false; }
}

async function findProduct() {
  try {
    const res = await fetch(`/api/product/${encodeURIComponent($("barcode").value.trim())}`);
    $("pname").value = res.ok ? (await res.json()).name : "";
    if (!res.ok) $("msg").textContent = "등록되지 않은 바코드입니다. 상품명을 직접 적어 주세요.";
  } catch (e) { $("msg").textContent = "상품 조회 실패: 서버에 연결할 수 없습니다"; }
}

$("start").onclick = start;
$("shoot").onclick = () => { if (!formOpen) { cur = cur || newItem(); cooldown = false; ocrFrame("full"); } };
$("confirm").onclick = () => { if (!formOpen) openForm(); };
$("rebase").onclick = () => { base = null; state = initial(); $("msg").textContent = "빈 배경을 다시 잡았습니다."; };
$("rescan").onclick = () => { const t = readBarcodeText(); if (t) { $("barcode").value = productKey(t); findProduct(); } else $("msg").textContent = "바코드를 찾지 못했습니다."; };
$("find").onclick = findProduct;
$("save").onclick = saveForm;
$("skip").onclick = () => { closeForm("버렸습니다."); cur = null; cooldown = true; lastSaved = ""; render(); };

// USB 바코드 스캐너: 키보드처럼 숫자와 엔터를 빠르게 보낸다 (입력 칸에 포커스가 없을 때)
let keyBuf = "", keyAt = 0;
document.addEventListener("keydown", (e) => {
  const tag = (e.target.tagName || "").toUpperCase();
  if (tag === "INPUT" || tag === "TEXTAREA") return;
  const now = performance.now();
  if (now - keyAt > 500) keyBuf = "";
  keyAt = now;
  if (e.key.length === 1) { keyBuf += e.key; return; }
  if (e.key !== "Enter" || keyBuf.length < 8) { if (e.key === "Enter") keyBuf = ""; return; }
  e.preventDefault();
  const text = keyBuf; keyBuf = "";
  if (formOpen) return;
  cooldown = false; cur = newItem(); setBarcode(text);
});
render();
