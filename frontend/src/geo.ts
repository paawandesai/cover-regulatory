// Small planar helpers for drawing a parcel in feet. Accurate enough for a lot-sized diagram; the
// backend does the real work in EPSG:2229.

type Ring = [number, number][]

export function rings(g: GeoJSON.Polygon | GeoJSON.MultiPolygon): Ring[] {
  const polys = g.type === 'Polygon' ? [g.coordinates] : g.coordinates
  return polys.map((p) => p[0] as Ring)
}

const FT_PER_M = 3.28084

/** Project lon/lat to feet around an origin, then rotate by `angle` radians. y grows northwards. */
export function toLocal(origin: [number, number], angle = 0) {
  const k = Math.cos((origin[1] * Math.PI) / 180)
  const cos = Math.cos(angle)
  const sin = Math.sin(angle)
  return ([lng, lat]: [number, number] | number[]): [number, number] => {
    const x = (lng - origin[0]) * k * 111320 * FT_PER_M
    const y = (lat - origin[1]) * 110540 * FT_PER_M
    return [x * cos - y * sin, x * sin + y * cos]
  }
}

export function centroid(r: Ring): [number, number] {
  const pts = r.slice(0, -1)
  const s = pts.reduce((a, p) => [a[0] + p[0], a[1] + p[1]], [0, 0])
  return [s[0] / pts.length, s[1] / pts.length]
}

export function bounds(rs: Ring[]): [number, number, number, number] {
  const xs = rs.flat().map((p) => p[0])
  const ys = rs.flat().map((p) => p[1])
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)]
}
