import type { GLTFLoader } from "three-stdlib";
import { artifactAuthorizationHeaders } from "../api/auth";

export function authenticateGltfLoader(loader: GLTFLoader, url: string): void {
  // R3F reuses loader instances, so clear headers for local blobs and public assets too.
  loader.setRequestHeader(artifactAuthorizationHeaders(url));
}
