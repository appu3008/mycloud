import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import "../styles/forms.css";

export function LoginPage() {
  const { enrollmentOpen, login, enroll } = useAuth();
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (enrollmentOpen && !email.includes("@")) {
        throw new Error("Email looks invalid");
      }
      if (enrollmentOpen) {
        // First admin enrollment (permanent window closure once submitted).
        await enroll(email, displayName || email.split("@")[0], password);
      } else {
        await login(email, password);
      }
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected failure");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1>{enrollmentOpen ? "Create the administrator" : "Sign in"}</h1>
        {enrollmentOpen && (
          <p className="hint">
            No admin exists yet. The first account created here owns the server.
            This window closes permanently afterwards.
          </p>
        )}
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
            required
          />
        </label>
        {enrollmentOpen && (
          <label>
            Display name
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Shown in the UI"
              required
            />
          </label>
        )}
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={enrollmentOpen ? "new-password" : "current-password"}
            minLength={enrollmentOpen ? 10 : 1}
            required
          />
        </label>
        {error && <div className="form-error">{error}</div>}
        <button className="primary-btn" type="submit" disabled={busy}>
          {busy ? "Working…" : enrollmentOpen ? "Create administrator" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
