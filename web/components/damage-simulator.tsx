"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { OrbitControls, useGLTF, Html } from "@react-three/drei";
import * as THREE from "three";
import { meshIndexToZone } from "@/lib/model-zones";
import { ALL_ZONES, ZONE_LABELS, SEVERITY_COLORS, type ZoneId, type Severity } from "@/lib/constants";

interface DamageEntry {
  id: string;
  zone: ZoneId;
  severity: Exclude<Severity, "GRAY">;
  description: string;
}

const SEV_OPTIONS: { value: Exclude<Severity, "GRAY">; label: string; hex: string }[] = [
  { value: "RED", label: "Critical", hex: "#c45050" },
  { value: "YELLOW", label: "Warning", hex: "#c9a832" },
  { value: "GREEN", label: "Minor", hex: "#5a9e62" },
];

const SEVERITY_HEX: Record<string, string> = {
  RED: "#c45050",
  YELLOW: "#c9a832",
  GREEN: "#5a9e62",
  GRAY: "#6b645e",
};

const SEVERITY_RANK: Record<string, number> = { RED: 3, YELLOW: 2, GREEN: 1 };

function worstSev(items: DamageEntry[]): Severity {
  let best: Severity = "GRAY";
  let bestR = 0;
  for (const d of items) {
    const r = SEVERITY_RANK[d.severity] ?? 0;
    if (r > bestR) { bestR = r; best = d.severity; }
  }
  return best;
}

/* ------------------------------------------------------------------ */
/*  Truck scene                                                        */
/* ------------------------------------------------------------------ */

function SimTruck({
  damages,
  selectedZone,
  onClickZone,
}: {
  damages: DamageEntry[];
  selectedZone: ZoneId | null;
  onClickZone: (zone: ZoneId, position: THREE.Vector3) => void;
}) {
  const { scene } = useGLTF("/cat797.glb");
  const meshMapRef = useRef<Map<THREE.Mesh, ZoneId>>(new Map());

  const zoneSev = useMemo(() => {
    const m: Record<string, Severity> = {};
    const byZone: Record<string, DamageEntry[]> = {};
    for (const d of damages) (byZone[d.zone] ??= []).push(d);
    for (const [z, entries] of Object.entries(byZone)) m[z] = worstSev(entries);
    return m;
  }, [damages]);

  useEffect(() => {
    const map = new Map<THREE.Mesh, ZoneId>();
    let idx = 0;
    scene.traverse((child) => {
      if (!(child instanceof THREE.Mesh)) return;
      const i = idx++;
      const zone = meshIndexToZone(i);
      if (zone) map.set(child, zone);

      const sev = zone ? zoneSev[zone] ?? null : null;
      const isSel = zone === selectedZone;

      if (sev) {
        const c = new THREE.Color(SEVERITY_HEX[sev]);
        child.material = new THREE.MeshStandardMaterial({
          color: c, emissive: c,
          emissiveIntensity: isSel ? 0.7 : 0.35,
          metalness: 0.3, roughness: 0.6,
          transparent: true, opacity: isSel ? 1 : 0.85,
          side: THREE.DoubleSide,
        });
      } else {
        child.material = new THREE.MeshStandardMaterial({
          color: new THREE.Color(isSel ? "#b0aba5" : "#8a8580"),
          metalness: 0.4, roughness: 0.7,
          transparent: true, opacity: isSel ? 0.7 : 0.3,
          side: THREE.DoubleSide,
        });
      }
    });
    meshMapRef.current = map;
  }, [scene, zoneSev, selectedZone]);

  const onClick = useCallback((e: any) => {
    e.stopPropagation();
    const zone = meshMapRef.current.get(e.object as THREE.Mesh);
    if (!zone) return;
    const box = new THREE.Box3().setFromObject(e.object);
    const center = new THREE.Vector3();
    box.getCenter(center);
    onClickZone(zone, center);
  }, [onClickZone]);

  return <primitive object={scene} onClick={onClick} />;
}

function AutoFit({ scene }: { scene: THREE.Object3D }) {
  const { camera } = useThree();
  useEffect(() => {
    const box = new THREE.Box3().setFromObject(scene);
    const size = new THREE.Vector3(); box.getSize(size);
    const center = new THREE.Vector3(); box.getCenter(center);
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
/*  Severity picker (appears in 3D space on click)                     */
/* ------------------------------------------------------------------ */

function SeverityPicker({
  zone,
  position,
  onPick,
  onCancel,
}: {
  zone: ZoneId;
  position: THREE.Vector3;
  onPick: (severity: Exclude<Severity, "GRAY">) => void;
  onCancel: () => void;
}) {
  return (
    <Html position={position} center style={{ pointerEvents: "auto" }}>
      <div style={{
        background: "rgba(20,19,19,0.96)", border: "1px solid var(--border)",
        borderRadius: 10, padding: "14px 18px", minWidth: 180,
        backdropFilter: "blur(12px)", color: "#e0ddd8",
      }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>
          {ZONE_LABELS[zone]}
        </div>
        <div style={{ fontSize: 11, color: "#8a837c", marginBottom: 10 }}>Select damage severity</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {SEV_OPTIONS.map((o) => (
            <button
              key={o.value}
              onClick={() => onPick(o.value)}
              style={{
                display: "flex", alignItems: "center", gap: 10,
                padding: "8px 12px", background: "rgba(255,255,255,0.04)",
                border: `1px solid ${o.hex}40`, borderRadius: 6,
                cursor: "pointer", fontSize: 12, color: o.hex,
                transition: "background 0.15s",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = `${o.hex}18`)}
              onMouseLeave={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.04)")}
            >
              <span style={{ width: 10, height: 10, borderRadius: "50%", background: o.hex }} />
              {o.label}
            </button>
          ))}
        </div>
        <button
          onClick={onCancel}
          style={{
            marginTop: 8, width: "100%", padding: "6px 0",
            background: "none", border: "1px solid var(--border)",
            borderRadius: 6, cursor: "pointer", fontSize: 11, color: "#8a837c",
          }}
        >
          Cancel
        </button>
      </div>
    </Html>
  );
}

/* ------------------------------------------------------------------ */
/*  Scene content                                                      */
/* ------------------------------------------------------------------ */

function SceneContent({
  damages,
  selectedZone,
  picker,
  onClickZone,
  onPick,
  onCancelPicker,
}: {
  damages: DamageEntry[];
  selectedZone: ZoneId | null;
  picker: { zone: ZoneId; position: THREE.Vector3 } | null;
  onClickZone: (zone: ZoneId, pos: THREE.Vector3) => void;
  onPick: (sev: Exclude<Severity, "GRAY">) => void;
  onCancelPicker: () => void;
}) {
  const { scene } = useGLTF("/cat797.glb");
  return (
    <>
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 10, 15]} intensity={1.2} />
      <directionalLight position={[-10, -5, 10]} intensity={0.4} />
      <SimTruck damages={damages} selectedZone={selectedZone} onClickZone={onClickZone} />
      <AutoFit scene={scene} />
      <OrbitControls makeDefault enableDamping dampingFactor={0.12} minDistance={10} maxDistance={100} target={[0, 0, 10]} />
      {picker && (
        <SeverityPicker zone={picker.zone} position={picker.position} onPick={onPick} onCancel={onCancelPicker} />
      )}
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Damage panel (sidebar)                                             */
/* ------------------------------------------------------------------ */

function DamagePanel({
  damages,
  onRemove,
  onClear,
  selectedZone,
  onSelectZone,
}: {
  damages: DamageEntry[];
  onRemove: (id: string) => void;
  onClear: () => void;
  selectedZone: ZoneId | null;
  onSelectZone: (z: ZoneId | null) => void;
}) {
  const grouped = useMemo(() => {
    const m: Record<string, DamageEntry[]> = {};
    for (const d of damages) (m[d.zone] ??= []).push(d);
    return m;
  }, [damages]);

  return (
    <div style={{
      width: 280, flexShrink: 0, display: "flex", flexDirection: "column",
      background: "var(--bg-card)", borderRadius: "var(--radius)",
      border: "1px solid var(--border)", overflow: "hidden",
    }}>
      <div style={{
        padding: "14px 16px", borderBottom: "1px solid var(--border)",
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>
          Damages ({damages.length})
        </span>
        {damages.length > 0 && (
          <button onClick={onClear} style={{
            background: "none", border: "none", color: "#8a837c",
            cursor: "pointer", fontSize: 11, textDecoration: "underline",
          }}>
            Clear all
          </button>
        )}
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "8px 12px" }}>
        {damages.length === 0 ? (
          <p style={{ fontSize: 12, color: "#6b645e", textAlign: "center", marginTop: 32 }}>
            Click on the 3D model to simulate damage
          </p>
        ) : (
          Object.entries(grouped).map(([zone, entries]) => (
            <div key={zone} style={{ marginBottom: 12 }}>
              <button
                onClick={() => onSelectZone(selectedZone === zone ? null : zone as ZoneId)}
                style={{
                  display: "flex", alignItems: "center", gap: 6,
                  fontSize: 12, fontWeight: 600, color: "#c5c1bc",
                  background: "none", border: "none", cursor: "pointer",
                  padding: "4px 0", width: "100%",
                }}
              >
                <span style={{
                  width: 8, height: 8, borderRadius: "50%",
                  background: SEVERITY_HEX[worstSev(entries)],
                }} />
                {ZONE_LABELS[zone as ZoneId] ?? zone}
              </button>
              {entries.map((d) => (
                <div key={d.id} style={{
                  display: "flex", alignItems: "flex-start", justifyContent: "space-between",
                  padding: "6px 8px 6px 18px", fontSize: 11, color: "#a09b96",
                  borderLeft: `2px solid ${SEVERITY_HEX[d.severity]}`,
                  marginLeft: 3, marginBottom: 2,
                }}>
                  <span style={{ flex: 1 }}>
                    <span style={{ color: SEVERITY_HEX[d.severity], fontWeight: 600, marginRight: 6 }}>
                      {d.severity}
                    </span>
                    {d.description}
                  </span>
                  <button onClick={() => onRemove(d.id)} style={{
                    background: "none", border: "none", color: "#6b645e",
                    cursor: "pointer", fontSize: 14, lineHeight: 1, padding: "0 0 0 8px", flexShrink: 0,
                  }}>
                    &times;
                  </button>
                </div>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Description modal                                                  */
/* ------------------------------------------------------------------ */

function DescriptionModal({
  zone,
  severity,
  onConfirm,
  onCancel,
}: {
  zone: ZoneId;
  severity: Exclude<Severity, "GRAY">;
  onConfirm: (desc: string) => void;
  onCancel: () => void;
}) {
  const [desc, setDesc] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => { inputRef.current?.focus(); }, []);

  return (
    <div style={{
      position: "absolute", inset: 0, zIndex: 50,
      display: "flex", alignItems: "center", justifyContent: "center",
      background: "rgba(0,0,0,0.5)", backdropFilter: "blur(4px)",
    }}>
      <div style={{
        background: "var(--bg-card)", border: "1px solid var(--border)",
        borderRadius: 10, padding: "20px 24px", width: 340,
      }}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
          Add Damage
        </div>
        <div style={{ fontSize: 12, color: "#8a837c", marginBottom: 16 }}>
          <span style={{ color: SEVERITY_HEX[severity], fontWeight: 600 }}>{severity}</span>
          {" "}damage on <span style={{ fontWeight: 600 }}>{ZONE_LABELS[zone]}</span>
        </div>
        <input
          ref={inputRef}
          type="text"
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") onConfirm(desc || "Simulated damage"); }}
          placeholder="Describe the damage (optional)"
          style={{
            width: "100%", padding: "8px 12px", fontSize: 13,
            background: "var(--bg)", border: "1px solid var(--border)",
            borderRadius: 6, color: "var(--text)", outline: "none",
            boxSizing: "border-box",
          }}
        />
        <div style={{ display: "flex", gap: 8, marginTop: 14, justifyContent: "flex-end" }}>
          <button onClick={onCancel} style={{
            padding: "7px 16px", background: "none",
            border: "1px solid var(--border)", borderRadius: 6,
            cursor: "pointer", fontSize: 12, color: "#8a837c",
          }}>
            Cancel
          </button>
          <button onClick={() => onConfirm(desc || "Simulated damage")} style={{
            padding: "7px 16px", background: SEVERITY_HEX[severity],
            border: "none", borderRadius: 6,
            cursor: "pointer", fontSize: 12, color: "#fff", fontWeight: 600,
          }}>
            Add Damage
          </button>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main export                                                        */
/* ------------------------------------------------------------------ */

export function DamageSimulator() {
  const [damages, setDamages] = useState<DamageEntry[]>([]);
  const [selectedZone, setSelectedZone] = useState<ZoneId | null>(null);
  const [picker, setPicker] = useState<{ zone: ZoneId; position: THREE.Vector3 } | null>(null);
  const [descPrompt, setDescPrompt] = useState<{ zone: ZoneId; severity: Exclude<Severity, "GRAY"> } | null>(null);
  const [canvasKey, setCanvasKey] = useState(0);
  const [contextLost, setContextLost] = useState(false);

  const handleClickZone = useCallback((zone: ZoneId, position: THREE.Vector3) => {
    setSelectedZone(zone);
    setPicker({ zone, position });
  }, []);

  const handlePickSeverity = useCallback((severity: Exclude<Severity, "GRAY">) => {
    if (!picker) return;
    setPicker(null);
    setDescPrompt({ zone: picker.zone, severity });
  }, [picker]);

  const handleConfirmDamage = useCallback((desc: string) => {
    if (!descPrompt) return;
    setDamages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), zone: descPrompt.zone, severity: descPrompt.severity, description: desc },
    ]);
    setDescPrompt(null);
  }, [descPrompt]);

  const handleRemove = useCallback((id: string) => {
    setDamages((prev) => prev.filter((d) => d.id !== id));
  }, []);

  const handleClear = useCallback(() => {
    setDamages([]);
    setSelectedZone(null);
  }, []);

  const handleRetryCanvas = useCallback(() => {
    setContextLost(false);
    setCanvasKey((k) => k + 1);
  }, []);

  return (
    <div style={{ display: "flex", gap: 20, height: "calc(100vh - 160px)", minHeight: 500 }}>
      {/* 3D canvas */}
      <div style={{
        flex: 1, position: "relative", borderRadius: "var(--radius)",
        overflow: "hidden", border: "1px solid var(--border)",
      }}>
        {contextLost ? (
          <div style={{
            height: "100%", display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center", gap: 12,
            background: "#1a1918", color: "var(--text-dim)", fontSize: 13,
          }}>
            <span>WebGL context was lost.</span>
            <button
              onClick={handleRetryCanvas}
              style={{
                padding: "8px 20px", background: "var(--amber)",
                border: "none", borderRadius: 6, cursor: "pointer",
                fontSize: 12, color: "#141313", fontWeight: 600,
              }}
            >
              Reload 3D Viewer
            </button>
          </div>
        ) : (
          <Suspense fallback={
            <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-dim)", fontSize: 13, background: "#1a1918" }}>
              Loading 3D model…
            </div>
          }>
            <Canvas
              key={canvasKey}
              camera={{ fov: 45, near: 0.1, far: 500 }}
              style={{ background: "#1a1918" }}
              onCreated={(state) => {
                state.gl.toneMapping = THREE.ACESFilmicToneMapping;
                state.gl.toneMappingExposure = 1.2;
                const canvas = state.gl.domElement;
                canvas.addEventListener("webglcontextlost", (e) => {
                  e.preventDefault();
                  setContextLost(true);
                });
              }}
            >
              <SceneContent
                damages={damages}
                selectedZone={selectedZone}
                picker={picker}
                onClickZone={handleClickZone}
                onPick={handlePickSeverity}
                onCancelPicker={() => setPicker(null)}
              />
            </Canvas>
          </Suspense>
        )}

        {/* Zone hint overlay */}
        {!contextLost && (
          <div style={{
            position: "absolute", bottom: 12, left: 12,
            display: "flex", gap: 6, flexWrap: "wrap",
          }}>
            {ALL_ZONES.map((z) => {
              const hasDmg = damages.some((d) => d.zone === z);
              const isSel = selectedZone === z;
              return (
                <button
                  key={z}
                  onClick={() => setSelectedZone(isSel ? null : z)}
                  style={{
                    padding: "3px 8px", fontSize: 10, borderRadius: 4,
                    background: hasDmg
                      ? `${SEVERITY_HEX[worstSev(damages.filter((d) => d.zone === z))]}20`
                      : "rgba(0,0,0,0.45)",
                    border: isSel ? "1px solid rgba(255,255,255,0.3)" : "1px solid transparent",
                    color: hasDmg
                      ? SEVERITY_HEX[worstSev(damages.filter((d) => d.zone === z))]
                      : "#6b645e",
                    cursor: "pointer",
                  }}
                >
                  {ZONE_LABELS[z]}
                </button>
              );
            })}
          </div>
        )}

        {!contextLost && (
          <div style={{
            position: "absolute", top: 12, right: 12,
            fontSize: 11, color: "rgba(255,255,255,0.3)", pointerEvents: "none",
          }}>
            Click a zone to add damage
          </div>
        )}

        {/* Description modal overlay */}
        {descPrompt && (
          <DescriptionModal
            zone={descPrompt.zone}
            severity={descPrompt.severity}
            onConfirm={handleConfirmDamage}
            onCancel={() => setDescPrompt(null)}
          />
        )}
      </div>

      {/* Sidebar */}
      <DamagePanel
        damages={damages}
        onRemove={handleRemove}
        onClear={handleClear}
        selectedZone={selectedZone}
        onSelectZone={setSelectedZone}
      />
    </div>
  );
}

useGLTF.preload("/cat797.glb");
