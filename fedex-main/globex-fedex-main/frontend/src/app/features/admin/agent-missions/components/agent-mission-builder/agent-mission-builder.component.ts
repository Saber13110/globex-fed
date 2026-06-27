import { CommonModule } from '@angular/common';
import { Component, ElementRef, HostListener, OnInit, ViewChild, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import {
  AGENT_OPTIONS,
  AgentMissionsService,
  AgentType,
  SCHEDULE_OPTIONS,
} from '../../../../../core/services/agent-missions.service';
import {
  AGENT_PALETTE,
  NODE_H,
  NODE_W,
  OUTPUT_OPTIONS,
  PaletteItem,
  WORKFLOW_PALETTE,
  WorkflowBuilderState,
  WorkflowEdge,
  WorkflowNode,
  WorkflowNodeType,
  deriveMissionFromWorkflow,
  edgePath,
  emptyWorkflow,
  newEdgeId,
  newNodeId,
  parseWorkflowBuilder,
  validateWorkflow,
} from '../../workflow-builder.types';

@Component({
  selector: 'app-agent-mission-builder',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './agent-mission-builder.component.html',
  styleUrl: './agent-mission-builder.component.scss',
})
export class AgentMissionBuilderComponent implements OnInit {
  @ViewChild('canvasEl') canvasEl?: ElementRef<HTMLElement>;

  readonly palette = WORKFLOW_PALETTE;
  readonly agentPalette = AGENT_PALETTE;
  readonly scheduleOptions = SCHEDULE_OPTIONS;
  readonly outputOptions = OUTPUT_OPTIONS;
  readonly agentOptions = AGENT_OPTIONS;

  readonly workflow = signal<WorkflowBuilderState>(emptyWorkflow());
  readonly selectedNodeId = signal<string | null>(null);
  readonly linkSourceId = signal<string | null>(null);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly validationErrors = signal<string[]>([]);
  readonly readOnly = signal(false);

  notifyOnStart = true;
  notifyOnComplete = true;

  readonly selectedNode = computed(() => {
    const id = this.selectedNodeId();
    return this.workflow().nodes.find((n) => n.id === id) ?? null;
  });

  private missionId: number | null = null;
  private dragNodeId: string | null = null;
  private dragOffsetX = 0;
  private dragOffsetY = 0;

  constructor(
    private readonly api: AgentMissionsService,
    private readonly route: ActivatedRoute,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    this.route.paramMap.subscribe((params) => {
      const id = Number(params.get('id'));
      if (Number.isFinite(id) && id > 0) {
        this.missionId = id;
        this.loadMission(id);
      } else {
        this.seedDefaultWorkflow();
      }
    });
  }

  private seedDefaultWorkflow(): void {
    const wf = emptyWorkflow();
    const timing: WorkflowNode = {
      id: newNodeId(),
      type: 'timing',
      x: 60,
      y: 180,
      data: { label: 'Lancement', scheduleType: 'now', scheduleTime: '08:00' },
    };
    const agent: WorkflowNode = {
      id: newNodeId(),
      type: 'agent',
      x: 320,
      y: 180,
      data: { label: 'Notifications Agent', agentType: 'notifications' },
    };
    const task: WorkflowNode = {
      id: newNodeId(),
      type: 'task',
      x: 580,
      y: 180,
      data: { label: 'Tâche', description: 'Détecter les attaques et alertes sécurité sur la plateforme' },
    };
    const output: WorkflowNode = {
      id: newNodeId(),
      type: 'output',
      x: 840,
      y: 180,
      data: { label: 'Voir résultat', destination: 'results_panel' },
    };
    wf.nodes = [timing, agent, task, output];
    wf.edges = [
      { id: newEdgeId(), from: timing.id, to: agent.id },
      { id: newEdgeId(), from: agent.id, to: task.id },
      { id: newEdgeId(), from: task.id, to: output.id },
    ];
    this.workflow.set(wf);
  }

  private loadMission(id: number): void {
    this.api.get(id).subscribe({
      next: (m) => {
        const wf = parseWorkflowBuilder(m.plan_json);
        if (wf) {
          this.workflow.set(wf);
        } else {
          this.seedDefaultWorkflow();
        }
        this.readOnly.set(m.status === 'completed' || m.status === 'running');
        this.notifyOnStart = m.notify_on_start ?? true;
        this.notifyOnComplete = m.notify_on_complete ?? true;
      },
      error: () => {
        this.error.set('Mission introuvable.');
      },
    });
  }

  addFromPalette(item: PaletteItem): void {
    if (this.readOnly()) return;
    const canvas = this.canvasEl?.nativeElement;
    const count = this.workflow().nodes.filter((n) => n.type === item.type).length;
    const x = 80 + (this.workflow().nodes.length % 4) * 240;
    const y = 80 + Math.floor(this.workflow().nodes.length / 4) * 130;

    const node: WorkflowNode = {
      id: newNodeId(),
      type: item.type,
      x: canvas ? Math.min(x, Math.max(40, canvas.clientWidth - NODE_W - 320)) : x,
      y,
      data: {
        ...item.defaults,
        label: item.type === 'agent' ? 'Agent' : `${item.label}${count ? ` ${count + 1}` : ''}`,
      },
    };
    this.workflow.update((wf) => ({ ...wf, nodes: [...wf.nodes, node] }));
    this.selectedNodeId.set(node.id);
    this.validationErrors.set([]);
  }

  addAgentBox(agentType: AgentType): void {
    if (this.readOnly()) return;
    const label = this.agentOptions.find((a) => a.value === agentType)?.label || 'Agent';
    const node: WorkflowNode = {
      id: newNodeId(),
      type: 'agent',
      x: 320,
      y: 80 + this.workflow().nodes.length * 20,
      data: { label, agentType: agentType as WorkflowNode['data']['agentType'] },
    };
    this.workflow.update((wf) => ({ ...wf, nodes: [...wf.nodes, node] }));
    this.selectedNodeId.set(node.id);
  }

  selectNode(id: string, event?: MouseEvent): void {
    event?.stopPropagation();
    if (this.linkSourceId()) {
      this.tryConnect(this.linkSourceId()!, id);
      return;
    }
    this.selectedNodeId.set(id);
  }

  startLink(id: string, event: MouseEvent): void {
    event.stopPropagation();
    if (this.readOnly()) return;
    this.linkSourceId.set(id);
    this.selectedNodeId.set(id);
  }

  tryConnect(fromId: string, toId: string): void {
    if (fromId === toId) {
      this.linkSourceId.set(null);
      return;
    }
    const exists = this.workflow().edges.some((e) => e.from === fromId && e.to === toId);
    if (!exists) {
      const edge: WorkflowEdge = { id: newEdgeId(), from: fromId, to: toId };
      this.workflow.update((wf) => ({ ...wf, edges: [...wf.edges, edge] }));
    }
    this.linkSourceId.set(null);
    this.validationErrors.set([]);
  }

  removeEdge(edgeId: string, event: MouseEvent): void {
    event.stopPropagation();
    if (this.readOnly()) return;
    this.workflow.update((wf) => ({ ...wf, edges: wf.edges.filter((e) => e.id !== edgeId) }));
  }

  deleteSelected(): void {
    const id = this.selectedNodeId();
    if (!id || this.readOnly()) return;
    this.workflow.update((wf) => ({
      ...wf,
      nodes: wf.nodes.filter((n) => n.id !== id),
      edges: wf.edges.filter((e) => e.from !== id && e.to !== id),
    }));
    this.selectedNodeId.set(null);
  }

  updateSelectedData(patch: Partial<WorkflowNode['data']>): void {
    const id = this.selectedNodeId();
    if (!id || this.readOnly()) return;
    this.workflow.update((wf) => ({
      ...wf,
      nodes: wf.nodes.map((n) => {
        if (n.id !== id) return n;
        const data = { ...n.data, ...patch };
        if (patch.agentType) {
          data.label = this.agentOptions.find((a) => a.value === patch.agentType)?.label || data.label;
        }
        return { ...n, data };
      }),
    }));
  }

  nodeById(id: string): WorkflowNode | undefined {
    return this.workflow().nodes.find((n) => n.id === id);
  }

  pathForEdge(edge: WorkflowEdge): string {
    const from = this.nodeById(edge.from);
    const to = this.nodeById(edge.to);
    if (!from || !to) return '';
    return edgePath(from, to);
  }

  nodeTypeLabel(type: WorkflowNodeType): string {
    return this.palette.find((p) => p.type === type)?.label || type;
  }

  nodeIcon(type: WorkflowNodeType): string {
    return this.palette.find((p) => p.type === type)?.icon || '•';
  }

  agentLabelFor(type?: string): string {
    return this.agentOptions.find((a) => a.value === type)?.label || 'Agent';
  }

  outputLabelFor(dest?: string): string {
    return this.outputOptions.find((o) => o.value === dest)?.label || 'Sortie';
  }

  onCanvasClick(): void {
    this.selectedNodeId.set(null);
    this.linkSourceId.set(null);
  }

  onNodeMouseDown(node: WorkflowNode, event: MouseEvent): void {
    if (this.readOnly() || this.linkSourceId()) return;
    if ((event.target as HTMLElement).closest('.wf-node__port')) return;
    this.dragNodeId = node.id;
    this.dragOffsetX = event.clientX - node.x;
    this.dragOffsetY = event.clientY - node.y;
    this.selectedNodeId.set(node.id);
    event.preventDefault();
  }

  @HostListener('document:mousemove', ['$event'])
  onMouseMove(event: MouseEvent): void {
    if (!this.dragNodeId) return;
    const canvas = this.canvasEl?.nativeElement;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const x = Math.max(8, Math.min(event.clientX - rect.left - this.dragOffsetX, rect.width - NODE_W - 8));
    const y = Math.max(8, Math.min(event.clientY - rect.top - this.dragOffsetY, rect.height - NODE_H - 8));
    const id = this.dragNodeId;
    this.workflow.update((wf) => ({
      ...wf,
      nodes: wf.nodes.map((n) => (n.id === id ? { ...n, x, y } : n)),
    }));
  }

  @HostListener('document:mouseup')
  onMouseUp(): void {
    this.dragNodeId = null;
  }

  cancelLinkMode(): void {
    this.linkSourceId.set(null);
  }

  save(andRun = false): void {
    const wf = this.workflow();
    const errors = validateWorkflow(wf);
    if (errors.length) {
      this.validationErrors.set(errors);
      return;
    }
    this.validationErrors.set([]);
    this.saving.set(true);
    this.error.set(null);

    const derived = deriveMissionFromWorkflow(wf);
    const payload = {
      ...derived,
      max_items: 10,
      max_duration_minutes: 15,
      require_approval_sensitive: true,
      notify_on_start: this.notifyOnStart,
      notify_on_complete: this.notifyOnComplete,
      plan_json: JSON.stringify(wf),
    };

    const onSaved = (id: number) => {
      if (andRun) {
        this.api.run(id).subscribe({
          next: () => this.router.navigate(['/admin/agent-missions', id], { queryParams: { tab: 'results' } }),
          error: (err: HttpErrorResponse) => {
            this.error.set(err.error?.detail || 'Lancement impossible.');
            this.router.navigate(['/admin/agent-missions', id]);
          },
        });
      } else {
        this.router.navigate(['/admin/agent-missions', id], { queryParams: { tab: 'schema' } });
      }
    };

    if (this.missionId) {
      this.api.updateWorkflow(this.missionId, payload).subscribe({
        next: () => onSaved(this.missionId!),
        error: (err: HttpErrorResponse) => {
          this.error.set(err.error?.detail || 'Sauvegarde impossible.');
          this.saving.set(false);
        },
      });
    } else {
      this.api.createWithWorkflow(payload).subscribe({
        next: (m: { id: number }) => onSaved(m.id),
        error: (err: HttpErrorResponse) => {
          this.error.set(err.error?.detail || 'Création impossible.');
          this.saving.set(false);
        },
      });
    }
  }
}
