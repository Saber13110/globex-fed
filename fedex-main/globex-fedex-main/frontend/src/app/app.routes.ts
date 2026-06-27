import { Routes } from '@angular/router';

import { adminGuard } from './core/guards/admin.guard';
import { authGuard } from './core/guards/auth.guard';
import { clientPortalGuard } from './core/guards/portal.guard';
import { employeePortalGuard } from './core/guards/portal.guard';
import { guestGuard } from './core/guards/guest.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'chat' },
  {
    path: 'login',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/login/login.component').then((m) => m.LoginComponent),
  },
  {
    path: 'register',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/register/register.component').then((m) => m.RegisterComponent),
  },
  {
    path: 'employee/login',
    canActivate: [guestGuard],
    data: { audience: 'employee' },
    loadComponent: () => import('./features/auth/login/login.component').then((m) => m.LoginComponent),
  },
  {
    path: 'employee/register',
    canActivate: [guestGuard],
    data: { audience: 'employee' },
    loadComponent: () => import('./features/auth/register/register.component').then((m) => m.RegisterComponent),
  },
  {
    path: 'employee/activate',
    loadComponent: () => import('./features/auth/activate/activate.component').then((m) => m.ActivateComponent),
  },
  {
    path: 'admin/login',
    redirectTo: 'login',
    pathMatch: 'full',
  },
  {
    path: 'chat',
    canActivate: [authGuard, clientPortalGuard],
    loadComponent: () => import('./features/chat/chat-page.component').then((m) => m.ChatPageComponent),
  },
  {
    path: 'chat/shared/:token',
    canActivate: [authGuard, clientPortalGuard],
    loadComponent: () => import('./features/chat/chat-page.component').then((m) => m.ChatPageComponent),
  },
  {
    path: 'history',
    canActivate: [authGuard, clientPortalGuard],
    loadComponent: () => import('./features/history/history-page.component').then((m) => m.HistoryPageComponent),
  },
  {
    path: 'documents',
    canActivate: [authGuard, clientPortalGuard],
    loadComponent: () => import('./features/documents/documents-page.component').then((m) => m.DocumentsPageComponent),
  },
  {
    path: 'support',
    redirectTo: 'help?support=1',
    pathMatch: 'full',
  },
  {
    path: 'espace',
    canActivate: [authGuard, clientPortalGuard],
    loadComponent: () => import('./features/user-space/user-space-page.component').then((m) => m.UserSpacePageComponent),
  },
  { path: 'settings', pathMatch: 'full', redirectTo: 'settings/profile' },
  {
    path: 'settings/:tab',
    canActivate: [authGuard, clientPortalGuard],
    loadComponent: () => import('./features/settings/settings-page.component').then((m) => m.SettingsPageComponent),
  },
  {
    path: 'help',
    canActivate: [authGuard, clientPortalGuard],
    loadComponent: () => import('./features/help/help-page.component').then((m) => m.HelpPageComponent),
  },
  {
    path: 'notifications',
    canActivate: [authGuard, clientPortalGuard],
    loadComponent: () =>
      import('./features/notifications/notifications-page.component').then((m) => m.NotificationsPageComponent),
  },
  {
    path: 'employee',
    canActivate: [authGuard, employeePortalGuard],
    loadComponent: () =>
      import('./features/employee/shell/employee-shell.component').then((m) => m.EmployeeShellComponent),
    children: [
      {
        path: '',
        loadComponent: () =>
          import('./features/employee/pages/dashboard/employee-dashboard.component').then((m) => m.EmployeeDashboardComponent),
      },
      {
        path: 'ai-assistant',
        loadComponent: () =>
          import('./features/employee/pages/ai-assistant/employee-ai-assistant-page.component').then(
            (m) => m.EmployeeAiAssistantPageComponent,
          ),
      },
      {
        path: 'ai-agent',
        loadComponent: () =>
          import('./features/employee/pages/ai-agent/employee-ai-agent-page.component').then(
            (m) => m.EmployeeAiAgentPageComponent,
          ),
      },
      {
        path: 'chat',
        redirectTo: 'ai-assistant',
        pathMatch: 'full',
      },
      {
        path: 'clients',
        loadComponent: () =>
          import('./features/employee/pages/clients/employee-clients-page.component').then((m) => m.EmployeeClientsPageComponent),
      },
      {
        path: 'client/:id',
        loadComponent: () =>
          import('./features/employee/pages/client-detail/employee-client-detail-page.component').then(
            (m) => m.EmployeeClientDetailPageComponent,
          ),
      },
      {
        path: 'tracking/:trackingNumber',
        loadComponent: () =>
          import('./features/employee/pages/shipment-detail/employee-shipment-detail-page.component').then(
            (m) => m.EmployeeShipmentDetailPageComponent,
          ),
      },
      {
        path: 'tracking',
        loadComponent: () =>
          import('./features/employee/pages/tracking/employee-tracking-page.component').then((m) => m.EmployeeTrackingPageComponent),
      },
      {
        path: 'tracking-history',
        loadComponent: () =>
          import('./features/employee/pages/tracking-history/employee-tracking-history-page.component').then(
            (m) => m.EmployeeTrackingHistoryPageComponent,
          ),
      },
      {
        path: 'support',
        loadComponent: () =>
          import('./features/employee/pages/support/employee-support-page.component').then((m) => m.EmployeeSupportPageComponent),
      },
      {
        path: 'support/:ticketId',
        loadComponent: () =>
          import('./features/employee/pages/support/employee-support-page.component').then((m) => m.EmployeeSupportPageComponent),
      },
      {
        path: 'documents',
        loadComponent: () =>
          import('./features/employee/pages/documents/employee-documents-page.component').then(
            (m) => m.EmployeeDocumentsPageComponent,
          ),
      },
      {
        path: 'notifications',
        loadComponent: () =>
          import('./features/employee/pages/notifications/employee-notifications-page.component').then(
            (m) => m.EmployeeNotificationsPageComponent,
          ),
      },
      {
        path: 'admin-chat',
        loadComponent: () =>
          import('./features/employee/pages/admin-chat/employee-admin-chat-page.component').then(
            (m) => m.EmployeeAdminChatPageComponent,
          ),
      },
      {
        path: 'help',
        loadComponent: () =>
          import('./features/employee/pages/help/employee-help-page.component').then((m) => m.EmployeeHelpPageComponent),
      },
    ],
  },
  {
    path: 'admin',
    canActivate: [authGuard, adminGuard],
    loadComponent: () => import('./features/admin/admin-page.component').then((m) => m.AdminPageComponent),
    children: [
      {
        path: 'agent-missions',
        loadChildren: () =>
          import('./features/admin/agent-missions/agent-missions.routes').then((m) => m.AGENT_MISSIONS_ROUTES),
      },
    ],
  },
  { path: '**', redirectTo: 'chat' },
];
