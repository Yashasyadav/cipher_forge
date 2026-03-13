import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { finalize } from 'rxjs';

import { Device } from '../../core/models/api.models';
import { ApiService } from '../../services/api.service';

@Component({
  selector: 'app-dashboard-page',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatIconModule,
    MatTableModule,
    MatButtonModule,
    MatProgressSpinnerModule
  ],
  templateUrl: './dashboard-page.component.html',
  styleUrl: './dashboard-page.component.scss'
})
export class DashboardPageComponent implements OnInit, OnDestroy {
  private readonly api = inject(ApiService);
  private pollTimerId: number | null = null;
  private bootstrapRetryTimerId: number | null = null;
  private bootstrapAttempts = 0;

  devices: Device[] = [];
  loading = false;
  errorMessage = '';
  displayedColumns = ['deviceName', 'deviceType', 'size', 'serialNumber', 'lastSeenAt'];

  get deviceCount(): number {
    return this.devices.length;
  }

  get ssdCount(): number {
    return this.devices.filter((d) => d.deviceType.toUpperCase().includes('SSD')).length;
  }

  get hddCount(): number {
    return this.devices.filter((d) => d.deviceType.toUpperCase().includes('HDD')).length;
  }

  ngOnInit(): void {
    this.loadDevices();
    window.setTimeout(() => this.loadDevices(true), 350);
    this.startBootstrapRetries();
    this.pollTimerId = window.setInterval(() => this.loadDevices(true), 10000);
  }

  loadDevices(silent = false): void {
    if (!silent) {
      this.loading = true;
      this.errorMessage = '';
    }
    this.api.getDevices()
      .pipe(
        finalize(() => {
          if (!silent) {
            this.loading = false;
          }
        })
      )
      .subscribe({
        next: (devices) => {
          this.devices = devices;
        },
        error: (error: Error) => {
          if (!silent) {
            this.devices = [];
            this.errorMessage = error.message || 'Unable to load devices.';
            window.setTimeout(() => this.loadDevices(true), 1800);
          }
        }
      });
  }

  ngOnDestroy(): void {
    if (this.pollTimerId !== null) {
      window.clearInterval(this.pollTimerId);
      this.pollTimerId = null;
    }
    if (this.bootstrapRetryTimerId !== null) {
      window.clearInterval(this.bootstrapRetryTimerId);
      this.bootstrapRetryTimerId = null;
    }
  }

  private startBootstrapRetries(): void {
    this.bootstrapAttempts = 0;
    if (this.bootstrapRetryTimerId !== null) {
      window.clearInterval(this.bootstrapRetryTimerId);
    }
    this.bootstrapRetryTimerId = window.setInterval(() => {
      this.bootstrapAttempts += 1;
      this.loadDevices(true);
      if (this.bootstrapAttempts >= 4 && this.bootstrapRetryTimerId !== null) {
        window.clearInterval(this.bootstrapRetryTimerId);
        this.bootstrapRetryTimerId = null;
      }
    }, 1500);
  }
}

