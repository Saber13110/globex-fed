import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';

import { AuthService } from '../services/auth.service';

export const authGuard: CanActivateFn = () => {
  const router = inject(Router);
  const auth = inject(AuthService);
  if (!auth.token()) {
    return router.createUrlTree(['/login']);
  }
  return auth.me().pipe(
    map(() => true),
    catchError(() => {
      auth.clearLocalSession();
      return of(router.createUrlTree(['/login']));
    }),
  );
};
