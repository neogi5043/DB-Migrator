import { useState, useEffect, useRef } from "react";
import {
    getConfig, getTables, getMapping, approveTable, approveAll as apiApproveAll,
    runExtract, runPropose, runApplySchema, runMigrate, runValidate, testConnection,
    saveMapping,
} from "./api.js";
import logoSrc from "../assests/unnamed.png";

// ─── Palette & Tokens ──────────────────────────────────────────────────────
const C = {
    bg0: "#000000", bg1: "#0f1217", bg2: "#151a21", bg3: "#1c2330",
    border: "#232d3a", borderHi: "#2e3f54",
    cyan: "#38bdf8", cyanDim: "#0e4a6b",
    green: "#34d399", greenDim: "#064e3b",
    amber: "#fbbf24", amberDim: "#451a03",
    red: "#f87171", redDim: "#450a0a",
    purple: "#a78bfa", purpleDim: "#2e1065",
    text0: "#e2e8f0", text1: "#94a3b8", text2: "#4b5563",
};

// Only engines actually supported by the connector registry
const SOURCE_ENGINES = ["postgres", "mssql"];
const TARGET_ENGINES = ["mysql"];
const ENGINE_ICONS = { postgres: "PG", mysql: "MY", mssql: "MS" };
const ENGINE_COLORS = { postgres: C.cyan, mysql: C.amber, mssql: C.purple };

const G = {
    fontMono: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
    fontSans: "'IBM Plex Sans', 'DM Sans', system-ui, sans-serif",
};

function injectStyles() {
    const css = `
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap');
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: ${C.bg0}; color: ${C.text0}; font-family: ${G.fontSans}; }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: ${C.bg1}; }
    ::-webkit-scrollbar-thumb { background: ${C.border}; border-radius: 3px; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
    @keyframes slideIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
    @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
    @keyframes flow { 0%{stroke-dashoffset:24} 100%{stroke-dashoffset:0} }
    @keyframes fadeIn { from{opacity:0} to{opacity:1} }
  `;
    const el = document.createElement("style");
    el.textContent = css;
    document.head.appendChild(el);
}

// ─── Utility Components ──────────────────────────────────────────────────
function Mono({ children, color, size = 12, style = {} }) {
    return <span style={{ fontFamily: G.fontMono, color: color || C.text1, fontSize: size, ...style }}>{children}</span>;
}

function Badge({ label, color = C.cyan, bg }) {
    return (
        <span style={{
            fontFamily: G.fontMono, fontSize: 10, fontWeight: 600,
            color, background: bg || color + "18",
            border: `1px solid ${color}40`,
            padding: "2px 8px", borderRadius: 3, letterSpacing: "0.05em",
            textTransform: "uppercase",
        }}>{label}</span>
    );
}

function StatusDot({ status }) {
    const map = { approved: C.green, draft: C.amber, pending: C.amber, error: C.red, running: C.cyan };
    const color = map[status] || C.text2;
    return (
        <span style={{
            display: "inline-block", width: 7, height: 7, borderRadius: "50%",
            background: color,
            boxShadow: status === "running" ? `0 0 6px ${color}` : "none",
            animation: status === "running" ? "pulse 1.2s infinite" : "none",
            flexShrink: 0,
        }} />
    );
}

function Divider({ style = {} }) {
    return <div style={{ height: 1, background: C.border, width: "100%", ...style }} />;
}

function Panel({ children, style = {} }) {
    return (
        <div style={{
            background: C.bg1, border: `1px solid ${C.border}`,
            borderRadius: 8, overflow: "hidden", ...style,
        }}>{children}</div>
    );
}

function PanelHeader({ title, right, icon }) {
    return (
        <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "10px 16px", borderBottom: `1px solid ${C.border}`, background: C.bg2,
        }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {icon && <span style={{ fontSize: 14 }}>{icon}</span>}
                <Mono size={11} color={C.text0} style={{ fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase" }}>{title}</Mono>
            </div>
            {right}
        </div>
    );
}

function ProgressBar({ value, max, color = C.cyan, style = {} }) {
    const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
    return (
        <div style={{ height: 4, background: C.bg3, borderRadius: 2, overflow: "hidden", ...style }}>
            <div style={{
                width: `${pct}%`, height: "100%",
                background: `linear-gradient(90deg, ${color}aa, ${color})`,
                transition: "width 0.4s ease", borderRadius: 2,
            }} />
        </div>
    );
}

function PipelineArrow({ active }) {
    return (
        <svg width="32" height="16" viewBox="0 0 32 16" style={{ flexShrink: 0 }}>
            <line x1="0" y1="8" x2="28" y2="8" stroke={active ? C.cyan : C.border}
                strokeWidth="1.5" strokeDasharray="4 4"
                style={{ animation: active ? "flow 0.8s linear infinite" : "none" }} />
            <polygon points="24,4 32,8 24,12" fill={active ? C.cyan : C.border} />
        </svg>
    );
}

function Field({ label, children, style = {} }) {
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 5, ...style }}>
            <Mono size={10} color={C.text2} style={{ letterSpacing: "0.06em", textTransform: "uppercase" }}>{label}</Mono>
            {children}
        </div>
    );
}

function Input({ value, onChange, placeholder, mono, password, error, disabled }) {
    return (
        <input type={password ? "password" : "text"} value={value || ""} onChange={e => onChange(e.target.value)}
            placeholder={placeholder} disabled={disabled}
            style={{
                background: disabled ? C.bg2 : C.bg0, border: `1px solid ${error ? C.red : C.border}`,
                borderRadius: 4, padding: "7px 10px", color: disabled ? C.text2 : C.text0, width: "100%",
                fontFamily: mono ? G.fontMono : G.fontSans, fontSize: 12, outline: "none",
                transition: "border-color 0.15s", cursor: disabled ? "not-allowed" : "text",
            }}
            onFocus={e => { if (!disabled) e.target.style.borderColor = C.cyan; }}
            onBlur={e => e.target.style.borderColor = error ? C.red : C.border}
        />
    );
}

function EngineSelect({ value, options, onChange }) {
    return (
        <select value={value} onChange={e => onChange(e.target.value)}
            style={{
                background: C.bg0, border: `1px solid ${C.border}`,
                borderRadius: 4, padding: "7px 10px", color: C.text0, width: "100%",
                fontFamily: G.fontMono, fontSize: 12, cursor: "pointer", outline: "none",
            }}>
            {options.map(o => <option key={o} value={o}>{ENGINE_ICONS[o] || "⚙"} {o}</option>)}
        </select>
    );
}

function Toggle({ checked, onChange }) {
    return (
        <div onClick={() => onChange(!checked)} style={{
            width: 32, height: 18, borderRadius: 9,
            background: checked ? C.cyan : C.border,
            position: "relative", cursor: "pointer", flexShrink: 0, transition: "background 0.2s",
        }}>
            <div style={{
                width: 12, height: 12, borderRadius: "50%", background: "#fff",
                position: "absolute", top: 3, left: checked ? 17 : 3, transition: "left 0.2s",
            }} />
        </div>
    );
}

function KVRow({ k, v, mono }) {
    return (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <Mono size={11} color={C.text2} style={{ textTransform: "uppercase", letterSpacing: "0.05em" }}>{k}</Mono>
            <span style={{ fontFamily: mono ? G.fontMono : G.fontSans, fontSize: 12, color: C.text0, fontWeight: 500 }}>{v}</span>
        </div>
    );
}

function btnStyle(color) {
    return {
        width: "100%", padding: "9px 16px", borderRadius: 5,
        background: color + "18", border: `1px solid ${color}60`,
        color, cursor: "pointer", transition: "all 0.15s", fontFamily: G.fontMono,
        fontSize: 12, fontWeight: 600, letterSpacing: "0.05em",
    };
}

function smallBtnStyle(color) {
    return {
        padding: "4px 10px", borderRadius: 4,
        background: color + "18", border: `1px solid ${color}60`,
        color, cursor: "pointer", fontSize: 10,
        fontFamily: G.fontMono, fontWeight: 600, letterSpacing: "0.05em",
    };
}

// ─── Steps ──────────────────────────────────────────────────────────────
const STEPS = [
    { id: "config", label: "Configure", icon: "1" },
    { id: "extract", label: "Extract", icon: "2" },
    { id: "propose", label: "LLM Map", icon: "3" },
    { id: "review", label: "Review", icon: "4" },
    { id: "migrate", label: "Migrate", icon: "5" },
    { id: "validate", label: "Validate", icon: "6" },
];

// ─── Config Step ────────────────────────────────────────────────────────
// Matches actual config.yaml structure: source.engine, source.postgres.*, 
// target.engine, target.mysql.*, llm.provider (azure_openai), migration.*
function ConfigStep({ config, setConfig, onNext }) {
    const [errors, setErrors] = useState({});
    const [testStatus, setTestStatus] = useState({ source: null, target: null });

    async function handleTest(side) {
        setTestStatus(s => ({ ...s, [side]: "testing" }));
        try {
            const res = await testConnection(side, config);
            setTestStatus(s => ({ ...s, [side]: res.status === "success" ? "success" : "error" }));
        } catch (err) {
            setTestStatus(s => ({ ...s, [side]: "error" }));
        }
    }

    function validate() {
        const e = {};
        if (!config.sourceHost) e.sourceHost = "Required";
        if (!config.sourcePort) e.sourcePort = "Required";
        if (!config.sourceDb) e.sourceDb = "Required";
        if (!config.sourceUser) e.sourceUser = "Required";
        if (!config.sourcePass) e.sourcePass = "Required";

        if (!config.targetHost) e.targetHost = "Required";
        if (!config.targetPort) e.targetPort = "Required";
        if (!config.targetDb) e.targetDb = "Required";
        if (!config.targetUser) e.targetUser = "Required";
        if (!config.targetPass) e.targetPass = "Required";
        return e;
    }

    function handleNext() {
        const e = validate();
        if (Object.keys(e).length) { setErrors(e); return; }
        onNext();
    }

    return (
        <div style={{ display: "flex", gap: 16, animation: "slideIn 0.3s ease" }}>
            {/* Source — PostgreSQL/MSSQL */}
            <Panel style={{ flex: 1 }}>
                <PanelHeader title="Source Database" />
                <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
                    <Field label="Engine">
                        <EngineSelect value={config.sourceEngine} options={SOURCE_ENGINES}
                            onChange={v => setConfig(c => ({ ...c, sourceEngine: v }))} />
                    </Field>
                    <Field label="Host">
                        <Input value={config.sourceHost} onChange={v => setConfig(c => ({ ...c, sourceHost: v }))} placeholder="db-host.postgres.database.azure.com" mono error={errors.sourceHost} />
                    </Field>
                    <div style={{ display: "flex", gap: 10 }}>
                        <Field label="Port" style={{ flex: "0 0 90px" }}>
                            <Input value={config.sourcePort} onChange={v => setConfig(c => ({ ...c, sourcePort: v }))} placeholder="eg:5432" mono error={errors.sourcePort} />
                        </Field>
                        <Field label="Database" style={{ flex: 1 }}>
                            <Input value={config.sourceDb} onChange={v => setConfig(c => ({ ...c, sourceDb: v }))} placeholder="example_db" mono error={errors.sourceDb} />
                        </Field>
                    </div>
                    <div style={{ display: "flex", gap: 10 }}>
                        <Field label="User" style={{ flex: 1 }}>
                            <Input value={config.sourceUser} onChange={v => setConfig(c => ({ ...c, sourceUser: v }))} placeholder="admin" mono error={errors.sourceUser} />
                        </Field>
                        <Field label="Password" style={{ flex: 1 }}>
                            <Input value={config.sourcePass} onChange={v => setConfig(c => ({ ...c, sourcePass: v }))} placeholder="••••••" mono password error={errors.sourcePass} />
                        </Field>
                    </div>
                    <div style={{ display: "flex", justifyContent: "flex-end" }}>
                        <button onClick={() => handleTest("source")} type="button" style={smallBtnStyle(testStatus.source === "success" ? C.green : testStatus.source === "error" ? C.red : C.cyan)}>
                            {testStatus.source === "testing" ? "TESTING..." : testStatus.source === "success" ? "SUCCESS" : testStatus.source === "error" ? "FAILED" : "TEST CONNECTION"}
                        </button>
                    </div>
                </div>
            </Panel>

            {/* Arrow */}
            <div style={{ display: "flex", alignItems: "center", paddingTop: 24 }}>
                <svg width="48" height="48" viewBox="0 0 48 48">
                    <text x="24" y="30" textAnchor="middle" fontSize="22" fill={C.cyan} style={{ fontFamily: G.fontMono }}>→</text>
                </svg>
            </div>

            {/* Target — MySQL */}
            <Panel style={{ flex: 1 }}>
                <PanelHeader title="Target Database" />
                <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
                    <Field label="Engine">
                        <EngineSelect value={config.targetEngine} options={TARGET_ENGINES}
                            onChange={v => setConfig(c => ({ ...c, targetEngine: v }))} />
                    </Field>
                    <Field label="Host">
                        <Input value={config.targetHost} onChange={v => setConfig(c => ({ ...c, targetHost: v }))} placeholder="mysql-host.aivencloud.com" mono error={errors.targetHost} />
                    </Field>
                    <div style={{ display: "flex", gap: 10 }}>
                        <Field label="Port" style={{ flex: "0 0 90px" }}>
                            <Input value={config.targetPort} onChange={v => setConfig(c => ({ ...c, targetPort: v }))} placeholder="eg:3306" mono error={errors.targetPort} />
                        </Field>
                        <Field label="Database / Schema" style={{ flex: 1 }}>
                            <Input value={config.targetDb} onChange={v => setConfig(c => ({ ...c, targetDb: v }))} placeholder="example_db" mono error={errors.targetDb} />
                        </Field>
                    </div>
                    <div style={{ display: "flex", gap: 10 }}>
                        <Field label="User" style={{ flex: 1 }}>
                            <Input value={config.targetUser} onChange={v => setConfig(c => ({ ...c, targetUser: v }))} placeholder="admin" mono error={errors.targetUser} />
                        </Field>
                        <Field label="Password" style={{ flex: 1 }}>
                            <Input value={config.targetPass} onChange={v => setConfig(c => ({ ...c, targetPass: v }))} placeholder="••••••" mono password error={errors.targetPass} />
                        </Field>
                    </div>
                    <div style={{ display: "flex", justifyContent: "flex-end" }}>
                        <button onClick={() => handleTest("target")} type="button" style={smallBtnStyle(testStatus.target === "success" ? C.green : testStatus.target === "error" ? C.red : C.cyan)}>
                            {testStatus.target === "testing" ? "TESTING..." : testStatus.target === "success" ? "SUCCESS" : testStatus.target === "error" ? "FAILED" : "TEST CONNECTION"}
                        </button>
                    </div>
                </div>
                <div style={{ padding: "0 20px 20px" }}>
                    <button
                        onClick={handleNext}
                        disabled={testStatus.source !== "success" || testStatus.target !== "success"}
                        style={{
                            ...btnStyle(testStatus.source === "success" && testStatus.target === "success" ? C.cyan : C.text2),
                            opacity: (testStatus.source === "success" && testStatus.target === "success") ? 1 : 0.5,
                            cursor: (testStatus.source === "success" && testStatus.target === "success") ? "pointer" : "not-allowed"
                        }}
                    >
                        <span style={{ fontFamily: G.fontMono, fontSize: 12, fontWeight: 600 }}>SAVE & CONTINUE</span>
                    </button>
                </div>
            </Panel>
        </div>
    );
}

// ─── Extract Step ───────────────────────────────────────────────────────
function ExtractStep({ config, onNext }) {
    const [phase, setPhase] = useState("idle");
    const [log, setLog] = useState([]);
    const [progress, setProgress] = useState(0);
    const [stats, setStats] = useState(null);
    const logRef = useRef(null);

    async function run() {
        setPhase("running"); setLog([]); setProgress(0); setStats(null);
        await runExtract(config, (ev) => {
            if (ev.type === "log") {
                setLog(l => [...l, ev.msg]);
                if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
            }
            if (ev.type === "progress") {
                if (ev.total > 0) {
                    setProgress(Math.floor((ev.done / ev.total) * 100));
                }
                if (ev.msg) {
                    setLog(l => [...l, ev.msg]);
                    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
                }
            }
            if (ev.type === "done") {
                setStats({ tables: ev.tables, columns: ev.columns });
                setProgress(100);
                setPhase("done");
            }
            if (ev.type === "error") {
                setLog(l => [...l, `✗ ERROR: ${ev.msg}`]);
                setPhase("done");
            }
        });
    }

    return (
        <div style={{ display: "flex", gap: 16, animation: "slideIn 0.3s ease" }}>
            <Panel style={{ flex: "0 0 280px" }}>
                <PanelHeader title="Extraction" />
                <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                    <KVRow k="Source" v={`${ENGINE_ICONS[config.sourceEngine]} ${config.sourceEngine}`} />
                    <KVRow k="Database" v={config.sourceDb || "—"} mono />
                    <Divider />
                    <KVRow k="Output" v="schemas/ + stats/" mono />
                </div>
                <div style={{ padding: "0 16px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
                    <button onClick={run} disabled={phase === "running"} style={btnStyle(C.cyan)}>
                        <Mono size={12} style={{ fontWeight: 600 }}>
                            {phase === "idle" ? "RUN EXTRACT" : phase === "running" ? "EXTRACTING…" : "RE-EXTRACT"}
                        </Mono>
                    </button>
                    {phase === "done" && (
                        <button onClick={onNext} style={btnStyle(C.green)}>
                            <Mono size={12} style={{ fontWeight: 600 }}>NEXT: LLM MAP →</Mono>
                        </button>
                    )}
                </div>
            </Panel>

            <Panel style={{ flex: 1 }}>
                <PanelHeader title="Extraction Log" right={phase === "running" && <StatusDot status="running" />} />
                {phase !== "idle" && (
                    <div style={{ padding: "10px 16px 0" }}><ProgressBar value={progress} max={100} /></div>
                )}
                <div ref={logRef} style={{
                    fontFamily: G.fontMono, fontSize: 12, color: C.text1,
                    padding: 16, minHeight: 220, maxHeight: 400, overflowY: "auto", lineHeight: 1.8,
                }}>
                    {phase === "idle" && <span style={{ color: C.text2 }}>— Press RUN EXTRACT to connect to {config.sourceEngine} and extract schema —</span>}
                    {log.map((line, i) => (
                        <div key={i} style={{
                            color: line.includes("✓") ? C.green : line.includes("✗") ? C.red : C.text1,
                            animation: "fadeIn 0.2s ease",
                        }}>{line}</div>
                    ))}
                    {phase === "running" && <span style={{ color: C.cyan, animation: "blink 1s infinite" }}>█</span>}
                </div>
                {stats && (
                    <div style={{ padding: 16, borderTop: `1px solid ${C.border}` }}>
                        <div style={{ display: "flex", gap: 16 }}>
                            {[
                                { label: "Tables", value: stats.tables, color: C.cyan },
                                { label: "Columns", value: stats.columns, color: C.green },
                            ].map(s => (
                                <div key={s.label} style={{ textAlign: "center", flex: 1 }}>
                                    <div style={{ fontFamily: G.fontMono, fontSize: 22, fontWeight: 600, color: s.color }}>{s.value}</div>
                                    <Mono size={10} color={C.text2}>{s.label}</Mono>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </Panel>
        </div>
    );
}

// ─── Propose Step ───────────────────────────────────────────────────────
function ProposeStep({ config, onNext }) {
    const [phase, setPhase] = useState("idle");
    const [log, setLog] = useState([]);
    const [progress, setProgress] = useState({ done: 0, total: 1, current: "" });

    async function run() {
        setPhase("running"); setLog([]);
        await runPropose(config, (ev) => {
            if (ev.type === "log") setLog(l => [...l, ev.msg]);
            if (ev.type === "progress") setProgress(ev);
            if (ev.type === "done") setPhase("done");
            if (ev.type === "error") {
                setLog(l => [...l, `✗ ERROR: ${ev.msg}`]);
                setPhase("done");
            }
        });
    }

    return (
        <div style={{ display: "flex", gap: 16, animation: "slideIn 0.3s ease" }}>
            <Panel style={{ flex: "0 0 280px" }}>
                <PanelHeader title="LLM Mapping" />
                <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                    <KVRow k="Provider" v="Azure OpenAI" />
                    <KVRow k="Deployment" v={config.azureDeployment || "gpt-4.1"} mono />
                    <KVRow k="Source" v={`${ENGINE_ICONS[config.sourceEngine]} ${config.sourceEngine}`} />
                    <KVRow k="Target" v={`${ENGINE_ICONS[config.targetEngine]} ${config.targetEngine}`} />
                    <Divider />
                    <KVRow k="Output" v="mappings/draft/" mono />
                </div>
                <div style={{ padding: "0 16px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
                    <button onClick={run} disabled={phase === "running"} style={btnStyle(C.purple)}>
                        <Mono size={12} style={{ fontWeight: 600 }}>
                            {phase === "idle" ? "RUN LLM MAPPING" : phase === "running" ? "MAPPING…" : "RE-MAP"}
                        </Mono>
                    </button>
                    {phase === "done" && (
                        <button onClick={onNext} style={btnStyle(C.green)}>
                            <Mono size={12} style={{ fontWeight: 600 }}>NEXT: REVIEW →</Mono>
                        </button>
                    )}
                </div>
            </Panel>

            <Panel style={{ flex: 1 }}>
                <PanelHeader title="LLM Mapping Progress" right={phase === "running" && <StatusDot status="running" />} />
                <div style={{ padding: 16 }}>
                    {phase !== "idle" && (
                        <>
                            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                                <Mono size={11} color={C.text1}>
                                    {phase === "running" ? `Mapping: ${progress.current}…` : "All mappings generated"}
                                </Mono>
                                <Mono size={11} color={C.cyan}>{progress.done}/{progress.total}</Mono>
                            </div>
                            <ProgressBar value={progress.done} max={progress.total} color={C.purple} style={{ marginBottom: 16 }} />
                        </>
                    )}
                    <div style={{ fontFamily: G.fontMono, fontSize: 12, color: C.text1, lineHeight: 1.8, maxHeight: 400, overflowY: "auto" }}>
                        {phase === "idle" && <span style={{ color: C.text2 }}>— Press RUN LLM MAPPING to translate {config.sourceEngine} → {config.targetEngine} via Azure OpenAI —</span>}
                        {log.map((line, i) => (
                            <div key={i} style={{
                                color: line.includes("✓") ? C.green : line.includes("✗") ? C.red : C.text1,
                                animation: "fadeIn 0.2s ease",
                            }}>{line}</div>
                        ))}
                    </div>
                </div>
            </Panel>
        </div>
    );
}

// ─── Review Step ────────────────────────────────────────────────────────
function ReviewStep({ onNext }) {
    const [tables, setTables] = useState([]);
    const [selected, setSelected] = useState("");
    const [columns, setColumns] = useState([]);
    const [fullMapping, setFullMapping] = useState(null);
    const [dirty, setDirty] = useState(false);
    const [saving, setSaving] = useState(false);
    const [loading, setLoading] = useState(true);
    const [targetTable, setTargetTable] = useState("");

    useEffect(() => {
        getTables().then(data => {
            setTables(data.tables || []);
            if (data.tables?.length) setSelected(data.tables[0].name);
            setLoading(false);
        }).catch(() => setLoading(false));
    }, []);

    useEffect(() => {
        if (!selected) return;
        getMapping(selected).then(data => {
            const m = data.mapping || {};
            setFullMapping(m);
            setColumns(m.columns || []);
            setTargetTable(m.target_table || "");
            setDirty(false);
        }).catch(() => { setColumns([]); setFullMapping(null); });
    }, [selected]);

    function updateCol(idx, field, value) {
        setColumns(cols => cols.map((c, i) => i === idx ? { ...c, [field]: value } : c));
        setDirty(true);
    }

    function updateTargetTable(value) {
        setTargetTable(value);
        setDirty(true);
    }

    async function handleSave() {
        if (!fullMapping) return;
        setSaving(true);
        const updated = { ...fullMapping, target_table: targetTable, columns };
        await saveMapping(selected, updated);
        setFullMapping(updated);
        setDirty(false);
        setSaving(false);
    }

    async function approve(name) {
        if (dirty) await handleSave();
        await approveTable(name);
        setTables(ts => ts.map(t => t.name === name ? { ...t, status: "approved" } : t));
    }

    async function handleApproveAll() {
        if (dirty) await handleSave();
        await apiApproveAll();
        setTables(ts => ts.map(t => ({ ...t, status: "approved" })));
    }

    const allApproved = tables.length > 0 && tables.every(t => t.status === "approved");
    const selectedTable = tables.find(t => t.name === selected);

    const editInputStyle = {
        background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 4,
        color: C.text0, fontFamily: G.fontMono, fontSize: 12, padding: "4px 8px",
        width: "100%", outline: "none",
    };

    if (loading) return <Panel style={{ padding: 40, textAlign: "center" }}><Mono size={14} color={C.text2}>Loading tables…</Mono></Panel>;
    if (tables.length === 0) return <Panel style={{ padding: 40, textAlign: "center" }}><Mono size={14} color={C.amber}>No mappings found. Run Extract → LLM Map first.</Mono></Panel>;

    return (
        <div style={{ display: "flex", gap: 16, animation: "slideIn 0.3s ease" }}>
            <Panel style={{ flex: "0 0 260px" }}>
                <PanelHeader title="Tables" right={
                    <button onClick={handleApproveAll} style={{ ...smallBtnStyle(C.green), fontSize: 10 }}>APPROVE ALL</button>
                } />
                <div style={{ padding: 8, display: "flex", flexDirection: "column", gap: 4, maxHeight: 400, overflowY: "auto" }}>
                    {tables.map(t => (
                        <button key={t.name} onClick={() => setSelected(t.name)} style={{
                            display: "flex", alignItems: "center", gap: 10, padding: "8px 10px",
                            borderRadius: 6, border: `1px solid ${selected === t.name ? C.cyan + "50" : "transparent"}`,
                            background: selected === t.name ? C.cyanDim : "transparent",
                            cursor: "pointer", textAlign: "left", width: "100%", transition: "all 0.15s",
                        }}>
                            <StatusDot status={t.status} />
                            <Mono size={12} color={selected === t.name ? C.cyan : C.text0} style={{ flex: 1 }}>{t.name}</Mono>
                            <Mono size={10} color={C.text2}>{t.columns} cols</Mono>
                        </button>
                    ))}
                </div>
                <div style={{ padding: "8px 12px 12px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                        <Mono size={10} color={C.text2}>APPROVED</Mono>
                        <Mono size={10} color={C.green}>{tables.filter(t => t.status === "approved").length}/{tables.length}</Mono>
                    </div>
                    <ProgressBar value={tables.filter(t => t.status === "approved").length} max={tables.length} color={C.green} />
                </div>
                {allApproved && (
                    <div style={{ padding: "0 12px 12px" }}>
                        <button onClick={onNext} style={btnStyle(C.green)}>
                            <Mono size={12} style={{ fontWeight: 600 }}>MIGRATE →</Mono>
                        </button>
                    </div>
                )}
            </Panel>

            <Panel style={{ flex: 1 }}>
                <PanelHeader title={`Mapping: ${selected}`} right={
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        {dirty && <Badge label="MODIFIED" color={C.amber} />}
                        <Badge label={selectedTable?.status || "—"} color={selectedTable?.status === "approved" ? C.green : C.amber} />
                        {dirty && (
                            <button onClick={handleSave} disabled={saving} style={smallBtnStyle(C.cyan)}>
                                {saving ? "SAVING..." : "SAVE"}
                            </button>
                        )}
                        {selectedTable?.status !== "approved" && (
                            <button onClick={() => approve(selected)} style={smallBtnStyle(C.green)}>APPROVE</button>
                        )}
                    </div>
                } />
                {/* Editable target table name */}
                <div style={{ padding: "12px 14px 0", display: "flex", alignItems: "center", gap: 10 }}>
                    <Mono size={10} color={C.text2} style={{ textTransform: "uppercase", letterSpacing: "0.06em", minWidth: 90 }}>Target Table</Mono>
                    <input
                        value={targetTable}
                        onChange={e => updateTargetTable(e.target.value)}
                        style={{ ...editInputStyle, maxWidth: 350 }}
                    />
                </div>
                <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                        <thead>
                            <tr style={{ background: C.bg2 }}>
                                {["Source Column", "Source Type", "Canonical", "Target Column", "Target Type", "Role"].map(h => (
                                    <th key={h} style={{
                                        padding: "8px 14px", textAlign: "left",
                                        fontFamily: G.fontMono, fontSize: 10, fontWeight: 600,
                                        color: C.text2, letterSpacing: "0.06em", textTransform: "uppercase",
                                        borderBottom: `1px solid ${C.border}`,
                                    }}>{h}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {columns.map((col, i) => (
                                <tr key={col.source || i} style={{
                                    borderBottom: `1px solid ${C.border}`,
                                    background: i % 2 === 0 ? "transparent" : C.bg0 + "60",
                                }}>
                                    <td style={{ padding: "9px 14px" }}><Mono size={12} color={C.cyan}>{col.source}</Mono></td>
                                    <td style={{ padding: "9px 14px" }}><Mono size={11} color={C.text2}>{col.source_type_raw}</Mono></td>
                                    <td style={{ padding: "9px 14px" }}><Badge label={col.canonical_type} color={C.purple} /></td>
                                    <td style={{ padding: "5px 10px" }}>
                                        <input value={col.target} onChange={e => updateCol(i, "target", e.target.value)} style={editInputStyle} />
                                    </td>
                                    <td style={{ padding: "5px 10px" }}>
                                        <input value={col.target_type} onChange={e => updateCol(i, "target_type", e.target.value)} style={editInputStyle} />
                                    </td>
                                    <td style={{ padding: "9px 14px" }}>{col.role && <Badge label={col.role} color={C.amber} />}</td>
                                </tr>
                            ))}
                            {columns.length === 0 && (
                                <tr><td colSpan={6} style={{ padding: "20px 14px" }}>
                                    <Mono size={12} color={C.text2}>Select a table to view its column mapping</Mono>
                                </td></tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </Panel>
        </div>
    );
}

// ─── Migrate Step ───────────────────────────────────────────────────────
function MigrateStep({ config, onNext, onHome }) {
    const [phase, setPhase] = useState("idle");
    const [log, setLog] = useState([]);
    const [results, setResults] = useState([]);
    const [runId, setRunId] = useState(null);
    const logRef = useRef(null);

    async function run() {
        setPhase("running"); setLog([]); setResults([]);

        // First apply schema
        setLog(l => [...l, "Applying schema to target MySQL..."]);
        await runApplySchema(config, (ev) => {
            if (ev.type === "log") {
                setLog(l => [...l, ev.msg]);
                if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
            }
        });

        // Then migrate data
        setLog(l => [...l, "Starting data migration..."]);
        await runMigrate(config, (ev) => {
            if (ev.type === "log") {
                setLog(l => [...l, ev.msg]);
                if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
            }
            if (ev.type === "table_done") setResults(r => [...r, ev]);
            if (ev.type === "done") {
                setPhase("done");
                if (ev.run_id) setRunId(ev.run_id);
            }
            if (ev.type === "error") {
                setLog(l => [...l, `✗ ERROR: ${ev.msg}`]);
                setPhase("done");
            }
        });
    }

    const totalRows = results.reduce((a, r) => a + (r.rows || 0), 0);

    return (
        <div style={{ display: "flex", gap: 16, animation: "slideIn 0.3s ease" }}>
            <Panel style={{ flex: "0 0 280px" }}>
                <PanelHeader title="Migration" />
                <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                    <KVRow k="Source" v={`${ENGINE_ICONS[config.sourceEngine]} ${config.sourceEngine}`} />
                    <KVRow k="Target" v={`${ENGINE_ICONS[config.targetEngine]} ${config.targetEngine}`} />
                    <KVRow k="Chunk Size" v={`${config.chunkSize || "5,000"} rows`} mono />
                    <KVRow k="FK During Load" v={config.disableFk ? "Disabled" : "Enabled"} />
                    {totalRows > 0 && (
                        <>
                            <Divider />
                            <KVRow k="Total Rows" v={totalRows.toLocaleString()} mono />
                            <KVRow k="Tables Done" v={results.length} />
                        </>
                    )}
                </div>
                <div style={{ padding: "8px 16px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
                    <button onClick={phase === "done" ? onHome : run} disabled={phase === "running"} style={btnStyle(C.cyan)}>
                        <Mono size={12} style={{ fontWeight: 600 }}>
                            {phase === "idle" ? "START MIGRATION" : phase === "done" ? "COMPLETE ✓" : "MIGRATING…"}
                        </Mono>
                    </button>
                    {phase === "done" && (
                        <button onClick={onNext} style={btnStyle(C.green)}>
                            <Mono size={12} style={{ fontWeight: 600 }}>VALIDATE →</Mono>
                        </button>
                    )}
                    {results.some(r => r.failures > 0) && runId && (
                        <button onClick={() => window.open(`/api/dlq/${runId}/download`, '_blank')} style={{ ...btnStyle(C.amber), marginTop: 8 }}>
                            <Mono size={12} style={{ fontWeight: 600 }}>DOWNLOAD EXCEPTION DATA</Mono>
                        </button>
                    )}
                </div>
            </Panel>

            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 16 }}>
                {results.length > 0 && (
                    <Panel>
                        <PanelHeader title="Tables Migrated" right={<StatusDot status={phase === "done" ? "approved" : "running"} />} />
                        <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 6 }}>
                            {results.map(r => (
                                <div key={r.table} style={{
                                    display: "flex", alignItems: "center", gap: 12, padding: "7px 12px",
                                    borderRadius: 6, background: C.bg2, border: `1px solid ${r.failures > 0 ? C.amber + "60" : C.border}`,
                                }}>
                                    <StatusDot status={r.failures > 0 ? "error" : "approved"} />
                                    <Mono size={12} style={{ flex: 1, color: r.failures > 0 ? C.amber : C.text0 }}>{r.table}</Mono>
                                    <Mono size={11} color={r.failures > 0 ? C.amber : C.green}>{(r.rows || 0).toLocaleString()} rows</Mono>
                                    {r.failures > 0 && <Badge label={`⚠️ SENT TO DLQ`} color={C.red} />}
                                    {r.failures > 0 && <Mono size={10} color={C.red}>Check /dlq folder</Mono>}
                                </div>
                            ))}
                        </div>
                    </Panel>
                )}
                <Panel style={{ flex: 1 }}>
                    <PanelHeader title="Migration Log" />
                    <div ref={logRef} style={{
                        fontFamily: G.fontMono, fontSize: 12, color: C.text1,
                        padding: 16, maxHeight: 300, overflowY: "auto", lineHeight: 1.8,
                    }}>
                        {log.length === 0 && <span style={{ color: C.text2 }}>— Press START MIGRATION to apply schema and load data —</span>}
                        {log.map((line, i) => (
                            <div key={i} style={{
                                color: line.includes("✓") ? C.green : line.includes("✗") ? C.red :
                                    line.includes("CREATE") ? C.purple : C.text1,
                            }}>{line}</div>
                        ))}
                        {phase === "running" && <span style={{ color: C.cyan, animation: "blink 1s infinite" }}>█</span>}
                    </div>
                </Panel>
            </div>
        </div>
    );
}

// ─── Validate Step ──────────────────────────────────────────────────────
function ValidateStep({ config }) {
    const [phase, setPhase] = useState("idle");
    const [results, setResults] = useState([]);
    const [log, setLog] = useState([]);
    const [allPass, setAllPass] = useState(false);

    async function run() {
        setPhase("running"); setResults([]); setLog([]);
        await runValidate(config, (ev) => {
            if (ev.type === "log") setLog(l => [...l, ev.msg]);
            if (ev.type === "table_result") setResults(r => [...r, ev.result]);
            if (ev.type === "done") {
                setAllPass(ev.all_pass);
                setPhase("done");
            }
            if (ev.type === "error") {
                setLog(l => [...l, `✗ ERROR: ${ev.msg}`]);
                setPhase("done");
            }
        });
    }

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 16, animation: "slideIn 0.3s ease" }}>
            <div style={{ display: "flex", gap: 16 }}>
                <Panel style={{ flex: "0 0 280px" }}>
                    <PanelHeader title="Validation" />
                    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                        <KVRow k="Row Count Tolerance" v="0%" mono />
                        <KVRow k="Float Tolerance" v="0.0001" mono />
                        <KVRow k="Checks" v="L1 Row · L2 Agg · L3 Distinct" />
                    </div>
                    <div style={{ padding: "0 16px 16px" }}>
                        <button onClick={run} disabled={phase === "running"} style={btnStyle(C.cyan)}>
                            <Mono size={12} style={{ fontWeight: 600 }}>
                                {phase === "idle" ? "RUN VALIDATION" : phase === "running" ? "VALIDATING…" : "RE-VALIDATE"}
                            </Mono>
                        </button>
                    </div>
                </Panel>

                {phase === "done" && (
                    <div style={{ flex: 1, display: "flex", gap: 12, alignItems: "flex-start", flexWrap: "wrap" }}>
                        {[
                            { label: "Tables", value: results.length, color: C.cyan },
                            { label: "Passed", value: results.filter(r => r.pass).length, color: C.green },
                            { label: "Failed", value: results.filter(r => !r.pass).length, color: results.some(r => !r.pass) ? C.red : C.green },
                            { label: "Overall", value: allPass ? "PASS" : "FAIL", color: allPass ? C.green : C.red },
                        ].map(s => (
                            <Panel key={s.label} style={{ flex: "0 0 calc(25% - 9px)", padding: 16 }}>
                                <Mono size={20} style={{ fontWeight: 700, color: s.color, display: "block", marginBottom: 4 }}>{s.value}</Mono>
                                <Mono size={10} color={C.text2} style={{ letterSpacing: "0.06em", textTransform: "uppercase" }}>{s.label}</Mono>
                            </Panel>
                        ))}
                    </div>
                )}
            </div>

            <Panel>
                <PanelHeader title="Validation Results" right={phase === "running" && <StatusDot status="running" />} />
                <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                        <thead>
                            <tr style={{ background: C.bg2 }}>
                                {["Table", "Checks", "Passed", "Status"].map(h => (
                                    <th key={h} style={{
                                        padding: "8px 14px", textAlign: "left",
                                        fontFamily: G.fontMono, fontSize: 10, fontWeight: 600,
                                        color: C.text2, borderBottom: `1px solid ${C.border}`,
                                        letterSpacing: "0.06em", textTransform: "uppercase",
                                    }}>{h}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {results.map((r, i) => (
                                <tr key={r.target_table || i} style={{
                                    borderBottom: `1px solid ${C.border}`,
                                    background: i % 2 === 0 ? "transparent" : C.bg0 + "60",
                                    animation: "fadeIn 0.3s ease",
                                }}>
                                    <td style={{ padding: "9px 14px" }}><Mono size={12} color={C.cyan}>{r.target_table}</Mono></td>
                                    <td style={{ padding: "9px 14px" }}><Mono size={12}>{r.checks?.length || 0}</Mono></td>
                                    <td style={{ padding: "9px 14px" }}><Mono size={12} color={C.green}>{r.checks?.filter(c => c.pass).length || 0}</Mono></td>
                                    <td style={{ padding: "9px 14px" }}><Badge label={r.pass ? "PASS" : "FAIL"} color={r.pass ? C.green : C.red} /></td>
                                </tr>
                            ))}
                            {phase === "idle" && results.length === 0 && (
                                <tr><td colSpan={4} style={{ padding: "20px 14px" }}>
                                    <Mono size={12} color={C.text2}>— Run validation to compare source vs target —</Mono>
                                </td></tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </Panel>
        </div>
    );
}

// ─── Login Screen ─────────────────────────────────────────────────────────
function LoginScreen({ onLogin }) {
    const [user, setUser] = useState("");
    const [pwd, setPwd] = useState("");
    const [error, setError] = useState(false);
    const [loading, setLoading] = useState(false);

    async function handleLogin(e) {
        e.preventDefault();
        setLoading(true);
        const token = "Basic " + btoa(`${user.trim()}:${pwd.trim()}`);
        localStorage.setItem("dbAdminAuth", token);
        try {
            await getConfig();
            onLogin(token);
        } catch (err) {
            setError(true);
            localStorage.removeItem("dbAdminAuth");
        } finally {
            setLoading(false);
        }
    }

    return (
        <div style={{ minHeight: "100vh", background: C.bg0, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Panel style={{ width: 360, animation: "slideIn 0.3s ease" }}>
                <PanelHeader title="RESTRICTED ACCESS" />
                <form onSubmit={handleLogin} style={{ padding: 24, display: "flex", flexDirection: "column", gap: 16 }}>
                    <div style={{ textAlign: "center", marginBottom: 8 }}>
                        <img src={logoSrc} alt="Exavalu" style={{ height: 40 }} />
                    </div>
                    <Field label="Admin Username">
                        <Input value={user} onChange={v => { setUser(v); setError(false); }} placeholder="admin" error={error} disabled={loading} />
                    </Field>
                    <Field label="Admin Password">
                        <Input password value={pwd} onChange={v => { setPwd(v); setError(false); }} placeholder="••••••••" error={error} disabled={loading} />
                    </Field>
                    {error && <Mono size={10} color={C.red}>Invalid Credentials. Access Denied.</Mono>}
                    <button type="submit" disabled={loading} style={{ ...btnStyle(C.cyan), opacity: loading ? 0.5 : 1 }}>
                        {loading ? "AUTHENTICATING..." : "UNLOCK PIPELINE"}
                    </button>
                </form>
            </Panel>
        </div>
    );
}

// ─── App ────────────────────────────────────────────────────────────────
export default function App() {
    const [auth, setAuth] = useState(() => localStorage.getItem("dbAdminAuth"));
    const [step, setStep] = useState(0);
    const [config, setConfig] = useState({
        sourceEngine: "postgres", sourceHost: "", sourcePort: "5432",
        sourceDb: "", sourceUser: "", sourcePass: "",
        targetEngine: "mysql", targetHost: "", targetPort: "3306",
        targetDb: "", targetUser: "", targetPass: "",
        llmProvider: "azure_openai", azureDeployment: "", azureEndpoint: "",
        chunkSize: "5000", disableFk: true,
    });

    useEffect(() => {
        injectStyles();
        if (!auth) return;

        // Load real config from backend's config.yaml
        getConfig().then(cfg => {
            if (cfg?.source) {
                const srcEngine = cfg.source.engine || "postgres";
                const srcCreds = cfg.source[srcEngine] || {};
                const tgtEngine = cfg.target?.engine || "mysql";
                const tgtCreds = cfg.target?.[tgtEngine] || {};
                setConfig(c => ({
                    ...c,
                    sourceEngine: srcEngine,
                    sourceHost: srcCreds.host || "",
                    sourcePort: srcCreds.port ? String(srcCreds.port) : "",
                    sourceDb: srcCreds.database || "",
                    sourceUser: srcCreds.user || "",
                    sourcePass: srcCreds.password || "",
                    targetEngine: tgtEngine,
                    targetHost: tgtCreds.host || "",
                    targetPort: tgtCreds.port ? String(tgtCreds.port) : "",
                    targetDb: tgtCreds.database || "",
                    targetUser: tgtCreds.user || "",
                    targetPass: tgtCreds.password || "",
                    llmProvider: cfg.llm?.provider || "azure_openai",
                    azureDeployment: cfg.llm?.azure_deployment || "",
                    azureEndpoint: cfg.llm?.azure_endpoint || "",
                    chunkSize: String(cfg.migration?.chunk_size || "5000"),
                    disableFk: cfg.migration?.disable_fk_during_load !== false,
                }));
            }
        }).catch(() => { });
    }, []);

    const stepComponents = [
        <ConfigStep config={config} setConfig={setConfig} onNext={() => setStep(1)} />,
        <ExtractStep config={config} onNext={() => setStep(2)} />,
        <ProposeStep config={config} onNext={() => setStep(3)} />,
        <ReviewStep onNext={() => setStep(4)} />,
        <MigrateStep config={config} onNext={() => setStep(5)} onHome={() => setStep(0)} />,
        <ValidateStep config={config} />,
    ];

    if (!auth) return <LoginScreen onLogin={setAuth} />;

    return (
        <div style={{ minHeight: "100vh", background: C.bg0, display: "flex", flexDirection: "column" }}>
            {/* Top bar */}
            <div style={{
                background: C.bg0, borderBottom: `1px solid ${C.border}`,
                padding: "0 28px", height: 54,
                display: "flex", alignItems: "center", justifyContent: "space-between",
                position: "sticky", top: 0, zIndex: 100,
            }}>
                <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                    <img src={logoSrc} alt="Exavalu" style={{ height: 35 }} />
                </div>
                <div style={{
                    display: "flex", alignItems: "center", gap: 10,
                    position: "absolute", left: "50%", transform: "translateX(-50%)"
                }}>
                    <div style={{
                        padding: "5px 12px", borderRadius: 4,
                        background: ENGINE_COLORS[config.sourceEngine] + "18",
                        border: `1px solid ${ENGINE_COLORS[config.sourceEngine]}40`,
                    }}>
                        <Mono size={12} color={ENGINE_COLORS[config.sourceEngine]}>
                            {ENGINE_ICONS[config.sourceEngine]} {config.sourceEngine}
                        </Mono>
                    </div>
                    <Mono size={16} color={C.text2}>→</Mono>
                    <div style={{
                        padding: "5px 12px", borderRadius: 4,
                        background: ENGINE_COLORS[config.targetEngine] + "18",
                        border: `1px solid ${ENGINE_COLORS[config.targetEngine]}40`,
                    }}>
                        <Mono size={12} color={ENGINE_COLORS[config.targetEngine]}>
                            {ENGINE_ICONS[config.targetEngine]} {config.targetEngine}
                        </Mono>
                    </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <button onClick={() => setStep(0)} style={{
                        padding: "5px 14px", borderRadius: 4,
                        background: C.cyan + "18", border: `1px solid ${C.cyan}40`,
                        color: C.cyan, cursor: "pointer", fontFamily: G.fontMono,
                        fontSize: 11, fontWeight: 600, letterSpacing: "0.05em",
                        transition: "all 0.15s",
                    }}>HOME</button>
                </div>
            </div>

            {/* Pipeline stepper */}
            <div style={{
                background: C.bg1, borderBottom: `1px solid ${C.border}`,
                padding: "0 28px", display: "flex", alignItems: "center",
            }}>
                {STEPS.map((s, i) => (
                    <div key={s.id} style={{ display: "flex", alignItems: "center" }}>
                        <div style={{
                            display: "flex", alignItems: "center", gap: 8,
                            padding: "14px 16px", border: "none", background: "transparent",
                            borderBottom: `2px solid ${i === step ? C.cyan : "transparent"}`,
                            cursor: "default", pointerEvents: "none", opacity: i > step ? 0.6 : 1, transition: "all 0.2s",
                        }}>
                            <div style={{
                                width: 22, height: 22, borderRadius: "50%",
                                background: i < step ? C.greenDim : i === step ? C.cyanDim : C.bg3,
                                border: `1px solid ${i < step ? C.green : i === step ? C.cyan : C.border}`,
                                display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
                            }}>
                                {i < step
                                    ? <span style={{ fontSize: 10, color: C.green }}>✓</span>
                                    : <Mono size={10} color={i === step ? C.cyan : C.text2}>{s.icon}</Mono>
                                }
                            </div>
                            <Mono size={11} color={i < step ? C.green : i === step ? C.cyan : C.text2}
                                style={{ fontWeight: i === step ? 600 : 400, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                                {s.label}
                            </Mono>
                        </div>
                        {i < STEPS.length - 1 && <PipelineArrow active={i < step} />}
                    </div>
                ))}
            </div>

            {/* Main content */}
            <div style={{ flex: 1, padding: 24 }}>{stepComponents[step]}</div>

            {/* Footer */}
            <div style={{
                borderTop: `1px solid ${C.border}`, padding: "10px 28px",
                display: "flex", justifyContent: "space-between", alignItems: "center", background: C.bg1,
            }}>
                <Mono size={11} color={C.text2}>
                    Bi Doctor DB Migration · {STEPS[step].label}
                </Mono>
                <Mono size={11} color={C.text2}>schemas/ · mappings/ · ddl/ · reports/</Mono>
            </div>
        </div>
    );
}
