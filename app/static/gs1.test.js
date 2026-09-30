import test from "node:test";
import assert from "node:assert/strict";
import { parseGS1, productKey } from "./gs1.js";

test("의약품 DataMatrix 원문: 상품코드, 유효기한, 제조번호", () => {
  const g = parseGS1("]d20108801234567890172712311023A45\u001d21SERIAL1");
  assert.equal(g.gtin, "08801234567890");
  assert.deepEqual(g.expiry, { year: "2027", month: "12", day: "31" });
  assert.equal(g.lot, "23A45");
});

test("괄호 표기와 일 00 은 말일", () => {
  const g = parseGS1("(01)08801234567890(17)260200(10)L1");
  assert.deepEqual(g.expiry, { year: "2026", month: "02", day: "28" });
});

test("EAN-13 에는 날짜가 없다", () => {
  assert.equal(parseGS1("8801234567890"), null);
  assert.equal(productKey("8801234567890"), "8801234567890");
});

test("GS1 상품 키는 13자리", () => {
  assert.equal(productKey("0108800000000110172712311012"), "8800000000110");
});

test("잘못된 달은 날짜 없음", () => {
  assert.equal(parseGS1("01088012345678901727133110X").expiry, null);
});
