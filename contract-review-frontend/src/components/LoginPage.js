// src/components/LoginPage.js
import React from "react";
import { useAuth } from "../contexts/AuthContext";
import "./LoginPage.css";

export default function LoginPage() {
  const { signInWithGoogle, authError } = useAuth();

  return (
    <div className="login-root">
      <div className="login-card">

        <div className="login-brand">
          <img src="/logo-icon-transparent.png" alt="LegalEyes" className="login-logo" />
          <p className="login-tagline">AI-Powered Contract Review</p>
        </div>

        <div className="login-options">
          <div className="login-option login-option--primary">
            <div className="login-option-text">
              <span className="login-option-label">Sign in with Google</span>
              <span className="login-option-desc">Analyses are saved to your account</span>
            </div>
            <button className="btn-google" onClick={signInWithGoogle}>
              <GoogleIcon />
              Sign in
            </button>
          </div>

          {authError && (
            <p className="login-error" role="alert">{authError}</p>
          )}

          <div className="login-divider"><span>or</span></div>

          <div className="login-option login-option--secondary">
            <div className="login-option-text">
              <span className="login-option-label">Continue as Guest</span>
              <span className="login-option-desc">No account needed, results are not saved</span>
            </div>
            <button
              className="btn-guest"
              onClick={() => document.dispatchEvent(new CustomEvent("lease:continue-as-guest"))}
            >
              Continue
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 18 18" aria-hidden="true">
      <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615Z"/>
      <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18Z"/>
      <path fill="#FBBC05" d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332Z"/>
      <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58Z"/>
    </svg>
  );
}
