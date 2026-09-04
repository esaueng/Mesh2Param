/**
 * How long a download's object URL is kept alive after the anchor is clicked.
 *
 * Chromium reads the blob for an `<a download>` in a task scheduled after the
 * click, not during it, and there is no event that reports when that read has
 * started. Revoking in the same task as the click therefore races the download
 * and can cancel it outright — which surfaces as a download that simply never
 * happens, more often on a loaded or single-vCPU machine. Holding the URL for a
 * bounded window and then releasing it is the standard way out.
 */
const OBJECT_URL_LIFETIME_MS = 60_000;

/** Revokes a download's object URL once the browser has had time to start it. */
export function releaseAfterDownloadStarts(url: string): void {
  setTimeout(() => URL.revokeObjectURL(url), OBJECT_URL_LIFETIME_MS);
}
