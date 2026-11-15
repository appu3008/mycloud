import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import iconArrowBtn from "../assets/figma/icon-arrow-btn.svg";
import iconLock from "../assets/figma/icon-lock.svg";
import "../styles/forms.css";

function EyeIcon({ open }: { open: boolean }) {
  // The design's toggle glyph (Figma 1:70), with a slash added when revealed.
  return (
    <svg width="17" height="17" viewBox="0 0 21 21" fill="none" aria-hidden="true">
      <path
        d="M1.75 10.5C1.75 10.5 4.8125 4.375 10.5 4.375C16.1875 4.375 19.25 10.5 19.25 10.5C19.25 10.5 16.1875 16.625 10.5 16.625C4.8125 16.625 1.75 10.5 1.75 10.5Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="10.5" cy="10.5" r="2.625" stroke="currentColor" strokeWidth="1.6" />
      {open && <path d="M3 3l15 15" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />}
    </svg>
  );
}

export function LoginPage() {
  const { enrollmentOpen, login, enroll } = useAuth();
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (enrollmentOpen) {
        if (!email.includes("@")) throw new Error("Email looks invalid");
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
        <span className="login-badge mono-label">
          {enrollmentOpen ? "First-run setup" : "Administrator account access"}
        </span>
        <h1>{enrollmentOpen ? "Create the administrator." : "Welcome back to your account."}</h1>
        <p className="login-sub">
          {enrollmentOpen
            ? "Claim this cloud. The window closes permanently once the first admin exists."
            : "Sign in to access your personal cloud and manage your files."}
        </p>

        <label className="login-field">
          <span>Enter your email address</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="username"
            required
          />
        </label>

        {enrollmentOpen && (
          <label className="login-field">
            <span>Display name</span>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Shown in the UI"
              required
            />
          </label>
        )}

        <label className="login-field">
          <span>Enter your password</span>
          <div className="password-box">
            <input
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={
                enrollmentOpen
                  ? "Choose a long, unique password"
                  : "Enter the password for your administrator account"
              }
              autoComplete={enrollmentOpen ? "new-password" : "current-password"}
              minLength={enrollmentOpen ? 10 : 1}
              required
            />
            <button
              type="button"
              className="eye-toggle"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              <EyeIcon open={showPassword} />
            </button>
          </div>
        </label>

        {error && <div className="form-error">{error}</div>}

        <button className="primary-btn login-submit" type="submit" disabled={busy}>
          <span>{busy ? "Working…" : enrollmentOpen ? "Create the administrator" : "Sign in to your account"}</span>
          {!busy && <img src={iconArrowBtn} alt="" width={20} height={20} />}
        </button>

        <div className={`login-note${enrollmentOpen ? " open" : ""}`}>
          <img src={iconLock} alt="" width={18} height={18} />
          <p>
            {enrollmentOpen
              ? "One-time window: the first account created here owns the server. It closes forever afterwards."
              : "New administrator enrollment is currently closed. Only an existing administrator can sign in and access this cloud."}
          </p>
        </div>

        <div className="login-tagline">
          Your personal cloud begins at home, keeping your files close and accessible.
        </div>
      </form>
    </div>
  );
}
