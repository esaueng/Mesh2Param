import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { panelLayoutStore, usePanelLayout, type PanelSectionId } from "./panelLayout";
import { NARROW_LAYOUT_QUERY, useMediaQuery } from "./useMediaQuery";

export interface PanelSectionProps {
  id: PanelSectionId;
  /** Heading text. Stays the section heading's accessible name. */
  title: string;
  /** Optional trailing count or status rendered inside the heading button. */
  meta?: ReactNode;
  className?: string;
  /**
   * Plain children unmount while collapsed. A render function is always
   * mounted and told whether the section is collapsed, for sections that must
   * keep part of themselves (the primary conversion action) reachable.
   */
  children: ReactNode | ((collapsed: boolean) => ReactNode);
}

/**
 * A collapsible command-panel section. The heading element stays an <h2> so
 * assistive tech and tests keep addressing sections by heading; the toggle is
 * the button inside it. Collapsed state is persisted per section and ignored
 * in the stacked narrow layout, where headings are hidden and every section
 * has to stay reachable.
 */
export function PanelSection({ id, title, meta, className = "", children }: PanelSectionProps) {
  const layout = usePanelLayout();
  const narrow = useMediaQuery(NARROW_LAYOUT_QUERY);
  const collapsed = layout.collapsed[id] && !narrow;
  const bodyId = `panel-section-${id}`;
  const headingId = `panel-section-${id}-heading`;
  return (
    <section
      className={`panel-group panel-section ${className}`.trim()}
      aria-labelledby={headingId}
      data-section={id}
      data-collapsed={collapsed ? "true" : "false"}
    >
      <h2 className="panel-label" id={headingId}>
        <button
          type="button"
          className="panel-section-toggle"
          aria-expanded={!collapsed}
          aria-controls={bodyId}
          onClick={() => panelLayoutStore.toggleCollapsed(id)}
        >
          <ChevronDown className="panel-section-chevron" size={13} aria-hidden />
          <span className="panel-section-title">{title}</span>
          {meta !== undefined ? (
            <>
              {/* Read as "Analysis, 5 features" rather than "Analysis5 features". */}
              <span className="visually-hidden">, </span>
              <span className="panel-section-meta">{meta}</span>
            </>
          ) : null}
        </button>
      </h2>
      {typeof children === "function" ? (
        <div className="panel-section-body" id={bodyId}>{children(collapsed)}</div>
      ) : collapsed ? null : (
        <div className="panel-section-body" id={bodyId}>{children}</div>
      )}
    </section>
  );
}
