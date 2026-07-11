import type { SVGProps } from "react";

export function Mesh2ParamLogoMark({ title = "", ...props }: SVGProps<SVGSVGElement> & { title?: string }) {
  const titleId = title ? "mesh2param-mark-title" : undefined;
  return (
    <svg viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="1.45" strokeLinecap="round" strokeLinejoin="round" role={title ? "img" : undefined} aria-labelledby={titleId} aria-hidden={title ? undefined : true} {...props}>
      {title ? <title id={titleId}>{title}</title> : null}
      <path d="M20 2.8 35 11.4v17.2L20 37.2 5 28.6V11.4L20 2.8Z" />
      <path d="m5 11.4 15 8.7 15-8.7M20 20.1v17.1M5 28.6l15-8.5 15 8.5" opacity=".9" />
      <path d="m5 11.4 8.2 4.7L20 2.8m0 17.3-6.8-4v8l6.8 4m0-8 7.4-4.3v8.5L20 28.6" opacity=".7" />
      <path d="m13.2 16.1 6.8 4-6.8 4 6.8 4 7.4-4.3M20 2.8v17.3l7.4 4.2" opacity=".55" />
      <circle cx="20" cy="20.1" r="2.7" fill="var(--color-bg)" />
    </svg>
  );
}

// ---- Hero geometry: a raw triangulated mesh shell transitioning to a clean parametric solid ----
type HeroPt = [number, number];
const HERO_AX: HeroPt = [26, 13];
const HERO_AY: HeroPt = [-26, 13];
const HERO_AZ: HeroPt = [0, -32];
const HERO_W = 2.6;
const HERO_D = 2.0;
const HERO_H = 1.7;

function heroProject(o: HeroPt, x: number, y: number, z: number): HeroPt {
  return [o[0] + x * HERO_AX[0] + y * HERO_AY[0] + z * HERO_AZ[0], o[1] + x * HERO_AX[1] + y * HERO_AY[1] + z * HERO_AZ[1]];
}
function heroRand(index: number, seed: number): number {
  const value = Math.sin((index + seed) * 127.1) * 43758.5453;
  return value - Math.floor(value);
}
function heroPoints(pts: HeroPt[]): string {
  return pts.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
}

interface HeroFace {
  base: [number, number, number];
  du: [number, number, number];
  dv: [number, number, number];
  nu: number;
  nv: number;
}
const HERO_FACES: HeroFace[] = [
  { base: [0, 0, HERO_H], du: [HERO_W, 0, 0], dv: [0, HERO_D, 0], nu: 5, nv: 4 },
  { base: [0, HERO_D, 0], du: [HERO_W, 0, 0], dv: [0, 0, HERO_H], nu: 5, nv: 4 },
  { base: [HERO_W, 0, 0], du: [0, HERO_D, 0], dv: [0, 0, HERO_H], nu: 4, nv: 4 },
];

// Deduplicated triangle edges of one jittered face grid — the "raw scan" look.
function heroFaceEdges(o: HeroPt, face: HeroFace, jitter: number, seed: number): Array<[HeroPt, HeroPt]> {
  const verts: HeroPt[] = [];
  for (let j = 0; j <= face.nv; j += 1) {
    for (let i = 0; i <= face.nu; i += 1) {
      let u = i / face.nu;
      let v = j / face.nv;
      const k = j * (face.nu + 1) + i;
      if (i > 0 && i < face.nu && j > 0 && j < face.nv) {
        u += ((heroRand(k, seed) - 0.5) * jitter) / face.nu;
        v += ((heroRand(k + 91, seed) - 0.5) * jitter) / face.nv;
      }
      verts.push(heroProject(o,
        face.base[0] + u * face.du[0] + v * face.dv[0],
        face.base[1] + u * face.du[1] + v * face.dv[1],
        face.base[2] + u * face.du[2] + v * face.dv[2]));
    }
  }
  const edges = new Set<string>();
  const add = (a: number, b: number) => edges.add(a < b ? `${a}-${b}` : `${b}-${a}`);
  for (let j = 0; j < face.nv; j += 1) {
    for (let i = 0; i < face.nu; i += 1) {
      const a = j * (face.nu + 1) + i;
      const b = a + 1;
      const c = a + face.nu + 1;
      const d = c + 1;
      if ((i + j) % 2 === 0) { add(a, b); add(b, d); add(d, a); add(d, c); add(c, a); }
      else { add(a, b); add(b, c); add(c, a); add(b, d); add(d, c); }
    }
  }
  return [...edges].map((edge) => {
    const parts = edge.split("-").map(Number);
    return [verts[parts[0]!]!, verts[parts[1]!]!] as [HeroPt, HeroPt];
  });
}

// Visible outline of the block (top ring, dropping verticals, bottom-front edges).
function heroOutline(o: HeroPt): HeroPt[][] {
  const p = (x: number, y: number, z: number) => heroProject(o, x, y, z);
  return [
    [p(0, 0, HERO_H), p(HERO_W, 0, HERO_H), p(HERO_W, HERO_D, HERO_H), p(0, HERO_D, HERO_H), p(0, 0, HERO_H)],
    [p(HERO_W, 0, HERO_H), p(HERO_W, 0, 0)],
    [p(HERO_W, HERO_D, HERO_H), p(HERO_W, HERO_D, 0)],
    [p(0, HERO_D, HERO_H), p(0, HERO_D, 0)],
    [p(HERO_W, 0, 0), p(HERO_W, HERO_D, 0), p(0, HERO_D, 0)],
  ];
}
function heroSolidFaces(o: HeroPt): Array<{ points: HeroPt[]; fill: string }> {
  const p = (x: number, y: number, z: number) => heroProject(o, x, y, z);
  return [
    { points: [p(0, 0, HERO_H), p(HERO_W, 0, HERO_H), p(HERO_W, HERO_D, HERO_H), p(0, HERO_D, HERO_H)], fill: "rgba(126,180,255,.06)" },
    { points: [p(HERO_W, 0, 0), p(HERO_W, HERO_D, 0), p(HERO_W, HERO_D, HERO_H), p(HERO_W, 0, HERO_H)], fill: "rgba(126,180,255,.035)" },
    { points: [p(0, HERO_D, 0), p(HERO_W, HERO_D, 0), p(HERO_W, HERO_D, HERO_H), p(0, HERO_D, HERO_H)], fill: "url(#hero-sheen)" },
  ];
}
// Projected through-hole on the front face (y = D) as a transformed unit circle.
function heroHoleTransform(o: HeroPt, cx: number, cz: number, r: number): string {
  const center = heroProject(o, cx, HERO_D, cz);
  const screen = (vx: number, vy: number, vz: number): HeroPt => [vx * HERO_AX[0] + vy * HERO_AY[0] + vz * HERO_AZ[0], vx * HERO_AX[1] + vy * HERO_AY[1] + vz * HERO_AZ[1]];
  const u = screen(1, 0, 0);
  const v = screen(0, 0, 1);
  return `matrix(${r * u[0]},${r * u[1]},${r * v[0]},${r * v[1]},${center[0]},${center[1]})`;
}

const HERO_MESH_O: HeroPt = [150, 96];
const HERO_SOLID_O: HeroPt = [470, 96];
const HERO_MESH_EDGES: Array<[HeroPt, HeroPt]> = HERO_FACES.flatMap((face, index) => heroFaceEdges(HERO_MESH_O, face, 0.5, 3 + index));
const HERO_MESH_OUTLINE = heroOutline(HERO_MESH_O);
const HERO_SOLID_OUTLINE = heroOutline(HERO_SOLID_O);
const HERO_SOLID_FACES = heroSolidFaces(HERO_SOLID_O);
const HERO_HOLE_TRANSFORM = heroHoleTransform(HERO_SOLID_O, HERO_W * 0.52, HERO_H * 0.5, 0.42);

export function MeshTransitionHero() {
  return (
    <svg className="mesh-transition-hero" viewBox="0 0 620 200" role="img" aria-label="A triangulated mesh becoming a clean parametric solid" fill="none">
      <defs>
        <radialGradient id="hero-halo"><stop stopColor="#1677de" stopOpacity=".34"/><stop offset="1" stopColor="#1677de" stopOpacity="0"/></radialGradient>
        <linearGradient id="hero-sheen" x1="0" x2="1"><stop stopColor="#dcebff" stopOpacity="0"/><stop offset="1" stopColor="#dcebff" stopOpacity=".16"/></linearGradient>
      </defs>
      <ellipse cx="310" cy="100" rx="288" ry="94" fill="url(#hero-halo)"/>

      {/* raw triangulated mesh shell */}
      <g stroke="#7fb4ea" strokeWidth="0.8" strokeOpacity="0.72" strokeLinejoin="round">
        {HERO_MESH_EDGES.map((e, i) => <line key={i} x1={e[0][0].toFixed(1)} y1={e[0][1].toFixed(1)} x2={e[1][0].toFixed(1)} y2={e[1][1].toFixed(1)} />)}
      </g>
      <g stroke="#bcd7f2" strokeWidth="1.1" strokeOpacity="0.92" strokeLinecap="round" strokeLinejoin="round">
        {HERO_MESH_OUTLINE.map((poly, i) => <polyline key={i} points={heroPoints(poly)} />)}
      </g>

      {/* transition */}
      <g>
        <circle cx="280" cy="82" r="1.7" fill="#8cc4ff" opacity="0.7"/>
        <circle cx="292" cy="92" r="1.4" fill="#8cc4ff" opacity="0.55"/>
        <circle cx="284" cy="104" r="1.2" fill="#8cc4ff" opacity="0.45"/>
        <line x1="300" y1="97" x2="344" y2="97" stroke="#8cc4ff" strokeWidth="1.5" strokeLinecap="round"/>
        <path d="M338 91 L346 97 L338 103" fill="none" stroke="#8cc4ff" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </g>

      {/* clean parametric solid */}
      {HERO_SOLID_FACES.map((f, i) => <polygon key={i} points={heroPoints(f.points)} fill={f.fill}/>)}
      <g stroke="#e3efff" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round">
        {HERO_SOLID_OUTLINE.map((poly, i) => <polyline key={i} points={heroPoints(poly)} />)}
      </g>
      <circle cx="0" cy="0" r="1" transform={HERO_HOLE_TRANSFORM} vectorEffect="non-scaling-stroke" fill="rgba(9,16,26,.55)" stroke="#bcd6f4" strokeWidth="1.15"/>
    </svg>
  );
}
