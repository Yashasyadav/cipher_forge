import { Routes } from '@angular/router';
import { DashboardPageComponent } from './pages/dashboard/dashboard-page.component';
import { WipeControlPageComponent } from './pages/wipe-control/wipe-control-page.component';
import { ProgressMonitorPageComponent } from './pages/progress-monitor/progress-monitor-page.component';
import { CertificatesPageComponent } from './pages/certificates/certificates-page.component';
import { AdminPageComponent } from './pages/admin-panel/admin-page.component';
import { LoginPageComponent } from './pages/login-page/login-page.component';
import { MainLayoutComponent } from './layout/main-layout/main-layout.component';
import { authGuard, roleGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  { path: 'login', component: LoginPageComponent, title: 'CipherForge | Login' },
  {
    path: '',
    component: MainLayoutComponent,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      { path: 'dashboard', component: DashboardPageComponent, title: 'CipherForge | Dashboard' },
      { path: 'wipe-control', component: WipeControlPageComponent, title: 'CipherForge | Wipe Control' },
      { path: 'progress-monitor', component: ProgressMonitorPageComponent, title: 'CipherForge | Progress Monitor' },
      {
        path: 'certificates',
        component: CertificatesPageComponent,
        title: 'CipherForge | Certificates',
        canActivate: [roleGuard],
        data: { roles: ['ADMIN'] }
      },
      {
        path: 'admin',
        component: AdminPageComponent,
        title: 'CipherForge | Admin Panel',
        canActivate: [roleGuard],
        data: { roles: ['ADMIN'] }
      }
    ]
  },
  { path: '**', redirectTo: 'dashboard' }
];
