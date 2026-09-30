import test from "node:test";
import assert from "node:assert/strict";
import { nextShot, SEQUENCE, FULL_COOLDOWN_MS, barcodeChange } from "./retry.js";

test("순환: first, first, mid, full 을 반복한다", () => {
  const got = Array.from({ length: 8 }, (_, i) => nextShot(i, null, 100000));
  assert.deepEqual(got, ["first", "first", "mid", "full", "first", "first", "mid", "full"]);
});

test("full 6초 제한: 직전 full 로부터 6초가 안 지나면 아직 full 을 허용하지 않는다", () => {
  const idx = SEQUENCE.indexOf("full");
  assert.equal(nextShot(idx, 1000, 1000 + FULL_COOLDOWN_MS - 1), "mid");
  assert.equal(nextShot(idx, 1000, 1000 + FULL_COOLDOWN_MS), "full");
});

test("mid 대체: full 차례가 막히면 항상 mid 로, first 로는 안 내려간다", () => {
  const idx = SEQUENCE.indexOf("full");
  for (const gap of [0, 1, 5999]) {
    assert.equal(nextShot(idx, 2000, 2000 + gap), "mid");
  }
});

test("리셋: tries 를 0으로 되돌리면 lastFullAt 과 무관하게 first 부터 다시 시작한다", () => {
  assert.equal(nextShot(0, 9_999_999, 10_000_000), "first");
  assert.equal(nextShot(0, null, 0), "first");
});

test("barcodeChange: 같은 키면 아무것도 안 함", () => {
  assert.equal(barcodeChange("880123", "880123", ""), "none");
});

test("barcodeChange: 바코드가 비어 있던 상품에 새로 채움", () => {
  assert.equal(barcodeChange("", "880123", ""), "set");
});

test("barcodeChange: 다른 바코드로 바뀌면 전환", () => {
  assert.equal(barcodeChange("880111", "880123", ""), "switch");
});
