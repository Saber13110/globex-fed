import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';

import { AuthService } from '../services/auth.service';

/** Espace client final : pas d’accès admin ni employé. */
export const clientPortalGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (!auth.token()) {
    return router.createUrlTree(['/login']);
  }
  return auth.me().pipe(
    map((profile) => {
      if (profile.role === 'admin') {
        return router.createUrlTree(['/admin']);
      }
      if (profile.role === 'employe') {
        return router.createUrlTree(['/employee']);
      }
      return true;
    }),
    catchError(() => {
      auth.clearLocalSession();
      return of(router.createUrlTree(['/login']));
    }),
  );
};

/** Espace employé : redirection admin → admin, client → chat client. */
export const employeePortalGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (!auth.token()) {
    return router.createUrlTree(['/employee/login']);
  }
  return auth.me().pipe(
    map((profile) => {
      if (profile.role === 'admin') {
        return router.createUrlTree(['/admin']);
      }
      if (profile.role === 'client') {
        return router.createUrlTree(['/chat']);
      }
      return true;
    }),
    catchError(() => {
      auth.clearLocalSession();
      return of(router.createUrlTree(['/employee/login']));
    }),
  );
};
