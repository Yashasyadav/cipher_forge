import { Component, EventEmitter, Output, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatIconModule],
  templateUrl: './header.component.html',
  styleUrl: './header.component.scss'
})
export class HeaderComponent {
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);

  @Output() menuToggle = new EventEmitter<void>();

  get username(): string {
    return this.authService.getUsername() ?? 'User';
  }

  get role(): string {
    return this.authService.getRole() ?? 'USER';
  }

  onToggleMenu(): void {
    this.menuToggle.emit();
  }

  logout(): void {
    this.authService.logout();
    this.router.navigateByUrl('/login');
  }
}

