import { CanActivateFn, Router } from '@angular/router';
import { inject } from '@angular/core';

import { UserRole } from '../models/api.models';
import { AuthService } from '../services/auth.service';

export const authGuard: CanActivateFn = () => {
  const authService = inject(AuthService);
  const router = inject(Router);
  if (authService.isAuthenticated()) {
    return true;
  }
  return router.createUrlTree(['/login']);
};

export const roleGuard: CanActivateFn = (route) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  if (!authService.isAuthenticated()) {
    return router.createUrlTree(['/login']);
  }

  const allowedRoles = (route.data?.['roles'] as UserRole[] | undefined) ?? [];
  if (allowedRoles.length === 0 || authService.hasAnyRole(...allowedRoles)) {
    return true;
  }

  return router.createUrlTree(['/dashboard']);
};
