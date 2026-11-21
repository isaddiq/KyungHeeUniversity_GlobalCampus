# Photo-based model progress

Each campus place is checked against the user-supplied reference photos in `kyunghee pictures/`
(git-ignored; rights unverified, never published). Places are processed in campus-map order 01 → 33, then
the outdoor areas. Positions, outlines, orientation and ground level always come from the OSM footprint
and the FABDEM DTM. Photographs and aerial views inform the shape within each footprint, entrance
details, proportions, materials and colours. All
photo-derived heights are labelled *estimated*.

After-screenshots are renders of this project's own model (not the reference photos) and live in
[`screenshots/places/`](screenshots/places/).

| No. | Place | Status |
|---|---|---|
| 01 | 정문 (Neo-Renaissance main gate) | revised |
| 02 | 애지원 (ROTC 학군단) | photo-based model |
| 03 | 르네상스공원 (Renaissance Park) | ground + fountain modelled |
| 05 | 인조잔디구장/지하주차장 (turf field) | ground, nets and Engineering-side stairs modelled |
| — | Campus roads + sidewalks (user request) | widths, sidewalks, kerbs, crossings |
| 06 | 공학관 (College of Engineering) | photo-based model |
| 10 | 외국어대학관 (College of Foreign Languages) | photo-based model |
| 11 | 경희공원 (Kyung Hee Park) | pagoda placed at map pin; garden outline not in OSM |
| 31 | 전자정보/응용과학대학관 (College of Electronics Information and Applied Science) | photo-based model |
| 14 | 대운동장 (Grand Stadium) | sunken bowl carved, terraces, track, field |
| 04 (ground) | 우정원 site + parking | levelled below the main road (user report) |
| 04 | 우정원 (Woojungwon Dormitory) | photo-based model |

**Order change (user request, 2026-11-21):** after 01–02, all ground work comes next: open spaces 03, 05,
11, 14, 26, 27 and 28, then every `outdoor/` folder (roads, slopes, retaining walls, stairs, pergolas,
courts). The remaining buildings are done after that.

---

## 01 · 정문 (새천년기념탑 · 네오르네상스문) — main gate

- **OSM / position:** way/473963422, 59.2 × 5.5 m footprint frame, axis bearing 88.5° (east–west). The
  street face looks north to 덕영대로 and the campus face looks south (both confirmed in the photos). The
  11.3 m opening comes from the footprint vertices around the entrance road (way/764171420). The paved
  forecourts are OSM plazas way/1385683781 and way/1385685748.
- **Photos used:** all 25 in `01-neo-renaissance-main-gate/`. Main references: *street facing wide* (clean
  frontal elevation, used for counts and proportions), *campus side axis and crosswalk*, *campus side
  elevation aerial*, *central statuary and arch*, *stone panel and carving*, *western relief side angle*,
  *side colonnade from the road* and *roofline sculpture*.
- **Changes in this revision:**
  - Wing colonnades: **4 coupled column pairs per row** (front and back rows; counted in the frontal
    photo), replacing 5 single columns. The columns are thicker (Ø ≈ 0.88 m).
  - **3-step stylobate** along both faces of each wing.
  - End pavilions: **white figural relief groups** (central figure with a raised arm and two companions)
    replace the flat noise panel. The brown "bronze" plaques became **light engraved stone tablets with
    fret frames, each with an eagle on a globe above**, as in the close-up photos.
  - New tablets with eagles inside each wing, on the arch-pier side faces and on the pavilion inner faces.
  - Spandrels: **winged figures flying towards the crown** on both faces.
  - **Dark medallion in place of a keystone** on both faces. The arch springing line is lowered from 8.2 to
    7.4 m, so the crown is ≈ 13.1 m, as measured in the frontal photo.
  - Arch piers widened from 4.2 to 4.6 m. The arch block is ≈ 20.5 m wide (≈ 20.9 m measured).
  - Attic: real engraved **"NEO-RENAISSANCE"** lettering (5×7 font in the shader; the letters span ≈ 43 % of
    the attic width) instead of pseudo-glyphs.
- **Estimated:** every detail height except the documented 22.5 m total (guidebook). This includes column
  heights, the crown, the attic and the pavilion tops, scaled from the frontal photo with the 11.3 m
  opening as the reference length. Sculpture is stylised.
- **Open questions:** the aerial video shows a paved forecourt on both sides of the road on the campus
  side, but OSM maps a plaza only on the east side, so the west side is still drawn as park grass. The
  wing ends look slightly curved in the fisheye night shots, but OSM and the aerial frames show straight
  wings, so the model keeps them straight.
- **Screenshots:** before `screenshots/places/01_gate_street_before.png`; after
  `screenshots/places/01_gate_street.png`, `screenshots/places/01_gate_campus.png`.

## 02 · 애지원 — ROTC 학군단 building

- **OSM / position:** way/170482640 (14-vertex outline, 2,099 m²). In the aerial imagery it is a complex: a
  south wing, a south-east wing, a lower central block and a north wing. The model keeps the single OSM
  outline. Front = the south face of the south wing (the OSM edge facing ≈ 170°, 31.4 m), which looks onto
  the parking lot in the photos. The map pin (37.24922, 127.08134) lies inside the footprint.
- **Photos used:** all 3 in `02-aejiwon/` (*approach and building corner*, *front car park and wing*,
  *official campus map view*).
- **Modelled:** 5 storeys of a white banded slab. This uses the new shader style `BANDED` (23): projecting
  floor bands, a recessed window strip, a fin at every bay, and 4 bays × 2 small two-pane windows on the
  31 m front. Taupe stair towers sit at both ends of the front and rise 1.6 m above the parapet. There is a
  green-glazed entrance in the first bay with a white sign band. The storey grid starts at the parking-lot
  level (DTM ≈ 3.3 m above the footprint's lowest point).
- **New generic framework:** `photo_buildings` in `build_campus_details.py` (the `Site` helper finds edges
  by outward bearing, and `mass`/`pbox`/`pcyl` describe the model) is rendered by `buildPhotoModel()` in
  `khu_landmarks.js`. A floor count from photos is shown with a "counted from photos" badge.
- **Estimated:** height 21.0 m above the lowest ground (17.7 m above the parking lot): 3.6 m ground floor +
  4 × 3.3 m + 0.9 m parapet, in `height_overrides.json` as *estimated*. Tower size: 3.3 m wide.
- **Open questions:** the central block and the north wing are not photographed. The imagery suggests a
  lower central block, but the model uses the full 5-storey height everywhere. The parking lot in front is
  not in OSM, so it is drawn as grass, and synthetic trees stand on it.
- **Screenshots:** before `screenshots/places/02_aejiwon_front_before.png`; after
  `screenshots/places/02_aejiwon_front.png`, `screenshots/places/02_aejiwon_aerial.png`.

## 03 · 르네상스공원 — Renaissance Park

- **OSM / position:** park way/455726192. Inside it: the plaza (place=square, way/1385683781), 6 flowerbeds
  (way/1385683775–780), and the fountain basin (natural=water way/764320697, "르네상스공원", 50 m² ⇒ r ≈ 4.0 m).
  There are 11 round planters (man_made=planter) along the gate approach. The map pin (37.24684, 127.07804)
  sits on the fountain.
- **Photos used:** all 10 in `03-renaissance-park/`. Main references: *fountain paths and hedges aerial*
  (drone, plan layout), *fountain and obelisk*, *obelisk and fountain up close*, *fountain surround and
  path*.
- **Ground-layer fixes (whole campus):**
  - Ground fills are now **disjoint by priority** (water > courts > flowerbeds > sport/parking > paving >
    plaza > grass > forest).
  - The fills are rendered as **one ground primitive per surface kind**. Before, Cesium dropped a
    degenerate polygon inside the single batch and shifted the following instances' colours and ids, so
    this plaza (and possibly other fills) was painted in the park's grass colour.
  - Small OSM `natural=water` areas are now drawn.
  - **OSM-mapped trees** (natural=tree, tree_row sampled every 7 m; 81 trees) now stand at their mapped
    positions and replace synthetic trees within 4 m. They come first in `trees.bin` (`mapped_count`).
- **New 3D ground objects** (`ground.json` → `objects`, rendered by `web/js/ground_objects.js`):
  - Fountain on the OSM outline: granite rim 0.55 m high and 0.55 m wide, blue-tiled basin, translucent
    water, and a ring of 28 nozzles arcing towards the centre. The white obelisk (≈ 5.0 m above the water,
    inscribed shaft) stands on a pedestal with a seated figure facing the open side of the plaza. The
    basin is level and sits on the highest DTM point of its outline.
  - **Clipped box-hedge borders** (0.6 m, scalloped) around the flowerbeds inside the park.
  - Granite **planter bowls** with shrubs for all `man_made=planter` on campus.
- **Estimated:** obelisk height (scaled from the 9 m basin in the panorama and the close-up), rim size, jet
  arcs, hedge height. The figure's facing direction is inferred, because the photos show it on the side
  away from the gate.
- **Open questions:** the photos show 5 hedged beds but OSM maps 6 (the OSM count is kept). The silver
  sphere sculpture beside the entrance road is not in OSM and is not modelled.
- **Screenshots:** before `screenshots/places/03_renaissance_park_aerial_before.png`; after
  `screenshots/places/03_renaissance_park_aerial.png`, `screenshots/places/03_renaissance_park_ground.png`.

## 05 · 인조잔디구장 / 지하주차장 — artificial turf field over the underground car park

- **OSM / position:** pitch way/326869014 (soccer, 5,727 m²), basketball ways 585696427 and 585696429,
  brick plaza way/1385685748, and the Engineering-side stair outline way/1385685749. The courts are
  west of the pitch, and the stairs ascend east towards the College of Engineering.
- **Photos used:** all 5 in `05-artificial-turf-field-and-underground-parking/` (*field and courts top down*,
  *field and sports courts aerial*, two 2017 panoramas, the map view).
- **Ground-layer fix (whole campus):** roads and all markings were drawn with `GroundPolylineGeometry`,
  whose width is in **screen pixels**. Roads were therefore hairlines and paint was invisible. All lines
  are now buffered into metre-width polygons (roads at their OSM/class width, paint 0.08–0.55 m) and go
  through the same disjoint, per-kind ground pipeline. This also makes the "before" bug visible: half the
  pitch had been painted as plaza by the batch colour shift.
- **Modelled:** turf with 5 m mowing stripes. A **"KHU" logo** fills the centre circle (letters ≈ 7.2 m
  tall, read from the stand side). **6 m ball-stop nets** with posts every 4 m run on both ends and the
  courts side (new see-through `NET` shader style). The
  basketball courts are **mint green with terracotta keys and centre circles**, and the surrounding squares
  are **terracotta brick**.
- **Revised stairs:** a broad tapered terrace with nine concrete treads, pale side coping, three mapped
  diamond planters (ways 1385685750–5752), lower planting beds, stone insets, and three upper tree
  pockets. The lower landing meets the pitch edge, and the upper brick landing joins the campus
  sidewalk. The official map photo, top-down photo, and two DreamVR aerial angles show the layout.
- **Estimated:** net height, tread count and dimensions, landscaping details, logo size, and colours. Markings are
  standard-dimension layouts fitted to the OSM outline.
- **Open questions:** the 30 m DTM is not flat across the pitch, so the turf follows a gentle slope. The
  retaining wall with the car-park entrance (west side, aerial photo) is not in OSM; it is a candidate for
  the outdoor/retaining-wall pass. The blue dugouts are not modelled.
- **Screenshots:** before `screenshots/places/05_turf_field_top_before.png`; after
  `screenshots/places/05_turf_field_top.png`, `screenshots/places/05_turf_field_oblique.png`,
  `screenshots/places/05_turf_field_ground.png`.
- **Revised stairs renders:** [oblique view](screenshots/places/05_engineering_terrace_oblique.png)
  and [overhead view](screenshots/places/05_engineering_terrace_top.png).

## 06 · 공학관 — College of Engineering

- The building uses OSM way/455725718 and faces west into the courtyard. The 78.1 m main
  facade and the returns of both wings follow the mapped outline. Ground levels come from FABDEM.
- The official map photo and the two close ground panoramas show five levels across the
  main block, four raised window bands, tall barred ground-floor bays, and twin concrete
  fins around the rooftop clock. The model includes the projecting entrance canopy with
  raised 工科大學 lettering, glazed vestibule, steps and side ramps. The aerial panorama
  of the engineering area shows the stepped roofs, lower ends of the wings and roof plant room.
- The main roof is estimated at 17.6 m above the car park and 24.4 m above the lowest
  ground on the footprint. The clock fins extend about 4.9 m above the main roof.
  The rear facade and less visible wing elevations use an inferred concrete and window pattern.
  The entrance platform sits just above the highest terrain sample under the canopy.
- Viewer renders of the [courtyard and facade](screenshots/places/06_engineering_courtyard.png)
  and the [entrance](screenshots/places/06_engineering_entrance.png).

## 10 · 외국어대학관 — College of Foreign Languages

- The building uses OSM way/585696507. Its entrance faces east, and the two rounded wings follow
  the mapped outline. The front steps rise from a forecourt set to the FABDEM ground level.
- The campus-map photo and close campus-tour frame show the entrance canopy with gold 외국어대학관
  lettering, a glazed vestibule, broad steps, stepped shrub beds and the sheltered side passage.
  The stadium view and side-walkway panoramas show the rounded bands of teal windows, open roof
  balustrades and lower garden arcade. The forecourt paving and garden walkway follow the terrain.
- Four levels are visible on the stadium-facing classroom block. The model's highest roof is
  estimated at 21.4 m above the lowest ground on the footprint, or about 16.3 m above the front
  forecourt. Stair dimensions and the less visible elevations are inferred from the references.
- Viewer renders show the [entrance and stairs](screenshots/places/10_foreign_languages_entrance.png),
  [both rounded wings](screenshots/places/10_foreign_languages_oblique.png) and
  [garden arcade](screenshots/places/10_foreign_languages_garden.png).

## Campus roads, sidewalks, kerbs and crossings (user request, before the outdoor pass)

- **Photos used:** `outdoor/campus-main-road/` (8: *main drive in spring*, *crossroads beside philosophers
  square*, *road 14 philosophers square crossing*, *crossing near dormitories*, *walkway beside sports
  courts*, *paved plaza edge and road*, …).
- **Road widths:** every campus road is `highway=service` in OSM without a width tag, so all used to get
  the 4.5 m default. The new widths are estimated from the photos and labelled so: the gate → 사색의 광장
  boulevard (way/764171420 + way/164635797) is **9.5 m**, two-way campus roads **6.5 m**, one-way roads
  4.5 m, parking aisles 5.5 m. `service=*` is now kept in `roads.geojson`.
- **Sidewalks:** **2.5 m red-brown sidewalks behind a 0.2 m granite kerb on both sides** of every campus
  through-road that is at least 20 m long (64 road sides). A side is skipped where a mapped footway or
  pedestrian area already runs alongside (≥ 40 % of its length within 3.5 m). They are clipped off
  buildings, pitches, water and parking, and cut by crossing roads. Kerbs are 3D (0.15 m upstand, follows
  the DTM; omitted on mobile).
- **Markings:** a double yellow centre line on two-way campus roads. **Zebra crossings** sit at the 24
  points where a mapped footway or path crosses a campus road; OSM has no crossing nodes inside the
  campus.
- **Rendering fix:** see 05. Roads are now metre-width polygons, not pixel-width ground polylines.
- **Estimated / illustrative:** all widths, the sidewalk and kerb layout, the crossing positions and the
  stripe sizes. They are not surveyed.
- **Open questions:** the bronze lamp posts with banners along the boulevard and the hedge strips
  between road and sidewalk are not modelled yet (candidates for the outdoor pass).
- **Screenshots:** before `screenshots/places/roads_drive_before.png`; after
  `screenshots/places/roads_drive.png`, `screenshots/places/roads_junction.png`,
  `screenshots/places/roads_drive2.png`.

**Kerb fix (user report, same day):** the first version drew kerbs as 3D boxes set on the bilinear DTM.
Cesium renders the terrain as triangulated tiles at varying detail, so those boxes floated or stood up
like low walls in places. Kerbs are now **draped 0.2 m granite strips** (ground fill `kerb`), like the
sidewalks. Hedges, planters and net posts are embedded 1.0–1.2 m below the DTM so no gap shows beneath
them.

## 11 · 경희공원 — Kyung Hee Park

- **OSM / position:** **no OSM feature.** The garden lies between 외국어대학관 (way/585696507) and the campus
  road way/1224707679. In the aerial imagery the pagoda's shadow sits exactly on the official map pin
  (37.24538, 127.07689).
- **Photos used:** all 5 in `11-kyung-hee-park/` (four 2017 panoramas and the map view): a garden square of
  brick paths in beige and red bands, dark gravel beds with rocks, a 7-tier stone pagoda inside clipped
  hedges, a stone turtle (귀부), a wisteria pergola, benches, and a road entrance with a black ring
  sculpture and an inscribed stone.
- **Modelled:** the **7-tier stone pagoda** (two-stage podium, body stones, thin roof stones, finial;
  ≈ 5.4 m) at the map pin, with a **square ring of clipped hedge blocks**, gapped on the path axes and
  aligned with the adjacent road. It is a ground object `pagoda` (`PIN_LANDMARKS` in `build_ground.py`)
  labelled with an approximate position.
- **Not modelled, by rule:** the paved and gravel layout, the pergola, the turtle and the entrance
  sculpture. They have no OSM geometry, and geometry is never traced from imagery here. The area still
  renders as canopy floor.
- **Open question for the user:** if you add the garden outline (and ideally the paths) to OSM, or give me
  permission to digitise it as an *estimated* outline from the photos and the map pin, I can lay the
  brick, gravel and pergola on it.
- **Screenshots:** before `screenshots/places/11_kyunghee_park_before.png`; after
  `screenshots/places/11_kyunghee_park_pagoda.png`, `screenshots/places/11_kyunghee_park_aerial.png`.

## 14 · 대운동장 — Grand Stadium

- **OSM / position:** stadium way/455725379 (leisure=stadium, 188 × 111 m oval, 18,616 m²). There are no
  inner OSM features. The map pin (37.24378, 127.07780) is at the oval's centroid.
- **Photos used:** all 13 in `14-grand-stadium/` (2017 panoramas, 2021–2025 photos, video frames). The newest
  (Aug 2025) show a **natural-grass field inside an oval sand track**, a low green field fence, and **grey
  concrete terrace steps all round**, with a road ring and parking above. The user confirmed that the grey
  ring is steps going **down**: the stadium lies below the surrounding road.
- **New: local terrain conditioning** (`web/data/terrain/terrain_mods.json`, applied in `DemGrid.heightOrtho`
  in `terrain.js`; `dtm.bin` is unchanged). The 30 m FABDEM smooths the bowl away, so the viewer carves it
  inside the OSM outline:
  - a 3 m retaining slope from the original ground;
  - **10 steps × 0.4 m** (0.9 m treads) down to a **level field at 57.32 m**. That is the lowest rim
    level (10th percentile of the DTM along the outline, 61.32 m) minus the stand height.
  The carve only ever lowers the DTM. Every draped surface, ground object and the walk camera follows it,
  because they all use the same height function.
- **Ground:** terrace ring (concrete grey, a step line on every tread edge), **sand track 9 m**, grass field.
  A **1.2 m green field fence**, a 1.1 m railing at the top of the steps and **two goals** (7.32 × 2.44 m)
  on the long axis.
- **Estimated:** the field level, step count, rise and tread, track width, fence heights. All are labelled
  estimated in `terrain_mods.json`. The Python validation still reports the raw FABDEM.
- **Open questions:** the white prefab shed, the brick-faced retaining wall on the north side, the
  floodlight poles and the cars parked on the south track band are not modelled. The south end may open
  onto the parking at near-field level; the model keeps steps all round.
- **Screenshots:** before `screenshots/places/14_grand_stadium_top_before.png`; after
  `screenshots/places/14_grand_stadium_aerial.png`, `screenshots/places/14_grand_stadium_top.png`,
  `screenshots/places/14_grand_stadium_ground.png`.

## 31 · 전자정보/응용과학대학관 — College of Electronics Information and Applied Science

- The outer outline follows OSM way/474085540. The main entrance faces north, as shown by the
  geolocated panorama in the [Look360 campus tour](https://look360.kr/vr/khu2_univ/khu2_univ).
  An [Esri aerial image](https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer)
  shows the open courtyard, taller brick wings, and lower uphill annex.
- The campus-map photograph shows five levels and 19 window bays across the north elevation.
  The two saved close panoramas show the flared front canopy, broad steps and planted retaining
  beds, plus the courtyard's glazed stair tower and the curved hood near the rear doors.
- The main roof slab is estimated at 22.5 m above the footprint's lowest FABDEM point, or 19.2 m
  above the entrance apron. The model also estimates the courtyard bounds, rear wing heights, and
  steps. The viewer levels the asphalt apron and brick courtyard locally, blending both into FABDEM
  past their edges.
- Viewer renders show the [entrance](screenshots/places/31_electronics_entrance.png),
  [courtyard](screenshots/places/31_electronics_courtyard.png), and
  [roof and wing layout](screenshots/places/31_electronics_oblique.png).

## 04 (ground only) · 우정원 site — levelled below the main road (user report)

- **User report:** 우정원 and its parking lots lie **lower than the main road**, with a slope down from the
  road. The photo *front from across the road* agrees (parking and entrance well below the road).
- **Terrain conditioning moved into one shared module, `scripts/terrain_mods.py`:**
  - it writes `web/data/terrain/terrain_mods.json`;
  - `dem.load()` now returns the **conditioned** DTM, so building ground levels, trees and ground objects
    in the pipeline match the viewer; `dem.load(raw=True)` returns the untouched FABDEM, and
    `validate.py` uses it;
  - `DemGrid.heightOrtho()` applies the same mods in the browser.
  The stadium bowl (14) now comes from here too.
- **New `platform` mod "woojungwon":** the OSM footprint of 우정원 (relation/8269760) plus parking
  way/829334051 and way/1365659109, padded 3 m. The level is **59.05 m**, the 10th percentile of the DTM
  over that region (the main road beside it is ≈ 68 m on the DTM). Outside the region a **1:4 cut slope**
  rises back to the original ground. It only ever lowers the DTM.
- **Merged with the other session's per-model `level` mods:** `terrain_mods.py` writes `base`, and
  `build_ground.py` appends the per-model `level` mods to `mods`.
- **Effect:** 우정원 now stands on 58.5–59.05 m (it spanned 58.5–65.8 m), and its parking sits below the
  road.
- **Estimated:** the level, the slope ratio and the region extent.
- **Screenshot:** `screenshots/places/04_woojungwon_terrain_before_after.jpg` (left before, right after).

## 04 · 우정원 — Woojungwon Dormitory

- The model follows OSM relation/8269760, including both mapped courtyard openings. The east
  entrance faces the parking deck below the campus road. The open courts have paved margins and
  planted centres based on the aerial views.
- The east elevation uses the campus-map photo, the car park panorama, and the campus-tour
  frames. It has twin curved glass towers, six rows of narrow room windows above a glazed
  ground floor, and a sage-green pediment above the signed teal canopy. The stairs rise
  from the existing Woojungwon platform.
- [Kyung Hee University](https://ile.khu.ac.kr/ile_kor/user/contents/view.do?menuNo=5900026)
  documents seven above-ground floors. The modeled main roof is estimated at 23.8 m above the
  parking deck. Tower caps, rooftop equipment, and the less visible elevations are approximate.
- Viewer renders show the [east façade](screenshots/places/04_woojungwon_facade.png),
  [entrance canopy](screenshots/places/04_woojungwon_entrance.png), and
  [both courtyards](screenshots/places/04_woojungwon_courtyards.png).

## Site-wide changes made in this session (user requests)

- **UI (Kyung Hee style):** split layout. On the left, a UI column with a crimson masthead (gold rule)
  and a section rail (Campus / Buildings / Terrain / Layers); the building details open in the same column. On
  the right, the 3D viewer with a toolbar strip underneath. Nothing floats over the 3D. Phones get the viewer
  on top and the UI below.
- **Names:** every campus-map place has an English name (`name_en` in `khu_official_campus_map.json`,
  descriptive translations labelled as such). 3D labels show Korean on top and English below (English only
  within 900 m).
- **Default view:** opens on the main gate from the street side, looking into the campus. "Whole campus"
  in the toolbar flies to the overview.
- **Clean start:** building names, icons and the boundary line are off by default (Layers tab to switch
  them on).
- **Light mode (default) and load time:** no shadows or MSAA, coarser terrain tiles, vegetation off until
  switched on. "Full detail" in the toolbar switches modes (stored, reloads). Measured cold load: transfer
  **7.2 MB → 3.9 MB** and main-thread blocking **7.2 s → 3.6 s**. Changes:
  - campus-only data subsets (`build_web_subset.py`: buildings 916 → 45 KB, roads 425 → 62 KB, trees
    17,954 → 2,634);
  - the slope overlay loads on demand;
  - the overlays are 1024 px instead of 2048 (the DTM is 30 m), and now include the terrain conditioning;
  - trees are built in chunks after first paint;
  - the facade and ground-object meshes compile in Cesium workers.
  The remaining cost is mostly Cesium itself (1 MB) and WebGL shader compiling, about 0.9 s for each of the
  two variants of the big facade material shader.
