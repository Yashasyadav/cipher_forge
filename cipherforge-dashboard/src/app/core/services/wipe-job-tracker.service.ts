import { Injectable } from '@angular/core';
import { BehaviorSubject, forkJoin, Observable, of } from 'rxjs';
import { map, switchMap, tap } from 'rxjs/operators';

import { FileShredStartRequest, WipeJobStatus, WipeStartRequest } from '../models/api.models';
import { ApiService } from '../../services/api.service';

@Injectable({ providedIn: 'root' })
export class WipeJobTrackerService {
  private readonly jobsSubject = new BehaviorSubject<WipeJobStatus[]>([]);
  readonly jobs$ = this.jobsSubject.asObservable();

  constructor(private readonly api: ApiService) {}

  startWipe(payload: WipeStartRequest): Observable<WipeJobStatus> {
    return this.api.startWipe(payload).pipe(
      map((job) => ({
        ...job,
        jobType: job.jobType || 'DEVICE',
        target: job.target || payload.device
      })),
      tap((job) => this.upsertJob(job))
    );
  }

  startFileShred(payload: FileShredStartRequest): Observable<WipeJobStatus> {
    return this.api.startFileShred(payload).pipe(
      map((job) => ({
        ...job,
        jobType: job.jobType || 'FILE',
        target: job.target || payload.targetPath,
        device: job.device || `${payload.drive} :: ${payload.targetPath}`,
        wipeMethod: job.wipeMethod || payload.method
      })),
      tap((job) => this.upsertJob(job))
    );
  }

  refreshJob(jobId: string): Observable<WipeJobStatus> {
    return this.api.getWipeStatus(jobId).pipe(
      tap((job) => this.upsertJob(job))
    );
  }

  refreshAllTrackedJobs(): Observable<WipeJobStatus[]> {
    const current = this.jobsSubject.value;
    if (!current.length) {
      return this.refreshJobs();
    }

    return of(current).pipe(
      switchMap((jobs) => forkJoin(jobs.map((j) => this.api.getWipeStatus(j.jobId)))),
      tap((jobs) => this.jobsSubject.next(jobs)),
      map((jobs) => jobs)
    );
  }

  refreshJobs(): Observable<WipeJobStatus[]> {
    return this.api.getWipeJobs().pipe(
      tap((jobs) => this.jobsSubject.next(jobs))
    );
  }

  setJobs(jobs: WipeJobStatus[]): void {
    this.jobsSubject.next(jobs);
  }

  upsertJob(next: Partial<WipeJobStatus> & { jobId: string }): void {
    const jobs = [...this.jobsSubject.value];
    const idx = jobs.findIndex((j) => j.jobId === next.jobId);
    if (idx >= 0) {
      jobs[idx] = { ...jobs[idx], ...next };
    } else {
      jobs.unshift({
        jobId: next.jobId,
        engineJobId: next.engineJobId ?? '',
        jobType: next.jobType,
        target: next.target,
        device: next.device ?? 'Unknown',
        wipeMethod: next.wipeMethod ?? 'Unknown',
        status: next.status ?? 'QUEUED',
        progress: next.progress ?? 0,
        startTime: next.startTime ?? null,
        endTime: next.endTime ?? null,
        certificateId: next.certificateId ?? null,
        error: next.error ?? null
      });
    }
    this.jobsSubject.next(jobs);
  }
}
