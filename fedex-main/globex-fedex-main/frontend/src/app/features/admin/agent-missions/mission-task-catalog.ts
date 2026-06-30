import { AgentType } from '../../../core/services/agent-missions.service';

export interface MissionTaskCatalogEntry {
  task_id: string;
  agent_type: AgentType;
  label: string;
  default_prompt: string;
  action_type: string;
  requires_description: boolean;
  /** Peut réutiliser le résultat de l'étape précédente (phase 1 — métadonnée). */
  consumes_prior: boolean;
  /** Son output est utile pour alimenter une étape suivante. */
  produces_context: boolean;
  /** Fin de chaîne (export, action sensible). */
  terminal: boolean;
}

/** Miroir backend — mission_task_catalog.py */
export const MISSION_TASK_CATALOG: MissionTaskCatalogEntry[] = [
  { task_id: 'log_list', agent_type: 'logs', label: 'Lister les logs', default_prompt: "Lister les derniers logs d'activité de la plateforme.", action_type: 'analyze_logs', requires_description: false, consumes_prior: false, produces_context: true, terminal: false },
  { task_id: 'log_detail', agent_type: 'logs', label: "Détail d'un log", default_prompt: "Afficher le détail d'un événement du journal d'activité récent.", action_type: 'analyze_logs', requires_description: false, consumes_prior: true, produces_context: true, terminal: false },
  { task_id: 'log_anomalies', agent_type: 'logs', label: 'Détecter anomalies', default_prompt: 'Détecter les anomalies et alertes WARNING/CRITICAL dans les logs.', action_type: 'analyze_logs', requires_description: false, consumes_prior: false, produces_context: true, terminal: false },
  { task_id: 'log_summary', agent_type: 'logs', label: 'Synthèse logs', default_prompt: 'Produire une synthèse des événements importants du journal.', action_type: 'analyze_logs', requires_description: false, consumes_prior: true, produces_context: true, terminal: false },
  { task_id: 'log_export_pdf', agent_type: 'logs', label: 'Export PDF logs', default_prompt: 'Exporter le journal d\'activité en fichier PDF téléchargeable.', action_type: 'export_activity_logs_pdf', requires_description: false, consumes_prior: false, produces_context: false, terminal: true },
  { task_id: 'log_export_excel', agent_type: 'logs', label: 'Export Excel logs', default_prompt: 'Exporter le journal d\'activité en fichier Excel téléchargeable.', action_type: 'export_activity_logs_excel', requires_description: false, consumes_prior: false, produces_context: false, terminal: true },
  { task_id: 'log_suspend_user', agent_type: 'logs', label: 'Suspendre depuis log', default_prompt: 'Identifier un utilisateur suspect dans les logs et préparer une suspension.', action_type: 'suspend_user', requires_description: true, consumes_prior: true, produces_context: false, terminal: true },
  { task_id: 'custom', agent_type: 'logs', label: 'Tâche libre', default_prompt: '', action_type: 'analyze_logs', requires_description: true, consumes_prior: false, produces_context: true, terminal: false },

  { task_id: 'ticket_list', agent_type: 'support', label: 'Tickets ouverts', default_prompt: 'Lister les tickets support ouverts et leurs priorités.', action_type: 'analyze_tickets', requires_description: false, consumes_prior: false, produces_context: true, terminal: false },
  { task_id: 'ticket_detail', agent_type: 'support', label: 'Détail ticket', default_prompt: 'Analyser en détail un ticket support spécifique.', action_type: 'analyze_tickets', requires_description: true, consumes_prior: true, produces_context: true, terminal: false },
  { task_id: 'ticket_reply', agent_type: 'support', label: 'Répondre ticket', default_prompt: 'Préparer une réponse au ticket client indiqué.', action_type: 'send_support_reply', requires_description: true, consumes_prior: true, produces_context: false, terminal: true },
  { task_id: 'ticket_resolve', agent_type: 'support', label: 'Clore ticket', default_prompt: 'Marquer comme résolu le ticket support indiqué.', action_type: 'resolve_ticket', requires_description: true, consumes_prior: true, produces_context: false, terminal: true },
  { task_id: 'custom', agent_type: 'support', label: 'Tâche libre', default_prompt: '', action_type: 'analyze_tickets', requires_description: true, consumes_prior: false, produces_context: true, terminal: false },

  { task_id: 'user_list', agent_type: 'users', label: 'Lister utilisateurs', default_prompt: 'Lister les comptes utilisateurs et leurs statuts.', action_type: 'analyze_users', requires_description: false, consumes_prior: false, produces_context: true, terminal: false },
  { task_id: 'user_detail', agent_type: 'users', label: 'Fiche utilisateur', default_prompt: "Afficher le détail d'un compte utilisateur.", action_type: 'analyze_users', requires_description: true, consumes_prior: true, produces_context: true, terminal: false },
  { task_id: 'user_logs', agent_type: 'users', label: 'Logs utilisateur', default_prompt: "Analyser l'activité récente d'un utilisateur.", action_type: 'analyze_users', requires_description: true, consumes_prior: true, produces_context: true, terminal: false },
  { task_id: 'user_permissions', agent_type: 'users', label: 'Permissions', default_prompt: "Vérifier les permissions et le rôle d'un utilisateur.", action_type: 'analyze_users', requires_description: true, consumes_prior: true, produces_context: true, terminal: false },
  { task_id: 'user_suspend', agent_type: 'users', label: 'Suspendre compte', default_prompt: 'Suspendre le compte utilisateur indiqué.', action_type: 'suspend_user', requires_description: true, consumes_prior: true, produces_context: false, terminal: true },
  { task_id: 'user_reactivate', agent_type: 'users', label: 'Réactiver compte', default_prompt: 'Réactiver le compte utilisateur indiqué.', action_type: 'reactivate_user', requires_description: true, consumes_prior: true, produces_context: false, terminal: true },
  { task_id: 'user_delete', agent_type: 'users', label: 'Supprimer compte', default_prompt: 'Préparer la suppression du compte utilisateur indiqué.', action_type: 'delete_user', requires_description: true, consumes_prior: true, produces_context: false, terminal: true },
  { task_id: 'user_reset_password', agent_type: 'users', label: 'Reset mot de passe', default_prompt: 'Préparer la réinitialisation du mot de passe.', action_type: 'reset_password', requires_description: true, consumes_prior: true, produces_context: false, terminal: true },
  { task_id: 'custom', agent_type: 'users', label: 'Tâche libre', default_prompt: '', action_type: 'analyze_users', requires_description: true, consumes_prior: false, produces_context: true, terminal: false },

  { task_id: 'incident_list', agent_type: 'security', label: 'Incidents sécurité', default_prompt: 'Lister les incidents de sécurité récents.', action_type: 'analyze_security', requires_description: false, consumes_prior: false, produces_context: true, terminal: false },
  { task_id: 'incident_detail', agent_type: 'security', label: 'Détail incident', default_prompt: 'Analyser un incident de sécurité spécifique.', action_type: 'analyze_security', requires_description: true, consumes_prior: true, produces_context: true, terminal: false },
  { task_id: 'incident_summary', agent_type: 'security', label: 'Synthèse sécurité', default_prompt: "Synthétiser l'état de la sécurité et les menaces détectées.", action_type: 'analyze_security', requires_description: false, consumes_prior: true, produces_context: true, terminal: false },
  { task_id: 'security_scan', agent_type: 'security', label: 'Scan sécurité', default_prompt: "Lancer une analyse des tentatives d'intrusion et alertes IDS.", action_type: 'analyze_security', requires_description: false, consumes_prior: false, produces_context: true, terminal: false },
  { task_id: 'security_report', agent_type: 'security', label: 'Rapport sécurité', default_prompt: 'Produire un rapport des alertes et incidents de sécurité.', action_type: 'analyze_security', requires_description: false, consumes_prior: true, produces_context: false, terminal: true },
  { task_id: 'notif_list', agent_type: 'security', label: 'Notifications plateforme', default_prompt: 'Lister les notifications admin non lues.', action_type: 'analyze_notifications', requires_description: false, consumes_prior: false, produces_context: false, terminal: false },
  { task_id: 'custom', agent_type: 'security', label: 'Tâche libre', default_prompt: '', action_type: 'analyze_security', requires_description: true, consumes_prior: false, produces_context: true, terminal: false },

  { task_id: 'tracking_analyze', agent_type: 'tracking', label: 'Analyser expéditions', default_prompt: 'Analyser les expéditions en cours et détecter les retards.', action_type: 'analyze_tracking', requires_description: false, consumes_prior: false, produces_context: true, terminal: false },
  { task_id: 'tracking_export_excel', agent_type: 'tracking', label: 'Export Excel tracking', default_prompt: 'Exporter les données de suivi en Excel.', action_type: 'export_tracking_excel', requires_description: false, consumes_prior: true, produces_context: false, terminal: true },
  { task_id: 'tracking_export_email', agent_type: 'tracking', label: 'Export e-mail tracking', default_prompt: 'Exporter les données de suivi et les envoyer par e-mail.', action_type: 'export_and_email_tracking', requires_description: false, consumes_prior: true, produces_context: false, terminal: true },
  { task_id: 'custom', agent_type: 'tracking', label: 'Tâche libre', default_prompt: '', action_type: 'analyze_tracking', requires_description: true, consumes_prior: false, produces_context: true, terminal: false },

  { task_id: 'report_list', agent_type: 'reports', label: 'Lister rapports', default_prompt: 'Lister les rapports disponibles.', action_type: 'generate_summary', requires_description: false, consumes_prior: false, produces_context: true, terminal: false },
  { task_id: 'report_preview', agent_type: 'reports', label: 'Aperçu rapport', default_prompt: "Prévisualiser le contenu d'un rapport.", action_type: 'generate_summary', requires_description: true, consumes_prior: true, produces_context: true, terminal: false },
  { task_id: 'report_redownload', agent_type: 'reports', label: 'Retélécharger rapport', default_prompt: 'Retélécharger un rapport exporté précédemment.', action_type: 'generate_summary', requires_description: true, consumes_prior: false, produces_context: false, terminal: false },
  { task_id: 'report_share', agent_type: 'reports', label: 'Partager rapport', default_prompt: 'Partager un rapport avec un destinataire.', action_type: 'generate_summary', requires_description: true, consumes_prior: true, produces_context: false, terminal: true },
  { task_id: 'custom', agent_type: 'reports', label: 'Tâche libre', default_prompt: '', action_type: 'generate_summary', requires_description: true, consumes_prior: false, produces_context: true, terminal: false },
];

const LEGACY_AGENT_MAP: Partial<Record<AgentType, AgentType>> = {
  notifications: 'security',
  summary: 'reports',
};

export function normalizeMissionAgentType(agentType: AgentType | string): AgentType {
  const key = agentType as AgentType;
  return (LEGACY_AGENT_MAP[key] as AgentType) || key;
}

export function tasksForAgent(agentType: AgentType | string): MissionTaskCatalogEntry[] {
  const canonical = normalizeMissionAgentType(agentType);
  return MISSION_TASK_CATALOG.filter((t) => t.agent_type === canonical);
}

export function getTaskSpec(agentType: AgentType | string, taskId: string): MissionTaskCatalogEntry | undefined {
  const canonical = normalizeMissionAgentType(agentType);
  return MISSION_TASK_CATALOG.find((t) => t.agent_type === canonical && t.task_id === taskId);
}

export function resolveTaskDescription(
  agentType: AgentType | string,
  taskId: string | undefined,
  customDescription: string,
): string {
  if (!taskId || taskId === 'custom') {
    return customDescription.trim();
  }
  const spec = getTaskSpec(agentType, taskId);
  if (!spec) {
    return customDescription.trim();
  }
  const parts = [spec.default_prompt, customDescription.trim()].filter(Boolean);
  return parts.join('\n\n');
}
