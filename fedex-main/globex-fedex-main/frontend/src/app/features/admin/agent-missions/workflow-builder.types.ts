import { AgentType, ScheduleType } from '../../../core/services/agent-missions.service';
import { getTaskSpec, normalizeMissionAgentType, resolveTaskDescription } from './mission-task-catalog';

export type WorkflowNodeType = 'timing' | 'agent' | 'task' | 'output';

export type OutputDestination = 'results_panel' | 'admin_notification' | 'email';

export interface WorkflowNodeData {
  label?: string;
  scheduleType?: ScheduleType;
  scheduledAt?: string;
  scheduleTime?: string;
  agentType?: AgentType;
  taskId?: string;
  priority?: number;
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
    defaults: { label: 'Agent', agentType: 'security' },
  },
  {
    type: 'task',
    label: 'Tâche',
    icon: '📋',
    description: 'Mission à exécuter',
    defaults: { label: 'Tâche', taskId: 'incident_list', description: '' },
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
  { agentType: 'security', label: 'Security Agent' },
  { agentType: 'tracking', label: 'Tracking Agent' },
  { agentType: 'reports', label: 'Reports Agent' },
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

export interface WorkflowTimingInfo {
  scheduleType: ScheduleType;
  scheduledAt?: string;
  scheduleTime: string;
}

export function getWorkflowTiming(planJson: string): WorkflowTimingInfo {
  const wf = parseWorkflowBuilder(planJson);
  if (!wf) {
    return { scheduleType: 'now', scheduleTime: '08:00' };
  }
  const timing = wf.nodes.find((n) => n.type === 'timing');
  return {
    scheduleType: timing?.data.scheduleType || 'now',
    scheduledAt: timing?.data.scheduledAt,
    scheduleTime: timing?.data.scheduleTime || '08:00',
  };
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

/** Remonte le graphe pour trouver l’agent lié à une tâche (miroir backend). */
export function workflowAgentForTask(wf: WorkflowBuilderState, taskNodeId: string): AgentType | null {
  const nodes = new Map(wf.nodes.map((n) => [n.id, n]));
  const inEdges = new Map<string, string[]>();
  for (const e of wf.edges) {
    const list = inEdges.get(e.to) ?? [];
    list.push(e.from);
    inEdges.set(e.to, list);
  }

  const queue = [taskNodeId];
  const visited = new Set<string>();
  while (queue.length) {
    const nid = queue.shift()!;
    if (visited.has(nid)) continue;
    visited.add(nid);
    const node = nodes.get(nid);
    if (node?.type === 'agent' && node.data.agentType) {
      return normalizeMissionAgentType(node.data.agentType);
    }
    for (const prev of inEdges.get(nid) ?? []) {
      if (!visited.has(prev)) queue.push(prev);
    }
  }

  const agentNodes = wf.nodes.filter((n) => n.type === 'agent');
  if (agentNodes.length === 1 && agentNodes[0].data.agentType) {
    return normalizeMissionAgentType(agentNodes[0].data.agentType);
  }
  return null;
}

/** Tâches dans l’ordre du graphe (BFS depuis le déclencheur). */
export function workflowOrderedTasks(wf: WorkflowBuilderState): WorkflowNode[] {
  const nodes = new Map(wf.nodes.map((n) => [n.id, n]));
  const outEdges = new Map<string, string[]>();
  for (const e of wf.edges) {
    const list = outEdges.get(e.from) ?? [];
    list.push(e.to);
    outEdges.set(e.from, list);
  }

  let starts = wf.nodes.filter((n) => n.type === 'timing');
  if (!starts.length) {
    const inTargets = new Set(wf.edges.map((e) => e.to));
    starts = wf.nodes.filter((n) => !inTargets.has(n.id));
  }
  if (!starts.length) {
    return wf.nodes.filter((n) => n.type === 'task');
  }

  const taskOrder: WorkflowNode[] = [];
  const visited = new Set<string>();
  const queue = [starts[0].id];

  while (queue.length) {
    const nid = queue.shift()!;
    if (visited.has(nid)) continue;
    visited.add(nid);
    const node = nodes.get(nid);
    if (node?.type === 'task') taskOrder.push(node);
    for (const nxt of outEdges.get(nid) ?? []) {
      if (!visited.has(nxt)) queue.push(nxt);
    }
  }
  return taskOrder;
}

/** Si plusieurs blocs Agent : chaque tâche doit utiliser un agent différent de l’étape précédente. */
export function validateDistinctWorkflowAgents(wf: WorkflowBuilderState): string[] {
  const errors: string[] = [];
  const agentNodeCount = wf.nodes.filter((n) => n.type === 'agent').length;
  if (agentNodeCount < 2) return errors;

  const tasks = workflowOrderedTasks(wf);
  let previousAgent: AgentType | null = null;
  for (const task of tasks) {
    const agent = workflowAgentForTask(wf, task.id);
    if (agent && previousAgent && agent === previousAgent) {
      const label = AGENT_PALETTE.find((a) => a.agentType === agent)?.label ?? agent;
      errors.push(
        `Utilisez un agent différent avant « ${task.data.label || task.id} » — « ${label} » est déjà utilisé à l’étape précédente.`,
      );
    }
    if (agent) previousAgent = agent;
  }
  return errors;
}

/** Miroir backend — paires (agent, tâche) autorisées après une étape productrice. */
const HANDOFF_ALLOWED: Record<string, string[]> = {
  'security:incident_list': [
    'security:incident_detail',
    'security:incident_summary',
    'security:security_report',
    'security:security_scan',
    'security:custom',
    'users:user_detail',
    'users:user_logs',
    'users:user_suspend',
    'users:custom',
    'support:ticket_detail',
    'support:ticket_reply',
    'support:custom',
  ],
  'logs:log_list': [
    'logs:log_detail',
    'logs:log_summary',
    'logs:log_anomalies',
    'logs:log_suspend_user',
    'logs:custom',
    'users:user_detail',
    'users:custom',
  ],
  'support:ticket_list': [
    'support:ticket_detail',
    'support:ticket_reply',
    'support:ticket_resolve',
    'support:custom',
    'users:user_detail',
    'users:user_logs',
  ],
  'support:ticket_detail': [
    'support:ticket_reply',
    'support:ticket_resolve',
    'support:custom',
    'users:user_detail',
    'users:user_logs',
    'users:user_permissions',
  ],
  'users:user_list': [
    'users:user_detail',
    'users:user_logs',
    'users:user_permissions',
    'users:user_suspend',
    'users:custom',
  ],
};

function handoffKey(agent: AgentType, taskId: string): string {
  return `${normalizeMissionAgentType(agent)}:${taskId || 'custom'}`;
}

/** Bloque les enchaînements incohérents (ex. liste incidents → détail log). */
export function validateTaskHandoffs(wf: WorkflowBuilderState): string[] {
  const errors: string[] = [];
  const tasks = workflowOrderedTasks(wf);
  let priorAgent: AgentType | null = null;
  let priorTaskId: string | null = null;

  for (const task of tasks) {
    const agent = workflowAgentForTask(wf, task.id);
    const taskId = (task.data.taskId || 'custom').trim() || 'custom';
    const spec = getTaskSpec(agent ?? 'reports', taskId);

    if (
      spec?.consumes_prior &&
      priorAgent &&
      priorTaskId &&
      HANDOFF_ALLOWED[handoffKey(priorAgent, priorTaskId)]
    ) {
      const allowed = HANDOFF_ALLOWED[handoffKey(priorAgent, priorTaskId)];
      const nextKey = handoffKey(agent ?? priorAgent, taskId);
      if (!allowed.includes(nextKey)) {
        const priorLabel = getTaskSpec(priorAgent, priorTaskId)?.label ?? priorTaskId;
        const nextLabel = spec?.label ?? taskId;
        if (priorAgent === 'security' && priorTaskId === 'incident_list' && agent === 'logs') {
          errors.push(
            `Après « ${priorLabel} », « ${nextLabel} » (Logs) ne peut pas afficher un incident sécurité — utilisez Security → Détail incident.`,
          );
        } else {
          errors.push(
            `« ${nextLabel} » ne peut pas exploiter directement le résultat de « ${priorLabel} ».`,
          );
        }
      }
    }

    if (agent) {
      priorAgent = agent;
      priorTaskId = taskId;
    }
  }
  return errors;
}

export function suggestNextAgentType(wf: WorkflowBuilderState): AgentType {
  const tasks = workflowOrderedTasks(wf);
  const order: AgentType[] = ['security', 'support', 'users', 'logs', 'tracking', 'reports'];
  const last = tasks.length ? workflowAgentForTask(wf, tasks[tasks.length - 1].id) : null;
  if (!last) return 'security';
  const idx = order.indexOf(last);
  return order[(idx + 1 + order.length) % order.length];
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
    const agentType = workflowAgentForTask(wf, n.id);
    if (!agentType) {
      errors.push(
        `La tâche « ${n.data.label || n.id} » doit être reliée à un bloc Agent IA en amont (Déclencheur → Agent → Tâche → …).`,
      );
      continue;
    }
    const taskId = n.data.taskId;
    const desc = (n.data.description || '').trim();
    const spec = taskId ? getTaskSpec(agentType, taskId) : undefined;
    const needsCustom = !taskId || taskId === 'custom' || spec?.requires_description;
    const resolved = resolveTaskDescription(agentType, taskId, desc);
    if (needsCustom && desc.length < 10 && (!taskId || taskId === 'custom')) {
      errors.push(`La tâche « ${n.data.label || n.id} » doit faire au moins 10 caractères (tâche libre).`);
    } else if (!resolved || resolved.length < 10) {
      errors.push(`La tâche « ${n.data.label || n.id} » est incomplète — choisissez une tâche catalogue ou décrivez-la.`);
    }
  }

  errors.push(...validateDistinctWorkflowAgents(wf));
  errors.push(...validateTaskHandoffs(wf));

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
  const tasks = workflowOrderedTasks(wf);
  const fallbackAgent = wf.nodes.find((n) => n.type === 'agent');

  const descriptions = tasks
    .map((t) => {
      const agentType = workflowAgentForTask(wf, t.id) ?? normalizeMissionAgentType('reports');
      return resolveTaskDescription(agentType, t.data.taskId, t.data.description || '');
    })
    .filter(Boolean);

  const primaryAgent =
    (tasks.length ? workflowAgentForTask(wf, tasks[0].id) : null) ??
    normalizeMissionAgentType(fallbackAgent?.data.agentType || 'reports');

  return {
    agent_type: primaryAgent,
    task_description: descriptions.length === 1 ? descriptions[0] : descriptions.map((d, i) => `${i + 1}. ${d}`).join('\n'),
    schedule_type: timing?.data.scheduleType || 'now',
    scheduled_at: timing?.data.scheduledAt ? new Date(timing.data.scheduledAt).toISOString() : null,
    schedule_time: timing?.data.scheduleTime || '08:00',
  };
}
