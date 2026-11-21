// EPSG:5186 (Korea 2000 / Central Belt 2010) forward Transverse Mercator, Kruger series (Karney 2011).
// Verified in the preprocessing pipeline against PROJ to < 0.01 mm.
const A = 6378137.0, F = 1 / 298.257222101;
const N = F / (2 - F);
const AA = A / (1 + N) * (1 + N * N / 4 + N ** 4 / 64);
const ALPHA = [N / 2 - 2 * N * N / 3 + 5 * N ** 3 / 16, 13 * N * N / 48 - 3 * N ** 3 / 5, 61 * N ** 3 / 240];
const E = Math.sqrt(F * (2 - F));
const LON0 = 127, LAT0 = 38, FE = 200000, FN = 600000;

function raw(lon, lat) {
  const phi = lat * Math.PI / 180, lam = (lon - LON0) * Math.PI / 180;
  const t = Math.sinh(Math.atanh(Math.sin(phi)) - E * Math.atanh(E * Math.sin(phi)));
  const xiP = Math.atan2(t, Math.cos(lam));
  const etaP = Math.atanh(Math.sin(lam) / Math.sqrt(1 + t * t));
  let xi = xiP, eta = etaP;
  ALPHA.forEach((a, k) => {
    const j = 2 * (k + 1);
    xi += a * Math.sin(j * xiP) * Math.cosh(j * etaP);
    eta += a * Math.cos(j * xiP) * Math.sinh(j * etaP);
  });
  return [AA * eta, AA * xi];
}
const Y0 = raw(LON0, LAT0)[1];

export function toEpsg5186(lon, lat) {
  const [x, y] = raw(lon, lat);
  return { x: FE + x, y: FN + (y - Y0) };
}

export function fmtLonLat(lon, lat) {
  return `${lat.toFixed(6)}°N, ${lon.toFixed(6)}°E`;
}
