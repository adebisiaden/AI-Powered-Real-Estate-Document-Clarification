// src/components/UserMenu.js
import React, { useRef, useState, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";
import "./UserMenu.css";

export default function UserMenu() {
  const { user, signOutUser } = useAuth();
  const [open, setOpen] = useState(false);
  const menuRef = useRef(null);

  // Close on outside click
  useEffect(() => {
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  if (!user) return null;

  return (
    <div className="user-menu" ref={menuRef}>
      <button
        className="user-avatar-btn"
        onClick={() => setOpen((v) => !v)}
        aria-label="Account menu"
        aria-expanded={open}
      >
        {user.photoURL ? (
          <img
            src={user.photoURL}
            alt={user.displayName || "User avatar"}
            className="user-avatar-img"
          />
        ) : (
          <span className="user-avatar-fallback">
            {(user.displayName || user.email || "?")[0].toUpperCase()}
          </span>
        )}
      </button>

      {open && (
        <div className="user-dropdown" role="menu">
          <div className="user-dropdown-header">
            <p className="user-name">{user.displayName || "Signed in"}</p>
            <p className="user-email">{user.email}</p>
          </div>
          <hr className="user-dropdown-divider" />
          <button
            className="user-dropdown-item"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              signOutUser();
            }}
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
