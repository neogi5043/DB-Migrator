import { useState, useEffect, useRef } from "react";

// ─── Palette & Tokens ──────────────────────────────────────────────────────
const C = {
    bg0: "#0a0c0f",
    bg1: "#0f1217",
    bg2: "#151a21",
    bg3: "#1c2330",
    border: "#232d3a",
    borderHi: "#2e3f54",
    cyan: "#38bdf8",
    cyanDim: "#0e4a6b",
    green: "#34d399",
    greenDim: "#064e3b",
    amber: "#fbbf24",
    amberDim: "#451a03",
    red: "#f87171",
    redDim: "#450a0a",
    purple: "#a78bfa",
    purpleDim: "#2e1065",
    text0: "#e2e8f0",
    text1: "#94a3b8",
    text2: "#4b5563",
};

const SOURCE_ENGINES = ["postgres", "mysql", "oracle", "mssql", "teradata"];
const TARGET_ENGINES = ["mysql", "postgres", "snowflake", "bigquery", "azure_synapse"];

const ENGINE_ICONS = {
    postgres: "🐘", mysql: "🐬", oracle: "🔴", mssql: "🪟",
    teradata: "🔷", snowflake: "❄️", bigquery: "📊", azure_synapse: "🔵",
};

const ENGINE_COLORS = {
    postgres: C.cyan, mysql: C.amber, oracle: C.red, mssql: C.purple,
    teradata: C.cyan, snowflake: "#67e8f9", bigquery: "#60a5fa", azure_synapse: "#818cf8",
};

// ─── Mock Data ─────────────────────────────────────────────────────────────
const MOCK_TABLES = [
    { name: "users", rows: 184203, status: "approved", columns: 12, warnings: 0 },
    { name: "orders", rows: 1024891, status: "approved", columns: 18, warnings: 1 },
    { name: "products", rows: 48712, status: "pending", columns: 15, warnings: 2 },
    { name: "payments", rows: 897234, status: "pending", columns: 22, warnings: 0 },
    { name: "sessions", rows: 5128004, status: "pending", columns: 8, warnings: 3 },
    { name: "audit_log", rows: 3201447, status: "pending", columns: 10, warnings: 0 },
];

const MOCK_COLUMNS_USERS = [
    { src: "id", srcType: "integer", canon: "INT4", tgt: "INT", tgtType: "INT", role: "primary_key", warning: null },
    { src: "email", srcType: "varchar(255)", canon: "TEXT", tgt: "VARCHAR(255)", tgtType: "VARCHAR(255)", role: null, warning: null },
    { src: "created_at", srcType: "timestamptz", canon: "DATETIMETZ", tgt: "DATETIME", tgtType: "DATETIME", role: null, warning: "Postgres TIMESTAMPTZ → MySQL DATETIME loses timezone info" },
    { src: "profile_json", srcType: "jsonb", canon: "JSON", tgt: "JSON", tgtType: "JSON", role: null, warning: null },
    { src: "is_active", srcType: "boolean", canon: "BOOL", tgt: "TINYINT(1)", tgtType: "TINYINT(1)", role: null, warning: null },
    { src: "balance", srcType: "numeric(18,4)", canon: "DECIMAL", tgt: "DECIMAL(18,4)", tgtType: "DECIMAL(18,4)", role: null, warning: null },
];

const MOCK_LOG = [
    "[10:02:01] Extractor connected to source postgres://prod-db:5432/app_db",
    "[10:02:02] Discovered 6 tables across schema: public",
    "[10:02:04] Extracted schema spec → schemas/app_db.json (184 KB)",
    "[10:02:05] Collected column statistics for 6 tables",
    "[10:02:06] LLM mapping started — model: gpt-4o",
    "[10:02:11] Draft mappings written → mappings/draft/ (6 files)",
    "[10:02:11] Awaiting human review...",
];

const MIGRATE_LOG = [
    "[10:15:00] Schema applied to target mysql://staging-db:3306/app_dw",
    "[10:15:01] Migrating table: users (184,203 rows)",
    "[10:15:08] ✓ users complete — 184,203 rows loaded",
    "[10:15:08] Migrating table: orders (1,024,891 rows)",
    "[10:15:31] ✓ orders complete — 1,024,891 rows loaded",
    "[10:15:31] Migrating table: products (48,712 rows)",
    "[10:15:34] ✓ products complete — 48,712 rows loaded",
];

// ─── Styles ────────────────────────────────────────────────────────────────
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
    @keyframes scanline {
      0%{transform:translateY(-100%)} 100%{transform:translateY(100vh)}
    }
    @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
    @keyframes flow {
      0%{stroke-dashoffset:24} 100%{stroke-dashoffset:0}
    }
    @keyframes fadeIn { from{opacity:0} to{opacity:1} }
    @keyframes shimmer {
      0%{background-position:-200% 0} 100%{background-position:200% 0}
    }
  `;
    const el = document.createElement("style");
    el.textContent = css;
    document.head.appendChild(el);
}

// ─── Utility Components ─────────────────────────────────────────────────────

function Mono({ children, color, size = 12, style = {} }) {
    return (
        <span style={{ fontFamily: G.fontMono, color: color || C.text1, fontSize: size, ...style }}>
            {children}
        </span>
    );
}

function Badge({ label, color = C.cyan, bg }) {
    return (
        <span style={{
            fontFamily: G.fontMono, fontSize: 10, fontWeight: 600,
            color, background: bg || color + "18",
            border: `1px solid ${color}40`,
            padding: "2px 8px", borderRadius: 3, letterSpacing: "0.05em",
            textTransform: "uppercase",
        }}>
            {label}
        </span>
    );
}

function StatusDot({ status }) {
    const map = {
        approved: C.green, pending: C.amber, error: C.red, running: C.cyan,
    };
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
        }}>
            {children}
        </div>
    );
}

function PanelHeader({ title, right, icon }) {
    return (
        <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "10px 16px", borderBottom: `1px solid ${C.border}`,
            background: C.bg2,
        }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {icon && <span style={{ fontSize: 14 }}>{icon}</span>}
                <Mono size={11} color={C.text0} style={{ fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                    {title}
                </Mono>
            </div>
            {right}
        </div>
    );
}

function ProgressBar({ value, max, color = C.cyan, style = {} }) {
    const pct = Math.min(100, (value / max) * 100);
    return (
        <div style={{
            height: 4, background: C.bg3, borderRadius: 2, overflow: "hidden", ...style,
        }}>
            <div style={{
                width: `${pct}%`, height: "100%",
                background: `linear-gradient(90deg, ${color}aa, ${color})`,
                transition: "width 0.4s ease", borderRadius: 2,
            }} />
        </div>
    );
}

// ─── Pipeline Flow SVG ──────────────────────────────────────────────────────
function PipelineArrow({ active }) {
    return (
        <svg width="32" height="16" viewBox="0 0 32 16" style={{ flexShrink: 0 }}>
            <line x1="0" y1="8" x2="28" y2="8"
                stroke={active ? C.cyan : C.border}
                strokeWidth="1.5"
                strokeDasharray="4 4"
                style={{ animation: active ? "flow 0.8s linear infinite" : "none" }}
            />
            <polygon points="24,4 32,8 24,12" fill={active ? C.cyan : C.border} />
        </svg>
    );
}

// ─── Steps ─────────────────────────────────────────────────────────────────
const STEPS = [
    { id: "config", label: "Configure", icon: "⚙" },
    { id: "extract", label: "Extract", icon: "⬇" },
    { id: "propose", label: "LLM Map", icon: "◈" },
    { id: "review", label: "Review", icon: "✎" },
    { id: "migrate", label: "Migrate", icon: "⇒" },
    { id: "validate", label: "Validate", icon: "✓" },
];

// ─── Config Step ────────────────────────────────────────────────────────────
function ConfigStep({ config, setConfig, onNext }) {
    const [errors, setErrors] = useState({});

    function validate() {
        const e = {};
        if (!config.sourceDb) e.sourceDb = "Required";
        if (!config.targetDb) e.targetDb = "Required";
        if (config.sourceEngine === config.targetEngine) e.sameEngine = "Source and target cannot be the same engine";
        return e;
    }

    function handleNext() {
        const e = validate();
        if (Object.keys(e).length) { setErrors(e); return; }
        onNext();
    }

    return (
        <div style={{ display: "flex", gap: 16, animation: "slideIn 0.3s ease" }}>
            {/* Source */}
            <Panel style={{ flex: 1 }}>
                <PanelHeader title="Source Database" icon={ENGINE_ICONS[config.sourceEngine]} />
                <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
                    <Field label="Engine">
                        <EngineSelect
                            value={config.sourceEngine}
                            options={SOURCE_ENGINES}
                            onChange={v => setConfig(c => ({ ...c, sourceEngine: v }))}
                        />
                    </Field>
                    <Field label="Host">
                        <Input value={config.sourceHost} onChange={v => setConfig(c => ({ ...c, sourceHost: v }))}
                            placeholder="prod-db.internal" mono />
                    </Field>
                    <div style={{ display: "flex", gap: 10 }}>
                        <Field label="Port" style={{ flex: "0 0 90px" }}>
                            <Input value={config.sourcePort} onChange={v => setConfig(c => ({ ...c, sourcePort: v }))}
                                placeholder="5432" mono />
                        </Field>
                        <Field label="Database" style={{ flex: 1 }}>
                            <Input value={config.sourceDb} onChange={v => setConfig(c => ({ ...c, sourceDb: v }))}
                                placeholder="app_db" mono error={errors.sourceDb} />
                        </Field>
                    </div>
                    <Field label="Schema Filter">
                        <Input value={config.sourceSchema} onChange={v => setConfig(c => ({ ...c, sourceSchema: v }))}
                            placeholder="public (leave blank for all)" mono />
                    </Field>
                    <Field label="DSN / Connection String">
                        <Input value={config.sourceDsn} onChange={v => setConfig(c => ({ ...c, sourceDsn: v }))}
                            placeholder="${SRC_PG_DSN}" mono password />
                    </Field>
                </div>
            </Panel>

            {/* Arrow */}
            <div style={{ display: "flex", alignItems: "center", paddingTop: 24 }}>
                <svg width="48" height="48" viewBox="0 0 48 48">
                    <text x="24" y="30" textAnchor="middle" fontSize="22"
                        fill={C.cyan} style={{ fontFamily: G.fontMono }}>→</text>
                </svg>
            </div>

            {/* Target */}
            <Panel style={{ flex: 1 }}>
                <PanelHeader title="Target Database" icon={ENGINE_ICONS[config.targetEngine]} />
                <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
                    <Field label="Engine">
                        <EngineSelect
                            value={config.targetEngine}
                            options={TARGET_ENGINES}
                            onChange={v => setConfig(c => ({ ...c, targetEngine: v }))}
                        />
                    </Field>
                    <Field label="Host">
                        <Input value={config.targetHost} onChange={v => setConfig(c => ({ ...c, targetHost: v }))}
                            placeholder="staging-db.internal" mono />
                    </Field>
                    <div style={{ display: "flex", gap: 10 }}>
                        <Field label="Port" style={{ flex: "0 0 90px" }}>
                            <Input value={config.targetPort} onChange={v => setConfig(c => ({ ...c, targetPort: v }))}
                                placeholder="3306" mono />
                        </Field>
                        <Field label="Database" style={{ flex: 1 }}>
                            <Input value={config.targetDb} onChange={v => setConfig(c => ({ ...c, targetDb: v }))}
                                placeholder="app_dw" mono error={errors.targetDb} />
                        </Field>
                    </div>
                    <Field label="Schema">
                        <Input value={config.targetSchema} onChange={v => setConfig(c => ({ ...c, targetSchema: v }))}
                            placeholder="dw" mono />
                    </Field>
                    <Field label="DSN / Connection String">
                        <Input value={config.targetDsn} onChange={v => setConfig(c => ({ ...c, targetDsn: v }))}
                            placeholder="${TARGET_MYSQL_DSN}" mono password />
                    </Field>
                </div>
            </Panel>

            {/* LLM Config */}
            <Panel style={{ flex: "0 0 280px" }}>
                <PanelHeader title="LLM Settings" icon="◈" />
                <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
                    <Field label="Provider">
                        <EngineSelect
                            value={config.llmProvider}
                            options={["openai", "anthropic"]}
                            onChange={v => setConfig(c => ({ ...c, llmProvider: v }))}
                        />
                    </Field>
                    <Field label="Model">
                        <Input value={config.llmModel} onChange={v => setConfig(c => ({ ...c, llmModel: v }))}
                            placeholder="gpt-4o" mono />
                    </Field>
                    <Field label="API Key">
                        <Input value={config.llmKey} onChange={v => setConfig(c => ({ ...c, llmKey: v }))}
                            placeholder="${OPENAI_API_KEY}" mono password />
                    </Field>

                    <Divider style={{ margin: "4px 0" }} />

                    <Field label="Chunk Size (rows)">
                        <Input value={config.chunkSize} onChange={v => setConfig(c => ({ ...c, chunkSize: v }))}
                            placeholder="100000" mono />
                    </Field>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 4 }}>
                        <Toggle
                            checked={config.disableFk}
                            onChange={v => setConfig(c => ({ ...c, disableFk: v }))}
                        />
                        <span style={{ fontSize: 12, color: C.text1 }}>Disable FK during load</span>
                    </div>

                    {errors.sameEngine && (
                        <div style={{ color: C.red, fontSize: 12, padding: "8px 12px", background: C.redDim, borderRadius: 4 }}>
                            {errors.sameEngine}
                        </div>
                    )}
                </div>

                <div style={{ padding: "12px 20px 20px" }}>
                    <button onClick={handleNext} style={btnStyle(C.cyan)}>
                        <span style={{ fontFamily: G.fontMono, fontSize: 12, fontWeight: 600 }}>
                            SAVE & CONTINUE →
                        </span>
                    </button>
                </div>
            </Panel>
        </div>
    );
}

// ─── Extract Step ───────────────────────────────────────────────────────────
function ExtractStep({ config, onNext }) {
    const [phase, setPhase] = useState("idle"); // idle | running | done
    const [log, setLog] = useState([]);
    const [progress, setProgress] = useState(0);
    const logRef = useRef(null);

    function run() {
        setPhase("running");
        setLog([]);
        setProgress(0);
        MOCK_LOG.forEach((line, i) => {
            setTimeout(() => {
                setLog(l => [...l, line]);
                setProgress((i + 1) / MOCK_LOG.length * 100);
                if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
                if (i === MOCK_LOG.length - 1) setPhase("done");
            }, i * 650);
        });
    }

    return (
        <div style={{ display: "flex", gap: 16, animation: "slideIn 0.3s ease" }}>
            <Panel style={{ flex: "0 0 280px" }}>
                <PanelHeader title="Extraction Config" icon="⬇" />
                <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                    <KVRow k="Source" v={`${ENGINE_ICONS[config.sourceEngine]} ${config.sourceEngine}`} />
                    <KVRow k="Host" v={config.sourceHost || "prod-db.internal"} mono />
                    <KVRow k="Database" v={config.sourceDb || "app_db"} mono />
                    <KVRow k="Schema" v={config.sourceSchema || "public"} mono />
                    <Divider />
                    <KVRow k="Output" v="schemas/ + stats/" mono />
                    <KVRow k="Sample rows" v="1,000 per column" />
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
                <PanelHeader
                    title="Extraction Log"
                    right={phase === "running" && <StatusDot status="running" />}
                />
                {phase !== "idle" && (
                    <div style={{ padding: "10px 16px 0" }}>
                        <ProgressBar value={progress} max={100} />
                    </div>
                )}
                <div ref={logRef} style={{
                    fontFamily: G.fontMono, fontSize: 12, color: C.text1,
                    padding: 16, minHeight: 220, maxHeight: 400, overflowY: "auto",
                    lineHeight: 1.8,
                }}>
                    {phase === "idle" && (
                        <span style={{ color: C.text2 }}>— Press RUN EXTRACT to begin —</span>
                    )}
                    {log.map((line, i) => (
                        <div key={i} style={{
                            color: line.includes("✓") ? C.green :
                                line.includes("Awaiting") ? C.amber : C.text1,
                            animation: "fadeIn 0.2s ease",
                        }}>
                            {line}
                        </div>
                    ))}
                    {phase === "running" && (
                        <span style={{ color: C.cyan, animation: "blink 1s infinite" }}>█</span>
                    )}
                </div>
                {phase === "done" && (
                    <div style={{ padding: 16, borderTop: `1px solid ${C.border}` }}>
                        <div style={{ display: "flex", gap: 16 }}>
                            {[
                                { label: "Tables", value: 6, color: C.cyan },
                                { label: "Columns", value: 85, color: C.green },
                                { label: "Total Rows", value: "10.5M", color: C.amber },
                                { label: "Schema Size", value: "184 KB", color: C.text1 },
                            ].map(s => (
                                <div key={s.label} style={{ textAlign: "center", flex: 1 }}>
                                    <div style={{ fontFamily: G.fontMono, fontSize: 22, fontWeight: 600, color: s.color }}>
                                        {s.value}
                                    </div>
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

// ─── Propose Step ────────────────────────────────────────────────────────────
function ProposeStep({ config, onNext }) {
    const [phase, setPhase] = useState("idle");
    const [progress, setProgress] = useState(0);
    const [currentTable, setCurrentTable] = useState("");
    const [done, setDone] = useState(0);

    function run() {
        setPhase("running");
        setProgress(0); setDone(0);
        MOCK_TABLES.forEach((t, i) => {
            setTimeout(() => {
                setCurrentTable(t.name);
                setDone(i + 1);
                setProgress((i + 1) / MOCK_TABLES.length * 100);
                if (i === MOCK_TABLES.length - 1) { setPhase("done"); setCurrentTable(""); }
            }, i * 900 + 400);
        });
    }

    return (
        <div style={{ display: "flex", gap: 16, animation: "slideIn 0.3s ease" }}>
            <Panel style={{ flex: "0 0 280px" }}>
                <PanelHeader title="LLM Mapping Config" icon="◈" />
                <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                    <KVRow k="Provider" v={config.llmProvider} />
                    <KVRow k="Model" v={config.llmModel || "gpt-4o"} mono />
                    <KVRow k="Source Engine" v={config.sourceEngine} />
                    <KVRow k="Target Engine" v={config.targetEngine} />
                    <KVRow k="Prompt Version" v="v1" mono />
                    <Divider />
                    <KVRow k="Output" v="mappings/draft/" mono />
                    <KVRow k="Tables" v={MOCK_TABLES.length} />
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
                <PanelHeader
                    title="LLM Mapping Progress"
                    right={phase === "running" && <StatusDot status="running" />}
                />
                <div style={{ padding: 16 }}>
                    {phase !== "idle" && (
                        <>
                            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                                <Mono size={11} color={C.text1}>
                                    {phase === "running" ? `Mapping: ${currentTable}…` : "All mappings generated"}
                                </Mono>
                                <Mono size={11} color={C.cyan}>{done}/{MOCK_TABLES.length}</Mono>
                            </div>
                            <ProgressBar value={progress} max={100} color={C.purple} style={{ marginBottom: 16 }} />
                        </>
                    )}
                    {phase === "idle" && (
                        <div style={{ color: C.text2, fontFamily: G.fontMono, fontSize: 12, padding: "20px 0" }}>
                            — Press RUN LLM MAPPING to generate draft mappings —
                        </div>
                    )}
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        {MOCK_TABLES.map((t, i) => {
                            const isDone = done > i || phase === "done";
                            const isActive = phase === "running" && done === i;
                            return (
                                <div key={t.name} style={{
                                    display: "flex", alignItems: "center", gap: 12,
                                    padding: "8px 12px",
                                    background: isActive ? C.purpleDim : isDone ? C.bg2 : "transparent",
                                    borderRadius: 6, border: `1px solid ${isActive ? C.purple + "60" : isDone ? C.border : "transparent"}`,
                                    transition: "all 0.3s ease",
                                }}>
                                    <StatusDot status={isActive ? "running" : isDone ? "approved" : "pending"} />
                                    <Mono size={12} color={isDone ? C.text0 : C.text2} style={{ flex: 1 }}>{t.name}</Mono>
                                    {isDone && <Mono size={10} color={C.text2}>{t.columns} cols</Mono>}
                                    {isDone && t.warnings > 0 && (
                                        <Badge label={`${t.warnings} warn`} color={C.amber} />
                                    )}
                                    {isDone && <Badge label="draft" color={C.purple} />}
                                </div>
                            );
                        })}
                    </div>
                </div>
            </Panel>
        </div>
    );
}

// ─── Review Step ─────────────────────────────────────────────────────────────
function ReviewStep({ onNext }) {
    const [tables, setTables] = useState(MOCK_TABLES.map(t => ({ ...t })));
    const [selected, setSelected] = useState("users");
    const selectedTable = tables.find(t => t.name === selected);
    const allApproved = tables.every(t => t.status === "approved");

    function approve(name) {
        setTables(ts => ts.map(t => t.name === name ? { ...t, status: "approved" } : t));
    }
    function approveAll() {
        setTables(ts => ts.map(t => ({ ...t, status: "approved" })));
    }

    return (
        <div style={{ display: "flex", gap: 16, animation: "slideIn 0.3s ease" }}>
            {/* Table list */}
            <Panel style={{ flex: "0 0 240px" }}>
                <PanelHeader
                    title="Tables"
                    right={
                        <button onClick={approveAll} style={{
                            ...smallBtnStyle(C.green), fontSize: 10
                        }}>APPROVE ALL</button>
                    }
                />
                <div style={{ padding: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                    {tables.map(t => (
                        <button key={t.name} onClick={() => setSelected(t.name)}
                            style={{
                                display: "flex", alignItems: "center", gap: 10, padding: "8px 10px",
                                borderRadius: 6, border: `1px solid ${selected === t.name ? C.cyan + "50" : "transparent"}`,
                                background: selected === t.name ? C.cyanDim : "transparent",
                                cursor: "pointer", textAlign: "left", width: "100%",
                                transition: "all 0.15s",
                            }}>
                            <StatusDot status={t.status} />
                            <Mono size={12} color={selected === t.name ? C.cyan : C.text0} style={{ flex: 1 }}>{t.name}</Mono>
                            {t.warnings > 0 && (
                                <span style={{ fontSize: 10, color: C.amber }}>⚠ {t.warnings}</span>
                            )}
                        </button>
                    ))}
                </div>
                <div style={{ padding: "8px 12px 12px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                        <Mono size={10} color={C.text2}>APPROVED</Mono>
                        <Mono size={10} color={C.green}>
                            {tables.filter(t => t.status === "approved").length}/{tables.length}
                        </Mono>
                    </div>
                    <ProgressBar
                        value={tables.filter(t => t.status === "approved").length}
                        max={tables.length}
                        color={C.green}
                    />
                </div>
                {allApproved && (
                    <div style={{ padding: "0 12px 12px" }}>
                        <button onClick={onNext} style={btnStyle(C.green)}>
                            <Mono size={12} style={{ fontWeight: 600 }}>MIGRATE →</Mono>
                        </button>
                    </div>
                )}
            </Panel>

            {/* Column mapping */}
            <Panel style={{ flex: 1 }}>
                <PanelHeader
                    title={`Mapping: ${selected}`}
                    icon="✎"
                    right={
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            <Badge
                                label={selectedTable?.status}
                                color={selectedTable?.status === "approved" ? C.green : C.amber}
                            />
                            {selectedTable?.status !== "approved" && (
                                <button onClick={() => approve(selected)} style={smallBtnStyle(C.green)}>
                                    ✓ APPROVE
                                </button>
                            )}
                        </div>
                    }
                />
                <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                        <thead>
                            <tr style={{ background: C.bg2 }}>
                                {["Source Column", "Source Type", "Canonical", "Target Column", "Target Type", "Role", ""].map(h => (
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
                            {MOCK_COLUMNS_USERS.map((col, i) => (
                                <tr key={col.src} style={{
                                    borderBottom: `1px solid ${C.border}`,
                                    background: i % 2 === 0 ? "transparent" : C.bg0 + "60",
                                }}>
                                    <td style={{ padding: "9px 14px" }}>
                                        <Mono size={12} color={C.cyan}>{col.src}</Mono>
                                    </td>
                                    <td style={{ padding: "9px 14px" }}>
                                        <Mono size={11} color={C.text2}>{col.srcType}</Mono>
                                    </td>
                                    <td style={{ padding: "9px 14px" }}>
                                        <Badge label={col.canon} color={C.purple} />
                                    </td>
                                    <td style={{ padding: "9px 14px" }}>
                                        <Mono size={12} color={C.text0}>{col.tgt}</Mono>
                                    </td>
                                    <td style={{ padding: "9px 14px" }}>
                                        <Mono size={11} color={C.green}>{col.tgtType}</Mono>
                                    </td>
                                    <td style={{ padding: "9px 14px" }}>
                                        {col.role && <Badge label={col.role} color={C.amber} />}
                                    </td>
                                    <td style={{ padding: "9px 14px" }}>
                                        {col.warning && (
                                            <span title={col.warning} style={{ cursor: "help", color: C.amber, fontSize: 13 }}>⚠</span>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                {/* Warnings section */}
                {MOCK_COLUMNS_USERS.some(c => c.warning) && (
                    <div style={{ padding: 14, borderTop: `1px solid ${C.border}` }}>
                        <Mono size={10} color={C.text2} style={{ display: "block", marginBottom: 8, letterSpacing: "0.06em" }}>
                            WARNINGS
                        </Mono>
                        {MOCK_COLUMNS_USERS.filter(c => c.warning).map(c => (
                            <div key={c.src} style={{
                                display: "flex", gap: 8, padding: "7px 12px",
                                background: C.amberDim, borderRadius: 4, marginBottom: 6,
                                border: `1px solid ${C.amber}30`,
                            }}>
                                <span style={{ color: C.amber, fontSize: 13 }}>⚠</span>
                                <Mono size={11} color={C.amber}>[{c.src}]</Mono>
                                <span style={{ fontSize: 12, color: C.text1 }}>{c.warning}</span>
                            </div>
                        ))}
                    </div>
                )}
            </Panel>
        </div>
    );
}

// ─── Migrate Step ────────────────────────────────────────────────────────────
function MigrateStep({ config, onNext }) {
    const [phase, setPhase] = useState("idle");
    const [log, setLog] = useState([]);
    const [tableProgress, setTableProgress] = useState({});
    const logRef = useRef(null);

    const totalRows = MOCK_TABLES.reduce((a, t) => a + t.rows, 0);

    function run() {
        setPhase("schema");
        setLog([]);
        setTableProgress({});

        const schemaLogs = [
            "[10:15:00] Applying schema to target...",
            `[10:15:00] CREATE TABLE users ... OK`,
            `[10:15:00] CREATE TABLE orders ... OK`,
            `[10:15:01] CREATE TABLE products ... OK`,
            `[10:15:01] CREATE TABLE payments ... OK`,
            `[10:15:01] CREATE TABLE sessions ... OK`,
            `[10:15:01] CREATE TABLE audit_log ... OK`,
            `[10:15:02] Schema applied. Starting data migration...`,
        ];

        schemaLogs.forEach((l, i) => {
            setTimeout(() => {
                setLog(prev => [...prev, l]);
                if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
                if (i === schemaLogs.length - 1) {
                    setPhase("data");
                    runDataMigration();
                }
            }, i * 200);
        });
    }

    function runDataMigration() {
        MOCK_TABLES.forEach((t, ti) => {
            const startDelay = ti * 2000;
            const chunks = Math.ceil(t.rows / 100000);

            setTimeout(() => {
                setLog(prev => [...prev, `[+${(ti * 2).toFixed(0).padStart(2, "0")}s] Migrating table: ${t.name} (${t.rows.toLocaleString()} rows, ${chunks} chunk${chunks > 1 ? "s" : ""})`]);
                setTableProgress(p => ({ ...p, [t.name]: { done: 0, total: t.rows, status: "running" } }));
            }, startDelay);

            for (let c = 0; c < chunks; c++) {
                const rowsDone = Math.min((c + 1) * 100000, t.rows);
                setTimeout(() => {
                    setTableProgress(p => ({
                        ...p,
                        [t.name]: { ...p[t.name], done: rowsDone },
                    }));
                    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
                }, startDelay + (c + 1) * 400);
            }

            setTimeout(() => {
                setLog(prev => [...prev, `[+${(ti * 2 + 1.8).toFixed(1)}s] ✓ ${t.name} — ${t.rows.toLocaleString()} rows loaded`]);
                setTableProgress(p => ({ ...p, [t.name]: { ...p[t.name], status: "done" } }));
                if (ti === MOCK_TABLES.length - 1) {
                    setTimeout(() => {
                        setLog(prev => [...prev, `[DONE] Migration complete. Total: ${totalRows.toLocaleString()} rows.`]);
                        setPhase("done");
                    }, 500);
                }
            }, startDelay + chunks * 400 + 200);
        });
    }

    const migratedRows = Object.values(tableProgress).reduce((a, t) => a + (t.done || 0), 0);

    return (
        <div style={{ display: "flex", gap: 16, animation: "slideIn 0.3s ease" }}>
            <Panel style={{ flex: "0 0 280px" }}>
                <PanelHeader title="Migration Config" icon="⇒" />
                <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                    <KVRow k="Source" v={`${config.sourceEngine}`} />
                    <KVRow k="Target" v={`${config.targetEngine}`} />
                    <KVRow k="Tables" v={MOCK_TABLES.length} />
                    <KVRow k="Total Rows" v={totalRows.toLocaleString()} />
                    <KVRow k="Chunk Size" v={(config.chunkSize || "100,000") + " rows"} mono />
                    <KVRow k="FK During Load" v={config.disableFk ? "Disabled" : "Enabled"} />
                </div>
                {phase !== "idle" && (
                    <div style={{ padding: "0 16px", marginBottom: 8 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                            <Mono size={11} color={C.text2}>OVERALL</Mono>
                            <Mono size={11} color={C.cyan}>
                                {Math.round(migratedRows / totalRows * 100)}%
                            </Mono>
                        </div>
                        <ProgressBar value={migratedRows} max={totalRows} color={C.cyan} />
                    </div>
                )}
                <div style={{ padding: "8px 16px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
                    <button onClick={run} disabled={phase !== "idle"} style={btnStyle(C.cyan)}>
                        <Mono size={12} style={{ fontWeight: 600 }}>
                            {phase === "idle" ? "START MIGRATION" :
                                phase === "done" ? "COMPLETE" : "MIGRATING…"}
                        </Mono>
                    </button>
                    {phase === "done" && (
                        <button onClick={onNext} style={btnStyle(C.green)}>
                            <Mono size={12} style={{ fontWeight: 600 }}>VALIDATE →</Mono>
                        </button>
                    )}
                </div>
            </Panel>

            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 16 }}>
                {/* Table progress */}
                <Panel>
                    <PanelHeader title="Table Progress" right={phase !== "idle" && <StatusDot status={phase === "done" ? "approved" : "running"} />} />
                    <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 6 }}>
                        {MOCK_TABLES.map(t => {
                            const tp = tableProgress[t.name];
                            const pct = tp ? Math.round(tp.done / tp.total * 100) : 0;
                            return (
                                <div key={t.name} style={{
                                    display: "flex", alignItems: "center", gap: 12,
                                    padding: "7px 12px", borderRadius: 6,
                                    background: tp?.status === "running" ? C.cyanDim : C.bg2,
                                    border: `1px solid ${tp?.status === "running" ? C.cyan + "40" : C.border}`,
                                    transition: "all 0.3s",
                                }}>
                                    <StatusDot status={tp?.status === "done" ? "approved" : tp?.status === "running" ? "running" : "pending"} />
                                    <Mono size={12} style={{ flex: "0 0 100px", color: tp ? C.text0 : C.text2 }}>{t.name}</Mono>
                                    <div style={{ flex: 1 }}>
                                        <ProgressBar value={tp?.done || 0} max={t.rows} color={tp?.status === "done" ? C.green : C.cyan} />
                                    </div>
                                    <Mono size={11} color={C.text2} style={{ flex: "0 0 100px", textAlign: "right" }}>
                                        {tp ? `${(tp.done).toLocaleString()} / ${t.rows.toLocaleString()}` : t.rows.toLocaleString()}
                                    </Mono>
                                    <Mono size={10} color={tp?.status === "done" ? C.green : C.cyan} style={{ flex: "0 0 36px", textAlign: "right" }}>
                                        {tp ? `${pct}%` : ""}
                                    </Mono>
                                </div>
                            );
                        })}
                    </div>
                </Panel>

                {/* Log */}
                <Panel style={{ flex: 1 }}>
                    <PanelHeader title="Migration Log" />
                    <div ref={logRef} style={{
                        fontFamily: G.fontMono, fontSize: 12, color: C.text1,
                        padding: 16, maxHeight: 200, overflowY: "auto", lineHeight: 1.8,
                    }}>
                        {log.length === 0 && (
                            <span style={{ color: C.text2 }}>— Awaiting migration start —</span>
                        )}
                        {log.map((line, i) => (
                            <div key={i} style={{
                                color: line.includes("✓") ? C.green :
                                    line.includes("DONE") ? C.cyan :
                                        line.includes("CREATE") ? C.purple : C.text1,
                            }}>{line}</div>
                        ))}
                    </div>
                </Panel>
            </div>
        </div>
    );
}

// ─── Validate Step ───────────────────────────────────────────────────────────
function ValidateStep() {
    const [phase, setPhase] = useState("idle");
    const [results, setResults] = useState([]);

    const MOCK_RESULTS = [
        { table: "users", srcRows: 184203, tgtRows: 184203, rowMatch: true, sumCheck: true, distinctCheck: true, warnings: [] },
        { table: "orders", srcRows: 1024891, tgtRows: 1024891, rowMatch: true, sumCheck: true, distinctCheck: false, warnings: ["COUNT(DISTINCT customer_id) diff by 1 — likely CHAR trailing-space issue"] },
        { table: "products", srcRows: 48712, tgtRows: 48712, rowMatch: true, sumCheck: true, distinctCheck: true, warnings: [] },
        { table: "payments", srcRows: 897234, tgtRows: 897234, rowMatch: true, sumCheck: true, distinctCheck: true, warnings: [] },
        { table: "sessions", srcRows: 5128004, tgtRows: 5128004, rowMatch: true, sumCheck: null, distinctCheck: true, warnings: ["No numeric columns for SUM validation"] },
        { table: "audit_log", srcRows: 3201447, tgtRows: 3201447, rowMatch: true, sumCheck: true, distinctCheck: true, warnings: [] },
    ];

    function run() {
        setPhase("running");
        setResults([]);
        MOCK_RESULTS.forEach((r, i) => {
            setTimeout(() => {
                setResults(prev => [...prev, r]);
                if (i === MOCK_RESULTS.length - 1) setPhase("done");
            }, i * 700);
        });
    }

    const allPass = results.every(r => r.rowMatch);
    const totalRows = MOCK_RESULTS.reduce((a, r) => a + r.srcRows, 0);

    function CheckIcon({ val }) {
        if (val === null) return <span style={{ color: C.text2, fontSize: 13 }}>—</span>;
        return <span style={{ color: val ? C.green : C.red, fontSize: 13 }}>{val ? "✓" : "✗"}</span>;
    }

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 16, animation: "slideIn 0.3s ease" }}>
            <div style={{ display: "flex", gap: 16 }}>
                <Panel style={{ flex: "0 0 280px" }}>
                    <PanelHeader title="Validation Config" icon="✓" />
                    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                        <KVRow k="Row Count Tolerance" v="0%" mono />
                        <KVRow k="Sample Rows" v="1,000" />
                        <KVRow k="Float Tolerance" v="0.0001%" />
                        <KVRow k="Timestamp Granularity" v="seconds" />
                        <KVRow k="Tables" v={MOCK_TABLES.length} />
                        <KVRow k="Total Source Rows" v={totalRows.toLocaleString()} />
                    </div>
                    <div style={{ padding: "0 16px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
                        <button onClick={run} disabled={phase === "running"} style={btnStyle(C.cyan)}>
                            <Mono size={12} style={{ fontWeight: 600 }}>
                                {phase === "idle" ? "RUN VALIDATION" : phase === "running" ? "VALIDATING…" : "RE-VALIDATE"}
                            </Mono>
                        </button>
                    </div>
                </Panel>

                {/* Summary cards */}
                {phase === "done" && (
                    <div style={{ flex: 1, display: "flex", gap: 12, alignItems: "flex-start", flexWrap: "wrap" }}>
                        {[
                            { label: "Tables Checked", value: results.length, color: C.cyan, icon: "⬡" },
                            { label: "Row Count Match", value: `${results.filter(r => r.rowMatch).length}/${results.length}`, color: C.green, icon: "✓" },
                            { label: "SUM Checks Pass", value: `${results.filter(r => r.sumCheck === true).length}/${results.filter(r => r.sumCheck !== null).length}`, color: C.green, icon: "Σ" },
                            { label: "Total Rows Validated", value: totalRows.toLocaleString(), color: C.amber, icon: "#" },
                            { label: "Warnings", value: results.reduce((a, r) => a + r.warnings.length, 0), color: results.reduce((a, r) => a + r.warnings.length, 0) > 0 ? C.amber : C.green, icon: "⚠" },
                            { label: "Overall Status", value: allPass ? "PASS" : "FAIL", color: allPass ? C.green : C.red, icon: allPass ? "✓" : "✗" },
                        ].map(s => (
                            <Panel key={s.label} style={{ flex: "0 0 calc(33% - 8px)", padding: 16 }}>
                                <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 4 }}>
                                    <Mono size={20} style={{ fontWeight: 700, color: s.color }}>{s.value}</Mono>
                                </div>
                                <Mono size={10} color={C.text2} style={{ letterSpacing: "0.06em", textTransform: "uppercase" }}>
                                    {s.label}
                                </Mono>
                            </Panel>
                        ))}
                    </div>
                )}
            </div>

            {/* Results table */}
            <Panel>
                <PanelHeader title="Validation Results" right={phase === "running" && <StatusDot status="running" />} />
                <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                        <thead>
                            <tr style={{ background: C.bg2 }}>
                                {["Table", "Source Rows", "Target Rows", "Row Match", "SUM Check", "Distinct Check", "Warnings"].map(h => (
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
                            {results.map((r, i) => (
                                <tr key={r.table} style={{
                                    borderBottom: `1px solid ${C.border}`,
                                    background: i % 2 === 0 ? "transparent" : C.bg0 + "60",
                                    animation: "fadeIn 0.3s ease",
                                }}>
                                    <td style={{ padding: "9px 14px" }}>
                                        <Mono size={12} color={C.cyan}>{r.table}</Mono>
                                    </td>
                                    <td style={{ padding: "9px 14px" }}>
                                        <Mono size={12}>{r.srcRows.toLocaleString()}</Mono>
                                    </td>
                                    <td style={{ padding: "9px 14px" }}>
                                        <Mono size={12} color={r.srcRows === r.tgtRows ? C.text0 : C.red}>
                                            {r.tgtRows.toLocaleString()}
                                        </Mono>
                                    </td>
                                    <td style={{ padding: "9px 14px", textAlign: "center" }}>
                                        <span style={{ color: r.rowMatch ? C.green : C.red, fontWeight: 700 }}>
                                            {r.rowMatch ? "✓" : "✗"}
                                        </span>
                                    </td>
                                    <td style={{ padding: "9px 14px", textAlign: "center" }}>
                                        {r.sumCheck === null
                                            ? <span style={{ color: C.text2 }}>—</span>
                                            : <span style={{ color: r.sumCheck ? C.green : C.red, fontWeight: 700 }}>
                                                {r.sumCheck ? "✓" : "✗"}
                                            </span>
                                        }
                                    </td>
                                    <td style={{ padding: "9px 14px", textAlign: "center" }}>
                                        <span style={{ color: r.distinctCheck ? C.green : C.amber, fontWeight: 700 }}>
                                            {r.distinctCheck ? "✓" : "⚠"}
                                        </span>
                                    </td>
                                    <td style={{ padding: "9px 14px" }}>
                                        {r.warnings.map((w, wi) => (
                                            <div key={wi} style={{
                                                fontSize: 11, color: C.amber,
                                                background: C.amberDim, borderRadius: 3, padding: "2px 8px",
                                                marginBottom: 2, maxWidth: 300,
                                            }}>
                                                {w}
                                            </div>
                                        ))}
                                    </td>
                                </tr>
                            ))}
                            {phase !== "idle" && results.length < MOCK_RESULTS.length && (
                                <tr>
                                    <td colSpan={7} style={{ padding: "10px 14px" }}>
                                        <Mono size={11} color={C.cyan} style={{ animation: "pulse 1.2s infinite" }}>
                                            Validating {MOCK_RESULTS[results.length]?.table}…
                                        </Mono>
                                    </td>
                                </tr>
                            )}
                            {phase === "idle" && (
                                <tr>
                                    <td colSpan={7} style={{ padding: "20px 14px" }}>
                                        <Mono size={12} color={C.text2}>— Run validation to see results —</Mono>
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </Panel>
        </div>
    );
}

// ─── Small helpers ──────────────────────────────────────────────────────────
function Field({ label, children, style = {} }) {
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 5, ...style }}>
            <Mono size={10} color={C.text2} style={{ letterSpacing: "0.06em", textTransform: "uppercase" }}>{label}</Mono>
            {children}
        </div>
    );
}

function Input({ value, onChange, placeholder, mono, password, error }) {
    return (
        <input
            type={password ? "password" : "text"}
            value={value || ""}
            onChange={e => onChange(e.target.value)}
            placeholder={placeholder}
            style={{
                background: C.bg0, border: `1px solid ${error ? C.red : C.border}`,
                borderRadius: 4, padding: "7px 10px", color: C.text0, width: "100%",
                fontFamily: mono ? G.fontMono : G.fontSans, fontSize: 12,
                outline: "none", transition: "border-color 0.15s",
            }}
            onFocus={e => e.target.style.borderColor = C.cyan}
            onBlur={e => e.target.style.borderColor = error ? C.red : C.border}
        />
    );
}

function EngineSelect({ value, options, onChange }) {
    return (
        <select
            value={value}
            onChange={e => onChange(e.target.value)}
            style={{
                background: C.bg0, border: `1px solid ${C.border}`,
                borderRadius: 4, padding: "7px 10px", color: C.text0, width: "100%",
                fontFamily: G.fontMono, fontSize: 12, cursor: "pointer", outline: "none",
            }}
        >
            {options.map(o => (
                <option key={o} value={o}>{ENGINE_ICONS[o]} {o}</option>
            ))}
        </select>
    );
}

function Toggle({ checked, onChange }) {
    return (
        <div
            onClick={() => onChange(!checked)}
            style={{
                width: 32, height: 18, borderRadius: 9,
                background: checked ? C.cyan : C.border,
                position: "relative", cursor: "pointer", flexShrink: 0,
                transition: "background 0.2s",
            }}
        >
            <div style={{
                width: 12, height: 12, borderRadius: "50%", background: "#fff",
                position: "absolute", top: 3, left: checked ? 17 : 3,
                transition: "left 0.2s",
            }} />
        </div>
    );
}

function KVRow({ k, v, mono }) {
    return (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <Mono size={11} color={C.text2} style={{ textTransform: "uppercase", letterSpacing: "0.05em" }}>{k}</Mono>
            <span style={{
                fontFamily: mono ? G.fontMono : G.fontSans,
                fontSize: 12, color: C.text0, fontWeight: 500,
            }}>{v}</span>
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

// ─── App ────────────────────────────────────────────────────────────────────
export default function App() {
    const [step, setStep] = useState(0);
    const [config, setConfig] = useState({
        sourceEngine: "postgres",
        sourceHost: "prod-db.internal",
        sourcePort: "5432",
        sourceDb: "app_db",
        sourceSchema: "public",
        sourceDsn: "",
        targetEngine: "mysql",
        targetHost: "staging-db.internal",
        targetPort: "3306",
        targetDb: "app_dw",
        targetSchema: "dw",
        targetDsn: "",
        llmProvider: "openai",
        llmModel: "gpt-4o",
        llmKey: "",
        chunkSize: "100000",
        disableFk: true,
    });

    useEffect(() => { injectStyles(); }, []);

    const stepComponents = [
        <ConfigStep config={config} setConfig={setConfig} onNext={() => setStep(1)} />,
        <ExtractStep config={config} onNext={() => setStep(2)} />,
        <ProposeStep config={config} onNext={() => setStep(3)} />,
        <ReviewStep onNext={() => setStep(4)} />,
        <MigrateStep config={config} onNext={() => setStep(5)} />,
        <ValidateStep />,
    ];

    return (
        <div style={{
            minHeight: "100vh",
            background: C.bg0,
            display: "flex", flexDirection: "column",
        }}>
            {/* Top bar */}
            <div style={{
                background: C.bg1, borderBottom: `1px solid ${C.border}`,
                padding: "0 28px", height: 54,
                display: "flex", alignItems: "center", justifyContent: "space-between",
                position: "sticky", top: 0, zIndex: 100,
            }}>
                <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                    {/* Logo */}
                    <div style={{
                        width: 32, height: 32, borderRadius: 6,
                        background: `linear-gradient(135deg, ${C.cyan}30, ${C.purple}30)`,
                        border: `1px solid ${C.cyan}40`,
                        display: "flex", alignItems: "center", justifyContent: "center",
                    }}>
                        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                            <rect x="1" y="1" width="6" height="6" rx="1" fill={C.cyan} opacity="0.8" />
                            <rect x="11" y="1" width="6" height="6" rx="1" fill={C.purple} opacity="0.8" />
                            <rect x="1" y="11" width="6" height="6" rx="1" fill={C.green} opacity="0.8" />
                            <rect x="11" y="11" width="6" height="6" rx="1" fill={C.amber} opacity="0.8" />
                            <line x1="7" y1="4" x2="11" y2="4" stroke={C.cyan} strokeWidth="1" strokeDasharray="1 1" />
                            <line x1="4" y1="7" x2="4" y2="11" stroke={C.green} strokeWidth="1" strokeDasharray="1 1" />
                        </svg>
                    </div>
                    <div>
                        <div style={{ fontFamily: G.fontMono, fontSize: 13, fontWeight: 600, color: C.text0, letterSpacing: "0.04em" }}>
                            DB MIGRATION FRAMEWORK
                        </div>
                        <div style={{ fontSize: 10, color: C.text2, letterSpacing: "0.06em" }}>UNIVERSAL PLUGIN PIPELINE · MVP</div>
                    </div>
                </div>

                {/* Engine pair display */}
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
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

                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <Badge label="MVP" color={C.amber} />
                    <Badge label="v2026-02-18" color={C.text2} />
                </div>
            </div>

            {/* Pipeline stepper */}
            <div style={{
                background: C.bg1, borderBottom: `1px solid ${C.border}`,
                padding: "0 28px",
                display: "flex", alignItems: "center",
            }}>
                {STEPS.map((s, i) => (
                    <div key={s.id} style={{ display: "flex", alignItems: "center" }}>
                        <button
                            onClick={() => i <= step && setStep(i)}
                            style={{
                                display: "flex", alignItems: "center", gap: 8,
                                padding: "14px 16px", border: "none",
                                background: "transparent",
                                borderBottom: `2px solid ${i === step ? C.cyan : "transparent"}`,
                                cursor: i <= step ? "pointer" : "default",
                                transition: "all 0.2s",
                            }}
                        >
                            <div style={{
                                width: 22, height: 22, borderRadius: "50%",
                                background: i < step ? C.greenDim : i === step ? C.cyanDim : C.bg3,
                                border: `1px solid ${i < step ? C.green : i === step ? C.cyan : C.border}`,
                                display: "flex", alignItems: "center", justifyContent: "center",
                                flexShrink: 0,
                            }}>
                                {i < step
                                    ? <span style={{ fontSize: 10, color: C.green }}>✓</span>
                                    : <Mono size={10} color={i === step ? C.cyan : C.text2}>{s.icon}</Mono>
                                }
                            </div>
                            <Mono size={11}
                                color={i < step ? C.green : i === step ? C.cyan : C.text2}
                                style={{ fontWeight: i === step ? 600 : 400, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                                {s.label}
                            </Mono>
                        </button>
                        {i < STEPS.length - 1 && (
                            <PipelineArrow active={i < step} />
                        )}
                    </div>
                ))}
            </div>

            {/* Main content */}
            <div style={{ flex: 1, padding: 24 }}>
                {stepComponents[step]}
            </div>

            {/* Footer */}
            <div style={{
                borderTop: `1px solid ${C.border}`, padding: "10px 28px",
                display: "flex", justifyContent: "space-between", alignItems: "center",
                background: C.bg1,
            }}>
                <Mono size={11} color={C.text2}>
                    Universal DB Migration Framework · Plugin Architecture · {STEPS[step].label}
                </Mono>
                <div style={{ display: "flex", gap: 16 }}>
                    <Mono size={11} color={C.text2}>
                        schemas/ · mappings/ · ddl/ · reports/
                    </Mono>
                </div>
            </div>
        </div>
    );
}