import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';

import { AuthService } from '../services/auth.service';

export const adminGuard: CanActivateFn = () => {
  const router = inject(Router);
  const auth = inject(AuthService);

  return auth.me().pipe(
    map((profile) => (profile.role === 'admin' ? true : router.createUrlTree(['/chat']))),
    catchError(() => {
      auth.clearLocalSession();
      return of(router.createUrlTree(['/login']));
    }),
  );
};
