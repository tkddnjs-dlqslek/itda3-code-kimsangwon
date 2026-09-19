import test from "node:test";
import assert from "node:assert/strict";
import { DEFAULTS, initial, step, toGray, meanAbsDiff } from "./motion.js";

// [diff, scene] 열을 차례로 넣고 촬영이 일어난 틱 번호를 돌려준다
function run(seq) {
  let state = initial();
  const captures = [];
  seq.forEach(([diff, scene], i) => {
    const r = step(state, diff, scene);
    state = r.state;
    if (r.capture) captures.push(i);
  });
  return { captures, state };
}

const EMPTY = [1, 2], ENTER = [30, 40], STILL = [1, 40], LEAVE = [30, 3];

test("빈 화면에서는 촬영하지 않는다", () => {
  assert.deepEqual(run(Array(20).fill(EMPTY)).captures, []);
});

test("물체가 들어와 stillTicks 만큼 멎으면 한 번 촬영한다", () => {
  const { captures, state } = run([EMPTY, ENTER, STILL, STILL, STILL, STILL, STILL, STILL]);
  assert.deepEqual(captures, [5]);           // 멎은 틱 2,3,4,5 의 네 번째
  assert.equal(state.phase, "captured");
});

test("계속 움직이는 물체는 촬영하지 않는다", () => {
  assert.deepEqual(run([EMPTY, ...Array(15).fill(ENTER)]).captures, []);
});

test("중간에 흔들리면 멎은 횟수를 처음부터 다시 센다", () => {
  const { captures } = run([ENTER, STILL, STILL, ENTER, STILL, STILL, STILL, STILL]);
  assert.deepEqual(captures, [7]);
});

test("치우기 전에는 같은 물건을 다시 찍지 않고, 치운 뒤 새 물건은 찍는다", () => {
  const first = [ENTER, STILL, STILL, STILL, STILL];
  const { captures } = run([...first, ...Array(10).fill(STILL), LEAVE, EMPTY, ...first]);
  assert.deepEqual(captures, [4, 21]);
});

test("멎기 전에 물건을 빼면 빈 화면으로 돌아간다", () => {
  const { captures, state } = run([ENTER, STILL, STILL, LEAVE, EMPTY]);
  assert.deepEqual(captures, []);
  assert.equal(state.phase, "empty");
});

test("toGray 와 meanAbsDiff", () => {
  const g = toGray(new Uint8ClampedArray([255, 255, 255, 255, 0, 0, 0, 255]));
  assert.equal(g.length, 2);
  assert.ok(Math.abs(g[0] - 255) < 0.01 && g[1] === 0);
  assert.equal(meanAbsDiff([10, 20], [13, 16]), 3.5);
  assert.equal(DEFAULTS.stillTicks, 4);
});
