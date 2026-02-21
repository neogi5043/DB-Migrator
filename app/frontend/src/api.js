/**
 * API client — talks to FastAPI backend (proxied via Vite in dev).
 *
 * SSE helpers stream JSON events from the backend.
 */

const BASE = "";  // Vite proxy handles /api → localhost:8000

export async function fetchJSON(path) {
    const headers = {};
    const auth = localStorage.getItem("dbAdminAuth");
    if (auth) headers["Authorization"] = auth;
    const res = await fetch(`${BASE}${path}`, { headers });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
}

export async function postJSON(path, body = {}) {
    const headers = { "Content-Type": "application/json" };
    const auth = localStorage.getItem("dbAdminAuth");
    if (auth) headers["Authorization"] = auth;

    const res = await fetch(`${BASE}${path}`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
}

export async function testConnection(side, config) {
    return postJSON(`/api/test-connection/${side}`, config);
}

/**
 * Stream SSE events from a POST endpoint.
 * @param {string} path  e.g. "/api/extract"
 * @param {function} onEvent  called with each parsed JSON event
 * @returns {Promise<void>}
 */
export async function streamSSE(path, body, onEvent) {
    const req = { method: "POST", headers: {} };
    const auth = localStorage.getItem("dbAdminAuth");
    if (auth) req.headers["Authorization"] = auth;

    if (body) {
        req.headers["Content-Type"] = "application/json";
        req.body = JSON.stringify(body);
    }
    const res = await fetch(`${BASE}${path}`, req);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Parse SSE format: "data: {...}\n\n"
        const lines = buffer.split("\n\n");
        buffer = lines.pop(); // keep incomplete chunk

        for (const block of lines) {
            const dataLine = block.trim();
            if (dataLine.startsWith("data: ")) {
                try {
                    const event = JSON.parse(dataLine.slice(6));
                    onEvent(event);
                } catch (e) {
                    console.warn("SSE parse error:", e, dataLine);
                }
            }
        }
    }
}

// ── Convenience wrappers ────────────────────────────────────────────────

export const getConfig = () => fetchJSON("/api/config");
export const getTables = () => fetchJSON("/api/tables");
export const getMapping = (table) => fetchJSON(`/api/mapping/${table}`);
export const getViews = () => fetchJSON("/api/views");
export const approveTable = (table) => postJSON(`/api/approve/${table}`);
export const approveAll = () => postJSON("/api/approve-all");

export const runExtract = (body, onEvent) => streamSSE("/api/extract", body, onEvent);
export const runPropose = (body, onEvent) => streamSSE("/api/propose", body, onEvent);
export const runApplySchema = (body, onEvent) => streamSSE("/api/apply-schema", body, onEvent);
export const runMigrate = (body, onEvent) => streamSSE("/api/migrate", body, onEvent);
export const runValidate = (body, onEvent) => streamSSE("/api/validate", body, onEvent);
