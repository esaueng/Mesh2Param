import { CadViewport } from "../viewer/CadViewport";
import { useWorkspaceSelector, workspaceStore } from "../state/store";
import { BottomDrawer } from "./BottomDrawer";
import { Inspector } from "./Inspector";
import { StatusStrip } from "./StatusStrip";
import { TopBar } from "./TopBar";
import type { WorkspaceActions, WorkspaceViewModel } from "./types";
import { WorkflowRail } from "./WorkflowRail";
import "./workspace.css";

export function WorkspaceShell({ vm, actions }: { vm: WorkspaceViewModel; actions: WorkspaceActions }) {
  const workflow = useWorkspaceSelector((state) => state.workflow);
  const viewer = useWorkspaceSelector((state) => state.viewer);
  const shell = useWorkspaceSelector((state) => state.shell);
  const logs = vm.activeJob?.logs ?? [];
  return (
    <main
      className={`app-shell ${shell.theme === "light" ? "theme-light" : ""} ${shell.railCollapsed ? "rail-collapsed" : ""} ${shell.inspectorExpanded ? "inspector-open" : ""}`}
      data-theme={shell.theme}
    >
      <a className="skip-link" href="#workspace-viewport">Skip to 3D viewport</a>
      <TopBar
        vm={vm}
        actions={actions}
        onToggleShortcuts={() => workspaceStore.getState().setShellState({
          singleKeyShortcuts: !workspaceStore.getState().shell.singleKeyShortcuts,
        })}
      />
      <WorkflowRail
        active={workflow.active}
        states={workflow.completion}
        collapsed={shell.railCollapsed}
        theme={shell.theme}
        units={vm.project.units}
        workerReady={vm.workerReady}
        onSelect={actions.setStep}
        onCollapse={() => workspaceStore.getState().setShellState({ railCollapsed: !shell.railCollapsed })}
        onTheme={() => workspaceStore.getState().setShellState({ theme: shell.theme === "dark" ? "light" : "dark" })}
      />
      <section id="workspace-viewport" className="viewport-region" tabIndex={-1}>
        <CadViewport
          projectId={vm.project.id}
          artifacts={vm.artifacts}
          preferences={viewer}
          theme={shell.theme}
          sourceProxyActive={vm.artifacts.some((artifact) => artifact.name === "reconstructed.glb" && artifact.kind === "preserved-source-proxy")}
          selectedPatchId={vm.selectedPatchId}
          onPreferences={(patch) => workspaceStore.getState().setViewerPreferences(patch)}
          onSelectPatch={actions.selectPatch}
        />
        <BottomDrawer
          logs={logs}
          metrics={vm.project.state.metrics as Record<string, unknown> | null}
          height={shell.bottomDrawerHeight}
          onHeight={(height) => workspaceStore.getState().setShellState({ bottomDrawerHeight: height })}
        />
      </section>
      <Inspector vm={vm} actions={actions} />
      <StatusStrip vm={vm} />
    </main>
  );
}
