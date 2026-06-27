import { Routes } from '@angular/router';

export const AGENT_MISSIONS_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./components/agent-missions-list/agent-missions-list.component').then((m) => m.AgentMissionsListComponent),
  },
  {
    path: 'new',
    loadComponent: () =>
      import('./components/agent-mission-builder/agent-mission-builder.component').then((m) => m.AgentMissionBuilderComponent),
  },
  {
    path: ':id/edit',
    loadComponent: () =>
      import('./components/agent-mission-builder/agent-mission-builder.component').then((m) => m.AgentMissionBuilderComponent),
  },
  {
    path: ':id',
    loadComponent: () =>
      import('./components/agent-mission-detail/agent-mission-detail.component').then((m) => m.AgentMissionDetailComponent),
  },
];
