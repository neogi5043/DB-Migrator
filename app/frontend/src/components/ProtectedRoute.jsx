import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";

function ProtectedRoute({ children }) {
    const [loading, setLoading] = useState(true);
    const [isAuth, setIsAuth] = useState(false);

    useEffect(() => {
        fetch("/api/me", {
            credentials: "include"
        })
            .then(res => {
                if (res.ok) setIsAuth(true);
                else setIsAuth(false);
            })
            .catch(() => setIsAuth(false))
            .finally(() => setLoading(false));
    }, []);

    if (loading) return null;

    return isAuth ? children : <Navigate to="/" replace />;
}

export default ProtectedRoute;