import { useEffect, useState } from "react";
import { supabase } from "./supabase.js";

const MANAGER_EMAILS = new Set(
  (import.meta.env.VITE_MANAGER_EMAILS ?? "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean),
);

function deriveRole(user) {
  if (!user) return null;
  return MANAGER_EMAILS.has(user.email?.toLowerCase()) ? "manager" : "candidate";
}

export function useAuth() {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });

    const { data: listener } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s);
      setLoading(false);
    });

    return () => listener.subscription.unsubscribe();
  }, []);

  const user = session?.user ?? null;
  const role = deriveRole(user);

  async function signInWithGoogle() {
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin },
    });
  }

  async function signOut() {
    await supabase.auth.signOut();
  }

  return { user, session, role, loading, signInWithGoogle, signOut };
}
