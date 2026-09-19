// 프레임 차분 상태 기계. 물체가 들어와 멎는 순간에만 촬영 신호를 낸다 (순수 함수, DOM 의존 없음).
//   diff  : 직전 프레임과의 평균 밝기 차 = 움직임
//   scene : 빈 배경과의 평균 밝기 차   = 물체가 있는가
// OCR 이 장당 1.5초라 프레임마다 돌릴 수 없어서 이 관문이 필요하다.

export const DEFAULTS = { stillT: 4, stillTicks: 4, sceneT: 10 };

export function initial() {
  return { phase: "empty", still: 0 };
}

export function step(state, diff, scene, cfg = DEFAULTS) {
  const present = scene > cfg.sceneT;
  if (state.phase === "empty") {
    return { state: present ? { phase: "present", still: 0 } : state, capture: false };
  }
  if (!present) {
    return { state: initial(), capture: false };              // 물건을 치움: 다음 물건을 기다린다
  }
  if (state.phase === "captured") {
    return { state, capture: false };                         // 같은 물건을 두 번 찍지 않는다
  }
  const still = diff < cfg.stillT ? state.still + 1 : 0;
  if (still >= cfg.stillTicks) {
    return { state: { phase: "captured", still: 0 }, capture: true };
  }
  return { state: { phase: "present", still }, capture: false };
}

export function toGray(rgba) {
  const out = new Float32Array(rgba.length / 4);
  for (let i = 0, j = 0; i < rgba.length; i += 4, j += 1) {
    out[j] = 0.299 * rgba[i] + 0.587 * rgba[i + 1] + 0.114 * rgba[i + 2];
  }
  return out;
}

export function meanAbsDiff(a, b) {
  let sum = 0;
  for (let i = 0; i < a.length; i += 1) sum += Math.abs(a[i] - b[i]);
  return sum / a.length;
}
