// ═══════════════════════════════════════════════════════════════
// auth.js
// ═══════════════════════════════════════════════════════════════

import { db, setCurrentUser, navigate, state } from './state.js';
import { mapSupabaseError } from './utils.js';

export function showLoginError(msg) {
  const loginError = document.getElementById('login-error');
  if (loginError) loginError.textContent = msg;
}

export function showApp(user) {
  setCurrentUser(user);
  const sidebarEmail = document.getElementById('sidebar-user-email');
  const loginScreen = document.getElementById('login-screen');
  const appShell = document.getElementById('app-shell');
  if (sidebarEmail) sidebarEmail.textContent = user.email;
  if (loginScreen) loginScreen.style.display = 'none';
  if (appShell) appShell.style.display = 'flex';
}

export function showLoginScreen(errorMsg) {
  setCurrentUser(null);
  const loginScreen = document.getElementById('login-screen');
  const appShell = document.getElementById('app-shell');
  if (appShell) appShell.style.display = 'none';
  if (loginScreen) loginScreen.style.display = 'flex';
  if (errorMsg) showLoginError(errorMsg);
}

export async function verifySessionWithServer(session) {
  try {
    const res = await fetch('/api/auth/verify', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({}),
    });
    if (res.status === 200) return true;
    if (res.status === 403) return 'denied';
    return false;
  } catch {
    // If server is unreachable, fail open for developer convenience —
    // the server enforces the allowlist on every actual API call anyway.
    return true;
  }
}

export async function initAuth() {
  if (!db) {
    showLoginScreen('Failed to connect to Supabase. Check your configuration.');
    return;
  }

  const { data: { session } } = await db.auth.getSession();

  if (!session) {
    showLoginScreen();
    return;
  }

  const ok = await verifySessionWithServer(session);
  if (ok === 'denied') {
    await db.auth.signOut();
    showLoginScreen('Access denied. Your email is not authorised to use this dashboard.');
    return;
  }
  if (!ok) {
    showLoginScreen();
    return;
  }

  showApp({ email: session.user.email, access_token: session.access_token });
  navigate(state.view);
}

export function initAuthBindings() {
  if (db) {
    db.auth.onAuthStateChange(async (event, session) => {
      if (event === 'SIGNED_IN' && session) {
        const ok = await verifySessionWithServer(session);
        if (ok === 'denied') {
          await db.auth.signOut();
          showLoginScreen('Access denied. Your email is not authorised to use this dashboard.');
          return;
        }
        showApp({ email: session.user.email, access_token: session.access_token });
        navigate(state.view);
      } else if (event === 'SIGNED_OUT') {
        showLoginScreen();
      }
    });
  }

  const btnGoogle = document.getElementById('btn-google-signin');
  if (btnGoogle) {
    btnGoogle.addEventListener('click', async () => {
      showLoginError('');
      btnGoogle.disabled = true;
      btnGoogle.textContent = 'Redirecting…';
      try {
        if (!db) {
          throw new Error('Supabase client is not initialized. Check browser console or refresh the page.');
        }
        const { error } = await db.auth.signInWithOAuth({
          provider: 'google',
          options: { redirectTo: window.location.origin },
        });
        if (error) {
          showLoginError(mapSupabaseError(error));
          btnGoogle.disabled = false;
          btnGoogle.innerHTML = `<svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M17.64 9.2045C17.64 8.5663 17.5827 7.9527 17.4764 7.3636H9V10.845H13.8436C13.635 11.97 13.0009 12.9231 12.0477 13.5613V15.8195H14.9564C16.6582 14.2527 17.64 11.9454 17.64 9.2045Z" fill="#4285F4"/><path d="M9 18C11.43 18 13.4673 17.1941 14.9564 15.8195L12.0477 13.5613C11.2418 14.1013 10.2109 14.4204 9 14.4204C6.65591 14.4204 4.67182 12.8372 3.96409 10.71H0.957275V13.0418C2.43818 15.9831 5.48182 18 9 18Z" fill="#34A853"/><path d="M3.96409 10.71C3.78409 10.17 3.68182 9.5931 3.68182 9C3.68182 8.4068 3.78409 7.8299 3.96409 7.29V4.9581H0.957275C0.347727 6.1731 0 7.5477 0 9C0 10.4522 0.347727 11.8268 0.957275 13.0418L3.96409 10.71Z" fill="#FBBC05"/><path d="M9 3.5795C10.3213 3.5795 11.5077 4.0336 12.4405 4.9254L15.0218 2.344C13.4632 0.8918 11.4259 0 9 0C5.48182 0 2.43818 2.0168 0.957275 4.9581L3.96409 7.29C4.67182 5.1627 6.65591 3.5795 9 3.5795Z" fill="#EA4335"/></svg> Continue with Google`;
        }
      } catch (err) {
        showLoginError(err.message || 'Failed to authenticate');
        btnGoogle.disabled = false;
        btnGoogle.innerHTML = `<svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M17.64 9.2045C17.64 8.5663 17.5827 7.9527 17.4764 7.3636H9V10.845H13.8436C13.635 11.97 13.0009 12.9231 12.0477 13.5613V15.8195H14.9564C16.6582 14.2527 17.64 11.9454 17.64 9.2045Z" fill="#4285F4"/><path d="M9 18C11.43 18 13.4673 17.1941 14.9564 15.8195L12.0477 13.5613C11.2418 14.1013 10.2109 14.4204 9 14.4204C6.65591 14.4204 4.67182 12.8372 3.96409 10.71H0.957275V13.0418C2.43818 15.9831 5.48182 18 9 18Z" fill="#34A853"/><path d="M3.96409 10.71C3.78409 10.17 3.68182 9.5931 3.68182 9C3.68182 8.4068 3.78409 7.8299 3.96409 7.29V4.9581H0.957275C0.347727 6.1731 0 7.5477 0 9C0 10.4522 0.347727 11.8268 0.957275 13.0418L3.96409 10.71Z" fill="#FBBC05"/><path d="M9 3.5795C10.3213 3.5795 11.5077 4.0336 12.4405 4.9254L15.0218 2.344C13.4632 0.8918 11.4259 0 9 0C5.48182 0 2.43818 2.0168 0.957275 4.9581L3.96409 7.29C4.67182 5.1627 6.65591 3.5795 9 3.5795Z" fill="#EA4335"/></svg> Continue with Google`;
      }
    });
  }

  const loginForm = document.getElementById('login-form');
  if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      showLoginError('');
      const btn = document.getElementById('btn-email-signin');
      const email = document.getElementById('login-email').value.trim();
      const password = document.getElementById('login-password').value;
      if (btn) {
        btn.disabled = true;
        btn.textContent = 'Signing in…';
      }
      const { error } = await db.auth.signInWithPassword({ email, password });
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Sign in';
      }
      if (error) showLoginError(mapSupabaseError(error));
    });
  }

  const btnSignout = document.getElementById('btn-signout');
  if (btnSignout) {
    btnSignout.addEventListener('click', async () => {
      await db.auth.signOut();
    });
  }
}
