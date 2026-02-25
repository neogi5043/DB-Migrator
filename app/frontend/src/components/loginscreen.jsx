import { useState } from "react";
import logoSrc from "../../assests/unnamed.png";

const C = {
    bg0: "#000000",
    bg1: "#0f1217",
    bg2: "#151a21",
    border: "#232d3a",
    cyan: "#38bdf8",
    red: "#f87171",
    text0: "#e2e8f0",
    text2: "#4b5563",
};

function LoginScreen() {
    const [user, setUser] = useState("");
    const [pwd, setPwd] = useState("");
    const [error, setError] = useState(false);
    const [loading, setLoading] = useState(false);

    async function handleLogin(e) {
        e.preventDefault();
        setLoading(true);
        setError(false);

        try {
            const res = await fetch("/api/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "include",
                body: JSON.stringify({
                    username: user.trim(),
                    password: pwd.trim(),
                }),
            });

            if (!res.ok) throw new Error("Invalid");

            window.location.href = "/migrator";
        } catch {
            setError(true);
        } finally {
            setLoading(false);
        }
    }

    return (
        <div
            style={{
                minHeight: "100vh",
                background: C.bg0,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
            }}
        >
            <div
                style={{
                    width: 360,
                    background: C.bg1,
                    border: `1px solid ${C.border}`,
                    borderRadius: 8,
                    overflow: "hidden",
                }}
            >
                <div
                    style={{
                        padding: 14,
                        borderBottom: `1px solid ${C.border}`,
                        background: C.bg2,
                        color: C.text0,
                        fontSize: 12,
                        letterSpacing: "0.08em",
                    }}
                >
                    RESTRICTED ACCESS
                </div>

                <form
                    onSubmit={handleLogin}
                    style={{
                        padding: 24,
                        display: "flex",
                        flexDirection: "column",
                        gap: 16,
                    }}
                >
                    <div style={{ textAlign: "center" }}>
                        <img src={logoSrc} alt="Logo" style={{ height: 40 }} />
                    </div>

                    <input
                        placeholder="Admin Username"
                        value={user}
                        onChange={(e) => setUser(e.target.value)}
                        style={{
                            padding: 8,
                            borderRadius: 4,
                            border: `1px solid ${error ? C.red : C.border}`,
                            background: C.bg0,
                            color: C.text0,
                        }}
                    />

                    <input
                        type="password"
                        placeholder="Admin Password"
                        value={pwd}
                        onChange={(e) => setPwd(e.target.value)}
                        style={{
                            padding: 8,
                            borderRadius: 4,
                            border: `1px solid ${error ? C.red : C.border}`,
                            background: C.bg0,
                            color: C.text0,
                        }}
                    />

                    {error && (
                        <div style={{ fontSize: 11, color: C.red }}>
                            Invalid Credentials. Access Denied.
                        </div>
                    )}

                    <button
                        type="submit"
                        disabled={loading}
                        style={{
                            padding: 10,
                            borderRadius: 4,
                            border: `1px solid ${C.cyan}`,
                            background: C.cyan + "18",
                            color: C.cyan,
                            fontWeight: 600,
                            cursor: "pointer",
                        }}
                    >
                        {loading ? "AUTHENTICATING..." : "UNLOCK PIPELINE"}
                    </button>
                </form>
            </div>
        </div>
    );
}

export default LoginScreen;