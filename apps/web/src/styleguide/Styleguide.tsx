import { useState } from "react";
import {
  Badge,
  Button,
  Checkbox,
  Field,
  IconButton,
  NumberField,
  PanelSection,
  SelectField,
  StatusGlyph,
  Switch,
  Tabs,
  Toast,
  type SemanticState,
} from "@mesh2param/ui";
import { Download, Moon, Plus, Save, ScanSearch, Sun, Trash2 } from "lucide-react";
import { JobFailure } from "../canvas/JobFailure";
import { EmptyState, PanelSkeleton } from "../canvas/PanelStates";
import type { JobViewState } from "../state/types";
import "../canvas/canvas.css";
import "./styleguide.css";

const FAILED_JOB: JobViewState = {
  job: {
    id: "reconstruct-demo",
    projectId: "demo",
    kind: "reconstruct",
    status: "failed",
    progress: 40,
    phase: "fit surfaces",
    inputRevision: 1,
    attempt: 1,
    maxAttempts: 1,
    createdAt: "2026-09-05T00:00:00Z",
    startedAt: "2026-09-05T00:00:01Z",
    heartbeatAt: null,
    finishedAt: "2026-09-05T00:00:09Z",
    eventsUrl: "/api/jobs/demo/events",
    cancelRequestedAt: null,
    error: {
      code: "no_extrusion_axis",
      summary: "No single extrusion axis covers the side walls.",
      detail: "Best axis covered 61% of side-wall area; 98% is required for parametric inference.",
      phase: "fit surfaces",
      projectId: "demo",
      jobId: "reconstruct-demo",
      recoverable: true,
      recommendedAction: "Generate a curved STEP instead.",
    },
    result: null,
  },
  connection: "closed",
  logs: [],
  cancelling: false,
  lastEventAt: "2026-09-05T00:00:09Z",
};

const COLOR_GROUPS: ReadonlyArray<{ title: string; tokens: readonly string[] }> = [
  {
    title: "Elevation",
    tokens: ["--color-bg", "--color-surface", "--color-surface-2", "--color-hover", "--color-border", "--color-border-strong", "--color-viewport", "--color-overlay-bg"],
  },
  {
    title: "Text",
    tokens: ["--color-text", "--color-muted", "--color-subtle"],
  },
  {
    title: "Accent",
    tokens: ["--color-accent", "--color-accent-soft", "--color-accent-strong", "--color-accent-strong-hover", "--color-accent-strong-border", "--color-accent-dim", "--color-accent-border", "--color-accent-contrast", "--color-on-accent", "--color-focus"],
  },
  {
    title: "Semantic",
    tokens: ["--color-success", "--color-success-dim", "--color-success-border", "--color-warning", "--color-warning-dim", "--color-warning-border", "--color-warning-contrast", "--color-error", "--color-error-dim", "--color-error-border"],
  },
];

const TYPE_SCALE: ReadonlyArray<{ token: string; sample: string }> = [
  { token: "--fs-display", sample: "Parametric" },
  { token: "--fs-xl", sample: "Reconstruction" },
  { token: "--fs-lg", sample: "Surface patches" },
  { token: "--fs-md", sample: "Conversion workspace" },
  { token: "--fs-base", sample: "Kernel-validated STEP export" },
  { token: "--fs-sm", sample: "Boundary continuity" },
  { token: "--fs-xs", sample: "Residual tolerance" },
  { token: "--fs-mini", sample: "PATCH 014" },
];

const STATUS_STATES: readonly SemanticState[] = ["idle", "active", "complete", "warning", "failed", "disabled"];

export function Styleguide() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [switchOn, setSwitchOn] = useState(true);
  const [switchOff, setSwitchOff] = useState(false);
  const [checkedA, setCheckedA] = useState(false);
  const [checkedB, setCheckedB] = useState(true);
  const [tab, setTab] = useState<"all" | "errors" | "warnings">("all");

  return (
    <main className={`sg ${theme === "light" ? "theme-light" : ""}`} data-testid="styleguide" data-theme={theme}>
      <header className="sg-header">
        <div>
          <h1>UI Styleguide</h1>
          <p>U1 foundation — tokens, typography, and base controls. Dev-only route; not in the production bundle.</p>
        </div>
        <div className="sg-theme-toggle" role="group" aria-label="Preview theme">
          <Button variant={theme === "dark" ? "primary" : "secondary"} onClick={() => setTheme("dark")}>
            <Moon size={14} /> Dark
          </Button>
          <Button variant={theme === "light" ? "primary" : "secondary"} onClick={() => setTheme("light")}>
            <Sun size={14} /> Light
          </Button>
        </div>
      </header>

      <GuideSection title="Color tokens">
        {COLOR_GROUPS.map((group) => (
          <div key={group.title} className="sg-token-group">
            <h3>{group.title}</h3>
            <div className="sg-swatches">
              {group.tokens.map((token) => (
                <div key={token} className="sg-swatch">
                  <span className="sg-swatch-chip" style={{ background: `var(${token})` }} />
                  <code>{token}</code>
                </div>
              ))}
            </div>
          </div>
        ))}
      </GuideSection>

      <GuideSection title="Typography">
        <div className="sg-type-grid">
          <div>
            <h3>Sans scale (UI)</h3>
            {TYPE_SCALE.map((row) => (
              <p key={row.token} className="sg-type-row" style={{ fontSize: `var(${row.token})` }}>
                <code>{row.token}</code> {row.sample}
              </p>
            ))}
          </div>
          <div>
            <h3>Mono (numerics, IDs, units)</h3>
            <div className="sg-numerals" aria-label="Tabular numeral alignment demo">
              <div><code>residual p95</code><span>0.0042 mm</span></div>
              <div><code>residual max</code><span>0.0313 mm</span></div>
              <div><code>triangles</code><span>18,204</span></div>
              <div><code>area</code><span>1,024.6 mm²</span></div>
              <div><code>deviation</code><span>−0.0008 mm</span></div>
            </div>
            <p className="sg-note">IBM Plex Mono 400/500/700 with <code>font-variant-numeric: tabular-nums</code> keeps columns aligned.</p>
          </div>
        </div>
      </GuideSection>

      <GuideSection title="Buttons">
        <div className="sg-matrix">
          <span className="sg-matrix-head">Variant</span>
          <span className="sg-matrix-head">Default</span>
          <span className="sg-matrix-head">Hover (forced)</span>
          <span className="sg-matrix-head">Active (forced)</span>
          <span className="sg-matrix-head">Disabled</span>
          {(["secondary", "primary", "ghost", "danger"] as const).map((variant) => (
            <ButtonRow key={variant} variant={variant} />
          ))}
        </div>
        <p className="sg-note">Focus-visible uses the global 2px <code>--color-focus</code> outline — tab through to preview.</p>
      </GuideSection>

      <GuideSection title="Icon buttons">
        <div className="sg-row">
          <IconButton label="Save project"><Save size={16} /></IconButton>
          <IconButton label="Download STEP" className="sg-force-hover"><Download size={16} /></IconButton>
          <IconButton label="Add patch" disabled><Plus size={16} /></IconButton>
          <IconButton label="Delete"><Trash2 size={16} /></IconButton>
        </div>
      </GuideSection>

      <GuideSection title="Fields">
        <div className="sg-fields">
          <Field label="Project name" hint="Stored with the working document">
            <input defaultValue="L-bracket with mounting holes" />
          </Field>
          <Field label="Tolerance" error="Must be within 0.001 – 0.1 mm">
            <input defaultValue="0.2" aria-invalid="true" />
          </Field>
          <NumberField label="Chord deviation" unit="mm" defaultValue="0.05" step="0.01" min="0" />
          <SelectField label="Units" defaultValue="mm">
            <option value="mm">mm</option>
            <option value="inch">inch</option>
          </SelectField>
          <Field label="Disabled input">
            <input disabled defaultValue="Locked by the server" />
          </Field>
        </div>
      </GuideSection>

      <GuideSection title="Checkboxes">
        <div className="sg-row">
          <Checkbox label="Unchecked" checked={checkedA} onChange={(event) => setCheckedA(event.currentTarget.checked)} />
          <Checkbox label="Checked" checked={checkedB} onChange={(event) => setCheckedB(event.currentTarget.checked)} />
          <Checkbox label="Disabled" disabled />
          <Checkbox label="Disabled checked" disabled defaultChecked />
        </div>
      </GuideSection>

      <GuideSection title="Switches">
        <div className="sg-row">
          <Switch label="Off" checked={switchOff} onCheckedChange={setSwitchOff} />
          <Switch label="On" checked={switchOn} onCheckedChange={setSwitchOn} />
          <Switch label="Disabled off" checked={false} disabled />
          <Switch label="Disabled on" checked disabled />
        </div>
      </GuideSection>

      <GuideSection title="Badges">
        <div className="sg-row">
          <Badge>draft</Badge>
          <Badge tone="accent">analyzed</Badge>
          <Badge tone="success">validated</Badge>
          <Badge tone="warning">degraded</Badge>
          <Badge tone="error">failed</Badge>
          <Badge tone="accent">1,204 tris</Badge>
          <Badge tone="neutral">p95 0.0042 mm</Badge>
        </div>
      </GuideSection>

      <GuideSection title="Status glyphs">
        <div className="sg-row">
          {STATUS_STATES.map((state) => (
            <StatusGlyph key={state} state={state} label={state} />
          ))}
        </div>
      </GuideSection>

      <GuideSection title="Tabs">
        <Tabs
          label="Log severity"
          items={[
            { id: "all", label: "All", count: 128 },
            { id: "errors", label: "Errors", count: 2 },
            { id: "warnings", label: "Warnings", count: 7 },
          ]}
          value={tab}
          onChange={setTab}
        />
      </GuideSection>

      <GuideSection title="Panel section">
        <PanelSection title="Convert" action={<Badge tone="accent">ready</Badge>}>
          <Button variant="primary"><Download size={14} /> Download STEP</Button>
        </PanelSection>
      </GuideSection>

      <GuideSection title="Panel states">
        <div className="sg-panel-states">
          <div>
            <h3>Empty</h3>
            <EmptyState icon={<ScanSearch size={22} />} title="Not analyzed yet" hint="Mesh health, surface patches, and fit residuals appear here after analysis." action={{ label: "Analyze mesh", onClick: () => {} }} />
          </div>
          <div>
            <h3>Loading</h3>
            <PanelSkeleton rows={5} label="Segmenting surfaces…" />
          </div>
          <div>
            <h3>Failed job</h3>
            <JobFailure view={FAILED_JOB} canRetry onRetry={() => {}} onDismiss={() => {}} />
          </div>
        </div>
      </GuideSection>

      <GuideSection title="Toasts">
        <div className="sg-toasts">
          <Toast tone="info" message="Analysis finished: 7 surface patches detected." onDismiss={() => {}} />
          <Toast tone="success" message="STEP exported and kernel-validated." onDismiss={() => {}} />
          <Toast tone="warning" message="Reconstruction used a faceted proxy for one patch." onDismiss={() => {}} />
          <Toast tone="error" message="Rebuild failed: boundary continuity could not be satisfied." onDismiss={() => {}} />
        </div>
      </GuideSection>

      <GuideSection title="Motion">
        <div className="sg-row sg-motion">
          <code>--dur-fast 120ms</code>
          <code>--dur-base 180ms</code>
          <code>--dur-slow 240ms</code>
          <code>--ease-out cubic-bezier(.16,1,.3,1)</code>
          <span className="sg-motion-demo" aria-hidden="true">hover me</span>
        </div>
        <p className="sg-note">All UI motion is ease-out and ≤ 240ms; <code>prefers-reduced-motion</code> disables transitions globally.</p>
      </GuideSection>
    </main>
  );
}

function GuideSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="sg-section">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function ButtonRow({ variant }: { variant: "secondary" | "primary" | "ghost" | "danger" }) {
  return (
    <>
      <span className="sg-matrix-label">{variant}</span>
      <Button variant={variant}>Apply</Button>
      <Button variant={variant} className="sg-force-hover">Apply</Button>
      <Button variant={variant} className="sg-force-active">Apply</Button>
      <Button variant={variant} disabled>Apply</Button>
    </>
  );
}
