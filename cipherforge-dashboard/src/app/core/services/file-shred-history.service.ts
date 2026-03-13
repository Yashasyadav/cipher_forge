import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

import { Certificate, WipeJobStatus } from '../models/api.models';

export type FileShredTaskKind = 'file' | 'folder';
export type FileShredTaskStatus = 'RUNNING' | 'COMPLETED' | 'FAILED';

export interface FileShredHistoryEntry {
  id: string;
  jobId: string;
  taskKind: FileShredTaskKind;
  targetPath: string;
  method: string;
  status: FileShredTaskStatus;
  progress: number;
  startTime: string;
  endTime?: string;
  error?: string;
  certificateId?: string;
}

@Injectable({ providedIn: 'root' })
export class FileShredHistoryService {
  private static readonly storageKey = 'cipherforge_file_shred_history_v1';
  private readonly entriesSubject = new BehaviorSubject<FileShredHistoryEntry[]>(this.restoreEntries());

  readonly entries$ = this.entriesSubject.asObservable();

  get entries(): FileShredHistoryEntry[] {
    return this.entriesSubject.value;
  }

  startTask(taskKind: FileShredTaskKind, targetPath: string, method: string): FileShredHistoryEntry {
    const now = new Date().toISOString();
    const token = Math.random().toString(36).slice(2, 8);
    const jobId = `file-shred-${Date.now()}-${token}`;

    const entry: FileShredHistoryEntry = {
      id: jobId,
      jobId,
      taskKind,
      targetPath,
      method,
      status: 'RUNNING',
      progress: 0,
      startTime: now
    };

    this.publish([entry, ...this.entriesSubject.value]);
    return entry;
  }

  updateProgress(jobId: string, progress: number): void {
    const bounded = Math.max(0, Math.min(100, Number.isFinite(progress) ? progress : 0));
    this.updateEntry(jobId, { progress: bounded });
  }

  completeTask(jobId: string): void {
    const now = new Date().toISOString();
    const certificateId = `local-cert-${jobId}`;
    this.updateEntry(jobId, {
      status: 'COMPLETED',
      progress: 100,
      endTime: now,
      certificateId,
      error: undefined
    });
  }

  failTask(jobId: string, error: string): void {
    this.updateEntry(jobId, {
      status: 'FAILED',
      endTime: new Date().toISOString(),
      error
    });
  }

  asWipeJobs(): WipeJobStatus[] {
    return this.entriesSubject.value.map((entry) => ({
      jobId: entry.jobId,
      engineJobId: '',
      jobType: 'FILE',
      target: entry.targetPath,
      device: `FILE :: ${entry.targetPath}`,
      wipeMethod: entry.method,
      status: entry.status,
      progress: entry.progress,
      startTime: entry.startTime,
      endTime: entry.endTime ?? null,
      certificateId: entry.certificateId ?? null,
      error: entry.error ?? null
    }));
  }

  asCertificates(): Certificate[] {
    return this.entriesSubject.value
      .filter((entry) => entry.status === 'COMPLETED')
      .map((entry) => ({
        id: entry.certificateId ?? `local-cert-${entry.jobId}`,
        jobId: entry.jobId,
        method: entry.method,
        verificationStatus: 'PASSED',
        recoveredFiles: 0,
        timestamp: entry.endTime ?? entry.startTime
      }));
  }

  getSummary(): { completed: number; failed: number; active: number; certificates: number } {
    let completed = 0;
    let failed = 0;
    let active = 0;
    for (const entry of this.entriesSubject.value) {
      if (entry.status === 'COMPLETED') {
        completed += 1;
      } else if (entry.status === 'FAILED') {
        failed += 1;
      } else {
        active += 1;
      }
    }

    return {
      completed,
      failed,
      active,
      certificates: completed
    };
  }

  buildEvidenceBlob(jobId: string): Blob {
    const payload = this.buildEvidencePayload(jobId);
    return new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  }

  buildEvidencePdfBlob(jobId: string): Blob {
    const payload = this.buildEvidencePayload(jobId);
    const entry = (payload['entry'] ?? {}) as Partial<FileShredHistoryEntry>;
    const qrCode = (payload['qrCode'] ?? {}) as Record<string, unknown>;
    const lines = [
      'CipherForge File Shred Evidence',
      `Job ID: ${String(entry.jobId ?? jobId)}`,
      `Task Type: ${String(entry.taskKind ?? 'file')}`,
      `Method: ${String(entry.method ?? 'DoD')}`,
      `Status: ${String(entry.status ?? 'UNKNOWN')}`,
      `Target: ${String(entry.targetPath ?? 'N/A')}`,
      `Started: ${String(entry.startTime ?? 'N/A')}`,
      `Ended: ${String(entry.endTime ?? 'N/A')}`,
      `Certificate ID: ${String(entry.certificateId ?? 'N/A')}`,
      `Verification URL: ${String(qrCode['verificationUrl'] ?? 'N/A')}`,
      `QR Text: ${String(qrCode['text'] ?? 'N/A')}`
    ];
    const pdfBytes = this.buildSimplePdf(lines);
    const normalizedBytes = new Uint8Array(Array.from(pdfBytes));
    return new Blob([normalizedBytes], { type: 'application/pdf' });
  }

  private buildEvidencePayload(jobId: string): Record<string, unknown> {
    const entry = this.entriesSubject.value.find((item) => item.jobId === jobId);
    if (!entry) {
      return { error: 'Entry not found', jobId };
    }

    const origin = typeof globalThis.location?.origin === 'string' ? globalThis.location.origin : '';
    const certificateId = entry.certificateId ?? `local-cert-${entry.jobId}`;
    const verificationUrl = `${origin}/certificates?jobId=${encodeURIComponent(entry.jobId)}`;
    const qrText = JSON.stringify({
      certificateId,
      jobId: entry.jobId,
      status: entry.status,
      method: entry.method,
      targetPath: entry.targetPath,
      verificationUrl
    });

    const payload = {
      source: 'CipherForge File Shred History',
      generatedAt: new Date().toISOString(),
      entry,
      qrCode: {
        format: 'payload',
        verificationUrl,
        text: qrText
      }
    };
    return payload;
  }

  private buildSimplePdf(lines: string[]): Uint8Array {
    const encoder = new TextEncoder();
    const safeLines = lines.map((line) => this.escapePdfText(line).slice(0, 130));
    const commands: string[] = ['BT', '/F1 11 Tf', '50 780 Td'];
    safeLines.forEach((line, index) => {
      if (index > 0) {
        commands.push('0 -16 Td');
      }
      commands.push(`(${line}) Tj`);
    });
    commands.push('ET');

    const contentStream = commands.join('\n');
    const streamLength = encoder.encode(contentStream).length;

    const objects = [
      '1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj',
      '2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj',
      '3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>\nendobj',
      `4 0 obj\n<< /Length ${streamLength} >>\nstream\n${contentStream}\nendstream\nendobj`,
      '5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj'
    ];

    let pdf = '%PDF-1.4\n';
    const offsets: number[] = [];
    for (const object of objects) {
      offsets.push(encoder.encode(pdf).length);
      pdf += `${object}\n`;
    }

    const xrefOffset = encoder.encode(pdf).length;
    pdf += `xref\n0 ${objects.length + 1}\n`;
    pdf += '0000000000 65535 f \n';
    for (const offset of offsets) {
      pdf += `${offset.toString().padStart(10, '0')} 00000 n \n`;
    }
    pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`;
    return encoder.encode(pdf);
  }

  private escapePdfText(input: string): string {
    return input.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');
  }

  private updateEntry(jobId: string, patch: Partial<FileShredHistoryEntry>): void {
    const entries = this.entriesSubject.value.map((entry) => {
      if (entry.jobId !== jobId) {
        return entry;
      }
      return { ...entry, ...patch };
    });
    this.publish(entries);
  }

  private publish(nextEntries: FileShredHistoryEntry[]): void {
    this.entriesSubject.next(nextEntries.slice(0, 300));
    this.persistEntries();
  }

  private persistEntries(): void {
    try {
      localStorage.setItem(FileShredHistoryService.storageKey, JSON.stringify(this.entriesSubject.value));
    } catch {
      // Ignore storage failures.
    }
  }

  private restoreEntries(): FileShredHistoryEntry[] {
    try {
      const raw = localStorage.getItem(FileShredHistoryService.storageKey);
      if (!raw) {
        return [];
      }
      const parsed = JSON.parse(raw) as unknown;
      if (!Array.isArray(parsed)) {
        return [];
      }

      return parsed
        .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
        .map((item) => ({
          id: String(item['id'] ?? ''),
          jobId: String(item['jobId'] ?? ''),
          taskKind: (item['taskKind'] === 'folder' ? 'folder' : 'file') as FileShredTaskKind,
          targetPath: String(item['targetPath'] ?? ''),
          method: String(item['method'] ?? 'DoD'),
          status: (item['status'] === 'FAILED' ? 'FAILED' : item['status'] === 'COMPLETED' ? 'COMPLETED' : 'RUNNING') as FileShredTaskStatus,
          progress: Number(item['progress'] ?? 0),
          startTime: String(item['startTime'] ?? ''),
          endTime: item['endTime'] ? String(item['endTime']) : undefined,
          error: item['error'] ? String(item['error']) : undefined,
          certificateId: item['certificateId'] ? String(item['certificateId']) : undefined
        }))
        .filter((entry) => Boolean(entry.jobId) && Boolean(entry.targetPath) && Boolean(entry.startTime));
    } catch {
      return [];
    }
  }
}
