// Minimal binary glTF 2.0 (GLB) writer: a node tree where every item is its own node + mesh.
// Coordinates are local metres, glTF convention (+Y up, +X east, -Z north), see glb_export.js.

const ALIGN = 4;
const pad = (n) => (n + ALIGN - 1) & ~(ALIGN - 1);

export class GlbBuilder {
  constructor() {
    this.nodes = [];
    this.meshes = [];
    this.materials = [];
    this.accessors = [];
    this.bufferViews = [];
    this.chunks = [];      // [Uint8Array, byteOffset]
    this.byteLength = 0;
    this.materialIndex = new Map();
    this.roots = [];
  }

  /** A shared material: { name, color:[r,g,b,a], alpha:"OPAQUE"|"BLEND", doubleSided, metallic, roughness }. */
  material(key, def) {
    if (this.materialIndex.has(key)) return this.materialIndex.get(key);
    const m = {
      name: def.name ?? key,
      pbrMetallicRoughness: { baseColorFactor: def.color ?? [1, 1, 1, 1], metallicFactor: def.metallic ?? 0, roughnessFactor: def.roughness ?? 0.9 },
      doubleSided: def.doubleSided ?? true,
    };
    if (def.alpha === "BLEND") m.alphaMode = "BLEND";
    this.materials.push(m);
    this.materialIndex.set(key, this.materials.length - 1);
    return this.materials.length - 1;
  }

  _view(typed, target) {
    const bytes = new Uint8Array(typed.buffer, typed.byteOffset, typed.byteLength);
    const off = this.byteLength;
    this.chunks.push([bytes, off]);
    this.byteLength = pad(off + bytes.byteLength);
    const v = { buffer: 0, byteOffset: off, byteLength: bytes.byteLength };
    if (target) v.target = target;
    this.bufferViews.push(v);
    return this.bufferViews.length - 1;
  }

  _accessor(typed, type, componentType, count, extra = {}) {
    const target = type === "SCALAR" ? 34963 : 34962;
    this.accessors.push({ bufferView: this._view(typed, target), componentType, count, type, ...extra });
    return this.accessors.length - 1;
  }

  /**
   * mesh: { positions: Float32Array (xyz), normals?: Float32Array, colors?: Uint8Array (rgba), indices: Uint16/32Array }
   * Returns the mesh index, or -1 if empty.
   */
  addMesh(name, mesh, material) {
    const n = mesh.positions.length / 3;
    if (!n || !mesh.indices.length) return -1;
    const p = mesh.positions;
    const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
    for (let i = 0; i < p.length; i += 3) for (let k = 0; k < 3; k++) {
      const v = p[i + k]; if (v < min[k]) min[k] = v; if (v > max[k]) max[k] = v;
    }
    const attributes = { POSITION: this._accessor(p, "VEC3", 5126, n, { min, max }) };
    if (mesh.normals) attributes.NORMAL = this._accessor(mesh.normals, "VEC3", 5126, n);
    if (mesh.colors) attributes.COLOR_0 = this._accessor(mesh.colors, "VEC4", 5121, n, { normalized: true });
    const idx = n > 65535 ? (mesh.indices instanceof Uint32Array ? mesh.indices : Uint32Array.from(mesh.indices))
      : (mesh.indices instanceof Uint16Array ? mesh.indices : Uint16Array.from(mesh.indices));
    const indices = this._accessor(idx, "SCALAR", idx instanceof Uint32Array ? 5125 : 5123, idx.length);
    this.meshes.push({ name, primitives: [{ attributes, indices, material, mode: 4 }] });
    return this.meshes.length - 1;
  }

  /** Adds a node under `parent` (node index) or as a scene root; returns the node index. */
  addNode(name, { parent = null, mesh = -1, extras, translation } = {}) {
    const node = { name };
    if (mesh >= 0) node.mesh = mesh;
    if (extras) node.extras = extras;
    if (translation) node.translation = translation;
    this.nodes.push(node);
    const i = this.nodes.length - 1;
    if (parent == null) this.roots.push(i);
    else (this.nodes[parent].children ??= []).push(i);
    return i;
  }

  toBlob(assetExtras) {
    const json = {
      asset: { version: "2.0", generator: "KHU Global Campus twin (web/js/glb_export.js)", extras: assetExtras },
      scene: 0, scenes: [{ name: "KHU Global Campus", nodes: this.roots }],
      nodes: this.nodes, meshes: this.meshes, materials: this.materials,
      accessors: this.accessors, bufferViews: this.bufferViews,
      buffers: [{ byteLength: this.byteLength }],
    };
    let jsonBytes = new TextEncoder().encode(JSON.stringify(json));
    const jsonLen = pad(jsonBytes.length);
    const total = 12 + 8 + jsonLen + 8 + this.byteLength;
    const out = new Uint8Array(total);
    const dv = new DataView(out.buffer);
    dv.setUint32(0, 0x46546c67, true); dv.setUint32(4, 2, true); dv.setUint32(8, total, true);
    dv.setUint32(12, jsonLen, true); dv.setUint32(16, 0x4e4f534a, true);
    out.set(jsonBytes, 20);
    for (let i = 20 + jsonBytes.length; i < 20 + jsonLen; i++) out[i] = 0x20;   // JSON padded with spaces
    const b0 = 20 + jsonLen;
    dv.setUint32(b0, this.byteLength, true); dv.setUint32(b0 + 4, 0x004e4942, true);
    for (const [bytes, off] of this.chunks) out.set(bytes, b0 + 8 + off);
    jsonBytes = null;
    return new Blob([out], { type: "model/gltf-binary" });
  }
}
