import { useState } from "react";
import { setApiToken } from "../api/auth";
import { Modal } from "./Modal";

export function ApiTokenDialog({ onClose }: { onClose(): void }) {
  const [token, setToken] = useState("");
  return (
    <Modal className="api-token-backdrop" labelledBy="api-token-title" onClose={onClose} dismissOnBackdrop={false}>
      <form className="api-token-dialog" onSubmit={(event) => {
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
    </Modal>
  );
}
