import { AgentType, ScheduleType } from '../../../core/services/agent-missions.service';

export type WorkflowNodeType = 'timing' | 'agent' | 'task' | 'output';

export type OutputDestination = 'results_panel' | 'admin_notification' | 'email';

export interface WorkflowNodeData {
  label?: string;
  scheduleType?: ScheduleType;
  scheduledAt?: string;
  scheduleTime?: string;
  agentType?: AgentType;
  description?: string;
  destination?: OutputDestination;
}

export interface WorkflowNode {
  id: string;
  type: WorkflowNodeType;
  x: number;
  y: number;
  data: WorkflowNodeData;
}

export interface WorkflowEdge {
  id: string;
  from: string;
  to: string;
}

export interface WorkflowBuilderState {
  version: 3;
  type: 'builder';
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

export interface PaletteItem {
  type: WorkflowNodeType;
  label: string;
  icon: string;
  description: string;
  defaults: WorkflowNodeData;
}

export const WORKFLOW_PALETTE: PaletteItem[] = [
  {
    type: 'timing',
    label: 'Déclencheur',
    icon: '▶',
    description: 'Quand lancer la mission',
    defaults: { label: 'Lancement', scheduleType: 'now', scheduleTime: '08:00' },
  },
  {
    type: 'agent',
    label: 'Agent IA',
    icon: '🤖',
    description: 'Choisir l’agent métier',
    defaults: { label: 'Agent', agentType: 'notifications' },
  },
  {
    type: 'task',
    label: 'Tâche',
    icon: '📋',
    description: 'Mission à exécuter',
    defaults: { label: 'Tâche', description: '' },
  },
  {
    type: 'output',
    label: 'Résultat',
    icon: '📤',
    description: 'Où voir / envoyer le résultat',
    defaults: { label: 'Voir résultat', destination: 'results_panel' },
  },
];

export const AGENT_PALETTE: { agentType: AgentType; label: string }[] = [
  { agentType: 'logs', label: 'Logs Agent' },
  { agentType: 'support', label: 'Support Agent' },
  { agentType: 'users', label: 'Users Agent' },
  { agentType: 'tracking', label: 'Tracking Agent' },
  { agentType: 'notifications', label: 'Notifications Agent' },
  { agentType: 'summary', label: 'Summary Agent' },
];

export const OUTPUT_OPTIONS: { value: OutputDestination; label: string }[] = [
  { value: 'results_panel', label: 'Voir dans Résultats' },
  { value: 'admin_notification', label: 'Notification admin' },
  { value: 'email', label: 'Envoyer par email' },
];

export const NODE_W = 200;
export const NODE_H = 88;

export function newNodeId(): string {
  return `n_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

export function newEdgeId(): string {
  return `e_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

export function emptyWorkflow(): WorkflowBuilderState {
  return { version: 3, type: 'builder', nodes: [], edges: [] };
}

export function parseWorkflowBuilder(planJson: string): WorkflowBuilderState | null {
  if (!planJson?.trim()) return null;
  try {
    const data = JSON.parse(planJson) as WorkflowBuilderState;
    if (data?.version === 3 && data.type === 'builder' && Array.isArray(data.nodes)) {
      return data;
    }
    return null;
  } catch {
    return null;
  }
}

export function nodeCenter(node: WorkflowNode): { x: number; y: number } {
  return { x: node.x + NODE_W / 2, y: node.y + NODE_H / 2 };
}

export function nodePortOut(node: WorkflowNode): { x: number; y: number } {
  return { x: node.x + NODE_W, y: node.y + NODE_H / 2 };
}

export function nodePortIn(node: WorkflowNode): { x: number; y: number } {
  return { x: node.x, y: node.y + NODE_H / 2 };
}

export function edgePath(from: WorkflowNode, to: WorkflowNode): string {
  const a = nodePortOut(from);
  const b = nodePortIn(to);
  const dx = Math.max(60, Math.abs(b.x - a.x) * 0.45);
  return `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`;
}

export function validateWorkflow(wf: WorkflowBuilderState): string[] {
  const errors: string[] = [];
  const types = wf.nodes.map((n) => n.type);
  if (!types.includes('timing')) errors.push('Ajoutez un bloc Déclencheur.');
  if (!types.includes('agent')) errors.push('Ajoutez un bloc Agent IA.');
  if (!types.includes('task')) errors.push('Ajoutez au moins un bloc Tâche.');
  if (!types.includes('output')) errors.push('Ajoutez un bloc Résultat.');

  const connected = new Set<string>();
  for (const e of wf.edges) {
    connected.add(e.from);
    connected.add(e.to);
  }
  for (const n of wf.nodes) {
    if (!connected.has(n.id) && wf.nodes.length > 1) {
      errors.push(`Le bloc « ${n.data.label || n.type} » n’est relié à rien.`);
    }
  }

  for (const n of wf.nodes.filter((x) => x.type === 'task')) {
    if (!(n.data.description || '').trim() || (n.data.description || '').trim().length < 10) {
      errors.push(`La tâche « ${n.data.label || n.id} » doit faire au moins 10 caractères.`);
    }
  }

  return errors;
}

export function deriveMissionFromWorkflow(wf: WorkflowBuilderState): {
  agent_type: AgentType;
  task_description: string;
  schedule_type: ScheduleType;
  scheduled_at: string | null;
  schedule_time: string;
} {
  const timing = wf.nodes.find((n) => n.type === 'timing');
  const agent = wf.nodes.find((n) => n.type === 'agent');
  const tasks = wf.nodes.filter((n) => n.type === 'task');

  const descriptions = tasks
    .map((t) => (t.data.description || '').trim())
    .filter(Boolean);

  return {
    agent_type: agent?.data.agentType || 'summary',
    task_description: descriptions.length === 1 ? descriptions[0] : descriptions.map((d, i) => `${i + 1}. ${d}`).join('\n'),
    schedule_type: timing?.data.scheduleType || 'now',
    scheduled_at: timing?.data.scheduledAt ? new Date(timing.data.scheduledAt).toISOString() : null,
    schedule_time: timing?.data.scheduleTime || '08:00',
  };
}
