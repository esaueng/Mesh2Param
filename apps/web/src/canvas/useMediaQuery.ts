import { useSyncExternalStore } from "react";

/** The breakpoint below which the command panel stacks under the viewport. */
export const NARROW_LAYOUT_QUERY = "(max-width: 720px)";

export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      if (typeof matchMedia !== "function") return () => {};
      const list = matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    () => (typeof matchMedia === "function" ? matchMedia(query).matches : false),
    () => false,
  );
}
