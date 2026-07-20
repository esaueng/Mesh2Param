import { useState } from "react";
import { setApiToken } from "../api/auth";

export function ApiTokenDialog({ onClose }: { onClose(): void }) {
  const [token, setToken] = useState("");
  return (
    <div className="api-token-backdrop" role="presentation">
      <form className="api-token-dialog" role="dialog" aria-modal="true" aria-labelledby="api-token-title" onSubmit={(event) => {
        event.preventDefault();
        if (!token.trim()) return;
        setApiToken(token);
        window.location.reload();
      }}>
        <p>Protected service</p>
        <h2 id="api-token-title">Enter API token</h2>
        <label htmlFor="mesh2param-api-token">Bearer token</label>
        <input id="mesh2param-api-token" type="password" value={token} onChange={(event) => setToken(event.target.value)} autoFocus autoComplete="current-password" />
        <small>The token is retained only for this browser tab.</small>
        <div><button type="button" onClick={onClose}>Cancel</button><button type="submit" disabled={!token.trim()}>Connect</button></div>
      </form>
    </div>
  );
}
