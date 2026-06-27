import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';

import { AuthService } from '../services/auth.service';

function homeForRole(role: string): string {
  if (role === 'admin') return '/admin';
  if (role === 'employe') return '/employee';
  return '/chat';
}

/** Pages login/register : redirige vers le bon portail si la session est encore valide. */
export const guestGuard: CanActivateFn = (route) => {
  const router = inject(Router);
  const auth = inject(AuthService);
  if (!auth.token()) {
    return true;
  }
  const audience = route.data['audience'] as string | undefined;
  return auth.me().pipe(
    map((profile) => {
      if (audience === 'employee' && profile.role === 'client') {
        return router.createUrlTree(['/chat']);
      }
      if (audience !== 'employee' && profile.role === 'employe') {
        return router.createUrlTree(['/employee']);
      }
      return router.createUrlTree([homeForRole(profile.role)]);
    }),
    catchError(() => {
      auth.clearLocalSession();
      return of(true);
    }),
  );
};
