import { DEFAULTS, initial, step, toGray, meanAbsDiff } from "./motion.js";
import { parseGS1, productKey } from "./gs1.js";
import { nextShot, barcodeChange } from "./retry.js";

// 연속 스캔 (09-30): 검수원이 상품을 카메라 앞에서 돌리는 동안
//   바코드는 브라우저가 0.5초마다 찾고 (GS1 2D 바코드에 유효기한이 있으면 그걸로 끝),
//   소비기한은 멎은 프레임에서만 1.2초마다 서버로 판독한다.
// 둘 다 잡히고 신뢰도가 기준 이상이면 완료음과 함께 자동 저장한다. 낮으면(needs_review) 확인 화면을 열고,
// 확인 버튼을 눌러도 언제든 연다. 못 읽어도 멈추지 않고 first, first, mid, full 순서를 계속 돈다
// (nextShot, ./retry.js). full 은 무거워서 직전 full 로부터 6초 안이면 mid 로 대신한다.

const $ = (id) => document.getElementById(id);
const video = $("video"), small = $("small"), full = $("full");
const sctx = small.getContext("2d", { willReadFrequently: true });
// 바코드 판독 힌트: 1D 상품 바코드와 의약품 2D 만 찾고(오탐 감소), TRY_HARDER 로 작은 바코드까지 훑는다
const hints = new Map();
const F = ZXingBrowser.BarcodeFormat;         // DecodeHintType 은 번들이 이름으로 내보내지 않아 숫자 사용: 2 = POSSIBLE_FORMATS, 3 = TRY_HARDER
hints.set(3, true);
hints.set(2, [
  F.EAN_13, F.EAN_8, F.UPC_A, F.CODE_128, F.DATA_MATRIX, F.QR_CODE]);
const reader = new ZXingBrowser.BrowserMultiFormatReader(hints);
const OCR_EVERY_MS = 1200;

let state = initial(), prev = null, base = null;
let formOpen = false, inflight = false, cooldown = false, ticks = 0;
let cur = null;                      // 지금 들고 있는 상품
let lastSaved = "";                  // 방금 저장한 바코드 (치우기 전 같은 상품 중복 저장 방지)
let audio = null;
let recent = [];                     // 최근 저장 목록 (최대 3건, 최신이 앞)

const newItem = () => ({ barcode: "", productName: "", date: null, source: "", ocr: null,
  tries: 0, lastFullAt: null, gotWith: null, startedAt: performance.now(), lastOcr: 0 });

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
      video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 }, focusMode: "continuous" }, audio: false });
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

// 실패가 쌓일수록 안내를 바꾼다: 2회부터 날짜 면 유도, 4회(한 바퀴, full 까지 실패)부터 직접 입력 유도.
function hintFor(item) {
  if (item.date) return "";
  if (item.tries >= 4) return "안 읽히면 확인 버튼으로 직접 입력";
  if (item.tries >= 2) return "날짜 면을 카메라에 보여 주세요";
  return "";
}

async function ocrFrame(forcedShot) {
  if (inflight || !cur) return;
  inflight = true;
  const item = cur;
  const now = performance.now();
  item.lastOcr = now;
  const shot = forcedShot || nextShot(item.tries, item.lastFullAt, now);
  if (shot === "full") item.lastFullAt = now;
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
      if (!item.date) { item.date = { year: data.year, month: data.month, day: data.day }; item.source = "ocr"; item.ocr = data; item.gotWith = shot; }
    } else {
      item.tries += 1;
    }
    const base = `판독 ${data.elapsed_ms}ms (${data.stage})`;
    const hint = hintFor(item);
    $("msg").textContent = hint ? `${base}. ${hint}` : base;
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
  if (ticks % 2 === 0) {              // 바코드는 상품을 들고 있는 내내 매번 읽는다: 안 그러면 A 를 든 채 B 를 대도 A 로 남는다
    const text = readBarcodeText();
    const key = productKey(text);
    const action = key ? barcodeChange(cur ? cur.barcode : "", key, lastSaved) : "none";
    if (action === "switch") {        // 진행 중이던 상품과 다른 바코드: 버리고 새로 시작
      $("msg").textContent = `다른 상품으로 바뀜: ${key}`;
      cooldown = false; cur = newItem(); setBarcode(text);
    } else if (action === "set") {    // 쿨다운 탈출 또는 바코드가 비어 있던 상품에 채움
      cooldown = false; cur = cur || newItem(); setBarcode(text);
    }
  }
  if (cooldown) return;               // 저장 직후: 상품을 치우거나 다른 바코드가 보일 때까지 쉰다
  if (!cur) cur = newItem();
  // 손이 움직이는 중인 프레임은 판독에 쓰지 않는다: 흔들린 사진은 시도 횟수만 낭비한다
  if (!cur.date && diff < DEFAULTS.stillT && performance.now() - cur.lastOcr > OCR_EVERY_MS) ocrFrame();
  render();
  maybeComplete();
}

function render() {
  const b = $("chipBarcode"), d = $("chipDate");
  b.classList.toggle("ok", !!(cur && cur.barcode));
  d.classList.toggle("ok", !!(cur && cur.date));
  b.textContent = cur && cur.barcode ? `✓ 바코드: ${cur.productName || `미등록 ${cur.barcode}`}` : "바코드 찾는 중";
  d.textContent = cur && cur.date ? `✓ 소비기한: ${cur.date.year}-${cur.date.month}-${cur.date.day}${cur.source === "barcode" ? " (바코드)" : ""}` : "소비기한 찾는 중";
  $("phase").textContent = cooldown ? "저장 완료: 다음 상품을 대 주세요"
    : !cur ? "상품을 카메라 앞에서 돌려 주세요"
    : !cur.barcode && !cur.date ? "바코드와 소비기한을 찾는 중"
    : !cur.barcode ? "바코드 면을 보여 주세요" : !cur.date ? "소비기한 면을 보여 주세요" : "확인 중";
}

function maybeComplete() {
  if (!cur || formOpen) return;
  if (cur.date && cur.barcode) {
    if (cur.source === "barcode" || (cur.ocr && !cur.ocr.needs_review)) autoSave();
    else openForm();                  // (가) 날짜는 읽혔지만 확인이 필요함
  }
  // (나) 사용자가 "확인 화면 열기" 버튼을 눌렀을 때는 그 클릭 핸들러가 직접 openForm() 을 부른다
}

const seconds = () => Math.round((performance.now() - cur.startedAt) / 100) / 10;

function itemFrom(date, edited) {
  const o = cur.ocr;
  return {
    barcode: cur.barcode, product_name: cur.productName, year: date.year, month: date.month, day: date.day,
    confidence: cur.source === "barcode" ? 1 : (o ? o.confidence : null),
    needs_review: cur.source === "barcode" ? false : (o ? o.needs_review : true),
    edited, second_shot: !!cur.gotWith && cur.gotWith !== "first", stage: cur.source === "barcode" ? "gs1" : (o ? o.stage : ""),
    evidence: cur.source === "barcode" ? ["GS1 바코드 유효기한"] : (o ? o.evidence : []),
    mode: "scan", seconds: seconds(),
  };
}

async function post(item) {
  const res = await fetch("/api/items", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(item) });
  if (res.status === 422) throw new Error("날짜 형식을 확인해 주세요 (연 4자리, 월과 일 2자리)");
  if (!res.ok) throw new Error(`서버 오류 ${res.status}`);
}

function pushRecent(item, confirmed) {
  const name = item.product_name || item.barcode || "(바코드 없음)";
  const via = confirmed ? "확인 후 저장" : "자동 저장";
  const gs1 = item.stage === "gs1" ? " (바코드)" : "";
  recent = [`${name} ${item.year}-${item.month}-${item.day} ${via}${gs1}`, ...recent].slice(0, 3);
  $("recent").replaceChildren(...recent.map((t) => Object.assign(document.createElement("li"), { textContent: t })));
}

function done(item, confirmed) {
  beep();
  $("flash").hidden = false; setTimeout(() => { $("flash").hidden = true; }, 350);
  $("msg").textContent = `저장: ${item.product_name || item.barcode || "(바코드 없음)"} ${item.year}-${item.month}-${item.day} (${item.seconds}초)`;
  lastSaved = item.barcode; cooldown = true; cur = null; render();
  pushRecent(item, confirmed);
}

async function autoSave() {
  const item = itemFrom(cur.date, false);
  formOpen = true;                    // 저장 중 중복 방지
  try { await post(item); done(item, false); } catch (e) { $("msg").textContent = `저장 실패: ${e.message}`; }
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
  try { await post(item); closeForm(); done(item, true); }
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
