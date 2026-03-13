import { Component, DestroyRef, OnDestroy, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { finalize } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { environment } from '../../../environments/environment';
import { Certificate } from '../../core/models/api.models';
import { FileShredHistoryService } from '../../core/services/file-shred-history.service';
import { ApiService } from '../../services/api.service';

interface CertificateRow extends Certificate {
  source: 'backend' | 'local';
}

@Component({
  selector: 'app-certificates-page',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatSnackBarModule,
    MatTooltipModule,
    MatProgressSpinnerModule
  ],
  templateUrl: './certificates-page.component.html',
  styleUrl: './certificates-page.component.scss'
})
export class CertificatesPageComponent implements OnInit, OnDestroy {
  private readonly api = inject(ApiService);
  private readonly fileShredHistory = inject(FileShredHistoryService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly destroyRef = inject(DestroyRef);

  certificates: CertificateRow[] = [];
  private backendCertificates: Certificate[] = [];
  private localCertificates: Certificate[] = [];
  private readonly verifyBaseUrl = environment.apiBaseUrl;
  loading = false;
  errorMessage = '';
  displayedColumns = ['jobId', 'source', 'method', 'verificationStatus', 'recoveredFiles', 'timestamp', 'actions'];
  private pollTimerId: number | null = null;
  private bootstrapRetryTimerId: number | null = null;
  private bootstrapAttempts = 0;

  ngOnInit(): void {
    this.fileShredHistory.entries$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        try {
          this.localCertificates = this.fileShredHistory.asCertificates();
          this.mergeCertificates();
        } catch (error) {
          console.error('Failed to merge local certificate history', error);
        }
      });

    this.load();
    window.setTimeout(() => this.load(true), 350);
    this.startBootstrapRetries();
    this.pollTimerId = window.setInterval(() => this.load(true), 10000);
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

  load(silent = false): void {
    if (!silent) {
      this.loading = true;
      this.errorMessage = '';
    }
    this.api.getCertificates()
      .pipe(finalize(() => {
        if (!silent) {
          this.loading = false;
        }
      }))
      .subscribe({
        next: (certs) => {
          this.backendCertificates = Array.isArray(certs) ? certs : [];
          this.mergeCertificates();
        },
        error: (error: Error) => {
          if (!silent) {
            this.backendCertificates = [];
            this.mergeCertificates();
            this.errorMessage = error.message || 'Unable to load certificates.';
            this.snackBar.open(this.errorMessage, 'Dismiss', { duration: 3000 });
            window.setTimeout(() => this.load(true), 1800);
          }
        }
      });
  }

  get totalCertificates(): number {
    return this.certificates.length;
  }

  get localCount(): number {
    return this.certificates.filter((row) => row.source === 'local').length;
  }

  get engineCount(): number {
    return this.certificates.filter((row) => row.source === 'backend').length;
  }

  downloadPdf(row: CertificateRow): void {
    if (row.source === 'local') {
      const blob = this.fileShredHistory.buildEvidencePdfBlob(row.jobId);
      this.downloadBlob(blob, `file-shred-evidence-${row.jobId}.pdf`);
      return;
    }

    this.api.downloadCertificatePdf(row.jobId).subscribe({
      next: (blob) => {
        this.downloadBlob(blob, `certificate-${row.jobId}.pdf`);
      },
      error: (error: Error) => {
        this.snackBar.open(error.message || 'Unable to download certificate PDF.', 'Dismiss', { duration: 3000 });
      }
    });
  }

  downloadJson(row: CertificateRow): void {
    if (row.source === 'local') {
      const blob = this.fileShredHistory.buildEvidenceBlob(row.jobId);
      this.downloadBlob(blob, `file-shred-evidence-${row.jobId}.json`);
      return;
    }

    this.api.downloadCertificateJson(row.jobId).subscribe({
      next: (blob) => {
        this.downloadBlob(blob, `certificate-${row.jobId}.json`);
      },
      error: (error: Error) => {
        this.snackBar.open(error.message || 'Unable to download certificate JSON.', 'Dismiss', { duration: 3000 });
      }
    });
  }

  openVerify(row: CertificateRow): void {
    if (row.source === 'local') {
      const blobUrl = URL.createObjectURL(this.fileShredHistory.buildEvidenceBlob(row.jobId));
      window.open(blobUrl, '_blank', 'noopener,noreferrer');
      window.setTimeout(() => URL.revokeObjectURL(blobUrl), 10_000);
      return;
    }

    const verifyUrl = `${this.verifyBaseUrl}/verify/${row.id}?view=html`;
    window.open(verifyUrl, '_blank', 'noopener,noreferrer');
  }

  getSourceLabel(row: CertificateRow): string {
    return row.source === 'backend' ? 'Engine' : 'Local';
  }

  getSourceClass(row: CertificateRow): string {
    return row.source === 'backend' ? 'source-badge source-badge--engine' : 'source-badge source-badge--local';
  }

  private downloadBlob(blob: Blob, fileName: string): void {
    const blobUrl = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = blobUrl;
    anchor.download = fileName;
    anchor.click();
    URL.revokeObjectURL(blobUrl);
  }

  private mergeCertificates(): void {
    const localCertificates = Array.isArray(this.localCertificates) ? this.localCertificates : [];
    const backendCertificates = Array.isArray(this.backendCertificates) ? this.backendCertificates : [];

    const rows: CertificateRow[] = [
      ...localCertificates.map((cert) => ({ ...cert, source: 'local' as const })),
      ...backendCertificates.map((cert) => ({ ...cert, source: 'backend' as const }))
    ];

    this.certificates = rows.sort((left, right) => {
      const leftTime = new Date(left.timestamp).getTime();
      const rightTime = new Date(right.timestamp).getTime();
      return rightTime - leftTime;
    });
  }

  private startBootstrapRetries(): void {
    this.bootstrapAttempts = 0;
    if (this.bootstrapRetryTimerId !== null) {
      window.clearInterval(this.bootstrapRetryTimerId);
    }
    this.bootstrapRetryTimerId = window.setInterval(() => {
      this.bootstrapAttempts += 1;
      this.load(true);
      if (this.bootstrapAttempts >= 4 && this.bootstrapRetryTimerId !== null) {
        window.clearInterval(this.bootstrapRetryTimerId);
        this.bootstrapRetryTimerId = null;
      }
    }, 1500);
  }
}
