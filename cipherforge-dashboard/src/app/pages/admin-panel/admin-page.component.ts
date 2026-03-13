import { AfterViewInit, Component, DestroyRef, ElementRef, OnDestroy, OnInit, ViewChild, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { finalize } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import Chart from 'chart.js/auto';

import { Stats } from '../../core/models/api.models';
import { FileShredHistoryService } from '../../core/services/file-shred-history.service';
import { ApiService } from '../../services/api.service';

@Component({
  selector: 'app-admin-page',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatButtonModule, MatProgressSpinnerModule, MatSnackBarModule],
  templateUrl: './admin-page.component.html',
  styleUrl: './admin-page.component.scss'
})
export class AdminPageComponent implements OnInit, AfterViewInit, OnDestroy {
  private readonly api = inject(ApiService);
  private readonly fileShredHistory = inject(FileShredHistoryService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly destroyRef = inject(DestroyRef);
  private volumeChart: Chart | null = null;
  private outcomeChart: Chart | null = null;
  private pollTimerId: number | null = null;
  private renderTimerId: number | null = null;
  private bootstrapRetryTimerId: number | null = null;
  private quickRetryTimerId: number | null = null;
  private bootstrapAttempts = 0;

  @ViewChild('volumeChartCanvas') private volumeChartCanvas?: ElementRef<HTMLCanvasElement>;
  @ViewChild('outcomeChartCanvas') private outcomeChartCanvas?: ElementRef<HTMLCanvasElement>;

  stats: Stats | null = null;
  isLoading = false;
  errorMessage = '';
  private localCompleted = 0;
  private localFailed = 0;
  private localActive = 0;
  private localCertificates = 0;

  get devicesWiped(): number {
    const remoteCompleted = this.stats?.devices_wiped ?? this.stats?.completedWipeJobs ?? this.stats?.totalWipeJobs ?? 0;
    return remoteCompleted + this.localCompleted;
  }

  get failedWipes(): number {
    const remoteFailed = this.stats?.failed_jobs ?? this.stats?.failedWipeJobs ?? 0;
    return remoteFailed + this.localFailed;
  }

  get successfulWipes(): number {
    const remoteSuccessful = this.stats?.successful_wipes ?? this.stats?.completedWipeJobs ?? this.stats?.devices_wiped ?? 0;
    return remoteSuccessful + this.localCompleted;
  }

  get certificatesIssued(): number {
    const remoteCertificates = this.stats?.certificates_generated ?? this.stats?.certificates ?? this.stats?.totalCertificates ?? 0;
    return remoteCertificates + this.localCertificates;
  }

  get activeJobs(): number {
    return (this.stats?.active_jobs ?? 0) + this.localActive;
  }

  ngOnInit(): void {
    this.fileShredHistory.entries$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        try {
          const summary = this.fileShredHistory.getSummary();
          this.localCompleted = summary.completed;
          this.localFailed = summary.failed;
          this.localActive = summary.active;
          this.localCertificates = summary.certificates;
          this.scheduleRenderCharts();
        } catch (error) {
          console.error('Failed to read local shred history summary', error);
        }
      });

    this.refresh();
    window.setTimeout(() => this.refresh(true), 350);
    this.startBootstrapRetries();
    this.pollTimerId = window.setInterval(() => this.refresh(true), 10000);
  }

  ngAfterViewInit(): void {
    this.scheduleRenderCharts();
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
    if (this.quickRetryTimerId !== null) {
      window.clearTimeout(this.quickRetryTimerId);
      this.quickRetryTimerId = null;
    }
    if (this.renderTimerId !== null) {
      window.clearTimeout(this.renderTimerId);
      this.renderTimerId = null;
    }
    this.destroyCharts();
  }

  refresh(silent = false): void {
    if (!silent) {
      this.isLoading = true;
      this.errorMessage = '';
    }
    this.api.getStats()
      .pipe(finalize(() => {
        if (!silent) {
          this.isLoading = false;
        }
      }))
      .subscribe({
        next: (stats) => {
          this.stats = stats;
          this.errorMessage = '';
          if (this.quickRetryTimerId !== null) {
            window.clearTimeout(this.quickRetryTimerId);
            this.quickRetryTimerId = null;
          }
          if (this.bootstrapRetryTimerId !== null) {
            window.clearInterval(this.bootstrapRetryTimerId);
            this.bootstrapRetryTimerId = null;
          }
          this.scheduleRenderCharts();
        },
        error: (error: Error) => {
          if (!silent) {
            this.stats = null;
            this.errorMessage = error.message || 'Unable to load statistics.';
            this.snackBar.open(this.errorMessage, 'Dismiss', { duration: 2800 });
            this.destroyCharts();
          }
          this.scheduleQuickRetry();
        }
      });
  }

  private startBootstrapRetries(): void {
    this.bootstrapAttempts = 0;
    if (this.bootstrapRetryTimerId !== null) {
      window.clearInterval(this.bootstrapRetryTimerId);
    }
    this.bootstrapRetryTimerId = window.setInterval(() => {
      if (this.stats) {
        if (this.bootstrapRetryTimerId !== null) {
          window.clearInterval(this.bootstrapRetryTimerId);
          this.bootstrapRetryTimerId = null;
        }
        return;
      }

      this.bootstrapAttempts += 1;
      this.refresh(true);
      if (this.bootstrapAttempts >= 20 && this.bootstrapRetryTimerId !== null) {
        window.clearInterval(this.bootstrapRetryTimerId);
        this.bootstrapRetryTimerId = null;
      }
    }, 1500);
  }

  private scheduleQuickRetry(): void {
    if (this.quickRetryTimerId !== null || this.stats) {
      return;
    }

    this.quickRetryTimerId = window.setTimeout(() => {
      this.quickRetryTimerId = null;
      this.refresh(true);
    }, 1500);
  }

  private scheduleRenderCharts(): void {
    if (this.renderTimerId !== null) {
      window.clearTimeout(this.renderTimerId);
    }

    // Wait for Angular to paint the conditional canvas nodes before Chart.js init.
    this.renderTimerId = window.setTimeout(() => {
      this.renderTimerId = null;
      this.renderCharts();
    }, 0);
  }

  private renderCharts(): void {
    try {
      if (!this.stats || !this.volumeChartCanvas || !this.outcomeChartCanvas) {
        return;
      }

      const volumeContext = this.volumeChartCanvas.nativeElement.getContext('2d');
      const outcomeContext = this.outcomeChartCanvas.nativeElement.getContext('2d');
      if (!volumeContext || !outcomeContext) {
        return;
      }

      if (this.volumeChart) {
        this.volumeChart.destroy();
      }
      this.volumeChart = new Chart(volumeContext, {
        type: 'bar',
        data: {
          labels: ['Devices Wiped', 'Successful Wipes', 'Certificates', 'Active Jobs'],
          datasets: [
            {
              label: 'Count',
              data: [this.devicesWiped, this.successfulWipes, this.certificatesIssued, this.activeJobs],
              backgroundColor: ['#2563eb', '#0ea5e9', '#1d4ed8', '#38bdf8'],
              borderRadius: 8
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false }
          },
          scales: {
            y: {
              beginAtZero: true,
              ticks: { precision: 0 }
            }
          }
        }
      });

      if (this.outcomeChart) {
        this.outcomeChart.destroy();
      }
      this.outcomeChart = new Chart(outcomeContext, {
        type: 'doughnut',
        data: {
          labels: ['Successful', 'Failed', 'Active'],
          datasets: [
            {
              data: [this.successfulWipes, this.failedWipes, this.activeJobs],
              backgroundColor: ['#16a34a', '#dc2626', '#2563eb'],
              borderColor: '#ffffff',
              borderWidth: 2
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: 'bottom'
            }
          }
        }
      });
    } catch (error) {
      console.error('Failed to render admin charts', error);
    }
  }

  private destroyCharts(): void {
    if (this.volumeChart) {
      this.volumeChart.destroy();
      this.volumeChart = null;
    }
    if (this.outcomeChart) {
      this.outcomeChart.destroy();
      this.outcomeChart = null;
    }
  }
}
