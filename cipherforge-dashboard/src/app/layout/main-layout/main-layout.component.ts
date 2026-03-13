import { Component, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet } from '@angular/router';
import { MatSidenavModule } from '@angular/material/sidenav';

import { FooterComponent } from '../footer/footer.component';
import { HeaderComponent } from '../header/header.component';
import { SidebarComponent } from '../sidebar/sidebar.component';

@Component({
  selector: 'app-main-layout',
  standalone: true,
  imports: [CommonModule, RouterOutlet, MatSidenavModule, SidebarComponent, HeaderComponent, FooterComponent],
  templateUrl: './main-layout.component.html',
  styleUrl: './main-layout.component.scss'
})
export class MainLayoutComponent {
  isMobile = typeof window !== 'undefined' ? window.innerWidth < 920 : false;
  mobileNavOpen = false;

  @HostListener('window:resize')
  onWindowResize(): void {
    const wasMobile = this.isMobile;
    this.isMobile = window.innerWidth < 920;
    if (!this.isMobile) {
      this.mobileNavOpen = false;
    } else if (!wasMobile) {
      this.mobileNavOpen = false;
    }
  }

  onMenuToggle(): void {
    if (this.isMobile) {
      this.mobileNavOpen = !this.mobileNavOpen;
    }
  }

  onSidebarNavigate(): void {
    if (this.isMobile) {
      this.mobileNavOpen = false;
    }
  }
}

