import { Component, EventEmitter, Output, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatListModule } from '@angular/material/list';

import { AuthService } from '../../core/services/auth.service';

interface NavItem {
  route: string;
  icon: string;
  label: string;
}

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterLinkActive, MatIconModule, MatListModule],
  templateUrl: './sidebar.component.html',
  styleUrl: './sidebar.component.scss'
})
export class SidebarComponent {
  private readonly authService = inject(AuthService);

  @Output() navigate = new EventEmitter<void>();

  get navigation(): NavItem[] {
    const baseItems: NavItem[] = [
      { route: '/dashboard', icon: 'dashboard', label: 'Dashboard' },
      { route: '/wipe-control', icon: 'security', label: 'Wipe Control' },
      { route: '/progress-monitor', icon: 'monitoring', label: 'Progress Monitor' }
    ];

    if (this.authService.hasAnyRole('ADMIN')) {
      return [
        ...baseItems,
        { route: '/certificates', icon: 'verified', label: 'Certificates' },
        { route: '/admin', icon: 'admin_panel_settings', label: 'Admin Panel' }
      ];
    }

    return baseItems;
  }

  onNavigate(): void {
    this.navigate.emit();
  }
}

