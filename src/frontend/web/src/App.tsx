import { ClerkProvider, SignIn, SignUp, Show, useClerk } from "@clerk/react";
import { publishableKeyFromHost } from "@clerk/react/internal";
import { dark } from "@clerk/themes";
import { BrowserRouter, Routes, Route, Navigate, Link } from "react-router-dom";
import type { ReactNode } from "react";
import { EncountersListPage } from "./components/EncountersListPage";
import { EncounterDetailPage } from "./components/EncounterDetailPage";

const clerkPubKey = publishableKeyFromHost(
  window.location.hostname,
  import.meta.env.VITE_CLERK_PUBLISHABLE_KEY,
);
const clerkProxyUrl = import.meta.env.VITE_CLERK_PROXY_URL;

if (!clerkPubKey) {
  throw new Error("Missing VITE_CLERK_PUBLISHABLE_KEY");
}

const appearance = {
  theme: dark,
  options: {
    logoPlacement: "inside" as const,
    logoLinkUrl: "/",
    logoImageUrl: `${window.location.origin}/logo.svg`,
  },
  variables: {
    colorPrimary: "#147d78",
    colorForeground: "#19343a",
    colorMutedForeground: "#6c8588",
    colorBackground: "#fbfdfc",
    colorInput: "#fbfdfc",
    colorInputForeground: "#19343a",
    colorDanger: "#ae5b63",
    colorNeutral: "#d5e6e1",
    fontFamily: '"Plus Jakarta Sans", sans-serif',
    borderRadius: "0.65rem",
  },
};

function LandingPage() {
  return (
    <main className="auth-shell">
      <img src="/logo.svg" alt="Clinic Scribe" className="brand-logo" />
      <h1>Secure clinical documentation</h1>
      <p>Sign in with your individual clinic account to access patient encounters.</p>
      <div className="auth-actions">
        <Link to="/sign-in">Sign in</Link>
        <Link to="/sign-up" className="secondary">Create account</Link>
      </div>
    </main>
  );
}

function AccountPage() {
  const { signOut } = useClerk();
  return (
    <main className="auth-shell">
      <h1>Account</h1>
      <p>Authentication is managed by your individual clinic identity.</p>
      <button onClick={() => signOut({ redirectUrl: "/" })}>Sign out</button>
    </main>
  );
}

function Protected({ children }: { children: ReactNode }) {
  return (
    <>
      <Show when="signed-in">{children}</Show>
      <Show when="signed-out"><Navigate to="/sign-in" replace /></Show>
    </>
  );
}

export function App() {
  return (
    <ClerkProvider
      publishableKey={clerkPubKey}
      proxyUrl={clerkProxyUrl}
      appearance={appearance}
      signInUrl="/sign-in"
      signUpUrl="/sign-up"
    >
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<><Show when="signed-out"><LandingPage /></Show><Show when="signed-in"><Navigate to="/encounters" replace /></Show></>} />
          <Route path="/sign-in/*" element={<div className="auth-shell"><SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" /></div>} />
          <Route path="/sign-up/*" element={<div className="auth-shell"><SignUp routing="path" path="/sign-up" signInUrl="/sign-in" /></div>} />
          <Route path="/settings" element={<Protected><AccountPage /></Protected>} />
          <Route path="/encounters" element={<Protected><EncountersListPage /></Protected>} />
          <Route path="/encounters/:id" element={<Protected><EncounterDetailPage /></Protected>} />
        </Routes>
      </BrowserRouter>
    </ClerkProvider>
  );
}
