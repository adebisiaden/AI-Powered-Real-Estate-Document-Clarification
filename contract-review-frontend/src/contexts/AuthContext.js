// src/contexts/AuthContext.js
import React, { createContext, useContext, useEffect, useState } from "react";
import {
  onAuthStateChanged,
  signInWithPopup,
  signOut,
} from "firebase/auth";
import { auth, googleProvider } from "../firebase";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser]         = useState(null);
  const [token, setToken]       = useState(null);
  const [loading, setLoading]   = useState(true);
  const [authError, setAuthError] = useState(null);

  // Listen for Firebase auth state changes and keep the ID token fresh.
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      if (firebaseUser) {
        const idToken = await firebaseUser.getIdToken();
        setUser(firebaseUser);
        setToken(idToken);
      } else {
        setUser(null);
        setToken(null);
      }
      setLoading(false);
    });
    return unsubscribe;
  }, []);

  // Firebase ID tokens expire after 1 hour — refresh proactively.
  useEffect(() => {
    if (!user) return;
    const interval = setInterval(async () => {
      try {
        const fresh = await user.getIdToken(/* forceRefresh */ true);
        setToken(fresh);
      } catch {
        // Token refresh failed; user will be prompted to sign in again.
        setUser(null);
        setToken(null);
      }
    }, 50 * 60 * 1000); // every 50 minutes
    return () => clearInterval(interval);
  }, [user]);

  const signInWithGoogle = async () => {
    setAuthError(null);
    try {
      await signInWithPopup(auth, googleProvider);
    } catch (err) {
      setAuthError(err.message);
    }
  };

  const signOutUser = () => signOut(auth);

  return (
    <AuthContext.Provider
      value={{ user, token, loading, authError, signInWithGoogle, signOutUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

/** Hook — use anywhere inside the tree. */
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
