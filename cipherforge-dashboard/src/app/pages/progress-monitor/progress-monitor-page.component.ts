import { Component, DestroyRef, OnDestroy, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatChipsModule } from '@angular/material/chips';
import { MatButtonModule } from '@angular/material/button';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { combineLatest } from 'rxjs';
import { finalize } from 'rxjs/operators';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { WipeJobStatus } from '../../core/models/api.models';
import { FileShredHistoryService } from '../../core/services/file-shred-history.service';
import { ProgressWebSocketService } from '../../core/services/progress-websocket.service';
import { WipeJobTrackerService } from '../../core/services/wipe-job-tracker.service';

@Component({
  selector: 'app-progress-monitor-page',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatTableModule, MatProgressBarModule, MatChipsModule, MatButtonModule, MatSnackBarModule],
  templateUrl: './progress-monitor-page.component.html',
  styleUrl: './progress-monitor-page.component.scss'
})
export class ProgressMonitorPageComponent implements OnInit, OnDestroy {
  private readonly tracker = inject(WipeJobTrackerService);
  private readonly fileShredHistory = inject(FileShredHistoryService);
  private readonly progressSocket = inject(ProgressWebSocketService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly destroyRef = inject(DestroyRef);
  private pollTimerId: number | null = null;
  private bootstrapRetryTimerId: number | null = null;
  private bootstrapAttempts = 0;

  jobs: WipeJobStatus[] = [];
  loading = false;
  errorMessage = '';
  liveConnected = false;
  displayedColumns = ['jobId', 'type', 'target', 'algorithm', 'progress', 'status'];

  ngOnInit(): void {
    combineLatest([this.tracker.jobs$, this.fileShredHistory.entries$])
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(([remoteJobs]) => {
        const localJobs = this.fileShredHistory.asWipeJobs();
        this.jobs = [...localJobs, ...remoteJobs].sort((left, right) => {
          const leftTime = new Date(left.startTime ?? 0).getTime();
          const rightTime = new Date(right.startTime ?? 0).getTime();
          return rightTime - leftTime;
        });
      });

    this.progressSocket.connected$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((connected) => (this.liveConnected = connected));

    this.progressSocket.updates$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((update) => this.tracker.upsertJob(update));

    this.refresh(false, true);
    window.setTimeout(() => this.refresh(false, false), 350);
    this.progressSocket.connect();
    this.startBootstrapRetries();
    this.pollTimerId = window.setInterval(() => this.refresh(false, false), 8000);
  }

  ngOnDestroy(): void {
    this.progressSocket.disconnect();
    if (this.pollTimerId !== null) {
      window.clearInterval(this.pollTimerId);
      this.pollTimerId = null;
    }
    if (this.bootstrapRetryTimerId !== null) {
      window.clearInterval(this.bootstrapRetryTimerId);
      this.bootstrapRetryTimerId = null;
    }
  }

  refresh(showErrorToast = true, showLoading = true): void {
    if (showLoading) {
      this.loading = true;
    }
    this.errorMessage = '';
    this.tracker.refreshJobs()
      .pipe(finalize(() => {
        if (showLoading) {
          this.loading = false;
        }
      }))
      .subscribe({
        error: (error: Error) => {
          this.errorMessage = error.message || 'Unable to refresh wipe jobs.';
          if (showErrorToast) {
            this.snackBar.open(this.errorMessage, 'Dismiss', { duration: 2600 });
          }
          window.setTimeout(() => this.refresh(false, false), 1800);
        }
      });
  }

  chipColor(status: string): 'primary' | 'accent' | 'warn' {
    const normalized = status.toLowerCase();
    if (normalized.includes('completed')) return 'primary';
    if (normalized.includes('failed')) return 'warn';
    return 'accent';
  }

  getJobType(job: WipeJobStatus): 'DEVICE' | 'FILE' {
    if (job.jobType === 'DEVICE' || job.jobType === 'FILE') {
      return job.jobType;
    }

    if (job.target) {
      return 'FILE';
    }

    return job.device.includes('::') ? 'FILE' : 'DEVICE';
  }

  getJobTarget(job: WipeJobStatus): string {
    if (job.target?.trim()) {
      return job.target;
    }

    const splitMarker = '::';
    if (job.device.includes(splitMarker)) {
      const [, inferredTarget = ''] = job.device.split(splitMarker);
      const normalized = inferredTarget.trim();
      return normalized || job.device;
    }

    return job.device;
  }

  getJobAlgorithm(job: WipeJobStatus): string {
    return job.wipeMethod || 'Unknown';
  }

  get activeJobs(): WipeJobStatus[] {
    return this.jobs.filter((job) => {
      const status = job.status.toUpperCase();
      return status !== 'COMPLETED' && status !== 'FAILED';
    });
  }

  private startBootstrapRetries(): void {
    this.bootstrapAttempts = 0;
    if (this.bootstrapRetryTimerId !== null) {
      window.clearInterval(this.bootstrapRetryTimerId);
    }
    this.bootstrapRetryTimerId = window.setInterval(() => {
      this.bootstrapAttempts += 1;
      this.refresh(false, false);
      if (this.bootstrapAttempts >= 4 && this.bootstrapRetryTimerId !== null) {
        window.clearInterval(this.bootstrapRetryTimerId);
        this.bootstrapRetryTimerId = null;
      }
    }, 1500);
  }
}
