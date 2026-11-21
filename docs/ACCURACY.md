# Accuracy & provenance report

Generated 2026-11-21T11:00:38+00:00 by `scripts/validate.py`. The machine-readable versions are [`web/data/accuracy_report.json`](../web/data/accuracy_report.json) and [`web/data/summary.json`](../web/data/summary.json).

## Campus

- Boundary: OSM relation 11246784 (2 parts), 72.00 ha, perimeter 4684 m
- Elevation inside the boundary (FABDEM): 55.5–112.9 m, mean 77.5 m, relief 57.4 m
- Buildings: 41 inside the boundary, 1104 including the ~600 m context
- Height status (campus): {'documented': 1, 'estimated': 39, 'derived': 1}
- Official KHU map: 23/24 building entries matched

## Automated checks

| Check | Status | Result |
|---|---|---|
| Campus terrain is not flat | pass | Relief inside the boundary: 55.5–112.9 m (57.4 m), from 28746 DTM samples |
| DTM vs mapped peak elevations (OSM ele) | pass | n=3; mean Δ -2.24 m, max |Δ| 3.54 m (매미산 156.1 vs 158.5 m, 아람산 146.3 vs 147.1 m, 독침산 105.5 vs 109.0 m). A 30 m DEM is expected to slightly underestimate summits. |
| DTM vs DSM agreement on open sports fields | pass | n=950 samples; median DSM−DTM +0.46 m, RMS 1.61 m. This is an internal consistency check only (FABDEM is derived from Copernicus). |
| EPSG:5186 transform vs PROJ | pass | max difference 0.0021 mm |
| Vertical datum handled (EGM2008 → WGS84 ellipsoid) | pass | N = 23.34–23.79 m over the terrain window (EGM2008 via PROJ (us_nga_egm08_25)); this is added to every DTM height before rendering |
| DEM grid registration | pass | GeoTIFF GTRasterTypeGeoKey=PixelIsPoint; pixel (0,0) centre = 127.0°E, 38.0°N; 1″ spacing honoured without resampling |
| Building footprint overlaps | pass | 0 overlapping footprint pairs (>1 m²) among 1104 buildings |
| Buildings on sloping ground | info | 23 of 41 campus buildings span >4 m of DTM relief. Their bases are set to the lowest ground point minus 1.5 m, so the uphill side is embedded in the slope and nothing floats. |
| Campus building heights | warn | In campus: 1 documented, 1 derived from floor count, 39 estimated. Whole scene: {'documented': 161, 'estimated': 936, 'derived': 7}. OSM and the official KHU pages do not publish heights for most campus buildings. |
| DSM−DTM as height estimator (rejected) | info | Compared with 160 OSM-documented heights in the context area, Copernicus DSM minus FABDEM underestimated heights by about 45 m (r≈0.1), so it was not used. |
| Official campus-map buildings matched to footprints | pass | 23/24 official building entries matched to OSM footprints; unmatched: 한방재료가공(경희보감); matched but outside boundary: 0 |
| Campus buildings connected to the path network | pass | 38/41 campus buildings lie within 30 m of a mapped road/footway (median 5.3 m) |
| Stylised Kyung Hee building appearance | info | Campus buildings use their real footprints and DTM ground, but their facades (windows per estimated storey, colours) are procedural. Main gate: illustrative model on the footprint frame (59.24 × 5.54 m, opening 11.3 m from footprint vertices); its heights are estimated. Amphitheatre: 41 seating terraces sliced from the real DTM. None of this detail is surveyed. |
| North orientation | pass | All geometry is in geographic coordinates on the WGS84 globe, so north follows from the coordinates. There is no local rotation or scaling. |
| Imagery ↔ footprint alignment | manual | Checked visually in top-down screenshots (see docs/screenshots). Imagery comes from tile services; their offset relative to OSM is not quantified here. |

## Datasets

| Dataset | Role | Resolution | Date | Licence | Limitations |
|---|---|---|---|---|---|
| [FABDEM V1-2 (tile N37E127)](https://data.bris.ac.uk/data/dataset/s5hqmjcdj8yo2ibzi9b4ew3sn) | Primary terrain: bare-earth DTM with forests and buildings removed | 1 arc-second (~24.6 × 30.9 m here) | Copernicus GLO-30 source data 2011–2015; FABDEM released 2022 (V1-2 2023) | CC BY-NC-SA 4.0 (non-commercial) | Machine-learning bare-earth correction; errors of metres, larger under dense forest and on steep slopes. Cannot resolve terraces or walls narrower than ~30 m. |
| [Copernicus DEM GLO-30 (tile N37E127)](https://registry.opendata.aws/copernicus-dem/) | DSM for cross-checks and the canopy-height model that guides vegetation | 1 arc-second | TanDEM-X acquisitions 2011–2015 | Copernicus DEM licence (free, attribution) | Published spec: absolute vertical accuracy < 4 m (LE90). It is a surface model. Buildings in this area appear strongly under-represented. |
| [OpenStreetMap](https://www.openstreetmap.org/relation/11246784) | Campus boundary, building footprints/names/levels, roads, paths, steps, parking, landcover, POIs | vector | snapshot 2026-11-21T10:16:19Z | ODbL 1.0 | Volunteered geometry; positional accuracy not quantified (typically 1–5 m). Heights missing for most campus buildings. |
| [Kyung Hee University official campus map list](https://www.khu.ac.kr/kor/user/contents/view.do?menuNo=200086) | Building names and numbering for verification (33 entries) | list (no geometry) | retrieved 2026-11-21 | © Kyung Hee University (names used for identification) | No coordinates, floor counts or English names on the pages. |
| [EGM2008 geoid (PROJ us_nga_egm08_25)](https://cdn.proj.org/) | Orthometric → ellipsoidal height conversion | 2.5′ grid, sampled 9×9 over the window | EGM2008 | Public domain | N varies only 0.45 m over the window; residual interpolation error < 1 cm. |
| [Stylised campus appearance (this project)](https://www.openstreetmap.org/way/473963422) | Procedural facades, main-gate model, amphitheatre terraces, observatory dome | derived from OSM footprints + FABDEM | generated | project code | Appearance only. Window layout, colours, gate form and gate heights are illustrative, not surveyed. |
| [Imagery tiles (Esri World Imagery default; Sentinel-2 cloudless, OSM, optional VWorld)](https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer) | Draped surface texture only, never used to derive geometry | ~0.3–1 m (Esri), 10 m (Sentinel-2) | varies by tile (provider-managed) | Provider terms; streamed, not redistributed | Third-party tiles; possible metre-level offsets and outdated capture dates. |

## Campus buildings

| No. | Name | OSM id | Footprint m² | Ground m | Height m | Status | Height source |
|---|---|---|---|---|---|---|---|
| 1 | 경희대학교 국제캠퍼스 정문 | way/473963422 | 328 | 67.3–70.2 | 22.5 | documented | Published guidebook: 조명화, 『캠퍼스투어008 경희대학교』 (Google Books) - gate width 62 m, height 22.5 m (incl. sculpture), 39 sculpted figures, completed 2001 |
| 2 | 애지원 | way/170482640 | 2099 | 80.3–85.3 | 16.2 | estimated | estimated: footprint-size heuristic (4 floor(s) x 3.8 m); no documented height or floor count available |
| 4 | 우정원 | relation/8269760 | 4137 | 58.5–65.8 | 16.2 | estimated | estimated: footprint-size heuristic (4 floor(s) x 3.8 m); no documented height or floor count available |
| 6 | 공학관 | way/455725718 | 6260 | 78.6–95.1 | 16.2 | estimated | estimated: footprint-size heuristic (4 floor(s) x 3.8 m); no documented height or floor count available |
| 7 | 원자로센터 | way/455728923 | 322 | 86.6–89.1 | 8.6 | estimated | estimated: footprint-size heuristic (2 floor(s) x 3.8 m); no documented height or floor count available |
| 8 | 공학실험동 | way/455728922 | 3689 | 88.2–100.8 | 16.2 | estimated | estimated: footprint-size heuristic (4 floor(s) x 3.8 m); no documented height or floor count available |
| 9 | 체육대학관 | way/455726113 | 7783 | 79.2–93.8 | 16.2 | estimated | estimated: footprint-size heuristic (4 floor(s) x 3.8 m); no documented height or floor count available |
| 10 | 외국어대학관 | way/585696507 | 3646 | 63.7–68.6 | 16.2 | estimated | estimated: footprint-size heuristic (4 floor(s) x 3.8 m); no documented height or floor count available |
| 12 | 글로벌관 | way/474085538 | 1281 | 57.5–61.9 | 12.4 | estimated | estimated: footprint-size heuristic (3 floor(s) x 3.8 m); no documented height or floor count available |
| 12 | 멀티미디어교육관 | way/474085537 | 1806 | 59.7–62.4 | 16.2 | estimated | estimated: footprint-size heuristic (4 floor(s) x 3.8 m); no documented height or floor count available |
| 13 | 제2기숙사 남자동 | relation/6739958 | 1895 | 60.3–79.6 | 16.2 | estimated | estimated: footprint-size heuristic (4 floor(s) x 3.8 m); no documented height or floor count available |
| 13 | 제2기숙사(여자동) | relation/6739964 | 1764 | 58.4–63.3 | 16.2 | estimated | estimated: footprint-size heuristic (4 floor(s) x 3.8 m); no documented height or floor count available |
| 15 | 예술디자인대학 도예관 | way/474521123 | 655 | 91.7–99.9 | 12.4 | estimated | estimated: footprint-size heuristic (3 floor(s) x 3.8 m); no documented height or floor count available |
| 16 | 원예생물공학온실 | way/474521122 | 649 | 90.2–93.0 | 5.0 | estimated | estimated: greenhouse default 5 m |
| 17 | 선승관 | way/585696506 | 5365 | 79.7–92.9 | 19.5 | estimated | estimated from photographs (brick arcade ~14 m to cornice + inset metal upper storey; clock tower ~37 m); not a documented value |
| 18 | 생명과학대학 | way/474521121 | 2556 | 85.7–95.5 | 16.2 | estimated | estimated: footprint-size heuristic (4 floor(s) x 3.8 m); no documented height or floor count available |
| 20 | 실험연구동 | way/778946313 | 1492 | 62.5–63.0 | 12.4 | estimated | estimated: footprint-size heuristic (3 floor(s) x 3.8 m); no documented height or floor count available |
| 20 | 실험연구동 | way/801815069 | 907 | 63.0–63.5 | 12.4 | estimated | estimated: footprint-size heuristic (3 floor(s) x 3.8 m); no documented height or floor count available |
| 21 | 예술디자인대학 | way/474085536 | 6575 | 63.1–72.2 | 36.0 | estimated | estimated from photographs (2-storey colonnaded base + ~8-storey main block; corner towers ~41 m); not a documented value |
| 22 | 국제대학 | way/474085539 | 2095 | 78.5–84.5 | 16.2 | estimated | estimated: footprint-size heuristic (4 floor(s) x 3.8 m); no documented height or floor count available |
| 23 | 학생회관 | way/474085535 | 3635 | 75.5–83.8 | 16.2 | estimated | estimated: footprint-size heuristic (4 floor(s) x 3.8 m); no documented height or floor count available |
| 24 | 경희대학교 국제캠퍼스 중앙도서관 | way/474085534 | 5530 | 74.6–79.3 | 21.0 | estimated | estimated from aerial/oblique photographs of the library (raised podium + ~4 storeys under a giant colonnade, ≈21 m); not a documented value |
| 29 | 노천극장 | way/474531805 | 5310 | 73.5–93.1 | 2.0 | estimated | estimated: open-air amphitheatre, rendered as low seating mass |
| 31 | 전자정보대학 | way/474085540 | 6655 | 69.0–83.6 | 16.2 | estimated | estimated: footprint-size heuristic (4 floor(s) x 3.8 m); no documented height or floor count available |
| 32 | 국제학관 | way/474085542 | 1511 | 76.8–84.3 | 16.2 | derived | OSM building:levels=4 x 3.8 m/floor |
| 33 | 천문대 | way/474521125 | 784 | 96.6–103.1 | 12.4 | estimated | estimated: footprint-size heuristic (3 floor(s) x 3.8 m); no documented height or floor count available |
|  | Emart 24 | way/764320683 | 280 | 65.3–67.7 | 8.6 | estimated | estimated: footprint-size heuristic (2 floor(s) x 3.8 m); no documented height or floor count available |
|  | 실습농장동 | way/585696420 | 560 | 72.0–75.3 | 12.4 | estimated | estimated: footprint-size heuristic (3 floor(s) x 3.8 m); no documented height or floor count available |
|  | (unnamed) | way/1370623062 | 84 | 72.4–73.2 | 4.8 | estimated | estimated: footprint-size heuristic (1 floor(s) x 3.8 m); no documented height or floor count available |
|  | (unnamed) | way/1370623063 | 92 | 72.8–74.1 | 4.8 | estimated | estimated: footprint-size heuristic (1 floor(s) x 3.8 m); no documented height or floor count available |
|  | (unnamed) | way/1385686358 | 12 | 86.7–90.8 | 4.8 | estimated | estimated: footprint-size heuristic (1 floor(s) x 3.8 m); no documented height or floor count available |
|  | (unnamed) | way/170482643 | 322 | 82.3–85.5 | 8.6 | estimated | estimated: footprint-size heuristic (2 floor(s) x 3.8 m); no documented height or floor count available |
|  | (unnamed) | way/474521124 | 254 | 93.4–102.2 | 8.6 | estimated | estimated: footprint-size heuristic (2 floor(s) x 3.8 m); no documented height or floor count available |
|  | (unnamed) | way/778946314 | 353 | 62.4–62.7 | 8.6 | estimated | estimated: footprint-size heuristic (2 floor(s) x 3.8 m); no documented height or floor count available |
|  | (unnamed) | way/778946315 | 214 | 62.3–62.4 | 8.6 | estimated | estimated: footprint-size heuristic (2 floor(s) x 3.8 m); no documented height or floor count available |
|  | (unnamed) | way/778946316 | 418 | 62.2–62.5 | 8.6 | estimated | estimated: footprint-size heuristic (2 floor(s) x 3.8 m); no documented height or floor count available |
|  | (unnamed) | way/778946317 | 632 | 62.6–66.6 | 12.4 | estimated | estimated: footprint-size heuristic (3 floor(s) x 3.8 m); no documented height or floor count available |
|  | (unnamed) | way/778946318 | 988 | 60.8–62.7 | 12.4 | estimated | estimated: footprint-size heuristic (3 floor(s) x 3.8 m); no documented height or floor count available |
|  | (unnamed) | way/778946319 | 222 | 58.2–62.9 | 8.6 | estimated | estimated: footprint-size heuristic (2 floor(s) x 3.8 m); no documented height or floor count available |
|  | (unnamed) | way/778946320 | 321 | 72.3–75.1 | 8.6 | estimated | estimated: footprint-size heuristic (2 floor(s) x 3.8 m); no documented height or floor count available |
|  | (unnamed) | way/778946321 | 365 | 73.9–75.2 | 8.6 | estimated | estimated: footprint-size heuristic (2 floor(s) x 3.8 m); no documented height or floor count available |
