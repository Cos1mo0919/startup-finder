import { useSyncExternalStore } from "react";

// Admin session shared by the header and the admin pages. A key counts only
// after the server accepted it; leaving the admin area forgets it.
const STORAGE = "izlanish-admin-key";
let verified: string | null = null;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

export function readStoredKey(): string {
  try {
    return sessionStorage.getItem(STORAGE) || "";
  } catch {
    return "";
  }
}

function storeKey(value: string | null) {
  try {
    if (value) sessionStorage.setItem(STORAGE, value);
    else sessionStorage.removeItem(STORAGE);
  } catch {
    /* storage unavailable: the session simply lasts until reload */
  }
}

export function verifiedKey(): string | null {
  return verified;
}

export function setVerifiedKey(value: string) {
  verified = value;
  storeKey(value);
  emit();
}

export function clearAdminSession() {
  const changed = verified !== null || readStoredKey() !== "";
  verified = null;
  storeKey(null);
  if (changed) emit();
}

export const ADMIN_LINKS: [string, string][] = [
  ["/admin/status", "Holat"],
  ["/admin/review", "Ko‘rib chiqish"],
  ["/admin/catalog", "Loyihalar"],
  ["/admin/sources", "Manbalar samarasi"],
  ["/admin/muammolar", "Muammolar"],
  ["/admin/goyalar", "G‘oyalar"],
  ["/admin/signallar", "Signallar"],
  ["/admin/sektorlar", "Sektorlar"],
];

export function isAdminPath(pathname: string): boolean {
  return pathname === "/admin" || pathname.startsWith("/admin/") || pathname === "/status";
}

if (typeof window !== "undefined") {
  // Back/forward cache can restore an admin page after a public page already
  // ended the session in this tab; re-check against the stored key.
  window.addEventListener("pageshow", (event) => {
    if (event.persisted && verified !== null && readStoredKey() !== verified) {
      verified = null;
      emit();
    }
  });
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useAdminVerified(): boolean {
  return useSyncExternalStore(subscribe, () => verified !== null, () => false);
}
