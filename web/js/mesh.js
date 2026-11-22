// Shared mesh + material core for the enhanced Kyung Hee models.
// One custom Cesium Appearance renders every campus model; the per-vertex "style" attribute selects
// a procedural material (facade windows, ashlar, fluted columns, coffers, reliefs, inscriptions ...).
const Cesium = window.Cesium;

export const hex = (h) => { const c = Cesium.Color.fromCssColorString(h); return [c.red, c.green, c.blue]; };

export const STY = {
  GRANITE: 0, MODERN: 1, RESID: 2, GLASS: 3, RUSTIC: 4, ASHLAR: 5, COFFER: 6, COLUMN: 7, ATTIC: 8,
  CORNICE: 9, BRONZE: 10, RELIEF: 11, STATUE: 12, PORTICO: 13, PAVILION: 14, OBELISK: 15,
  BALUSTRADE: 16, ARCADE: 18, METAL: 19, CLOCK: 20, FOLIAGE: 21, TABLET: 22, BANDED: 23, NET: 24,
  ENGINEERING_WING: 25, FOREIGN_LANGUAGES_WINDOWS: 26, ELECTRONICS_BRICK: 27,
  WOOJUNGWON_WINDOWS: 28, WOOJUNGWON_GLASS: 29,
  DORM_WINDOWS: 30,
};

const VS = `
in vec3 position3DHigh;
in vec3 position3DLow;
in vec3 normal;
in vec2 st;
in vec4 wall;
in vec4 style;
in vec2 edge;
in vec4 color;
in float batchId;
out vec3 v_positionEC;
out vec3 v_normalEC;
out vec2 v_st;
out vec4 v_wall;
out vec4 v_style;
out vec2 v_edge;
out vec4 v_color;
void main() {
  vec4 p = czm_computePosition();
  v_positionEC = (czm_modelViewRelativeToEye * p).xyz;
  v_normalEC = czm_normal * normal;
  v_st = st; v_wall = wall; v_style = style; v_edge = edge; v_color = color;
  gl_Position = czm_modelViewProjectionRelativeToEye * p;
}`;

const FS = `
in vec3 v_positionEC;
in vec3 v_normalEC;
in vec2 v_st;
in vec4 v_wall;
in vec4 v_style;
in vec2 v_edge;
in vec4 v_color;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float vnoise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}
float glyph(vec2 cellId, vec2 g) {          // 3x5 pseudo-letter, g in [0,1]^2
  if (g.x < 0.12 || g.x > 0.88 || g.y < 0.12 || g.y > 0.88) return 0.0;
  vec2 px = floor(vec2((g.x - 0.12) / 0.76 * 3.0, (g.y - 0.12) / 0.76 * 5.0));
  return step(0.42, hash(cellId * 7.13 + px));
}
// 5x7 capitals for the gate inscription "NEO-RENAISSANCE"; rows 0-3 in a, rows 4-6 in b (MSB = left pixel)
vec2 fontGlyph(float g) {
  if (g < 0.5) return vec2(583347.0, 17969.0);   // N
  if (g < 1.5) return vec2(1032734.0, 16927.0);  // E
  if (g < 2.5) return vec2(476721.0, 17966.0);   // O
  if (g < 3.5) return vec2(31.0, 0.0);           // -
  if (g < 4.5) return vec2(1001022.0, 21073.0);  // R
  if (g < 5.5) return vec2(476735.0, 17969.0);   // A
  if (g < 6.5) return vec2(462980.0, 4238.0);    // I
  if (g < 7.5) return vec2(508430.0, 1086.0);    // S
  return vec2(476688.0, 16942.0);                // C
}
float textChar(float i) {                         // N E O - R E N A I S S A N C E
  if (i < 0.5) return 0.0; if (i < 1.5) return 1.0; if (i < 2.5) return 2.0; if (i < 3.5) return 3.0;
  if (i < 4.5) return 4.0; if (i < 5.5) return 1.0; if (i < 6.5) return 0.0; if (i < 7.5) return 5.0;
  if (i < 8.5) return 6.0; if (i < 10.5) return 7.0; if (i < 11.5) return 5.0; if (i < 12.5) return 0.0;
  if (i < 13.5) return 8.0; return 1.0;
}
float fontPixel(float g, float row, float px) {   // row 0 = top
  vec2 v = fontGlyph(g);
  float bits = row < 3.5 ? mod(floor(v.x / exp2(5.0 * (3.0 - row))), 32.0) : mod(floor(v.y / exp2(5.0 * (6.0 - row))), 32.0);
  return mod(floor(bits / exp2(4.0 - px)), 2.0);
}
vec3 glass(vec3 n, vec3 toEye, float var) {
  float fres = pow(1.0 - max(dot(n, toEye), 0.0), 3.0);
  vec3 g = mix(vec3(0.13, 0.18, 0.23), vec3(0.20, 0.27, 0.33), var);
  return mix(g, vec3(0.62, 0.70, 0.78), clamp(0.18 + fres * 0.75, 0.0, 0.9));
}
vec3 ashlar(vec3 base, float u, float h) {
  float row = floor(h / 0.8);
  float ox = 0.8 * mod(row, 2.0);
  float jy = min(fract(h / 0.8), 1.0 - fract(h / 0.8)) * 0.8;
  float jx = min(fract((u + ox) / 1.6), 1.0 - fract((u + ox) / 1.6)) * 1.6;
  float joint = 1.0 - smoothstep(0.008, 0.03, min(jx, jy));
  return base * (0.96 + 0.05 * hash(vec2(floor((u + ox) / 1.6), row))) * (1.0 - 0.12 * joint);
}
void main() {
  vec3 toEye = normalize(-v_positionEC);
  vec3 n = normalize(v_normalEC);
  if (dot(n, toEye) < 0.0) n = -n;
  czm_materialInput mi;
  mi.normalEC = n;
  mi.positionToEyeEC = -v_positionEC;
  czm_material m = czm_getDefaultMaterial(mi);
  vec3 base = v_wall.rgb;
  vec3 col = base;
  float spec = 0.03, shin = 8.0;
  float u = v_st.x, h = v_st.y;
  float fh = v_style.x, bw = v_style.y, sty = floor(v_style.z + 0.5), H = v_style.w;
  float L = v_edge.x, gl = v_edge.y;
  if (v_wall.a < 0.5) {
    vec2 cell = floor(vec2(u, h) / 4.0);
    col = base * (0.93 + 0.07 * hash(cell));
    col *= 1.0 - 0.06 * max(step(0.97, fract(u / 4.0)), step(0.97, fract(h / 4.0)));
    if (sty == 3.0) { spec = 0.5; shin = 40.0; }
  } else if (sty == 5.0) {
    col = ashlar(base, u, h);
  } else if (sty == 6.0) {                        // coffered vault
    vec2 g = fract(vec2(u, h) / 1.1);
    float e = min(min(g.x, 1.0 - g.x), min(g.y, 1.0 - g.y));
    col = base * (e < 0.1 ? 1.02 : (e < 0.17 ? 0.8 : 0.7));
    if (length(g - 0.5) < 0.11) col = base * 1.05;
  } else if (sty == 7.0) {                        // fluted Corinthian column
    float fl = 0.5 + 0.5 * cos(6.2831853 * u / max(L, 0.1) * 24.0);
    col = base * (0.86 + 0.14 * fl);
    if (h > H - 1.15) col = base * (0.74 + 0.38 * (0.6 * vnoise(vec2(u, h) * 6.0) + 0.4 * vnoise(vec2(u, h) * 13.0)));
    if (h < 0.5) col = base * (0.88 + 0.12 * step(0.5, fract(h / 0.17)));
    spec = 0.12; shin = 18.0;
  } else if (sty == 8.0) {                        // attic with inscription band
    col = ashlar(base, u, h);
    float lo = H * 0.3, hi = H * 0.62;
    if (h > lo - 0.12 && h < hi + 0.12 && u > L * 0.12 && u < L * 0.88) col = base * 0.95;
    // engraved "NEO-RENAISSANCE" (15 letters, 6-pixel advance), centred; letter size from photographs (~43 % of attic width)
    float cell = min((hi - lo) / 7.0, L * 0.43 / 89.0);
    float x = (u - (L * 0.5 - 44.5 * cell)) / cell, y = (h - (lo + hi) * 0.5 + 3.5 * cell) / cell;
    if (x >= 0.0 && x < 89.0 && y >= 0.0 && y < 7.0) {
      float ci = floor(x / 6.0), px = floor(x) - ci * 6.0;
      if (px < 5.0 && fontPixel(textChar(ci), 6.0 - floor(y), px) > 0.5) col = base * 0.56;
    }
  } else if (sty == 9.0) {                        // entablature: architrave, frieze, dentil cornice
    float r = h / max(H, 0.1);
    col = base;
    if (r < 0.35) col = base * (0.97 + 0.05 * step(0.5, fract(h / 0.22)));
    else if (r < 0.62) col = base * 0.98;
    else if (r < 0.74) col = base * (fract(u / 0.3) < 0.55 ? 1.05 : 0.66);
    else col = base * (r > 0.92 ? 0.84 : 1.07);
  } else if (sty == 10.0) {                       // bronze plaque
    col = vec3(0.34, 0.27, 0.15);
    float line = fract(h / 0.24);
    if (u > 0.2 && u < L - 0.2 && h > 0.3 && h < H - 0.35 && line > 0.35 && line < 0.72 &&
        hash(vec2(floor(u / 0.16), floor(h / 0.24))) > 0.22) col = vec3(0.78, 0.64, 0.38);
    if (u < 0.08 || u > L - 0.08 || h < 0.08 || h > H - 0.08) col = vec3(0.55, 0.45, 0.27);
    spec = 0.5; shin = 40.0;
  } else if (sty == 11.0) {                       // sculpted relief
    float nn = 0.55 * vnoise(vec2(u, h) * 2.0) + 0.3 * vnoise(vec2(u, h) * 4.5) + 0.15 * vnoise(vec2(u, h) * 11.0);
    col = base * (0.66 + 0.5 * nn);
    if (u < 0.15 || u > L - 0.15 || h < 0.15 || h > H - 0.15) col = base * 1.04;
  } else if (sty == 12.0) {                       // statuary
    col = base * (0.93 + 0.08 * vnoise(vec2(u, h) * 3.0));
    spec = 0.15; shin = 22.0;
  } else if (sty == 13.0) {                       // portico back wall: tall windows per bay
    col = ashlar(base * 0.9, u, h);
    float nb = max(1.0, floor(L / bw + 0.5));
    float bww = L / nb;
    float wx = (fract(u / bww) - 0.5) * bww;
    float hw = min(0.3 * bww, 1.4);
    if (abs(wx) < hw && h > 0.4 && h < H - 3.2) {
      col = glass(n, toEye, hash(vec2(floor(u / bww), 2.0)));
      if (abs(wx) < 0.05 || abs(fract((h - 0.4) / 3.6) - 0.0) < 0.02 || hw - abs(wx) < 0.09) col = vec3(0.24, 0.23, 0.22);
      spec = 0.5; shin = 60.0;
    }
    col *= 0.86;                                   // portico shade
  } else if (sty == 14.0) {                       // end pavilion: grand arched window + small windows
    col = ashlar(base, u, h);
    float cx = u - L * 0.5;
    float hw = min(L * 0.22, 2.8);
    float y0 = H * 0.2, y1 = H * 0.72;
    bool win = abs(cx) < hw && h > y0 && h < y1;
    if (win && h > y1 - hw) win = length(vec2(cx, h - (y1 - hw))) < hw;
    if (abs(cx) < hw + 0.45 && h > y0 - 0.4 && h < y1 + 0.45 && !win) {
      bool frame = h < y1 - hw ? true : length(vec2(cx, h - (y1 - hw))) < hw + 0.45;
      if (frame) col = base * 1.08;
    }
    if (win) {
      col = glass(n, toEye, 0.4);
      vec2 mg = fract(vec2(cx / 0.9, (h - y0) / 1.2));
      if (min(mg.x, 1.0 - mg.x) < 0.05 || min(mg.y, 1.0 - mg.y) < 0.04) col = vec3(0.25, 0.24, 0.22);
      spec = 0.5; shin = 60.0;
    }
    if (h < y0 - 0.9 && h > 0.6 && abs(abs(cx) - L * 0.3) < 0.6 && fract(h / 3.0) > 0.25) col = glass(n, toEye, 0.2);
  } else if (sty == 15.0) {                       // obelisk shaft with vertical inscription
    col = base * (0.95 + 0.05 * vnoise(vec2(u, h) * 2.0));
    float Lf = L * 0.25, uf = mod(u, Lf);           // 4 faces
    if (uf > Lf * 0.3 && uf < Lf * 0.7 && h > 1.0 && h < H - 2.0) {
      float ch = Lf * 0.4;
      vec2 g = vec2((uf - Lf * 0.3) / (Lf * 0.4), fract(h / ch));
      if (glyph(vec2(floor(h / ch), floor(u / Lf) + 5.0), g) > 0.5) col = base * 0.55;
    }
  } else if (sty == 16.0) {                       // balustrade: balusters with shadowed gaps
    float bx = fract(u / 0.34);
    bool body = h > 0.16 * H && h < H - 0.2;
    if (body && (bx < 0.26 || bx > 0.74)) col = base * 0.42;
    else if (body) col = base * (0.88 + 0.16 * sin(bx * 3.14159));
    else col = base * 1.02;
  } else if (sty == 18.0) {                       // brick arcade: arched bays, white band, gold frieze
    float row = floor(h / 0.075);
    float bond = fract(u / 0.24 + 0.5 * mod(row, 2.0));
    col = base * (0.93 + 0.08 * hash(vec2(floor(u / 0.24 + 0.5 * mod(row, 2.0)), row)));
    if (fract(h / 0.075) < 0.12 || bond < 0.04) col = mix(col, vec3(0.86, 0.82, 0.76), 0.55);
    float nb = max(1.0, floor(L / bw + 0.5)), bww = L / nb;
    float cx = (fract(u / bww) - 0.5) * bww;
    float hw = 0.34 * bww, ya = fh;
    bool arch = fh > 1.0 && abs(cx) < hw && h > 0.15 && h < ya && L > 4.0;
    if (arch && h > ya - hw) arch = length(vec2(cx, h - (ya - hw))) < hw;
    if (arch) {
      col = vec3(0.32, 0.27, 0.24);
      if (h < 3.4 && abs(cx) < hw - 0.3) col = glass(n, toEye, 0.3);
    }
    float px = fract(u / bww) * bww; px = min(px, bww - px);
    if (fh > 1.0 && L > 4.0 && length(vec2(px, h - (ya + 1.05))) < 0.35) col = vec3(0.85, 0.66, 0.25);
    if (h < 0.6) col = vec3(0.8, 0.78, 0.74);
    if (h > H - 3.0 && h < H - 2.5) col = vec3(0.93, 0.92, 0.89);
    if (h >= H - 2.5 && h < H - 0.9) {
      float fr = vnoise(vec2(u * 2.5, h * 3.0));
      col = mix(vec3(0.55, 0.38, 0.12), vec3(0.88, 0.7, 0.28), fr);
      spec = 0.35; shin = 30.0;
    }
    if (h >= H - 0.9) col = vec3(0.92, 0.91, 0.88);
  } else if (sty == 19.0) {                       // dark ribbed metal upper storey with window strip
    col = vec3(0.27, 0.29, 0.31) * (0.9 + 0.1 * step(0.5, fract(u / 0.6)));
    if (h > H * 0.45 && h < H * 0.7 && fract(u / 6.0) > 0.15 && fract(u / 6.0) < 0.55) col = glass(n, toEye, 0.1) * 0.8;
    spec = 0.3; shin = 25.0;
  } else if (sty == 20.0) {                       // clock face stage (white) with clock dial
    col = base;
    vec2 c = vec2(u - L * 0.5, h - H * 0.5);
    float r = length(c);
    if (r < 1.5) {
      col = vec3(0.96);
      if (r > 1.38) col = vec3(0.15);
      float ang = atan(c.y, c.x);
      if (r > 1.1 && r < 1.35 && fract(ang / 6.2831853 * 12.0) < 0.08) col = vec3(0.12);
      if (abs(c.x) < 0.05 && c.y > 0.0 && c.y < 1.1) col = vec3(0.1);
      if (abs(c.y + c.x * 0.3) < 0.06 && c.x > 0.0 && c.x < 0.8) col = vec3(0.1);
    }
  } else if (sty == 22.0) {                       // engraved stone tablet: fret frame, title, lines of text
    col = base * (0.89 + 0.055 * vnoise(vec2(u, h) * 5.0));
    float across = min(u, L - u), vertical = min(h, H - h);
    float fr = min(across, vertical);
    if (fr < 0.155) {
      float run = across < vertical ? h : u;
      float stepWidth = 0.010 * (floor(mod(run, 0.22) / 0.055) - 1.5);
      float groove = abs(fract((fr + stepWidth) / 0.036) - 0.5);
      col = mix(base * 0.71, vec3(0.32, 0.36, 0.34), 0.58 * smoothstep(0.34, 0.48, groove));
    } else if (fr < 0.18) {
      col = base * 0.74;
    } else {
      float fromTop = H - h, line = floor(fromTop / 0.072);
      bool title = fromTop > 0.32 && fromTop < 0.54 && abs(u - L * 0.5) < L * 0.27;
      float lineWidth = 0.30 + hash(vec2(line, 4.1)) * 0.10;
      bool body = fromTop > 0.66 && h > 0.27 && abs(u - L * 0.5) < L * lineWidth && mod(line, 6.0) < 5.0;
      vec2 glyph = vec2(u / 0.024, fromTop / 0.072);
      vec2 pen = fract(glyph);
      float ink = hash(floor(glyph));
      if ((title || body) && ink > 0.19 && pen.y > 0.26 && pen.y < 0.56 && pen.x < 0.73 &&
          (pen.x < 0.23 || pen.y < 0.33 || (ink > 0.4 && pen.y > 0.48))) {
        col *= mix(title ? 0.54 : 0.69, 1.0, smoothstep(0.011, 0.05, fwidth(u)));
      }
    }
    spec = 0.1; shin = 20.0;
  } else if (sty == 23.0) {                       // banded slab: projecting floor bands, recessed window strip, fins per bay
    float npb = max(1.0, floor((v_style.z - 23.0) * 10.0 + 0.5));   // windows per bay (encoded as 23 + n/10)
    float nb = max(1.0, floor(L / bw + 0.5)), bww = L / nb;
    float bx = fract(u / bww) * bww, wy = mod(h, fh);
    col = base * 0.83;
    if (wy < 0.95) col = base * 1.04;
    else if (min(bx, bww - bx) < 0.24) col = base * 0.99;
    else {
      float cw = (bww - 0.48) / npb;
      float cx = mod(bx - 0.24, cw) - cw * 0.5;
      float ww = min(cw * 0.2, 0.56);
      if (abs(cx) < ww && wy > 1.45 && wy < fh - 0.5 && L > 3.0) {
        col = glass(n, toEye, hash(vec2(floor(u / cw), floor(h / fh))));
        if (ww - abs(cx) < 0.07 || abs(cx) < 0.03 || abs(wy - fh * 0.66) < 0.03) col = vec3(0.9, 0.9, 0.88);
        spec = 0.55; shin = 70.0;
      } else if (abs(cx) < ww + 0.08 && wy > 1.35 && wy < 1.45) col = base;
    }
    if (h > H - 0.9) col = base * 1.05;
    if (h < 0.0) col = base * 0.78;
  } else if (sty == 24.0) {                       // ball-stop net: 0.12 m mesh, see-through between the cords
    vec2 g = fract(vec2(u, h) / 0.12);
    if (min(min(g.x, 1.0 - g.x), min(g.y, 1.0 - g.y)) > 0.12 && h < H - 0.08 && h > 0.05) discard;
    col = base;
  } else if (sty == 25.0) {                       // engineering wings: broad punched windows and concrete courses
    float bay = L / max(1.0, floor(L / bw + 0.5));
    float x = (fract(u / bay) - 0.5) * bay;
    float y = mod(h, fh);
    float halfWindow = min(bay * 0.32, 1.75);
    col = base * (y < 0.42 || h > H - 0.62 ? 1.04 : 0.96);
    if (h < max(gl, 0.0) + 0.25) col = base * 0.78;
    else if (h < H - 0.65 && L > 3.3 && abs(x) < halfWindow && y > 0.75 && y < fh - 0.68) {
      col = mix(glass(n, toEye, hash(vec2(floor(u / bay), floor(h / fh)))), vec3(0.15, 0.24, 0.22), 0.56);
      if (halfWindow - abs(x) < 0.06 || y - 0.75 < 0.06 || fh - 0.68 - y < 0.06 ||
          abs(fract(x / 1.0 + 0.5) - 0.5) < 0.035 || abs(y - fh * 0.62) < 0.035) col *= 0.45;
      spec = 0.45; shin = 50.0;
    }
  } else if (sty == 26.0) {                       // Foreign Languages window bands
    float bay = L / max(1.0, floor(L / bw + 0.5));
    float x = (fract(u / bay) - 0.5) * bay;
    float y = mod(h, fh);
    float hw = max(0.1, bay * 0.5 - (bw > 5.0 ? 0.27 : 0.54));
    float lo = h < 0.0 ? 1.12 : 0.57;
    float hi = h < 0.0 ? 2.38 : fh - 0.76;
    float radius = min(0.29, hw);
    float clip = length(max(vec2(abs(x) - hw + radius, y - hi + radius), 0.0)) - radius;
    col = base * (y < 0.25 ? 1.02 : 0.98);
    float lowestBand = bw > 5.0 ? -fh : 0.0;
    if (L > 2.0 && h > gl + 0.07 && h > lowestBand && h < H - 0.67 && y > lo && clip < 0.02) {
      float var = hash(vec2(floor(u / bay), floor(h / fh)));
      col = mix(glass(n, toEye, var), vec3(0.17, 0.30, 0.31), 0.58);
      float panes = bw > 5.0 ? 5.0 : 3.0;
      float mullion = abs(fract((x + hw) * panes / (2.0 * hw) + 0.5) - 0.5);
      if (clip > -0.08 || y - lo < 0.075 || mullion < 0.035 || abs(y - mix(lo, hi, 0.74)) < 0.028) col *= 0.52;
      spec = 0.46; shin = 55.0;
    }
  } else if (sty == 27.0) {                       // Electronics building: pale brick courses and inset windows
    float bay = L / max(1.0, floor(L / bw + 0.5));
    float x = (fract(u / bay) - 0.5) * bay;
    float y = mod(h, fh);
    bool stair = bw > 7.5;
    float hw = bay * (stair ? 0.24 : 0.385);
    float sill = stair ? 0.98 : 0.55;
    float head = fh - (stair ? 1.04 : 0.66);
    float course = floor(h / 0.088);
    float bx = (u + 0.125 * mod(course, 2.0)) / 0.25;
    float joint = min(min(fract(bx), 1.0 - fract(bx)) * 0.25, mod(h, 0.088));
    float detail = 1.0 - 0.16 * (1.0 - smoothstep(0.002, 0.014, joint)) *
      (1.0 - smoothstep(0.02, 0.18, max(fwidth(h), 0.4 * fwidth(u))));
    col = base * (0.94 + 0.08 * hash(vec2(floor(bx), course))) * detail;
    if (y > head || y < sill) col = mix(col, vec3(0.76, 0.73, 0.68), stair ? 0.12 : 0.36);
    if (!stair && y > sill - 0.13 && y < sill) col *= 0.91;
    if (L > 1.7 && h > max(gl, -0.12) && h < H - 0.35 && abs(x) < hw && y > sill && y < head) {
      float var = hash(vec2(floor(u / bay), floor(h / fh)));
      col = mix(glass(n, toEye, var), vec3(0.14, 0.23, 0.26), 0.59);
      float split = min(abs(x + hw * 0.34), abs(x - hw * 0.34));
      if (min(hw - abs(x), y - sill) < 0.105 || head - y < 0.12 ||
          split < 0.032 || abs(y - mix(sill, head, 0.51)) < 0.037) col *= 0.40;
      spec = 0.43; shin = 54.0;
    }
  } else if (sty == 28.0) {                       // Woojungwon: narrow dormitory windows with jade pediments
    float bay = L / max(1.0, floor(L / bw + 0.5));
    float x = abs((fract(u / bay) - 0.5) * bay);
    float y = mod(h, fh);
    float sill = 0.67, head = 2.34;
    float hw = min(bay * 0.2, 0.58);
    col = base * (0.98 + 0.045 * vnoise(vec2(u, h) * 0.72));
    if (h < max(gl, -3.08)) col *= 0.88;
    if (L > 1.35 && h >= -0.02 && h < H - 0.44) {
      if (x < hw + 0.13 && y > sill - 0.108 && y < sill) col = vec3(0.41, 0.55, 0.46);
      if (x < hw + 0.13 && y > head && y < head + 0.25 - x * 0.16) col = vec3(0.36, 0.49, 0.42);
      if (x < hw && y > sill && y < head) {
        float var = hash(vec2(floor(u / bay), floor(h / fh)));
        col = mix(glass(n, toEye, var), vec3(0.27, 0.33, 0.34), 0.58);
        if (min(hw - x, min(y - sill, head - y)) < 0.077 || x < 0.021 || abs(y - 1.67) < 0.031) {
          col = vec3(0.74, 0.77, 0.74);
        }
        spec = 0.38; shin = 51.0;
      }
    }
  } else if (sty == 29.0) {                       // curved glass towers
    float pane = u / (L / 14.0);
    col = mix(base, glass(n, toEye, hash(vec2(floor(pane), floor(h / 1.68)))), 0.22);
    if (min(fract(pane), 1.0 - fract(pane)) < 0.042 ||
        abs(fract(h / 1.68 + 0.5) - 0.5) < 0.023) col *= 0.62;
    spec = 0.59; shin = 64.0;
  } else if (sty == 30.0) {                       // Second Dormitory: punched room windows and vertical piers
    float bay = L / max(1.0, floor(L / bw + 0.5));
    float x = abs((fract(u / bay) - 0.5) * bay), y = mod(h, fh);
    float hw = min(0.87, bay * 0.32), sill = 0.81, head = fh - 0.48;
    col = base * (x < bay * 0.38 ? 0.91 : 1.025);
    if (h > max(gl, 0.0) && h < H - 0.36 && x < hw && y > sill && y < head) {
      float var = hash(vec2(floor(u / bay), floor(h / fh)));
      col = mix(glass(n, toEye, var), vec3(0.24, 0.36, 0.39), 0.53);
      if (min(hw - x, min(y - sill, head - y)) < 0.063 || abs(y - sill - 0.31) < 0.042 ||
          (x < 0.034 && y < sill + 0.31)) col = vec3(0.69, 0.73, 0.71);
      spec = 0.48; shin = 52.0;
    }
  } else if (sty == 21.0) {                       // foliage
    float n1 = vnoise(vec2(u, h) * 1.7), n2 = vnoise(vec2(u, h) * 6.0);
    col = base * (0.6 + 0.5 * n1 + 0.22 * n2);
    spec = 0.02; shin = 4.0;
  } else if (sty == 4.0) {                        // rusticated granite
    float row = floor(h / 0.6);
    float jy = min(fract(h / 0.6), 1.0 - fract(h / 0.6)) * 0.6;
    float jx = min(fract(u / 1.2 + 0.5 * mod(row, 2.0)), 1.0 - fract(u / 1.2 + 0.5 * mod(row, 2.0))) * 1.2;
    float joint = 1.0 - smoothstep(0.015, 0.05, min(jy, jx));
    col = base * (0.94 + 0.08 * hash(vec2(floor(u / 1.2 + 0.5 * mod(row, 2.0)), row))) * (1.0 - 0.22 * joint);
  } else {                                         // windowed facades (0 granite, 1 modern, 2 residential, 3 glass)
    float y0 = gl + 0.9;
    float nb = max(1.0, floor(L / bw));
    float bww = L / nb;
    float bx = fract(u / bww);
    float wx = (bx - 0.5) * bww;
    float wy = mod(h, fh);
    float flr = floor(h / fh);
    float hw, wy0, wy1;
    if (sty < 0.5)      { hw = min(0.30 * bww, 0.95); wy0 = 0.95; wy1 = fh - 0.55; }
    else if (sty < 1.5) { hw = 0.5 * bww - 0.14;      wy0 = 0.85; wy1 = fh - 0.35; }
    else if (sty < 2.5) { hw = min(0.27 * bww, 0.8);  wy0 = 0.9;  wy1 = min(2.25, fh - 0.4); }
    else                { hw = 0.5 * bww - 0.05;      wy0 = 0.08; wy1 = fh - 0.08; }
    bool canWin = L > 2.8 && h > y0 + 0.2 && h < H - 1.6 && u > 0.7 && u < L - 0.7;
    bool inside = canWin && abs(wx) < hw && wy > wy0 && wy < wy1;
    if (inside && sty < 0.5 && wy > wy1 - hw) inside = length(vec2(wx, wy - (wy1 - hw))) < hw;
    col = base * (0.95 + 0.06 * hash(vec2(floor(u / 1.4), floor(h / 0.7))));
    if (sty < 0.5 && (abs(bx) < 0.06 || abs(bx - 1.0) < 0.06)) col *= 1.05;
    if (wy < 0.22 && sty < 1.5) col *= 1.06;
    if (canWin && abs(wx) < hw + 0.12 && wy > wy0 - 0.14 && wy < wy0) col = base * 1.12;
    if (inside) {
      float var = hash(vec2(floor(u / bww), flr));
      col = sty > 2.5 ? vec3(0.62, 0.72, 0.74) : glass(n, toEye, var);
      if (var > 0.93) col = mix(col, vec3(0.95, 0.85, 0.6), 0.35);
      float fx = hw - abs(wx), fy = min(wy - wy0, wy1 - wy);
      if (min(fx, fy) < 0.07 || abs(wx) < 0.035 || abs(wy - (wy0 + (wy1 - wy0) * 0.66)) < 0.03) col = vec3(0.22, 0.22, 0.24);
      spec = 0.55; shin = 70.0;
    }
    if (h < y0) col = base * 0.72;
    if (h > H - 1.3 && h < H - 0.25) col = base * 1.1;
    if (h >= H - 0.25) col = base * 0.78;
  }
  if (gl > -50.0) col *= mix(0.8, 1.0, clamp(smoothstep(gl, gl + 3.0, h) + (v_wall.a < 0.5 ? 1.0 : 0.0), 0.0, 1.0));
  col = mix(col, v_color.rgb, v_color.a);
  m.diffuse = col * 0.72;
  m.emission = col * 0.42;         // sky ambient: light stone stays light on the shaded side
  m.specular = spec;
  m.shininess = shin;
  m.normal = n;
  m.alpha = 1.0;
  out_FragColor = czm_phong(toEye, m, czm_lightDirectionEC);
}`;

export function createFacadeAppearance() {
  return new Cesium.Appearance({
    vertexShaderSource: VS,
    fragmentShaderSource: FS,
    translucent: false,
    closed: false,
    renderState: { depthTest: { enabled: true }, depthMask: true, cull: { enabled: false } },
  });
}

/** Accumulates a mesh with the attribute layout the shader expects. */
export class Mesh {
  constructor() { this.p = []; this.n = []; this.st = []; this.w = []; this.s = []; this.e = []; this.i = []; }
  v(pos, nrm, u, h, wall, style, edge) {
    this.p.push(pos.x, pos.y, pos.z); this.n.push(nrm.x, nrm.y, nrm.z);
    this.st.push(u, h); this.w.push(...wall); this.s.push(...style); this.e.push(...edge);
    return this.p.length / 3 - 1;
  }
  tri(a, b, c) { this.i.push(a, b, c); }
  get empty() { return this.i.length === 0; }
  geometry() {
    const F = Cesium.ComponentDatatype.FLOAT;
    const pos = new Float64Array(this.p);
    const A = (vals, n, dt = F) => new Cesium.GeometryAttribute({ componentDatatype: dt, componentsPerAttribute: n, values: vals });
    return new Cesium.Geometry({
      attributes: {
        position: A(pos, 3, Cesium.ComponentDatatype.DOUBLE),
        normal: A(new Float32Array(this.n), 3),
        st: A(new Float32Array(this.st), 2),
        wall: A(new Float32Array(this.w), 4),
        style: A(new Float32Array(this.s), 4),
        edge: A(new Float32Array(this.e), 2),
      },
      indices: this.p.length / 3 > 65535 ? new Uint32Array(this.i) : new Uint16Array(this.i),
      primitiveType: Cesium.PrimitiveType.TRIANGLES,
      boundingSphere: Cesium.BoundingSphere.fromVertices(pos),
    });
  }
}

/** Local East-North-Up frame. */
export class Frame {
  constructor(lon, lat, h = 0) {
    this.o = Cesium.Cartesian3.fromDegrees(lon, lat, h);
    const m = Cesium.Transforms.eastNorthUpToFixedFrame(this.o);
    this.E = new Cesium.Cartesian3(m[0], m[1], m[2]);
    this.N = new Cesium.Cartesian3(m[4], m[5], m[6]);
    this.U = new Cesium.Cartesian3(m[8], m[9], m[10]);
    this.lon = lon; this.lat = lat; this.h = h;
    this.mx = 111320 * Math.cos(lat * Math.PI / 180); this.my = 110950;
  }
  pt(e, n, u) {
    const { o, E, N, U } = this;
    return new Cesium.Cartesian3(o.x + E.x * e + N.x * n + U.x * u, o.y + E.y * e + N.y * n + U.y * u, o.z + E.z * e + N.z * n + U.z * u);
  }
  dir(e, n, u) {
    const { E, N, U } = this;
    const r = new Cesium.Cartesian3(E.x * e + N.x * n + U.x * u, E.y * e + N.y * n + U.y * u, E.z * e + N.z * n + U.z * u);
    return Cesium.Cartesian3.normalize(r, r);
  }
  local(lon, lat) { return [(lon - this.lon) * this.mx, (lat - this.lat) * this.my]; }
  lonlat(e, n) { return [this.lon + e / this.mx, this.lat + n / this.my]; }
}

/**
 * Solid-modelling helper in a rotated local frame: s along `axis`, t across (left-hand normal),
 * z up (metres relative to frame.h). (s,t) origin is offset by `off` (east, north metres).
 */
export class Local {
  constructor(mesh, frame, axis = [1, 0], off = [0, 0]) {
    this.m = mesh; this.f = frame; this.ax = axis; this.off = off;
  }
  P(s, t, z) {
    const [ax, ay] = this.ax;
    return this.f.pt(this.off[0] + ax * s - ay * t, this.off[1] + ay * s + ax * t, z);
  }
  D(s, t, z) {
    const [ax, ay] = this.ax;
    return this.f.dir(ax * s - ay * t, ay * s + ax * t, z);
  }
  _v(p, nrm, u, h, col, sty, H, L, gl = -99) {
    return this.m.v(p, nrm, u, h, [...col, 1], [this.fh ?? 3.8, this.bw ?? 3.6, sty, H], [L, gl]);
  }
  /** planar quad a,b,c,d (each [s,t,z]) with uv given as [u,h] per corner */
  quad(a, b, c, d, nrm, uv, col, sty, H, L) {
    const N = this.D(...nrm);
    const i = [a, b, c, d].map((q, k) => this._v(this.P(...q), N, uv[k][0], uv[k][1], col, sty, H, L));
    this.m.tri(i[0], i[1], i[2]); this.m.tri(i[0], i[2], i[3]);
  }
  box({ s0, s1, t0, t1, z0, z1, col, sty = STY.ASHLAR, faces = {}, top = true, bottom = false, zref }) {
    const zr = zref ?? z0, H = z1 - zr;
    const sides = [
      [[s0, t0], [s1, t0], [0, -1, 0], "front"], [[s1, t0], [s1, t1], [1, 0, 0], "right"],
      [[s1, t1], [s0, t1], [0, 1, 0], "back"], [[s0, t1], [s0, t0], [-1, 0, 0], "left"],
    ];
    for (const [A, B, nrm, name] of sides) {
      const L = Math.hypot(B[0] - A[0], B[1] - A[1]);
      const st = faces[name] ?? sty;
      if (st === null) continue;
      this.quad([A[0], A[1], z0], [B[0], B[1], z0], [B[0], B[1], z1], [A[0], A[1], z1], nrm,
        [[0, z0 - zr], [L, z0 - zr], [L, H], [0, H]], col, st, H, L);
    }
    const capSty = faces.top ?? sty;
    if (top) this.quad([s0, t0, z1], [s1, t0, z1], [s1, t1, z1], [s0, t1, z1], [0, 0, 1],
      [[s0, t0], [s1, t0], [s1, t1], [s0, t1]], col, capSty === STY.ATTIC || capSty === STY.CORNICE ? STY.ASHLAR : capSty, H, s1 - s0);
    if (bottom) this.quad([s0, t0, z0], [s1, t0, z0], [s1, t1, z0], [s0, t1, z0], [0, 0, -1],
      [[s0, t0], [s1, t0], [s1, t1], [s0, t1]], col, faces.bottom ?? (sty === STY.CORNICE || sty === STY.ATTIC ? STY.ASHLAR : sty), H, s1 - s0);
  }
  /** vertical (optionally tapered) prism/cylinder */
  cyl({ s, t, z0, z1, r0, r1 = r0, seg = 14, col, sty = STY.COLUMN, a0 = 0, cap = false }) {
    const H = z1 - z0, circ = 2 * Math.PI * r0;
    for (let k = 0; k < seg; k++) {
      const A = a0 + k / seg * 2 * Math.PI, B = a0 + (k + 1) / seg * 2 * Math.PI;
      const nA = [Math.cos(A), Math.sin(A), (r0 - r1) / H], nB = [Math.cos(B), Math.sin(B), (r0 - r1) / H];
      const u0 = k / seg * circ, u1 = (k + 1) / seg * circ;
      const p = (a, r, z) => this.P(s + Math.cos(a) * r, t + Math.sin(a) * r, z);
      const i0 = this._v(p(A, r0, z0), this.D(...nA), u0, 0, col, sty, H, circ);
      const i1 = this._v(p(B, r0, z0), this.D(...nB), u1, 0, col, sty, H, circ);
      const i2 = this._v(p(B, r1, z1), this.D(...nB), u1, H, col, sty, H, circ);
      const i3 = this._v(p(A, r1, z1), this.D(...nA), u0, H, col, sty, H, circ);
      this.m.tri(i0, i1, i2); this.m.tri(i0, i2, i3);
    }
    if (cap && r1 > 0) {
      const c = this._v(this.P(s, t, z1), this.D(0, 0, 1), 0, 0, col, STY.STATUE, H, 1);
      for (let k = 0; k < seg; k++) {
        const A = a0 + k / seg * 2 * Math.PI, B = a0 + (k + 1) / seg * 2 * Math.PI;
        const a = this._v(this.P(s + Math.cos(A) * r1, t + Math.sin(A) * r1, z1), this.D(0, 0, 1), 0, 0, col, STY.STATUE, H, 1);
        const b = this._v(this.P(s + Math.cos(B) * r1, t + Math.sin(B) * r1, z1), this.D(0, 0, 1), 0, 0, col, STY.STATUE, H, 1);
        this.m.tri(c, a, b);
      }
    }
  }
  /** cylinder between two arbitrary points [s,t,z] */
  cylBetween(a, b, r, col, sty = STY.STATUE, seg = 8) {
    const d = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
    const len = Math.hypot(...d);
    const w = d.map((x) => x / len);
    const ref = Math.abs(w[2]) < 0.9 ? [0, 0, 1] : [1, 0, 0];
    const cr = (x, y) => [x[1] * y[2] - x[2] * y[1], x[2] * y[0] - x[0] * y[2], x[0] * y[1] - x[1] * y[0]];
    let u1 = cr(w, ref); const l1 = Math.hypot(...u1); u1 = u1.map((x) => x / l1);
    const u2 = cr(w, u1);
    for (let k = 0; k < seg; k++) {
      const A = k / seg * 2 * Math.PI, B = (k + 1) / seg * 2 * Math.PI;
      const rad = (ang) => u1.map((x, i) => Math.cos(ang) * x + Math.sin(ang) * u2[i]);
      const nA = rad(A), nB = rad(B);
      const at = (o, nn) => [o[0] + nn[0] * r, o[1] + nn[1] * r, o[2] + nn[2] * r];
      const i0 = this._v(this.P(...at(a, nA)), this.D(...nA), A * r, 0, col, sty, len, 2 * Math.PI * r);
      const i1 = this._v(this.P(...at(a, nB)), this.D(...nB), B * r, 0, col, sty, len, 2 * Math.PI * r);
      const i2 = this._v(this.P(...at(b, nB)), this.D(...nB), B * r, len, col, sty, len, 2 * Math.PI * r);
      const i3 = this._v(this.P(...at(b, nA)), this.D(...nA), A * r, len, col, sty, len, 2 * Math.PI * r);
      this.m.tri(i0, i1, i2); this.m.tri(i0, i2, i3);
    }
  }
  sphere({ s, t, z, r, col, sty = STY.STATUE, seg = 10, sz = 1, jit = 0, ph = 0 }) {
    const rows = Math.max(4, seg >> 1);
    const idx = [];
    this.__ph = ph;
    for (let i = 0; i <= rows; i++) {
      const pa = i / rows * Math.PI, row = [];
      for (let j = 0; j <= seg; j++) {
        const th = j / seg * 2 * Math.PI;
        const nrm = [Math.sin(pa) * Math.cos(th), Math.sin(pa) * Math.sin(th), Math.cos(pa)];
        const rr = r * (1 + jit * Math.sin(th * 3 + pa * 5 + this.__ph) * Math.cos(th * 2 - pa * 3 + this.__ph * 0.7));
        row.push(this._v(this.P(s + nrm[0] * rr, t + nrm[1] * rr, z + nrm[2] * rr * sz), this.D(...nrm), th * r, pa * r, col, sty, Math.PI * r, 2 * Math.PI * r));
      }
      idx.push(row);
    }
    for (let i = 0; i < rows; i++) for (let j = 0; j < seg; j++) {
      this.m.tri(idx[i][j], idx[i + 1][j], idx[i + 1][j + 1]); this.m.tri(idx[i][j], idx[i + 1][j + 1], idx[i][j + 1]);
    }
  }
  /** planar polygon in the (s,z) plane at fixed t (e.g. arch spandrel face) */
  sFace(pts, t, nrmT, col, sty, zref = 0) {
    const flat = pts.map(([s, z]) => new Cesium.Cartesian2(s, z));
    let tri = [];
    try { tri = Cesium.PolygonPipeline.triangulate(flat, []); } catch { return; }
    const s0 = Math.min(...pts.map((p) => p[0])), s1 = Math.max(...pts.map((p) => p[0]));
    const H = Math.max(...pts.map((p) => p[1])) - zref;
    const N = this.D(0, nrmT, 0);
    const ids = pts.map(([s, z]) => this._v(this.P(s, t, z), N, s - s0, z - zref, col, sty, H, s1 - s0));
    for (let k = 0; k < tri.length; k += 3) this.m.tri(ids[tri[k]], ids[tri[k + 1]], ids[tri[k + 2]]);
  }
  /** Closed extrusion of a counterclockwise (s,z) profile from t0 to t1. */
  profile(pts, t0, t1, col, sty = STY.STATUE) {
    const base = Math.min(...pts.map(([, z]) => z));
    this.sFace(pts, t0, -1, col, sty, base);
    this.sFace(pts, t1, 1, col, sty, base);
    for (let i = 0; i < pts.length; i++) {
      const [s, z] = pts[i], [nextS, nextZ] = pts[(i + 1) % pts.length];
      const ds = nextS - s, dz = nextZ - z, len = Math.hypot(ds, dz);
      if (len < 0.001) continue;
      const d = t1 - t0;
      this.quad([s, t0, z], [nextS, t0, nextZ], [nextS, t1, nextZ], [s, t1, z],
        [dz / len, 0, -ds / len], [[0, 0], [len, 0], [len, d], [0, d]], col, sty, d, len);
    }
  }
}
