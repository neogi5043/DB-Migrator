import { Routes, Route, Navigate } from "react-router-dom";
import LoginScreen from "./components/loginscreen";
import MigratorScreen from "./components/migratorscreen";
import ProtectedRoute from "./components/ProtectedRoute";

export default function App() {
    return (
        <Routes>
            <Route path="/" element={<LoginScreen />} />
            {/* <Route path="/migrator" element={<MigratorScreen />} /> */}

            <Route
            path="/migrator"
            element={
                    <ProtectedRoute>
                        <MigratorScreen />
                    </ProtectedRoute>
                }
            />
            <Route path="*" element={<Navigate to="/" />} />
        </Routes>
    );
}