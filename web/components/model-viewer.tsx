"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { OrbitControls, useGLTF, Html, Environment } from "@react-three/drei";
import * as THREE from "three";
import { ZONE_MESH_INDICES, meshIndexToZone } from "@/lib/model-zones";
import { ZONE_LABELS, SEVERITY_COLORS, type ZoneId, type Severity } from "@/lib/constants";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface FindingEntry {
  zone: string;
  rating: string;
  description: string;
}

interface ModelViewerProps {
  findings: FindingEntry[];
}

/* ------------------------------------------------------------------ */
/*  Severity helpers                                                   */
/* ------------------------------------------------------------------ */

const SEVERITY_ORDER: Record<string, number> = { RED: 3, YELLOW: 2, GREEN: 1 };

function worstSeverity(ratings: string[]): Severity | null {
  let worst: Severity | null = null;
  let worstVal = 0;
  for (const r of ratings) {
    const upper = r.toUpperCase();
    const val = SEVERITY_ORDER[upper] ?? 0;
    if (val > worstVal) {
      worstVal = val;
      worst = upper as Severity;
    }
  }
  return worst;
}

const SEVERITY_HEX: Record<Severity, string> = {
  RED: "#c45050",
  YELLOW: "#c9a832",
  GREEN: "#5a9e62",
  GRAY: "#6b645e",
};

/* ------------------------------------------------------------------ */
/*  Build per-zone severity map from findings                          */
/* ------------------------------------------------------------------ */

function useZoneSeverityMap(findings: FindingEntry[]) {
  return useMemo(() => {
    const byZone: Record<string, string[]> = {};
    for (const f of findings) {
      (byZone[f.zone] ??= []).push(f.rating);
    }
    const map: Record<string, Severity> = {};
    for (const [zone, ratings] of Object.entries(byZone)) {
      const sev = worstSeverity(ratings);
      if (sev) map[zone] = sev;
    }
    return map;
  }, [findings]);
}

/* ------------------------------------------------------------------ */
/*  Tooltip state                                                      */
/* ------------------------------------------------------------------ */

interface TooltipData {
  zone: ZoneId;
  label: string;
  severity: Severity;
  findings: FindingEntry[];
  position: THREE.Vector3;
}

/* ------------------------------------------------------------------ */
/*  Truck model (inner scene)                                          */
/* ------------------------------------------------------------------ */

function TruckModel({
  findings,
  zoneSeverity,
  onSelectZone,
  selectedZone,
}: {
  findings: FindingEntry[];
  zoneSeverity: Record<string, Severity>;
  onSelectZone: (data: TooltipData | null) => void;
  selectedZone: string | null;
}) {
  const { scene } = useGLTF("/cat797.glb");
  const meshMapRef = useRef<Map<THREE.Mesh, { zone: ZoneId; meshIdx: number }>>(new Map());
  const materialsRef = useRef<Map<THREE.Mesh, THREE.Material>>(new Map());

  useEffect(() => {
    const meshMap = new Map<THREE.Mesh, { zone: ZoneId; meshIdx: number }>();
    const origMaterials = new Map<THREE.Mesh, THREE.Material>();
    let meshIdx = 0;

    scene.traverse((child) => {
      if (!(child instanceof THREE.Mesh)) return;
      const idx = meshIdx++;
      const zone = meshIndexToZone(idx);

      origMaterials.set(child, child.material);

      if (zone) {
        meshMap.set(child, { zone, meshIdx: idx });
      }

      const severity = zone ? zoneSeverity[zone] : null;
      const isSelected = zone === selectedZone;

      if (severity) {
        const color = new THREE.Color(SEVERITY_HEX[severity]);
        const mat = new THREE.MeshStandardMaterial({
          color,
          emissive: color,
          emissiveIntensity: isSelected ? 0.6 : 0.3,
          metalness: 0.3,
          roughness: 0.6,
          transparent: true,
          opacity: isSelected ? 1.0 : 0.85,
          side: THREE.DoubleSide,
        });
        child.material = mat;
      } else {
        const mat = new THREE.MeshStandardMaterial({
          color: new THREE.Color("#8a8580"),
          metalness: 0.4,
          roughness: 0.7,
          transparent: true,
          opacity: zone && isSelected ? 0.95 : 0.35,
          side: THREE.DoubleSide,
        });
        child.material = mat;
      }
    });

    meshMapRef.current = meshMap;
    materialsRef.current = origMaterials;
  }, [scene, zoneSeverity, selectedZone]);

  const handleClick = useCallback(
    (e: any) => {
      e.stopPropagation();
      const mesh = e.object as THREE.Mesh;
      const entry = meshMapRef.current.get(mesh);
      if (!entry) {
        onSelectZone(null);
        return;
      }
      const { zone } = entry;
      const severity = zoneSeverity[zone] ?? "GRAY";
      const zoneFindings = findings.filter((f) => f.zone === zone);
      const box = new THREE.Box3().setFromObject(mesh);
      const center = new THREE.Vector3();
      box.getCenter(center);

      onSelectZone({
        zone,
        label: ZONE_LABELS[zone] ?? zone,
        severity: severity as Severity,
        findings: zoneFindings,
        position: center,
      });
    },
    [findings, zoneSeverity, onSelectZone],
  );

  return <primitive object={scene} onClick={handleClick} />;
}

/* ------------------------------------------------------------------ */
/*  Camera auto-fit                                                    */
/* ------------------------------------------------------------------ */

function AutoFit({ scene }: { scene: THREE.Object3D }) {
  const { camera } = useThree();
  useEffect(() => {
    const box = new THREE.Box3().setFromObject(scene);
    const size = new THREE.Vector3();
    box.getSize(size);
    const center = new THREE.Vector3();
    box.getCenter(center);
    const maxDim = Math.max(size.x, size.y, size.z);
    const fov = (camera as THREE.PerspectiveCamera).fov * (Math.PI / 180);
    const dist = maxDim / (2 * Math.tan(fov / 2)) * 1.4;
    camera.position.set(center.x + dist * 0.7, center.y - dist * 0.5, center.z + dist * 0.5);
    camera.lookAt(center);
    camera.updateProjectionMatrix();
  }, [scene, camera]);
  return null;
}

/* ------------------------------------------------------------------ */
/*  Zone legend                                                        */
/* ------------------------------------------------------------------ */

function ZoneLegend({
  zoneSeverity,
  selectedZone,
  onSelect,
}: {
  zoneSeverity: Record<string, Severity>;
  selectedZone: string | null;
  onSelect: (zone: string | null) => void;
}) {
  const zones = Object.keys(zoneSeverity);
  if (zones.length === 0) return null;

  return (
    <div
      style={{
        position: "absolute",
        top: 12,
        left: 12,
        display: "flex",
        flexDirection: "column",
        gap: 4,
        zIndex: 10,
        pointerEvents: "auto",
      }}
    >
      {zones.map((zone) => {
        const sev = zoneSeverity[zone];
        const isActive = selectedZone === zone;
        return (
          <button
            key={zone}
            onClick={() => onSelect(isActive ? null : zone)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "5px 10px",
              background: isActive ? "rgba(255,255,255,0.12)" : "rgba(0,0,0,0.5)",
              border: isActive ? `1px solid ${SEVERITY_COLORS[sev].border}` : "1px solid transparent",
              borderRadius: 6,
              cursor: "pointer",
              fontSize: 11,
              color: "#e0ddd8",
              whiteSpace: "nowrap",
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: SEVERITY_HEX[sev],
                flexShrink: 0,
              }}
            />
            {ZONE_LABELS[zone as ZoneId] ?? zone}
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Tooltip overlay                                                    */
/* ------------------------------------------------------------------ */

function ZoneTooltip({ data, onClose }: { data: TooltipData; onClose: () => void }) {
  return (
    <Html position={data.position} center style={{ pointerEvents: "auto" }}>
      <div
        style={{
          background: "rgba(20,19,19,0.95)",
          border: `1px solid ${SEVERITY_COLORS[data.severity].border}`,
          borderRadius: 8,
          padding: "12px 16px",
          minWidth: 200,
          maxWidth: 300,
          fontSize: 12,
          color: "#e0ddd8",
          backdropFilter: "blur(8px)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <span style={{ fontWeight: 600, fontSize: 13, color: SEVERITY_COLORS[data.severity].text }}>
            {data.label}
          </span>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: "#8a837c",
              cursor: "pointer",
              fontSize: 16,
              lineHeight: 1,
              padding: 0,
            }}
          >
            &times;
          </button>
        </div>
        {data.findings.length > 0 ? (
          <ul style={{ margin: 0, padding: "0 0 0 14px", listStyle: "disc" }}>
            {data.findings.map((f, i) => (
              <li key={i} style={{ marginBottom: 4, lineHeight: 1.4, color: "#c5c1bc" }}>
                <span
                  style={{
                    display: "inline-block",
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    background: SEVERITY_HEX[f.rating.toUpperCase() as Severity] ?? "#6b645e",
                    marginRight: 6,
                    verticalAlign: "middle",
                  }}
                />
                {f.description}
              </li>
            ))}
          </ul>
        ) : (
          <p style={{ margin: 0, color: "#8a837c" }}>No findings in this zone.</p>
        )}
      </div>
    </Html>
  );
}

/* ------------------------------------------------------------------ */
/*  Loading fallback                                                   */
/* ------------------------------------------------------------------ */

function LoadingFallback() {
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "var(--text-dim)",
        fontSize: 13,
      }}
    >
      Loading 3D model…
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Inner canvas content (needs to be a child of Canvas)               */
/* ------------------------------------------------------------------ */

function SceneContent({
  findings,
  zoneSeverity,
  tooltip,
  setTooltip,
  selectedZone,
  setSelectedZone,
}: {
  findings: FindingEntry[];
  zoneSeverity: Record<string, Severity>;
  tooltip: TooltipData | null;
  setTooltip: (d: TooltipData | null) => void;
  selectedZone: string | null;
  setSelectedZone: (z: string | null) => void;
}) {
  const { scene } = useGLTF("/cat797.glb");

  const handleSelectZone = useCallback(
    (data: TooltipData | null) => {
      setTooltip(data);
      setSelectedZone(data?.zone ?? null);
    },
    [setTooltip, setSelectedZone],
  );

  return (
    <>
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 10, 15]} intensity={1.2} />
      <directionalLight position={[-10, -5, 10]} intensity={0.4} />
      <TruckModel
        findings={findings}
        zoneSeverity={zoneSeverity}
        onSelectZone={handleSelectZone}
        selectedZone={selectedZone}
      />
      <AutoFit scene={scene} />
      <OrbitControls
        makeDefault
        enableDamping
        dampingFactor={0.12}
        minDistance={10}
        maxDistance={100}
        target={[0, 0, 10]}
      />
      {tooltip && <ZoneTooltip data={tooltip} onClose={() => handleSelectZone(null)} />}
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Public component                                                   */
/* ------------------------------------------------------------------ */

export function ModelViewer({ findings }: ModelViewerProps) {
  const zoneSeverity = useZoneSeverityMap(findings);
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);
  const [selectedZone, setSelectedZone] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [canvasKey, setCanvasKey] = useState(0);

  if (error) {
    return (
      <div
        style={{
          height: 400,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 12,
          color: "var(--text-dim)",
          fontSize: 13,
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          background: "var(--bg-card)",
        }}
      >
        <span>3D viewer lost WebGL context.</span>
        <button
          onClick={() => { setError(false); setCanvasKey((k) => k + 1); }}
          style={{
            padding: "7px 18px", background: "var(--amber)",
            border: "none", borderRadius: 6, cursor: "pointer",
            fontSize: 12, color: "#141313", fontWeight: 600,
          }}
        >
          Reload Viewer
        </button>
      </div>
    );
  }

  return (
    <div style={{ position: "relative", width: "100%", height: 480, borderRadius: "var(--radius)", overflow: "hidden" }}>
      <ZoneLegend zoneSeverity={zoneSeverity} selectedZone={selectedZone} onSelect={setSelectedZone} />
      <Suspense fallback={<LoadingFallback />}>
        <Canvas
          key={canvasKey}
          camera={{ fov: 45, near: 0.1, far: 500 }}
          style={{ background: "#1a1918", borderRadius: "var(--radius)" }}
          onCreated={(state) => {
            state.gl.toneMapping = THREE.ACESFilmicToneMapping;
            state.gl.toneMappingExposure = 1.2;
            const canvas = state.gl.domElement;
            canvas.addEventListener("webglcontextlost", (e) => {
              e.preventDefault();
              setError(true);
            });
          }}
        >
          <SceneContent
            findings={findings}
            zoneSeverity={zoneSeverity}
            tooltip={tooltip}
            setTooltip={setTooltip}
            selectedZone={selectedZone}
            setSelectedZone={setSelectedZone}
          />
        </Canvas>
      </Suspense>
      <div
        style={{
          position: "absolute",
          bottom: 10,
          right: 12,
          fontSize: 11,
          color: "rgba(255,255,255,0.3)",
          pointerEvents: "none",
        }}
      >
        Drag to rotate · Scroll to zoom
      </div>
    </div>
  );
}

useGLTF.preload("/cat797.glb");
