// Camera modes: orbit, pan/zoom, first-person walk, free fly, top-down, terrain-following,
// reset-to-campus and focus-on-building. The camera is never allowed below the DTM surface.
const Cesium = window.Cesium;
const { Math: CMath, Cartesian3, Cartographic, HeadingPitchRange, BoundingSphere } = Cesium;

export const MODES = {
  orbit: "Orbit", pan: "Pan / zoom", walk: "First-person walk", fly: "Fly-through",
  follow: "Terrain-following", top: "Top-down",
};

export class CameraController {
  constructor(viewer, dem, layers, home, onMode = () => {}, { bounds = null, walkStart = null } = {}) {
    this.viewer = viewer;
    this.scene = viewer.scene;
    this.camera = viewer.camera;
    this.ssc = viewer.scene.screenSpaceCameraController;
    this.dem = dem;
    this.layers = layers;
    this.home = home;
    this.onMode = onMode;
    this.mode = "orbit";
    this.bounds = bounds;       // {west,south,east,north}: the diorama the camera must stay over
    this.walkStart = walkStart; // {lon,lat,heading}: main gate approach
    this.keys = new Set();
    this.speed = { walk: 1.6, fly: 40, follow: 30 };
    this.followAGL = 60;
    this.eye = 1.7;
    this.lastT = performance.now();
    this.look = { dx: 0, dy: 0 };
    this.homeSphere = new BoundingSphere(
      Cartesian3.fromDegrees(home.lon, home.lat, dem.heightEllipsoid(home.lon, home.lat)), home.radius);

    this.ssc.minimumZoomDistance = 3;
    this.ssc.maximumZoomDistance = 7000;
    this.ssc.enableCollisionDetection = true;

    const canvas = viewer.canvas;
    canvas.setAttribute("tabindex", "0");
    addEventListener("keydown", (e) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
      this.keys.add(e.code);
      if (this.isFree() && ["Space", "ArrowUp", "ArrowDown"].includes(e.code)) e.preventDefault();
      if (e.code === "Escape" && this.isFree()) this.setMode("orbit");
    });
    addEventListener("keyup", (e) => this.keys.delete(e.code));
    addEventListener("blur", () => this.keys.clear());
    canvas.addEventListener("click", () => {
      if (this.isFree() && document.pointerLockElement !== canvas) canvas.requestPointerLock?.();
    });
    document.addEventListener("mousemove", (e) => {
      if (this.isFree() && document.pointerLockElement === canvas) {
        this.look.dx += e.movementX; this.look.dy += e.movementY;
      }
    });
    // drag-to-look fallback (touch / no pointer lock)
    let drag = null;
    canvas.addEventListener("pointerdown", (e) => { if (this.isFree() && document.pointerLockElement !== canvas) drag = { x: e.clientX, y: e.clientY }; });
    addEventListener("pointerup", () => { drag = null; });
    addEventListener("pointermove", (e) => {
      if (drag && this.isFree()) { this.look.dx += e.clientX - drag.x; this.look.dy += e.clientY - drag.y; drag = { x: e.clientX, y: e.clientY }; }
    });
    canvas.addEventListener("wheel", (e) => {
      if (!this.isFree()) return;
      e.preventDefault();
      const f = e.deltaY < 0 ? 1.2 : 1 / 1.2;
      if (this.mode === "walk") this.speed.walk = CMath.clamp(this.speed.walk * f, 0.5, 15);
      else if (this.mode === "follow" && e.shiftKey) this.followAGL = CMath.clamp(this.followAGL * f, 5, 600);
      else this.speed[this.mode] = CMath.clamp(this.speed[this.mode] * f, 2, 600);
      this.onMode(this.mode, this.status());
    }, { passive: false });

    this.scene.preRender.addEventListener(() => this.tick());
  }

  isFree() { return this.mode === "walk" || this.mode === "fly" || this.mode === "follow"; }

  /** inside the diorama rectangle grown (or shrunk, if negative) by margin metres */
  inBounds(lon, lat, margin = 0) {
    const b = this.bounds;
    if (!b) return true;
    const mx = margin / (111320 * Math.cos(lat * Math.PI / 180)), my = margin / 110950;
    return lon >= b.west - mx && lon <= b.east + mx && lat >= b.south - my && lat <= b.north + my;
  }

  clampToBounds(lon, lat, margin) {
    const b = this.bounds;
    if (!b) return [lon, lat];
    const mx = margin / (111320 * Math.cos(lat * Math.PI / 180)), my = margin / 110950;
    return [CMath.clamp(lon, b.west - mx, b.east + mx), CMath.clamp(lat, b.south - my, b.north + my)];
  }

  groundEll(lon, lat) {
    if (this.dem.contains(lon, lat)) return this.dem.heightEllipsoid(lon, lat);
    const g = this.scene.globe.getHeight(Cartographic.fromDegrees(lon, lat));
    return g ?? this.dem.heightEllipsoid(lon, lat);
  }

  setInputs(enabled, { tiltLeft = false } = {}) {
    const s = this.ssc;
    s.enableInputs = enabled;
    const E = Cesium.CameraEventType, M = Cesium.KeyboardEventModifier;
    if (tiltLeft) {
      s.rotateEventTypes = [E.RIGHT_DRAG, { eventType: E.LEFT_DRAG, modifier: M.SHIFT }];
      s.tiltEventTypes = [E.LEFT_DRAG, E.PINCH, { eventType: E.LEFT_DRAG, modifier: M.CTRL }];
      s.zoomEventTypes = [E.WHEEL, E.PINCH, E.MIDDLE_DRAG];
    } else {
      s.rotateEventTypes = E.LEFT_DRAG;
      s.tiltEventTypes = [E.MIDDLE_DRAG, E.PINCH, { eventType: E.LEFT_DRAG, modifier: M.CTRL }, { eventType: E.RIGHT_DRAG, modifier: M.CTRL }];
      s.zoomEventTypes = [E.RIGHT_DRAG, E.WHEEL, E.PINCH];
    }
  }

  setMode(mode) {
    const prev = this.mode;
    this.mode = mode;
    this.flying = false;
    if (document.pointerLockElement && !this.isFree()) document.exitPointerLock?.();
    this.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
    this.ssc.enableTilt = true;
    if (mode === "orbit") this.setInputs(true, { tiltLeft: true });
    else if (mode === "pan") this.setInputs(true);
    else if (mode === "top") {
      this.setInputs(true);
      this.ssc.enableTilt = false;
      this.topDown();
    } else {
      this.setInputs(false);
      const c = this.camera.positionCartographic;
      const lon = CMath.toDegrees(c.longitude), lat = CMath.toDegrees(c.latitude);
      if (mode === "walk") {
        // close to the ground: drop where the camera looks; otherwise start at the main gate
        const agl = c.height - this.groundEll(lon, lat);
        let target = agl < 400 ? this.pickCenterGround() : null;
        let heading = this.camera.heading;
        if (target && this.bounds && !this.inBounds(CMath.toDegrees(target.longitude), CMath.toDegrees(target.latitude), -30)) target = null;
        if (!target && this.walkStart) {
          target = Cartographic.fromDegrees(this.walkStart.lon, this.walkStart.lat);
          heading = this.walkStart.heading;
        }
        target ??= Cartographic.fromDegrees(this.home.lon, this.home.lat);
        const tl = CMath.toDegrees(target.longitude), tt = CMath.toDegrees(target.latitude);
        const h = this.groundEll(tl, tt) + this.eye;
        this.camera.flyTo({
          destination: Cartesian3.fromDegrees(tl, tt, h),
          orientation: { heading, pitch: CMath.toRadians(2), roll: 0 }, duration: 2.2,
          complete: () => { this.flying = false; }, cancel: () => { this.flying = false; },
        });
        this.flying = true;
      } else if (mode === "follow") {
        const agl = c.height - this.groundEll(lon, lat);
        this.followAGL = CMath.clamp(agl, 15, 400);
        this.camera.setView({ orientation: { heading: this.camera.heading, pitch: CMath.toRadians(-12), roll: 0 } });
      } else if (mode === "fly" && prev === "walk") {
        this.camera.setView({ orientation: { heading: this.camera.heading, pitch: this.camera.pitch, roll: 0 } });
      }
    }
    this.onMode(mode, this.status());
  }

  status() {
    if (this.mode === "walk") return `Walk ${this.speed.walk.toFixed(1)} m/s · WASD move · mouse look · Shift run · wheel speed · Esc exit`;
    if (this.mode === "fly") return `Fly ${this.speed.fly.toFixed(0)} m/s · WASD move · Q/E down/up · mouse look · wheel speed · Esc exit`;
    if (this.mode === "follow") return `Terrain-following ${this.followAGL.toFixed(0)} m AGL · WASD · Q/E or Shift+wheel altitude · Esc exit`;
    if (this.mode === "orbit") return "Orbit: left-drag rotate around view centre · right/Shift-drag pan · wheel zoom";
    if (this.mode === "pan") return "Pan/zoom: left-drag pan · right-drag or wheel zoom · Ctrl/middle-drag tilt";
    if (this.mode === "top") return "Top-down (north up): drag to pan · wheel zoom";
    return "";
  }

  pickCenterGround() {
    const c = this.viewer.canvas;
    const ray = this.camera.getPickRay(new Cesium.Cartesian2(c.clientWidth / 2, c.clientHeight / 2));
    const p = ray && this.scene.globe.pick(ray, this.scene);
    return p ? Cartographic.fromCartesian(p) : null;
  }

  flyHome(duration = 2.2) {
    if (this.isFree()) this.setMode("orbit");
    const h = this.home;
    this.camera.flyToBoundingSphere(this.homeSphere, {
      offset: new HeadingPitchRange(CMath.toRadians(h.heading), CMath.toRadians(h.pitch), h.range), duration,
    });
  }

  topDown() {
    const h = this.home;
    const g = this.dem.heightEllipsoid(h.lon, h.lat);
    this.camera.flyTo({
      destination: Cartesian3.fromDegrees(h.lon, h.lat, g + 2600),
      orientation: { heading: 0, pitch: CMath.toRadians(-90), roll: 0 }, duration: 2,
    });
  }

  focusBuilding(rec) {
    if (this.isFree()) this.setMode("orbit");
    const r = Math.max(120, rec.sphere.radius * 3.2);
    const heading = rec.focusHeading == null ? this.camera.heading : CMath.toRadians(rec.focusHeading);
    this.camera.flyToBoundingSphere(rec.sphere, {
      offset: new HeadingPitchRange(heading, CMath.toRadians(-32), r), duration: 1.8,
    });
  }

  tick() {
    const now = performance.now();
    const dt = Math.min(0.1, (now - this.lastT) / 1000);
    this.lastT = now;
    const cam = this.camera;
    if (this.isFree() && !this.flying) {
      const k = this.keys;
      // look
      const sens = 0.0022;
      if (this.look.dx || this.look.dy) {
        const heading = cam.heading + this.look.dx * sens;
        const pitch = CMath.clamp(cam.pitch - this.look.dy * sens, CMath.toRadians(-89), CMath.toRadians(89));
        cam.setView({ orientation: { heading, pitch, roll: 0 } });
        this.look.dx = this.look.dy = 0;
      }
      if (k.has("ArrowLeft")) cam.setView({ orientation: { heading: cam.heading - 1.2 * dt, pitch: cam.pitch, roll: 0 } });
      if (k.has("ArrowRight")) cam.setView({ orientation: { heading: cam.heading + 1.2 * dt, pitch: cam.pitch, roll: 0 } });
      const fwd = (k.has("KeyW") || k.has("ArrowUp") ? 1 : 0) - (k.has("KeyS") || k.has("ArrowDown") ? 1 : 0);
      const side = (k.has("KeyD") ? 1 : 0) - (k.has("KeyA") ? 1 : 0);
      const up = (k.has("KeyE") || k.has("Space") ? 1 : 0) - (k.has("KeyQ") ? 1 : 0);
      const run = k.has("ShiftLeft") || k.has("ShiftRight") ? 3.5 : 1;
      const carto = cam.positionCartographic;
      let lon = CMath.toDegrees(carto.longitude), lat = CMath.toDegrees(carto.latitude), h = carto.height;
      const hd = cam.heading;
      const mLat = 1 / 110950, mLon = 1 / (111320 * Math.cos(carto.latitude));
      if (this.mode === "walk" || this.mode === "follow") {
        const v = (this.mode === "walk" ? this.speed.walk : this.speed.follow) * run * dt;
        const de = (Math.sin(hd) * fwd + Math.cos(hd) * side) * v;
        const dn = (Math.cos(hd) * fwd - Math.sin(hd) * side) * v;
        let nlon = lon + de * mLon, nlat = lat + dn * mLat;
        if (this.mode === "walk" && this.layers.insideBuilding(nlon, nlat) && !this.layers.insideBuilding(lon, lat)) {
          nlon = lon; nlat = lat; // building footprints block walking
        }
        [lon, lat] = this.clampToBounds(nlon, nlat, -3); // stay on the diorama
        if (this.mode === "follow") {
          this.followAGL = CMath.clamp(this.followAGL + up * 40 * dt * run, 5, 800);
          const target = this.groundEll(lon, lat) + this.followAGL;
          h = h + (target - h) * Math.min(1, dt * 4);
        } else {
          h = this.groundEll(lon, lat) + this.eye;
        }
        if (fwd || side || up || this.mode === "walk") cam.setView({ destination: Cartesian3.fromDegrees(lon, lat, h), orientation: { heading: cam.heading, pitch: cam.pitch, roll: 0 } });
      } else if (this.mode === "fly") {
        const v = this.speed.fly * run * dt;
        const move = new Cartesian3();
        if (fwd) Cartesian3.add(move, Cartesian3.multiplyByScalar(cam.direction, fwd * v, new Cartesian3()), move);
        if (side) Cartesian3.add(move, Cartesian3.multiplyByScalar(cam.right, side * v, new Cartesian3()), move);
        if (up) Cartesian3.add(move, Cartesian3.multiplyByScalar(Cesium.Ellipsoid.WGS84.geodeticSurfaceNormal(cam.position, new Cartesian3()), up * v, new Cartesian3()), move);
        if (fwd || side || up) cam.position = Cartesian3.add(cam.position, move, new Cartesian3());
      }
    }
    // never below terrain, never far away from the diorama (all modes)
    const c = cam.positionCartographic;
    let lon = CMath.toDegrees(c.longitude), lat = CMath.toDegrees(c.latitude);
    const g = this.groundEll(lon, lat);
    const minH = g + (this.mode === "walk" ? this.eye : 2.0);
    const margin = this.isFree() ? -3 : 2500;
    const out = !this.inBounds(lon, lat, margin);
    if (out) [lon, lat] = this.clampToBounds(lon, lat, margin);
    const maxH = g + 7000;
    if ((c.height < minH - 0.01 && this.mode !== "walk") || out || c.height > maxH) {
      const hh = CMath.clamp(c.height, minH, maxH);
      cam.setView({ destination: Cartesian3.fromDegrees(lon, lat, hh), orientation: { heading: cam.heading, pitch: cam.pitch, roll: cam.roll } });
    }
  }
}
