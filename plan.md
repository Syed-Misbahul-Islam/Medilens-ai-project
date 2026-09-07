# Firebase Authentication Migration Plan — MediLens AI

## Overview

This plan migrates the MediLens AI frontend from a no-op local auth (navigate-on-submit) to **Firebase Authentication** with Email/Password and Google Sign-In. The backend already uses Firebase Admin SDK (`FIREBASE_PROJECT_ID`, `FIREBASE_CLIENT_EMAIL`, `FIREBASE_PRIVATE_KEY` are in `.env`), so we are extending the same Firebase project to the frontend.

---

## Current State (What Exists)

| File | Current Behavior |
|---|---|
| `frontend/src/pages/Login.jsx` | `handleLogin` just calls `navigate('/home')` — no real auth |
| `frontend/src/pages/SignUp.jsx` | `handleSignUp` just calls `navigate('/home')` — no real auth |
| `frontend/src/App.jsx` | All routes are public — no route protection |
| `frontend/.env` | Does not exist yet (Vite needs `VITE_` prefixed vars) |

---

## Target State (What We Are Building)

```
frontend/src/
├── firebase/
│   └── firebaseConfig.js       ← Firebase app init + exports
├── services/
│   └── authService.js          ← Wrappers: signUp, login, googleLogin, logout
├── context/
│   └── AuthContext.jsx         ← Global auth state via Context API
├── components/
│   └── ProtectedRoute.jsx      ← Redirects unauthenticated users
├── pages/
│   ├── Login.jsx               ← Connected to Firebase
│   └── SignUp.jsx              ← Connected to Firebase
└── App.jsx                     ← Wrapped in AuthProvider, protected routes added
```

---

## Step 1 — Firebase Console Setup

1. Go to [https://console.firebase.google.com](https://console.firebase.google.com)
2. Open the project **medilens-90592** (already exists — your backend uses it)
3. Navigate to **Authentication → Sign-in method**
4. Enable **Email/Password** provider
5. Enable **Google** provider (set support email)
6. Navigate to **Project Settings → General → Your apps**
7. Click **Add app → Web (</> icon)**
8. Register the app (e.g., "MediLens Web")
9. Copy the `firebaseConfig` object — you will need it in Step 3

---

## Step 2 — Install Firebase SDK

Run inside the `frontend/` directory:

```bash
cd frontend
npm install firebase
```

This installs the modular Firebase v9+ SDK (`firebase@^11.x`).

---

## Step 3 — Environment Variables

Create `frontend/.env` (Vite requires the `VITE_` prefix):

```env
VITE_FIREBASE_API_KEY=your_api_key_here
VITE_FIREBASE_AUTH_DOMAIN=medilens-90592.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=medilens-90592
VITE_FIREBASE_STORAGE_BUCKET=medilens-90592.appspot.com
VITE_FIREBASE_MESSAGING_SENDER_ID=your_sender_id_here
VITE_FIREBASE_APP_ID=your_app_id_here
```

> **Important:** Add `frontend/.env` to `frontend/.gitignore` so these values are never committed.
> These are public-facing web SDK keys (not the Admin SDK private key). They are safe to use in frontend code as long as Firebase Security Rules are configured correctly.

---

## Step 4 — Firebase Config File

**Create `frontend/src/firebase/firebaseConfig.js`:**

```js
import { initializeApp } from 'firebase/app';
import { getAuth, GoogleAuthProvider } from 'firebase/auth';

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const googleProvider = new GoogleAuthProvider();
```

---

## Step 5 — Auth Service Functions

**Create `frontend/src/services/authService.js`:**

```js
import {
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
  sendEmailVerification,
  sendPasswordResetEmail,
} from 'firebase/auth';
import { auth, googleProvider } from '../firebase/firebaseConfig';

// Email/Password Signup
export const signUpWithEmail = async (email, password) => {
  const userCredential = await createUserWithEmailAndPassword(auth, email, password);
  await sendEmailVerification(userCredential.user);
  return userCredential.user;
};

// Email/Password Login
export const loginWithEmail = async (email, password) => {
  const userCredential = await signInWithEmailAndPassword(auth, email, password);
  return userCredential.user;
};

// Google Sign-In (popup)
export const loginWithGoogle = async () => {
  const userCredential = await signInWithPopup(auth, googleProvider);
  return userCredential.user;
};

// Logout
export const logout = async () => {
  await signOut(auth);
};

// Password Reset
export const resetPassword = async (email) => {
  await sendPasswordResetEmail(auth, email);
};
```

---

## Step 6 — Auth Context (Global State)

**Create `frontend/src/context/AuthContext.jsx`:**

```jsx
import React, { createContext, useContext, useEffect, useState } from 'react';
import { onAuthStateChanged } from 'firebase/auth';
import { auth } from '../firebase/firebaseConfig';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Listens for auth state changes and persists session across refreshes
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      setCurrentUser(user);
      setLoading(false);
    });
    return unsubscribe; // cleanup on unmount
  }, []);

  const value = { currentUser, loading };

  return (
    <AuthContext.Provider value={value}>
      {!loading && children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
```

---

## Step 7 — Protected Route Component

**Create `frontend/src/components/ProtectedRoute.jsx`:**

```jsx
import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function ProtectedRoute({ children }) {
  const { currentUser } = useAuth();

  if (!currentUser) {
    return <Navigate to="/" replace />;
  }

  return children;
}
```

---

## Step 8 — Update `main.jsx`

Wrap the app with `AuthProvider`:

```jsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import { AuthProvider } from './context/AuthContext.jsx';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </React.StrictMode>
);
```

---

## Step 9 — Update `App.jsx` (Protected Routes)

```jsx
import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import ThreeBackground from './components/ThreeBackground';
import Sidebar from './components/Sidebar';
import AssistantModal from './components/AssistantModal';
import ProtectedRoute from './components/ProtectedRoute';
import Login from './pages/Login';
import SignUp from './pages/SignUp';
import Home from './pages/Home';
import Analysis from './pages/Analysis';
import PreviousReports from './pages/PreviousReports';
import './App.css';

// ... AppLayout stays the same ...

export default function App() {
  const [modalType, setModalType] = useState(null);

  return (
    <BrowserRouter>
      <ThreeBackground />
      <AppLayout setModalType={setModalType}>
        <Routes>
          {/* Public routes */}
          <Route path="/" element={<Login />} />
          <Route path="/login" element={<Navigate to="/" replace />} />
          <Route path="/signup" element={<SignUp />} />

          {/* Protected routes */}
          <Route path="/home" element={
            <ProtectedRoute><Home setModalType={setModalType} /></ProtectedRoute>
          } />
          <Route path="/analysis" element={
            <ProtectedRoute><Analysis /></ProtectedRoute>
          } />
          <Route path="/reports" element={
            <ProtectedRoute><PreviousReports /></ProtectedRoute>
          } />
        </Routes>
      </AppLayout>

      {modalType && (
        <AssistantModal type={modalType} onClose={() => setModalType(null)} />
      )}
    </BrowserRouter>
  );
}
```

---

## Step 10 — Update `Login.jsx`

```jsx
import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import GlassPanel from '../components/GlassPanel';
import Logo from '../components/Logo';
import { loginWithEmail, loginWithGoogle } from '../services/authService';
import './Login.css';

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await loginWithEmail(email, password);
      navigate('/home');
    } catch (err) {
      setError(mapFirebaseError(err.code));
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
    setError('');
    setLoading(true);
    try {
      await loginWithGoogle();
      navigate('/home');
    } catch (err) {
      setError(mapFirebaseError(err.code));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-logo-container"><Logo /></div>
      <GlassPanel className="login-panel">
        <h2 className="login-title">Login</h2>

        {error && <p className="auth-error">{error}</p>}

        <form className="login-form" onSubmit={handleLogin}>
          <div className="input-group">
            <label>Mail ID</label>
            <input
              type="email" placeholder="Enter Mail ID" required
              value={email} onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="input-group">
            <label>Password</label>
            <input
              type="password" placeholder="Enter Password" required
              value={password} onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <button type="submit" className="login-submit-btn" disabled={loading}>
            {loading ? 'Logging in...' : 'Login'}
          </button>
        </form>

        <div className="auth-divider"><span>or</span></div>

        <button className="google-btn" onClick={handleGoogleLogin} disabled={loading}>
          <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" alt="Google" />
          Continue with Google
        </button>

        <p className="login-footer">
          New user? <Link to="/signup">Sign up now</Link>
        </p>
        <p className="login-footer">
          <Link to="/forgot-password">Forgot Password?</Link>
        </p>
      </GlassPanel>
    </div>
  );
}

function mapFirebaseError(code) {
  const errors = {
    'auth/user-not-found': 'No account found with this email.',
    'auth/wrong-password': 'Incorrect password.',
    'auth/invalid-email': 'Invalid email address.',
    'auth/too-many-requests': 'Too many attempts. Please try again later.',
    'auth/popup-closed-by-user': 'Google sign-in was cancelled.',
  };
  return errors[code] || 'An error occurred. Please try again.';
}
```

---

## Step 11 — Update `SignUp.jsx`

```jsx
import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import GlassPanel from '../components/GlassPanel';
import Logo from '../components/Logo';
import { signUpWithEmail, loginWithGoogle } from '../services/authService';
import './SignUp.css';

export default function SignUp() {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    name: '', gender: '', dob: '', address: '', phone: '', email: '', password: '',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => setFormData({ ...formData, [e.target.name]: e.target.value });

  const handleSignUp = async (e) => {
    e.preventDefault();
    setError('');
    if (formData.password.length < 6) {
      return setError('Password must be at least 6 characters.');
    }
    setLoading(true);
    try {
      await signUpWithEmail(formData.email, formData.password);
      // TODO: Save extra profile fields (name, gender, dob, etc.) to Firestore here
      navigate('/home');
    } catch (err) {
      const errors = {
        'auth/email-already-in-use': 'An account with this email already exists.',
        'auth/invalid-email': 'Invalid email address.',
        'auth/weak-password': 'Password is too weak.',
      };
      setError(errors[err.code] || 'Sign-up failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignUp = async () => {
    setError('');
    setLoading(true);
    try {
      await loginWithGoogle();
      navigate('/home');
    } catch (err) {
      setError('Google sign-in failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="signup-page">
      <div className="signup-logo-container"><Logo /></div>
      <GlassPanel className="signup-panel">
        <h2 className="signup-title">Sign Up</h2>

        {error && <p className="auth-error">{error}</p>}

        <form className="signup-form" onSubmit={handleSignUp}>
          <div className="input-group">
            <label>Name</label>
            <input name="name" type="text" placeholder="Enter Full Name" required onChange={handleChange} />
          </div>
          <div className="signup-form-row">
            <div className="input-group signup-flex-1">
              <label>Gender</label>
              <select name="gender" required className="signup-select" onChange={handleChange}>
                <option value="">Select Gender</option>
                <option value="male">Male</option>
                <option value="female">Female</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div className="input-group signup-flex-1">
              <label>Date of Birth</label>
              <input name="dob" type="date" required onChange={handleChange} />
            </div>
          </div>
          <div className="input-group">
            <label>Address</label>
            <input name="address" type="text" placeholder="Enter Address" required onChange={handleChange} />
          </div>
          <div className="input-group">
            <label>Phone Number</label>
            <input name="phone" type="tel" placeholder="Enter Phone Number" required onChange={handleChange} />
          </div>
          <div className="input-group">
            <label>Mail (User ID)</label>
            <input name="email" type="email" placeholder="Enter Mail ID" required onChange={handleChange} />
          </div>
          <div className="input-group">
            <label>Create Password</label>
            <input name="password" type="password" placeholder="Min. 6 characters" required onChange={handleChange} />
          </div>
          <button type="submit" className="signup-submit-btn" disabled={loading}>
            {loading ? 'Creating account...' : 'Sign Up'}
          </button>
        </form>

        <div className="auth-divider"><span>or</span></div>
        <button className="google-btn" onClick={handleGoogleSignUp} disabled={loading}>
          <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" alt="Google" />
          Continue with Google
        </button>

        <p className="signup-footer">
          Already have an account? <Link to="/" className="login-link">Login</Link>
        </p>
      </GlassPanel>
    </div>
  );
}
```

---

## Step 12 — Logout (Sidebar Integration)

In `frontend/src/components/Sidebar.jsx`, add a logout button:

```jsx
import { logout } from '../services/authService';
import { useNavigate } from 'react-router-dom';

// Inside the component:
const navigate = useNavigate();

const handleLogout = async () => {
  await logout();
  navigate('/');
};

// In JSX:
<button onClick={handleLogout} className="sidebar-logout-btn">Logout</button>
```

---

## Step 13 — Optional: Forgot Password Page

**Create `frontend/src/pages/ForgotPassword.jsx`:**

```jsx
import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { resetPassword } from '../services/authService';
import GlassPanel from '../components/GlassPanel';
import Logo from '../components/Logo';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const handleReset = async (e) => {
    e.preventDefault();
    try {
      await resetPassword(email);
      setMessage('Password reset email sent! Check your inbox.');
    } catch {
      setError('Failed to send reset email. Check the address and try again.');
    }
  };

  return (
    <div className="login-page">
      <div className="login-logo-container"><Logo /></div>
      <GlassPanel className="login-panel">
        <h2 className="login-title">Reset Password</h2>
        {message && <p className="auth-success">{message}</p>}
        {error && <p className="auth-error">{error}</p>}
        <form onSubmit={handleReset} className="login-form">
          <div className="input-group">
            <label>Email Address</label>
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <button type="submit" className="login-submit-btn">Send Reset Email</button>
        </form>
        <p className="login-footer"><Link to="/">Back to Login</Link></p>
      </GlassPanel>
    </div>
  );
}
```

Add the route in `App.jsx`:
```jsx
<Route path="/forgot-password" element={<ForgotPassword />} />
```

---

## Step 14 — CSS for Auth UI Elements

Add these shared styles to `frontend/src/index.css` or a new `auth.css`:

```css
.auth-error {
  color: #ff4d4f;
  background: rgba(255, 77, 79, 0.1);
  border: 1px solid rgba(255, 77, 79, 0.3);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 0.85rem;
  margin-bottom: 12px;
  text-align: center;
}

.auth-success {
  color: #52c41a;
  background: rgba(82, 196, 26, 0.1);
  border: 1px solid rgba(82, 196, 26, 0.3);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 0.85rem;
  margin-bottom: 12px;
  text-align: center;
}

.auth-divider {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 16px 0;
  color: rgba(255,255,255,0.4);
  font-size: 0.8rem;
}
.auth-divider::before,
.auth-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: rgba(255,255,255,0.15);
}

.google-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 10px 16px;
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.2);
  border-radius: 8px;
  color: #fff;
  font-size: 0.95rem;
  cursor: pointer;
  transition: background 0.2s;
}
.google-btn:hover { background: rgba(255,255,255,0.15); }
.google-btn img { width: 20px; height: 20px; }
```

---

## Step 15 — Security Best Practices

| Practice | Detail |
|---|---|
| **Env vars** | All Firebase web config values stored in `frontend/.env` with `VITE_` prefix |
| **`.gitignore`** | `frontend/.env` must be listed in `frontend/.gitignore` |
| **Admin SDK** | Backend `.env` already holds the private key — keep it server-side only, never import into React |
| **Firebase Rules** | In Firebase Console → Firestore → Rules, set read/write to `request.auth != null` to block unauthenticated access |
| **Email Verification** | `sendEmailVerification` is called on signup (implemented in Step 5) |

Example Firestore Security Rule:
```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
  }
}
```

---

## Auth Flow Diagram

```
User visits /home (protected)
        │
        ▼
ProtectedRoute checks currentUser
        │
   ┌────┴─────┐
   │ null     │ user object
   ▼          ▼
Redirect    Render page
to "/"
   │
   ▼
Login.jsx
   ├── Email + Password ──► loginWithEmail() ──► Firebase
   └── Google btn ────────► loginWithGoogle() ─► Firebase
                                    │
                            onAuthStateChanged fires
                                    │
                            AuthContext updates currentUser
                                    │
                            ProtectedRoute allows /home
```

---

## Optional Enhancements (Not Required Now)

| Feature | Firebase API |
|---|---|
| Email Verification | `sendEmailVerification(user)` — already wired in signup |
| Password Reset | `sendPasswordResetEmail(auth, email)` — implemented in Step 13 |
| Multi-Factor Auth | Enable in Firebase Console → Authentication → MFA (Phone SMS) |
| Persist Auth State | Firebase persists by default using `localStorage` via `browserLocalPersistence` |

---

## Execution Checklist

- [ ] Enable Email/Password and Google in Firebase Console for project `medilens-90592`
- [ ] Copy web SDK config from Firebase Console
- [ ] Create `frontend/.env` with `VITE_` prefixed values
- [ ] Run `npm install firebase` inside `frontend/`
- [ ] Create `frontend/src/firebase/firebaseConfig.js`
- [ ] Create `frontend/src/services/authService.js`
- [ ] Create `frontend/src/context/AuthContext.jsx`
- [ ] Create `frontend/src/components/ProtectedRoute.jsx`
- [ ] Update `frontend/src/main.jsx` to wrap with `AuthProvider`
- [ ] Update `frontend/src/App.jsx` with protected routes
- [ ] Update `frontend/src/pages/Login.jsx` with Firebase login + Google
- [ ] Update `frontend/src/pages/SignUp.jsx` with Firebase signup + Google
- [ ] Add logout button to `Sidebar.jsx`
- [ ] (Optional) Create `ForgotPassword.jsx` page
- [ ] Add auth CSS styles
- [ ] Set Firebase Security Rules
- [ ] Test all flows: email login, email signup, Google login, logout, protected routes
