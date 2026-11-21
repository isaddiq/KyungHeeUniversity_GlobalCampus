import { STY, hex } from "./mesh.js";

const MARBLE = hex("#ddd3c0");
const LINEN = hex("#d3c6af");
const HAIR = hex("#c8b9a2");
const CARVING = hex("#d4c9b5");
const DARK_BRONZE = hex("#555042");
const BRONZE = hex("#827451");
const add = (a, b) => a.map((v, i) => v + b[i]);
const sub = (a, b) => a.map((v, i) => v - b[i]);
const mul = (a, k) => a.map((v) => v * k);
const mix = (a, b, k) => add(mul(a, 1 - k), mul(b, k));
const cross = ([a, b, c], [x, y, z]) => [b * z - c * y, c * x - a * z, a * y - b * x];
const unit = (v) => mul(v, 1 / (Math.hypot(...v) || 1));

// Sculpt in x, outward depth, and up. Compress depth for reliefs, rotating the same
// geometry onto each face of the gate. Longitudinal and circumferential derivatives
// give the folded cloth and feathers smooth normals even when the sculpture is shallow.
class Carving {
  constructor(G, s, t, z, scale, yaw = 0, depth = 1) {
    Object.assign(this, { G, s, t, z, scale, depth, cos: Math.cos(yaw), sin: Math.sin(yaw) });
  }

  point([x, y, z]) {
    const { cos, sin, depth, scale } = this;
    return this.G.P(this.s + (cos * x + sin * y * depth) * scale,
      this.t + (sin * x - cos * y * depth) * scale, this.z + z * scale);
  }

  normal([x, y, z]) {
    const { cos, sin, depth } = this;
    return this.G.D(...unit([cos * x + sin * y / depth, sin * x - cos * y / depth, z]));
  }

  sweep(rows, col = MARBLE, segments = 10, folds = 0) {
    const centers = rows.map((row) => row.slice(0, 3));
    const last = rows.length - 1;
    const tangent = (i) => unit(sub(centers[Math.min(i + 1, last)], centers[Math.max(i - 1, 0)]));
    const points = rows.map(([, , , width, depth], i) => {
      const axis = tangent(i);
      const across = unit(cross(Math.abs(axis[1]) > 0.94 ? [0, 0, 1] : [0, 1, 0], axis));
      const forward = cross(axis, across);
      return Array.from({ length: segments }, (_, k) => {
        const a = k * Math.PI * 2 / segments;
        const pleat = 1 + folds * (Math.cos(6 * a + i * 0.59) + 0.35 * Math.cos(11 * a - i * 0.34));
        return add(centers[i], add(mul(across, Math.cos(a) * width * pleat),
          mul(forward, Math.sin(a) * depth * pleat)));
      });
    });
    const mesh = this.G.m, color = [...col, 1], style = [1, 1, STY.STATUE, 1];
    const vertex = (p, n) => mesh.v(this.point(p), this.normal(n), p[0] * this.scale,
      p[2] * this.scale, color, style, [1, -99]);
    const ids = points.map((ring, i) => ring.map((p, k) => {
      const along = sub(points[Math.min(i + 1, last)][k], points[Math.max(i - 1, 0)][k]);
      const around = sub(ring[(k + 1) % segments], ring[(k + segments - 1) % segments]);
      return vertex(p, cross(around, along));
    }));
    for (let i = 0; i < last; i++) {
      for (let k = 0; k < segments; k++) {
        const j = (k + 1) % segments;
        mesh.tri(ids[i][k], ids[i][j], ids[i + 1][j]);
        mesh.tri(ids[i][k], ids[i + 1][j], ids[i + 1][k]);
      }
    }
    for (const i of [0, last]) {
      const normal = mul(tangent(i), i === 0 ? -1 : 1);
      const cap = vertex(centers[i], normal);
      const rim = ids[i];
      for (let k = 0; k < segments; k++) {
        const j = (k + 1) % segments;
        if (i === 0) mesh.tri(cap, rim[j], rim[k]);
        else mesh.tri(cap, rim[k], rim[j]);
      }
    }
  }

  oval(center, shape, col = MARBLE, segments = 12) {
    const [x, y, z] = center, [rx, ry, rz] = shape;
    this.sweep(Array.from({ length: 7 }, (_, k) => {
      const a = -Math.PI / 2 + k * Math.PI / 6;
      const r = Math.max(0.012, Math.cos(a));
      return [x, y, z + rz * Math.sin(a), rx * r, ry * r];
    }), col, segments);
  }

  line(path, width, col = MARBLE, sides = 6) {
    this.sweep(path.map((p) => [...p, width, width]), col, sides);
  }

  leaf(a, b, width, thickness, col = CARVING) {
    const points = [a, mix(a, b, 0.25), add(mix(a, b, 0.56), [0, thickness * 0.7, 0]),
      add(mix(a, b, 0.82), [0, thickness * 0.5, 0]), b];
    const radii = [0.22, 0.84, 1, 0.61, 0.035];
    this.sweep(points.map((p, i) => [...p, width * radii[i], thickness * radii[i]]), col, 6);
  }
}

function limb(C, [a, joint, end], [start, middle, tip], col = MARBLE) {
  C.sweep([[...a, start * 0.85, start * 0.82],
    [...mix(a, joint, 0.31), start, start * 0.86],
    [...mix(a, joint, 0.78), middle * 1.16, middle],
    [...joint, middle * 0.92, middle * 0.88],
    [...mix(joint, end, 0.25), middle * 1.04, middle * 0.93],
    [...mix(joint, end, 0.7), tip * 1.28, tip * 1.05],
    [...end, tip, tip * 0.78]], col, 11);
}

function hand(C, wrist, direction, thumbs = 1) {
  const dir = unit(direction), spread = unit(cross([0, 1, 0], dir));
  const p = (length, x = 0, front = 0) => add(add(wrist, mul(dir, length)), add(mul(spread, x), [0, front, 0]));
  C.sweep([[...wrist, 0.017, 0.014], [...p(0.024), 0.027, 0.019],
    [...p(0.045), 0.023, 0.013]], MARBLE, 8);
  for (const [slot, length] of [[-1.5, 0.065], [-0.5, 0.078], [0.5, 0.075], [1.5, 0.062]]) {
    C.sweep([[...p(0.038, slot * 0.011), 0.0068, 0.0065],
      [...p(length - 0.008, slot * 0.011), 0.006, 0.006],
      [...p(length, slot * 0.010, 0.005), 0.0034, 0.0036]], MARBLE, 6);
  }
  C.line([p(0.016, thumbs * 0.012), p(0.028, thumbs * 0.028, 0.008),
    p(0.046, thumbs * 0.032, 0.011)], 0.008);
}

function face(C, [x, y, z], hair = "wavy") {
  C.sweep([[x, y + 0.016, z - 0.068, 0.028, 0.032], [x, y + 0.012, z - 0.057, 0.039, 0.042],
    [x, y, z - 0.031, 0.050, 0.052], [x, y, z + 0.008, 0.052, 0.056],
    [x, y - 0.009, z + 0.045, 0.049, 0.053], [x, y - 0.014, z + 0.068, 0.028, 0.032]], MARBLE, 16);
  C.oval([x, y - 0.027, z + 0.037], [0.054, 0.048, 0.043], HAIR);
  for (const sign of [-1, 1]) {
    C.oval([x + sign * 0.05, y, z - 0.011], [0.010, 0.018, 0.024], MARBLE, 8);
    const brow = [x + sign * 0.019, y + 0.051, z + 0.008];
    C.line([add(brow, [-0.013, -0.002, 0]), add(brow, [0, 0.004, 0.004]),
      add(brow, [0.013, -0.002, 0.001])], 0.0046, HAIR);
    for (let i = 0; i < 3; i++) {
      const a = i * 0.31;
      C.oval([x + sign * (0.019 + 0.008 * i), y + 0.023 - a * 0.045, z + 0.056 - a * 0.031],
        [0.016, 0.031, 0.012], HAIR, 8);
    }
    if (hair === "laurel") {
      C.leaf([x + sign * 0.028, y + 0.03, z + 0.039],
        [x + sign * 0.059, y + 0.001, z + 0.091], 0.009, 0.006, CARVING);
      C.leaf([x + sign * 0.042, y + 0.015, z + 0.042],
        [x + sign * 0.062, y - 0.007, z + 0.069], 0.008, 0.005, CARVING);
    }
  }
  C.sweep([[x, y + 0.060, z - 0.028, 0.012, 0.010], [x, y + 0.066, z - 0.021, 0.011, 0.015],
    [x, y + 0.054, z + 0.009, 0.006, 0.005]], MARBLE, 9);
  C.line([[x - 0.015, y + 0.047, z - 0.043], [x, y + 0.052, z - 0.045],
    [x + 0.015, y + 0.047, z - 0.043]], 0.0034, HAIR);
}

const standing = {
  hips: [0, 0, 0.44], chest: [-0.025, 0.016, 0.746],
  legs: [[[-0.075, 0.021, 0.243], [-0.087, 0, 0.05]], [[0.094, 0.06, 0.25], [0.12, 0.046, 0.047]]],
  arms: [[[-0.184, 0.055, 0.58], [-0.29, 0.072, 0.48]], [[0.16, 0.065, 0.57], [0.19, 0.095, 0.42]]],
};
const sitting = {
  hips: [0, 0, 0.286], chest: [-0.027, 0.032, 0.58],
  legs: [[[-0.124, 0.23, 0.255], [-0.14, 0.255, 0.048]], [[0.124, 0.209, 0.225], [0.15, 0.231, 0.049]]],
  arms: [[[-0.18, 0.095, 0.42], [-0.085, 0.24, 0.32]], [[0.166, 0.135, 0.42], [0.087, 0.24, 0.32]]],
};
const kneeling = {
  hips: [0, 0, 0.268], chest: [0.032, 0.035, 0.552],
  legs: [[[-0.085, 0.166, 0.096], [-0.13, -0.032, 0.052]], [[0.135, 0.209, 0.31], [0.145, 0.255, 0.051]]],
  arms: [[[-0.13, 0.12, 0.41], [-0.105, 0.22, 0.35]], [[0.177, 0.12, 0.43], [0.145, 0.22, 0.35]]],
};

function person(C, pose, { robe = "tunic", hair = "wavy" } = {}) {
  const { hips, chest, legs, arms } = pose;
  const h = (x, y, z) => add(hips, [x, y, z]);
  const c = (x, y, z) => add(chest, [x, y, z]);
  C.sweep([[...h(0, 0, -0.04), 0.107, 0.075], [...hips, 0.125, 0.088],
    [...mix(hips, chest, 0.28), 0.096, 0.069], [...mix(hips, chest, 0.64), 0.117, 0.083],
    [...c(0, 0, -0.04), 0.135, 0.083], [...chest, 0.113, 0.068],
    [...c(0, -0.005, 0.033), 0.045, 0.044]], MARBLE, 16);
  C.sweep([[...c(0, -0.005, 0.015), 0.047, 0.038], [...c(0, 0.005, 0.079), 0.034, 0.034]]);
  face(C, c(pose.head ?? 0, 0.013, 0.115), hair);
  for (const [i, sign] of [-1, 1].entries()) {
    const [knee, ankle] = legs[i], [elbow, wrist] = arms[i];
    limb(C, [h(sign * 0.066, 0, -0.009), knee, ankle], [0.075, 0.047, 0.029]);
    C.sweep([[...add(ankle, [0, -0.027, -0.02]), 0.022, 0.021],
      [...add(ankle, [0, 0.012, -0.021]), 0.029, 0.026],
      [...add(ankle, [sign * 0.006, 0.063, -0.028]), 0.032, 0.015],
      [...add(ankle, [sign * 0.008, 0.093, -0.029]), 0.018, 0.009]], MARBLE, 9);
    limb(C, [c(sign * 0.109, 0.006, -0.015), elbow, wrist], [0.048, 0.028, 0.017]);
    hand(C, wrist, sub(wrist, elbow), sign);
  }

  if (robe === "full") {
    C.sweep([[...h(0, 0.036, -hips[2] + 0.018), 0.139, 0.127],
      [...h(0.016, 0.059, -hips[2] * 0.72), 0.154, 0.144],
      [...h(0.022, pose.legs[0][0][1] * 0.44, -hips[2] * 0.43), 0.149, 0.143],
      [...h(0.003, 0.008, -0.02), 0.129, 0.103], [...h(0, 0, 0.054), 0.106, 0.076]], LINEN, 24, 0.09);
    for (const offset of [-0.62, -0.19, 0.31, 0.67]) {
      const x = offset * 0.133, depth = Math.sqrt(1 - offset * offset);
      C.sweep([[...h(x * 0.86, depth * 0.079, 0.022), 0.008, 0.005],
        [...h(x + 0.012, 0.037 + depth * 0.113, -hips[2] * 0.37), 0.012, 0.011],
        [...h(x - 0.003, 0.060 + depth * 0.141, -hips[2] * 0.70), 0.012, 0.009],
        [...h(x * 1.1, 0.040 + depth * 0.124, 0.034 - hips[2]), 0.006, 0.005]], CARVING, 7);
    }
  } else {
    C.sweep([[...h(-0.041, 0.036, -0.139), 0.133, 0.092],
      [...h(0.006, 0.033, -0.099), 0.135, 0.108], [...h(0.018, 0.013, -0.029), 0.142, 0.111],
      [...h(-0.01, 0.005, 0.034), 0.111, 0.086]], LINEN, 22, 0.08);
  }
  // Overlapping diagonal folds run from the shoulder to the opposite hip.
  for (let i = 0; i < 5; i++) {
    const k = i * 0.016;
    C.sweep([[...c(-0.094 + k, 0.014, 0.023), 0.017, 0.014],
      [...c(-0.090 + k, 0.076, -0.04 - k * 0.3), 0.027, 0.016],
      [...mix(c(-0.038 + k, 0.092, -0.064), h(0.076 + k * 0.35, 0.087, 0.012), 0.44), 0.024, 0.014],
      [...h(0.083 + k * 0.31, 0.059, 0.014 - k), 0.017, 0.011]], LINEN, 7);
  }
}

function book(C, x, y, z) {
  // Slightly raised page blocks, dipped at the spine.
  for (const sign of [-1, 1]) {
    C.sweep([[x + sign * 0.017, y, z, 0.041, 0.013],
      [x + sign * 0.065, y, z + 0.014, 0.045, 0.012],
      [x + sign * 0.103, y, z + 0.032, 0.039, 0.010]], CARVING, 6);
    for (const line of [0.010, 0.022]) {
      C.line([[x, y + 0.042, z + line], [x + sign * 0.066, y + 0.042, z + line + 0.013],
        [x + sign * 0.103, y + 0.041, z + line + 0.026]], 0.0029, HAIR);
    }
  }
}

function scroll(C, x, y, z) {
  C.line([[x, y, z], [x + 0.011, y, z + 0.13]], 0.018, CARVING, 9);
  C.oval([x + 0.012, y, z + 0.13], [0.020, 0.02, 0.017], MARBLE, 8);
}

function dove(C, x, y, z) {
  C.sweep([[x - 0.11, y, z - 0.025, 0.014, 0.01], [x - 0.044, y, z + 0.005, 0.04, 0.027],
    [x + 0.041, y, z + 0.038, 0.032, 0.03], [x + 0.072, y, z + 0.059, 0.013, 0.014]], CARVING, 8);
  C.oval([x + 0.079, y, z + 0.066], [0.025, 0.021, 0.019], MARBLE, 8);
  C.leaf([x + 0.089, y, z + 0.067], [x + 0.124, y, z + 0.065], 0.008, 0.008, CARVING);
  for (let i = 0; i < 4; i++) C.leaf([x - 0.01, y + 0.008 * i, z + 0.02],
    [x - 0.11 + i * 0.019, y + 0.017 * i, z + 0.15 - 0.012 * i], 0.029, 0.012);
}

function seat(G, s, t, z, h, yaw, pose = sitting, object = "book") {
  const C = new Carving(G, s, t, z, h, yaw);
  C.sweep([[0, -0.039, 0.007, 0.146, 0.113], [-0.009, -0.049, 0.076, 0.156, 0.133],
    [0.009, -0.036, 0.207, 0.123, 0.106], [0.007, -0.029, 0.286, 0.104, 0.081]], CARVING, 10, 0.055);
  person(C, pose, { robe: "full" });
  if (object === "book") book(C, 0, 0.24, 0.314);
}

export function crownSculptures(G, s, z) {
  const C = new Carving(G, s - 0.13, 0.12, z, 2.66, -0.09);
  person(C, { ...standing,
    arms: [[[-0.176, 0.067, 0.679], [-0.335, 0.13, 0.642]], [[0.14, 0.029, 0.694], [0.23, 0.053, 0.889]]],
  }, { robe: "full", hair: "laurel" });
  const top = (22.5 - z) / 2.66;
  C.line([[0.245, 0.065, 0.05], [0.237, 0.066, 0.628], [0.237, 0.066, top - 0.038]], 0.010, CARVING, 8);
  C.oval([0.237, 0.066, top - 0.027], [0.029, 0.024, 0.027], BRONZE, 10);
  for (const side of [-1, 1]) C.leaf([0.237, 0.066, top - 0.073],
    [0.237 + side * 0.049, 0.066, top - 0.022], 0.010, 0.008, BRONZE);

  seat(G, s - 0.98, -0.42, z, 1.99, -0.12);
  seat(G, s - 1.56, 0.19, z, 1.81, -0.77, {
    ...sitting, chest: [-0.062, 0.089, 0.543],
    arms: [[[-0.143, 0.132, 0.407], [-0.105, 0.175, 0.551]], [[0.145, 0.145, 0.411], [0.143, 0.235, 0.323]]],
  }, null);
  const reader = new Carving(G, s + 0.61, -0.48, z, 2.5, 0.06);
  person(reader, { ...kneeling, arms: [[[-0.102, 0.117, 0.403], [-0.089, 0.218, 0.359]],
    [[0.19, 0.046, 0.622], [0.249, 0.066, 0.77]]] });
  scroll(reader, 0.256, 0.076, 0.775);
  const bearer = new Carving(G, s + 1.35, 0.19, z, 1.87, 1.06);
  person(bearer, { ...kneeling, arms: [[[-0.095, 0.151, 0.45], [-0.039, 0.304, 0.47]],
    [[0.131, 0.143, 0.457], [0.024, 0.28, 0.527]]] }, { robe: "full" });
  dove(bearer, 0.015, 0.316, 0.546);
  seat(G, s + 0.12, 0.79, z, 1.84, Math.PI + 0.12);
}

export function cornerSculpture(G, s, t, z, outward, side) {
  seat(G, s, t, z, 1.93, (outward > 0 ? Math.PI : 0) + side * 0.24, sitting, side === 1 ? null : "book");
}

function wing(C, root, tips) {
  C.leaf(root, mix(tips[1], tips[tips.length - 2], 0.45), 0.093, 0.024, CARVING);
  for (const [i, tip] of tips.entries()) {
    const shoulder = add(root, [(tip[0] - root[0]) * (0.11 + i * 0.019), -0.004 * i,
      (tip[2] - root[2]) * 0.105]);
    C.leaf(shoulder, tip, 0.058 - i * 0.0027, 0.018, i % 3 === 1 ? MARBLE : CARVING);
    C.leaf(mix(shoulder, tip, 0.22), add(mix(shoulder, tip, 0.67), [0, 0.027, 0]),
      0.030, 0.012, MARBLE);
  }
}

export function spandrelSculpture(G, s, wall, z, out, toward) {
  // Mirror across s while keeping the relief's outward depth on the same face.
  const yaw = out < 0 ? 0 : Math.PI;
  const C = new Carving(G, s, wall - out * 0.04, z, 3.35, yaw, 0.52);
  const d = toward * -out;
  const p = (x, y, z) => [d * x, y, z];
  const fan = (a, b) => Array.from({ length: 8 }, (_, i) =>
    p(a - i * 0.021, 0.061 - i * 0.004, b - i * (0.013 + i * 0.002)));
  wing(C, p(0.077, 0.058, 0.584), fan(-0.34, 0.861));
  wing(C, p(0.13, 0.045, 0.573), fan(-0.075, 0.943));
  const legs = [[p(-0.169, 0.031, 0.17), p(-0.29, 0.018, 0.055)],
    [p(-0.089, 0.035, 0.19), p(-0.18, 0.065, 0.085)]];
  const reaching = [p(0.32, 0.091, 0.69), p(0.49, 0.081, 0.774)];
  const trailing = [p(-0.095, 0.101, 0.63), p(-0.07, 0.10, 0.439)];
  person(C, { hips: p(-0.01, 0.047, 0.308), chest: p(0.16, 0.08, 0.64), legs,
    arms: d > 0 ? [trailing, reaching] : [reaching, trailing], head: d * 0.019 });
  C.sweep([[...p(-0.25, 0.001, 0.062), 0.044, 0.037], [...p(-0.14, 0.02, 0.19), 0.117, 0.046],
    [...p(-0.048, 0.062, 0.28), 0.133, 0.07], [...p(0.068, 0.083, 0.405), 0.125, 0.075]], LINEN, 20, 0.11);
  C.line([p(0.50, 0.094, 0.781), p(0.68, 0.096, 0.87), p(0.871, 0.078, 0.984)], 0.012, CARVING);
  for (let i = 0; i < 7; i++) {
    const x = 0.53 + 0.041 * i, h = 0.801 + 0.023 * i;
    C.leaf(p(x, 0.095, h), p(x + 0.086, 0.094, h + 0.058), 0.018, 0.009);
    C.leaf(p(x, 0.101, h), p(x + 0.118, 0.106, h - 0.004), 0.016, 0.009);
  }
}

export function pavilionRelief(G, s, wall, z, out) {
  const yaw = out < 0 ? 0 : Math.PI, across = -out;
  const sculpt = (x, level, h, depth) => new Carving(G, s + across * x, wall + out * level, z, h, yaw, depth);
  person(sculpt(0.5, -0.042, 2.94, 0.44), { ...standing,
    arms: [[[-0.16, 0.04, 0.53], [-0.11, 0.10, 0.46]], [[0.13, 0.06, 0.54], [0.16, 0.05, 0.43]]],
  });
  const central = sculpt(0, -0.026, 3.98, 0.45);
  person(central, { ...standing,
    legs: [[[-0.076, 0.065, 0.233], [-0.08, 0.057, 0.04]], [[0.085, 0.092, 0.245], [0.101, 0.082, 0.051]]],
    arms: [[[-0.224, 0.041, 0.737], [-0.263, 0.029, 0.92]], [[0.203, 0.037, 0.922], [0.288, 0.02, 1.102]]],
  }, { hair: "laurel" });
  scroll(central, -0.276, 0.083, 0.893);
  const dancers = [
    [-1.03, { ...standing, hips: [-0.036, 0.018, 0.43], chest: [-0.064, 0.049, 0.7],
      arms: [[[-0.239, 0.053, 0.543], [-0.347, 0.045, 0.443]], [[0.104, 0.098, 0.573], [0.205, 0.131, 0.49]]] }],
    [0.984, { ...standing, hips: [0.025, 0.017, 0.4], chest: [0.026, 0.058, 0.72],
      legs: [[[-0.159, 0.112, 0.229], [-0.099, 0.034, 0.039]], [[0.121, 0.042, 0.16], [0.208, 0.014, 0.054]]],
      arms: [[[-0.164, 0.112, 0.562], [-0.258, 0.167, 0.455]], [[0.195, 0.082, 0.591], [0.286, 0.063, 0.493]]] }],
  ];
  for (const [x, pose] of dancers) person(sculpt(x, -0.02, 2.96, 0.55), pose, { robe: "full" });
}

export function tabletEagle(G, s, wall, z, out) {
  const C = new Carving(G, s, wall + out * 0.027, z, 1, out < 0 ? 0 : Math.PI, 0.72);
  for (const dir of [-1, 1]) {
    const tips = Array.from({ length: 9 }, (_, i) => [dir * (0.85 - 0.035 * i), 0.037, 1.13 - 0.056 * i]);
    wing(C, [dir * 0.10, 0.042, 0.423], tips);
    C.leaf([dir * 0.103, 0.13, 0.23], [dir * 0.18, 0.135, 0.303], 0.026, 0.012);
  }
  C.oval([0, 0.052, -0.035], [0.302, 0.215, 0.299]);
  C.sweep([[0, 0.107, 0.264, 0.068, 0.034], [0.008, 0.128, 0.407, 0.141, 0.085],
    [0.011, 0.137, 0.549, 0.120, 0.073], [0.052, 0.136, 0.674, 0.057, 0.044]], MARBLE, 12);
  C.oval([0.05, 0.152, 0.697], [0.075, 0.053, 0.071]);
  C.leaf([0.085, 0.193, 0.699], [0.131, 0.200, 0.643], 0.028, 0.023, CARVING);
  // The oblique ribbon wraps the globe and trails toward both corners.
  C.sweep([[-0.395, 0.068, -0.277, 0.027, 0.023], [-0.229, 0.192, -0.153, 0.052, 0.017],
    [-0.061, 0.247, -0.074, 0.054, 0.021], [0.155, 0.221, -0.002, 0.055, 0.021],
    [0.311, 0.123, 0.091, 0.052, 0.020], [0.328, 0.033, 0.183, 0.040, 0.013]], CARVING, 9);
}

function orbit(C, center, a, b, r, thickness, col) {
  const path = Array.from({ length: 42 }, (_, i) => {
    const t = 2 * Math.PI * i / 41;
    return add(center, add(mul(a, r * Math.cos(t)), mul(b, r * Math.sin(t))));
  });
  C.line(path, thickness, col, 7);
}

export function pavilionCrown(G, s, z, side) {
  const C = new Carving(G, s, 0.12, z, 2.45, side * 0.13);
  person(C, { ...standing, arms: [[[-0.177, 0.026, 0.622], [-0.23, 0.115, 0.551]],
    [[0.19, 0.042, 0.571], [0.295, 0.01, 0.515]]] });
  for (const offset of [-1, 1]) {
    const W = new Carving(G, s + offset * 1.23, -0.045 + offset * 0.32, z, 2.02,
      offset * 0.47 + side * 0.09);
    person(W, { ...standing, arms: [[[-0.199, 0.027, 0.64], [-0.235, 0.04, 0.54]],
      [[0.201, 0.07, 0.628], [0.265, 0.085, 0.69]]] }, { robe: "full" });
  }
  const sphere = new Carving(G, s, 0.53, z + 2.39, 1, side * 0.21);
  sphere.line([[-0.08, -0.38, -2.35], [-0.04, -0.37, -1.01], [0, -0.34, -0.65],
    [0, -0.12, -0.1]], 0.047, DARK_BRONZE, 8);
  orbit(sphere, [0, 0, 0], [1, 0, 0], [0, 0.72, 0.694], 0.94, 0.036, DARK_BRONZE);
  orbit(sphere, [0, 0, 0], [0.54, 0, 0.842], [0.36, 0.9, -0.231], 0.92, 0.033, BRONZE);
  orbit(sphere, [0, 0, 0], [0.89, 0.12, -0.439], [-0.11, 0.993, 0.043], 0.89, 0.028, DARK_BRONZE);
  sphere.oval([0, 0, 0], [0.145, 0.145, 0.145], CARVING);
  sphere.oval([0.49, 0.06, 0.79], [0.11, 0.11, 0.11], BRONZE);
  sphere.oval([-0.77, 0.38, -0.27], [0.094, 0.094, 0.094], BRONZE);
}

export function archMedallion(G, s, wall, z, out) {
  const C = new Carving(G, s, wall + out * 0.012, z, 1, out < 0 ? 0 : Math.PI, 0.36);
  C.oval([0, 0.13, 0], [0.597, 0.23, 0.597], DARK_BRONZE, 32);
  for (const [radius, y, w] of [[0.537, 0.23, 0.027], [0.456, 0.30, 0.011]]) {
    orbit(C, [0, y, 0], [1, 0, 0], [0, 0, 1], radius, w, BRONZE);
  }
  for (let i = 0; i < 12; i++) {
    const a = Math.PI * i / 6;
    const p = (r, spin) => [r * Math.cos(a + spin), 0.366 - r * 0.11, r * Math.sin(a + spin)];
    C.leaf(p(0.09, 0), p(0.31, 0.24), 0.049, 0.017, BRONZE);
    C.leaf(p(0.28, -0.19), p(0.427, -0.066), 0.026, 0.016, BRONZE);
  }
  C.oval([0, 0.38, 0], [0.069, 0.027, 0.069], BRONZE, 10);
}

export function capitalCarving(G, s, t, z, radius, height) {
  const compact = height < 0.65;
  const stations = compact ? 7 : 11;
  for (let i = 0; i < 4; i++) {
    const a = i * Math.PI / 2;
    const C = new Carving(G, s + radius * Math.sin(a), t - radius * Math.cos(a), z, height, a);
    for (const side of [-1, 1]) {
      C.leaf([0, -0.05, 0], [side * 0.58, 0.13, 0.86], 0.20, 0.058);
      if (!compact) C.leaf([side * 0.14, -0.011, 0.37], [side * 0.48, 0.14, 0.78], 0.15, 0.061, MARBLE);
      const curl = Array.from({ length: stations }, (_, k) => {
        const u = k / (stations - 1), theta = u * Math.PI * 1.53, r = 0.24 * (1 - u) + 0.03;
        return [side * (0.63 + r * Math.cos(theta)), 0.13, 0.80 + r * Math.sin(theta)];
      });
      C.line(curl, 0.055, CARVING, compact ? 5 : 7);
    }
    C.leaf([0, -0.028, 0.16], [0, 0.22, 1.0], 0.20, 0.060, MARBLE);
  }
}
