// Runtime configuration. Everything here is public: never put private credentials in this file.
export const CONFIG = {
  campusCenter: { lon: 127.0818, lat: 37.2427 },
  // initial oblique aerial view of the entire campus
  home: { heading: 18, pitch: -36, range: 1650, radius: 640 },

  // Optional VWorld (https://www.vworld.kr) WMTS key. VWorld keys are issued per domain:
  // register https://USERNAME.github.io as the service URL when requesting the key.
  // Leave empty to disable; users can also paste a key at runtime (stored only in their browser).
  vworldKey: "",

  imagery: {
    esri: {
      label: "Esri World Imagery (aerial)",
      url: "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      maximumLevel: 19,
      credit: "Imagery © Esri, Maxar, Earthstar Geographics, and the GIS User Community",
    },
    s2: {
      label: "Sentinel-2 cloudless 2023 (10 m, EOX)",
      url: "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/default/g/{z}/{y}/{x}.jpg",
      maximumLevel: 15,
      credit: "Sentinel-2 cloudless 2023 by EOX IT Services GmbH (CC BY-NC-SA 4.0; contains modified Copernicus Sentinel data 2023)",
    },
    osm: {
      label: "OpenStreetMap (map)",
      url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      maximumLevel: 19,
      credit: "© OpenStreetMap contributors (ODbL)",
    },
    vworld: {
      label: "VWorld Satellite (needs key)",
      url: "https://api.vworld.kr/req/wmts/1.0.0/{key}/Satellite/{z}/{y}/{x}.jpeg",
      maximumLevel: 19,
      credit: "© VWorld / 국토교통부 공간정보 오픈플랫폼",
    },
  },
};

export const isMobile = matchMedia("(pointer: coarse)").matches || Math.min(innerWidth, innerHeight) < 600;
