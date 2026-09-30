// 연속 스캔 재시도 순서 (09-30): 한 번 실패해도 멈추지 않고 first/first/mid/full 을 돌며 반복한다.
// full 은 무겁기 때문에(장당 최대 8초) 직전 full 로부터 FULL_COOLDOWN_MS 안에 다시 차례가 오면 mid 로 대신한다.

export const SEQUENCE = ["first", "first", "mid", "full"];
export const FULL_COOLDOWN_MS = 6000;

// tries: 지금까지 이 상품에서 실패한 시도 횟수 (0부터). lastFullAt: 직전 full 판독 시각(ms) 또는 null.
export function nextShot(tries, lastFullAt, now) {
  const want = SEQUENCE[((tries % SEQUENCE.length) + SEQUENCE.length) % SEQUENCE.length];
  if (want === "full" && lastFullAt != null && now - lastFullAt < FULL_COOLDOWN_MS) return "mid";
  return want;
}

// 바코드 전환 판단 (09-30): 매 틱마다 바코드를 읽을 때, 방금 읽은 키(newKey)로 무엇을 할지 결정한다.
// curKey: 지금 들고 있는 상품의 바코드("" 면 아직 없음). lastSaved: 방금 저장한 바코드(쿨다운 중 같은 상품 무시용).
// "none": 아무것도 안 함(같은 상품이거나 키 없음, 또는 쿨다운 중 같은 상품이 아직 화면에 있음)
// "set": 지금 상품에 바코드를 채움(cur.barcode 가 비어 있던 경우)
// "switch": 다른 상품으로 바뀜(진행 중이던 항목은 버리고 새로 시작)
export function barcodeChange(curKey, newKey, lastSaved) {
  if (!newKey || newKey === curKey) return "none";
  if (!curKey) return newKey === lastSaved ? "none" : "set";
  return "switch";
}
