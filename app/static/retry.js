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
