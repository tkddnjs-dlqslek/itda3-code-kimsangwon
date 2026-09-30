// GS1 바코드 해석. 의약품 일련번호 바코드(GS1 DataMatrix, GS1-128)는 상품코드(AI 01)와 함께
// 유효기한(AI 17, YYMMDD)과 제조번호(AI 10)를 담는다. 유효기한이 들어 있으면 OCR 없이 바로 기록한다.
// 일반 EAN-13(식품, 일반의약품)에는 날짜가 없으므로 null 을 돌려주고, 날짜는 OCR 로 읽는다.

const FIXED = { "00": 18, "01": 14, "02": 14, "11": 6, "12": 6, "13": 6, "15": 6, "16": 6, "17": 6, "20": 2 };
const GS = "\u001d";

function yymmdd(v) {
  if (!/^\d{6}$/.test(v)) return null;
  const y = 2000 + Number(v.slice(0, 2)), m = Number(v.slice(2, 4));
  let d = Number(v.slice(4, 6));
  if (m < 1 || m > 12) return null;
  if (d === 0) d = new Date(y, m, 0).getDate();        // GS1 규칙: 일이 00 이면 그 달 말일
  return { year: String(y), month: String(m).padStart(2, "0"), day: String(d).padStart(2, "0") };
}

function finish(ai) {
  if (!ai["01"] && !ai["17"]) return null;
  return { gtin: ai["01"] || null, lot: ai["10"] || null, expiry: ai["17"] ? yymmdd(ai["17"]) : null };
}

export function parseGS1(text) {
  if (!text) return null;
  let s = String(text).replace(/^\][A-Za-z]\d/, "");   // 심볼 식별자(]d2, ]C1) 제거
  if (/^\(\d{2,4}\)/.test(s)) {                         // 사람이 읽는 괄호 표기
    const ai = {};
    for (const m of s.matchAll(/\((\d{2,4})\)([^(]*)/g)) ai[m[1]] = m[2].trim();
    return finish(ai);
  }
  s = s.replace(/^\u001d/, "");
  if (s.length < 16 || !/^(01|02|17)/.test(s)) return null;   // EAN-13 같은 일반 바코드
  const ai = {};
  let i = 0;
  while (i < s.length) {
    const k = s.slice(i, i + 2);
    if (FIXED[k]) { ai[k] = s.slice(i + 2, i + 2 + FIXED[k]); i += 2 + FIXED[k]; if (s[i] === GS) i += 1; continue; }
    if (k === "10" || k === "21") {                     // 가변 길이: 구분자(GS) 또는 끝까지
      let j = s.indexOf(GS, i + 2); if (j < 0) j = s.length;
      ai[k] = s.slice(i + 2, j); i = j + 1; continue;
    }
    break;
  }
  return finish(ai);
}

// 상품 조회용 키: GS1 이면 GTIN-14 의 앞자리 0 을 뗀 13자리, 아니면 읽은 그대로
export function productKey(text) {
  const g = parseGS1(text);
  if (g && g.gtin) return g.gtin.replace(/^0/, "");
  return String(text || "").trim();
}
