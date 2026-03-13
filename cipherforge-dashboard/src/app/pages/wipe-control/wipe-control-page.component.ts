import { NestedTreeControl } from '@angular/cdk/tree';
import { CommonModule } from '@angular/common';
import { Component, DestroyRef, HostListener, OnDestroy, OnInit, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTreeModule, MatTreeNestedDataSource } from '@angular/material/tree';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { finalize, firstValueFrom, startWith } from 'rxjs';

import {
  Device,
  FileMetadata,
  FolderWipeJobStatus,
  LogicalDriveInfo,
  WipeJobStatus,
  WipeMode,
  WipeStartRequest
} from '../../core/models/api.models';
import { ProgressWebSocketService } from '../../core/services/progress-websocket.service';
import { FileShredHistoryService } from '../../core/services/file-shred-history.service';
import { WipeJobTrackerService } from '../../core/services/wipe-job-tracker.service';
import { ApiService } from '../../services/api.service';
import { WipeModeToggleComponent } from './components/wipe-mode-toggle/wipe-mode-toggle.component';

interface ExplorerFile {
  name: string;
  path: string;
  size: string;
}

interface FolderTreeNode {
  name: string;
  path: string;
  children: FolderTreeNode[];
  files: ExplorerFile[];
  loaded: boolean;
  loading: boolean;
  expandable: boolean;
}

interface ExecutionTask {
  path: string;
  kind: 'file' | 'folder';
}

interface PersistedWipeControlState {
  mode: WipeMode;
  device: string;
  method: string;
  drive: string;
  shredMethod: string;
  selectedFolderPath: string | null;
  selectedFolderPaths: string[];
  selectedFilePaths: string[];
}

@Component({
  selector: 'app-wipe-control-page',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatIconModule,
    MatProgressBarModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTreeModule,
    WipeModeToggleComponent
  ],
  templateUrl: './wipe-control-page.component.html',
  styleUrl: './wipe-control-page.component.scss'
})
export class WipeControlPageComponent implements OnInit, OnDestroy {
  private static readonly stateStorageKey = 'cipherforge_wipe_control_state_v1';
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly tracker = inject(WipeJobTrackerService);
  private readonly fileShredHistory = inject(FileShredHistoryService);
  private readonly progressSocket = inject(ProgressWebSocketService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly snackBar = inject(MatSnackBar);
  private deviceStatusPollTimerId: number | null = null;
  private lastDeviceStatusSnapshot = '';
  private lastDeviceProgressSnapshot = -1;
  private readonly maxLogLines = 240;
  private pendingSelectedFolderPath: string | null = null;
  private pendingRestoreFolderPaths = new Set<string>();
  private pendingRestoreFilePaths = new Set<string>();
  private hasPendingSelectionRestore = false;
  private bootstrapRetryTimerId: number | null = null;
  private bootstrapRetryAttempts = 0;

  readonly treeControl = new NestedTreeControl<FolderTreeNode>((node) => node.children);
  readonly folderTreeDataSource = new MatTreeNestedDataSource<FolderTreeNode>();

  devices: Device[] = [];
  drives: LogicalDriveInfo[] = [];
  loadingDevices = false;
  loadingDrives = false;
  loadingMethods = false;
  loadingFolder = false;
  devicesError = '';
  drivesError = '';
  methodsError = '';
  folderError = '';
  wipeMethods: string[] = [];
  starting = false;
  latestJobId: string | null = null;
  activeDeviceJob: WipeJobStatus | null = null;
  deviceLiveConnected = false;
  fileDeleteRunning = false;
  fileDeleteProgress = 0;
  fileDeleteCompleted = 0;
  fileDeleteTotal = 0;
  fileDeleteSuccess = 0;
  fileDeleteFailed = 0;
  currentDeleteTarget = '';
  currentFolderJob: FolderWipeJobStatus | null = null;
  readonly executionLogs: string[] = [];
  selectedFolderNode: FolderTreeNode | null = null;
  currentFiles: ExplorerFile[] = [];
  readonly selectedFilePaths = new Set<string>();
  readonly selectedFolderPaths = new Set<string>();

  readonly form = this.fb.nonNullable.group({
    mode: 'DEVICE_WIPE' as WipeMode,
    device: '',
    method: '',
    drive: '',
    shredMethod: ''
  });

  ngOnInit(): void {
    this.restoreUiState();
    this.bindModeChanges();

    this.form.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.persistUiState());

    this.loadDevices();
    this.loadWipeMethods();
    window.setTimeout(() => {
      this.loadDevices(true);
      this.loadWipeMethods(true);
      if (this.isFileShredMode) {
        this.loadDrives(true);
      }
    }, 350);
    this.startBootstrapRetries();

    this.progressSocket.connected$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((connected) => (this.deviceLiveConnected = connected));

    this.progressSocket.updates$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((update) => this.handleDeviceProgressUpdate(update));

    this.progressSocket.connect();
  }

  ngOnDestroy(): void {
    this.stopDeviceStatusPolling();
    this.progressSocket.disconnect();
    if (this.bootstrapRetryTimerId !== null) {
      window.clearInterval(this.bootstrapRetryTimerId);
      this.bootstrapRetryTimerId = null;
    }
  }

  get selectedMode(): WipeMode {
    return this.form.controls.mode.value;
  }

  get isDeviceMode(): boolean {
    return this.selectedMode === 'DEVICE_WIPE';
  }

  get isFileShredMode(): boolean {
    return this.selectedMode === 'FILE_SHREDDER';
  }

  get selectedFilesCount(): number {
    return this.selectedFilePaths.size;
  }

  get selectedFoldersCount(): number {
    return this.selectedFolderPaths.size;
  }

  get totalSelectedCount(): number {
    return this.selectedFilesCount + this.selectedFoldersCount;
  }

  get showRuntimePanel(): boolean {
    return Boolean(this.activeDeviceJob) || Boolean(this.currentFolderJob) || this.fileDeleteRunning || this.executionLogs.length > 0;
  }

  get deviceJobRunning(): boolean {
    return this.activeDeviceJob ? this.isActiveStatus(this.activeDeviceJob.status) : false;
  }

  get folderJobRunning(): boolean {
    return this.currentFolderJob ? this.isActiveStatus(this.currentFolderJob.status) : false;
  }

  get hasOngoingOperation(): boolean {
    return this.starting || this.fileDeleteRunning || this.deviceJobRunning || this.folderJobRunning;
  }

  readonly hasChild = (_: number, node: FolderTreeNode): boolean => node.expandable;

  onWipeModeChanged(mode: WipeMode): void {
    if (this.hasOngoingOperation) {
      this.snackBar.open('Mode cannot be changed while a wipe job is running.', 'Dismiss', { duration: 2600 });
      return;
    }

    if (this.form.controls.mode.value !== mode) {
      this.form.controls.mode.setValue(mode);
    }
  }

  preventNativeSubmit(event: Event): void {
    // Prevent browser form submission from reloading the page.
    event.preventDefault();
    event.stopPropagation();
  }

  @HostListener('window:beforeunload', ['$event'])
  handleBeforeUnload(event: BeforeUnloadEvent): void {
    if (!this.hasOngoingOperation) {
      return;
    }

    // Trigger browser confirmation dialog to avoid accidental refresh/close.
    event.preventDefault();
    event.returnValue = '';
  }

  onDriveChanged(drive: string): void {
    if (!drive) {
      this.folderTreeDataSource.data = [];
      this.selectedFolderNode = null;
      this.currentFiles = [];
      this.persistUiState();
      return;
    }

    const rootPath = this.toDriveRoot(drive);
    const rootNode: FolderTreeNode = {
      name: rootPath,
      path: rootPath,
      children: [],
      files: [],
      loaded: false,
      loading: false,
      expandable: true
    };

    this.folderTreeDataSource.data = [rootNode];
    this.selectedFolderNode = rootNode;
    this.currentFiles = [];
    this.selectedFilePaths.clear();
    this.selectedFolderPaths.clear();
    this.treeControl.collapseAll();
    this.treeControl.expand(rootNode);
    this.loadFolderNode(rootNode);
    this.persistUiState();
  }

  toggleFolder(node: FolderTreeNode, event: Event): void {
    event.stopPropagation();

    const isExpanded = this.treeControl.isExpanded(node);
    if (!isExpanded && !node.loaded) {
      this.loadFolderNode(node);
    }

    this.treeControl.toggle(node);
  }

  selectFolder(node: FolderTreeNode): void {
    this.selectedFolderNode = node;
    this.currentFiles = node.files;

    if (!node.loaded) {
      this.loadFolderNode(node);
    }

    this.persistUiState();
  }

  onFolderSelection(node: FolderTreeNode, checked: boolean): void {
    if (checked) {
      this.selectedFolderPaths.add(node.path);
      this.persistUiState();
      return;
    }

    this.selectedFolderPaths.delete(node.path);
    this.persistUiState();
  }

  onFileSelection(filePath: string, checked: boolean): void {
    if (checked) {
      this.selectedFilePaths.add(filePath);
      this.persistUiState();
      return;
    }

    this.selectedFilePaths.delete(filePath);
    this.persistUiState();
  }

  isFolderSelected(path: string): boolean {
    return this.selectedFolderPaths.has(path);
  }

  isFileSelected(path: string): boolean {
    return this.selectedFilePaths.has(path);
  }

  startDeviceWipe(): void {
    if (!this.isDeviceMode) {
      return;
    }

    if (this.form.controls.device.invalid || this.form.controls.method.invalid || this.loadingMethods) {
      this.form.controls.device.markAsTouched();
      this.form.controls.method.markAsTouched();
      return;
    }

    this.starting = true;
    const payload: WipeStartRequest = {
      mode: 'DEVICE_WIPE',
      device: this.form.controls.device.value,
      method: this.form.controls.method.value
    };

    this.tracker.startWipe(payload)
      .pipe(finalize(() => (this.starting = false)))
      .subscribe({
        next: (job) => {
          this.latestJobId = job.jobId;
          this.applyDeviceJobState(job, 'started');
          this.appendLog(`Device wipe queued: ${job.jobId} | ${job.device} | ${job.wipeMethod}`);
          this.startDeviceStatusPolling(job.jobId);
          this.snackBar.open(`Wipe job ${job.jobId} started`, 'OK', { duration: 2800 });
        },
        error: (error: Error) => {
          this.appendLog(`Device wipe start failed: ${error.message || 'Unknown error'}`);
          this.snackBar.open(error.message || 'Failed to start wipe job', 'Dismiss', { duration: 3200 });
        }
      });
  }

  async secureDelete(): Promise<void> {
    if (!this.isFileShredMode) {
      return;
    }

    if (this.form.controls.drive.invalid || this.form.controls.shredMethod.invalid || this.loadingMethods) {
      this.form.controls.drive.markAsTouched();
      this.form.controls.shredMethod.markAsTouched();
      return;
    }

    if (!this.totalSelectedCount) {
      this.snackBar.open('Select one or more files/folders to delete.', 'Dismiss', { duration: 2800 });
      return;
    }

    const hasRootFolderSelection = [...this.selectedFolderPaths].some((path) => this.isDriveRootPath(path));
    if (hasRootFolderSelection) {
      this.snackBar.open('Drive root cannot be shredded. Select a subfolder instead.', 'Dismiss', { duration: 3600 });
      return;
    }

    const method = this.form.controls.shredMethod.value;
    const tasks: ExecutionTask[] = [
      ...[...this.selectedFolderPaths].map((path) => ({ path, kind: 'folder' as const })),
      ...[...this.selectedFilePaths].map((path) => ({ path, kind: 'file' as const }))
    ];

    if (!tasks.length) {
      return;
    }

    if (tasks.some((task) => task.kind === 'folder')) {
      this.snackBar.open(
        `Secure folder wipe started with ${method}. This can take several minutes for large folders.`,
        'OK',
        { duration: 4200 }
      );
    }

    this.starting = true;
    this.fileDeleteRunning = true;
    this.fileDeleteTotal = tasks.length;
    this.fileDeleteCompleted = 0;
    this.fileDeleteProgress = 0;
    this.fileDeleteSuccess = 0;
    this.fileDeleteFailed = 0;
    this.currentDeleteTarget = '';
    this.currentFolderJob = null;

    this.appendLog(`Secure delete started (${tasks.length} item(s), method: ${method})`);

    try {
      for (const [index, task] of tasks.entries()) {
        this.currentDeleteTarget = task.path;
        const taskLabel = `${task.kind.toUpperCase()}: ${task.path}`;
        const historyEntry = this.fileShredHistory.startTask(task.kind, task.path, method);
        this.appendLog(`Running ${taskLabel}`);

        try {
          if (task.kind === 'folder') {
            const folderResult = await this.runFolderWipeJob(task.path, method, index, historyEntry.jobId);
            if (folderResult.total_files === 0) {
              this.appendLog(
                `Warning ${taskLabel} -> no wipeable files found. Folder may be empty, protected, or contain only excluded entries.`
              );
            }
          } else {
            const fileResult = await firstValueFrom(this.api.wipeFile({ path: task.path, method }));
            if (fileResult.stage_logs && fileResult.stage_logs.length > 0) {
              for (const stage of fileResult.stage_logs) {
                this.appendLog(`FILE STAGE ${task.path} -> ${stage}`);
              }
            } else if (fileResult.last_message) {
              this.appendLog(`FILE STAGE ${task.path} -> ${fileResult.last_message}`);
            }
            this.fileDeleteProgress = Math.round(((index + 1) / this.fileDeleteTotal) * 100);
            this.fileShredHistory.updateProgress(historyEntry.jobId, 100);
          }
          this.fileDeleteSuccess += 1;
          this.fileShredHistory.completeTask(historyEntry.jobId);
          this.appendLog(`Done ${taskLabel}`);
        } catch (error) {
          this.fileDeleteFailed += 1;
          const errorMessage = error instanceof Error ? error.message : 'Unknown error';
          this.fileShredHistory.failTask(historyEntry.jobId, errorMessage);
          this.appendLog(`Failed ${taskLabel} -> ${errorMessage}`);
        }

        this.fileDeleteCompleted = index + 1;
        this.fileDeleteProgress = Math.round((this.fileDeleteCompleted / this.fileDeleteTotal) * 100);
      }
    } finally {
      this.starting = false;
      this.fileDeleteRunning = false;
      this.currentDeleteTarget = '';
      this.currentFolderJob = null;
    }

    if (this.fileDeleteFailed > 0) {
      this.snackBar.open(
        `Secure delete finished with errors: ${this.fileDeleteSuccess} succeeded, ${this.fileDeleteFailed} failed.`,
        'Dismiss',
        { duration: 4200 }
      );
      return;
    }

    this.snackBar.open(
      `Secure delete completed for ${this.fileDeleteSuccess} item(s).`,
      'OK',
      { duration: 3400 }
    );

    this.appendLog(`Secure delete completed successfully (${this.fileDeleteSuccess} item(s)).`);

    this.selectedFilePaths.clear();
    this.selectedFolderPaths.clear();

    if (this.selectedFolderNode) {
      this.selectedFolderNode.loaded = false;
      this.loadFolderNode(this.selectedFolderNode);
    }
  }

  private loadDevices(silent = false): void {
    this.loadingDevices = true;
    if (!silent) {
      this.devicesError = '';
    }
    this.api.getDevices()
      .pipe(finalize(() => (this.loadingDevices = false)))
      .subscribe({
        next: (devices) => {
          this.devices = devices;
        },
        error: (error: Error) => {
          this.devices = [];
          if (!silent) {
            this.devicesError = error.message || 'Unable to load devices.';
            this.snackBar.open(this.devicesError, 'Dismiss', { duration: 3200 });
          }
        }
      });
  }

  private loadDrives(silent = false): void {
    this.loadingDrives = true;
    if (!silent) {
      this.drivesError = '';
    }
    this.api.getDrives()
      .pipe(finalize(() => (this.loadingDrives = false)))
      .subscribe({
        next: (drives) => {
          this.drives = drives;
          const selectedDrive = this.form.controls.drive.value;
          const hasSelectedDrive = selectedDrive && drives.some((drive) => drive.drive === selectedDrive);
          if (!hasSelectedDrive) {
            this.form.patchValue({ drive: '' }, { emitEvent: false });
            this.folderTreeDataSource.data = [];
            this.selectedFilePaths.clear();
            this.selectedFolderPaths.clear();
            this.currentFiles = [];
            this.selectedFolderNode = null;
            this.persistUiState();
            return;
          }

          this.onDriveChanged(selectedDrive);
        },
        error: (error: Error) => {
          this.drives = [];
          if (!silent) {
            this.drivesError = error.message || 'Unable to load logical drives.';
          }
          this.form.patchValue({ drive: '' }, { emitEvent: false });
          this.folderTreeDataSource.data = [];
          this.selectedFilePaths.clear();
          this.selectedFolderPaths.clear();
          this.currentFiles = [];
          this.selectedFolderNode = null;
          this.persistUiState();
          if (!silent) {
            this.snackBar.open(this.drivesError, 'Dismiss', { duration: 3200 });
          }
        }
      });
  }

  private loadWipeMethods(silent = false): void {
    this.loadingMethods = true;
    if (!silent) {
      this.methodsError = '';
    }
    this.api.getWipeMethods()
      .pipe(finalize(() => (this.loadingMethods = false)))
      .subscribe({
        next: (methods) => {
          this.wipeMethods = methods;
          const selected = this.form.controls.method.value;
          if (!selected || !methods.includes(selected)) {
            this.form.patchValue({ method: methods[0] ?? '' });
          }

          const selectedShred = this.form.controls.shredMethod.value;
          if (!selectedShred || !methods.includes(selectedShred)) {
            this.form.patchValue({ shredMethod: methods[0] ?? '' });
          }
        },
        error: (error: Error) => {
          this.wipeMethods = [];
          this.form.patchValue({ method: '', shredMethod: '' });
          if (!silent) {
            this.methodsError = error.message || 'Unable to load wipe methods.';
            this.snackBar.open(this.methodsError, 'Dismiss', { duration: 3200 });
          }
        }
      });
  }

  private startBootstrapRetries(): void {
    this.bootstrapRetryAttempts = 0;
    if (this.bootstrapRetryTimerId !== null) {
      window.clearInterval(this.bootstrapRetryTimerId);
    }
    this.bootstrapRetryTimerId = window.setInterval(() => {
      this.bootstrapRetryAttempts += 1;

      if (!this.loadingDevices && this.devices.length === 0) {
        this.loadDevices(true);
      }
      if (!this.loadingMethods && this.wipeMethods.length === 0) {
        this.loadWipeMethods(true);
      }
      if (this.isFileShredMode && !this.loadingDrives && this.drives.length === 0) {
        this.loadDrives(true);
      }

      const readyForCurrentMode = this.devices.length > 0
        && this.wipeMethods.length > 0
        && (!this.isFileShredMode || this.drives.length > 0);

      if (readyForCurrentMode || this.bootstrapRetryAttempts >= 6) {
        if (this.bootstrapRetryTimerId !== null) {
          window.clearInterval(this.bootstrapRetryTimerId);
          this.bootstrapRetryTimerId = null;
        }
      }
    }, 1500);
  }

  private loadFolderNode(node: FolderTreeNode): void {
    if (node.loading) {
      return;
    }

    node.loading = true;
    this.loadingFolder = true;
    this.folderError = '';

    this.api.browseFilesystem(node.path)
      .pipe(finalize(() => {
        node.loading = false;
        this.loadingFolder = false;
      }))
      .subscribe({
        next: (response) => {
          const childNodes = response.folders.map((folderName) => this.buildFolderNode(response.path, folderName));
          node.children = childNodes;
          node.files = response.files.map((file) => this.buildFile(response.path, file));
          node.loaded = true;
          node.expandable = node.children.length > 0;

          this.restorePendingSelections();
          this.tryRestoreSelectedFolderNode(node);

          if (this.selectedFolderNode?.path === node.path) {
            this.currentFiles = [...node.files];
          }

          this.refreshTree();
        },
        error: (error: Error) => {
          node.children = [];
          node.files = [];
          node.loaded = true;
          node.expandable = false;
          this.folderError = error.message || 'Unable to browse selected folder.';
          this.snackBar.open(this.folderError, 'Dismiss', { duration: 3200 });
          this.refreshTree();
        }
      });
  }

  private buildFolderNode(parentPath: string, folderName: string): FolderTreeNode {
    return {
      name: folderName,
      path: this.joinPath(parentPath, folderName),
      children: [],
      files: [],
      loaded: false,
      loading: false,
      expandable: true
    };
  }

  private buildFile(parentPath: string, file: FileMetadata): ExplorerFile {
    return {
      name: file.name,
      path: this.joinPath(parentPath, file.name),
      size: file.size
    };
  }

  private refreshTree(): void {
    this.folderTreeDataSource.data = [...this.folderTreeDataSource.data];
  }

  private bindModeChanges(): void {
    this.form.controls.mode.valueChanges
      .pipe(startWith(this.form.controls.mode.value))
      .subscribe((mode) => {
        const deviceValidators = mode === 'DEVICE_WIPE' ? [Validators.required] : [];
        const fileModeValidators = mode === 'FILE_SHREDDER' ? [Validators.required] : [];

        this.form.controls.device.setValidators(deviceValidators);
        this.form.controls.method.setValidators(deviceValidators);

        this.form.controls.drive.setValidators(fileModeValidators);
        this.form.controls.shredMethod.setValidators(fileModeValidators);

        this.form.controls.device.updateValueAndValidity({ emitEvent: false });
        this.form.controls.method.updateValueAndValidity({ emitEvent: false });
        this.form.controls.drive.updateValueAndValidity({ emitEvent: false });
        this.form.controls.shredMethod.updateValueAndValidity({ emitEvent: false });

        if (mode === 'DEVICE_WIPE') {
          this.form.patchValue({ drive: '' }, { emitEvent: false });
          this.folderTreeDataSource.data = [];
          this.selectedFilePaths.clear();
          this.selectedFolderPaths.clear();
          this.currentFiles = [];
          this.selectedFolderNode = null;
          return;
        }

        this.form.patchValue({ device: '' }, { emitEvent: false });
        if (!this.loadingDrives) {
          this.loadDrives();
        }
        this.startBootstrapRetries();

        this.persistUiState();
      });
  }

  private async runFolderWipeJob(path: string, method: string, taskIndex: number, historyJobId: string): Promise<FolderWipeJobStatus> {
    const start = await firstValueFrom(this.api.startFolderWipe({ path, method }));
    this.currentFolderJob = start;
    this.appendLog(
      `Folder job queued: ${start.job_id} | ${start.path} | files=${start.total_files}`
    );

    let lastProgressBucket = -1;
    let lastMessage = '';

    while (true) {
      let status: FolderWipeJobStatus;
      try {
        status = await firstValueFrom(this.api.getFolderWipeStatus(start.job_id));
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown poll error';
        const normalizedError = errorMessage.toLowerCase();
        if (normalizedError.includes('404') || normalizedError.includes('not found')) {
          throw new Error(`Folder wipe job was lost on backend: ${start.job_id}. Please start the wipe again.`);
        }
        this.appendLog(`Folder job poll warning (${start.job_id}): ${errorMessage}`);
        await this.delay(1200);
        continue;
      }

      this.currentFolderJob = status;
      this.fileShredHistory.updateProgress(historyJobId, status.progress);

      const progressBucket = Math.floor(status.progress);
      if (progressBucket !== lastProgressBucket) {
        this.appendLog(
          `Folder job ${status.job_id} -> ${Math.round(status.progress)}% (${status.processed_files}/${status.total_files})`
        );
        lastProgressBucket = progressBucket;
      }

      const nextMessage = (status.last_message ?? '').trim();
      if (nextMessage && nextMessage !== lastMessage) {
        this.appendLog(`Folder job ${status.job_id}: ${nextMessage}`);
        lastMessage = nextMessage;
      }

      const taskFraction = (status.progress / 100);
      this.fileDeleteProgress = Math.round(((taskIndex + taskFraction) / this.fileDeleteTotal) * 100);

      const normalized = status.status.toLowerCase();
      if (normalized === 'completed') {
        this.fileDeleteProgress = Math.round(((taskIndex + 1) / this.fileDeleteTotal) * 100);
        this.fileShredHistory.updateProgress(historyJobId, 100);
        return status;
      }
      if (normalized === 'failed') {
        const failureMessage = status.error || status.last_message || 'Folder wipe failed';
        throw new Error(failureMessage);
      }

      await this.delay(800);
    }
  }

  clearExecutionLogs(): void {
    this.executionLogs.splice(0, this.executionLogs.length);
    this.persistUiState();
  }

  private handleDeviceProgressUpdate(update: Partial<WipeJobStatus> & { jobId: string }): void {
    if (!this.latestJobId || update.jobId !== this.latestJobId) {
      return;
    }

    const current: WipeJobStatus = this.activeDeviceJob ?? {
      jobId: update.jobId,
      engineJobId: update.engineJobId ?? '',
      device: update.device ?? 'Unknown',
      wipeMethod: update.wipeMethod ?? 'Unknown',
      status: update.status ?? 'QUEUED',
      progress: update.progress ?? 0
    };

    const merged: WipeJobStatus = {
      ...current,
      ...update,
      jobId: update.jobId,
      status: update.status ?? current.status,
      progress: typeof update.progress === 'number' ? update.progress : current.progress
    };

    this.applyDeviceJobState(merged, 'live');
  }

  private startDeviceStatusPolling(jobId: string): void {
    this.stopDeviceStatusPolling();
    this.refreshDeviceJobStatus(jobId, true);

    this.deviceStatusPollTimerId = window.setInterval(() => {
      this.refreshDeviceJobStatus(jobId, false);
    }, 3000);
  }

  private stopDeviceStatusPolling(): void {
    if (this.deviceStatusPollTimerId !== null) {
      window.clearInterval(this.deviceStatusPollTimerId);
      this.deviceStatusPollTimerId = null;
    }
  }

  private refreshDeviceJobStatus(jobId: string, silentError: boolean): void {
    this.api.getWipeStatus(jobId).subscribe({
      next: (job) => this.applyDeviceJobState(job, 'poll'),
      error: (error: Error) => {
        if (!silentError) {
          this.appendLog(`Status poll warning for ${jobId}: ${error.message || 'Unable to fetch status'}`);
        }
      }
    });
  }

  private applyDeviceJobState(job: WipeJobStatus, source: 'started' | 'poll' | 'live'): void {
    const previousStatus = this.lastDeviceStatusSnapshot;
    const previousProgress = this.lastDeviceProgressSnapshot;

    this.activeDeviceJob = job;
    this.lastDeviceStatusSnapshot = job.status;
    this.lastDeviceProgressSnapshot = job.progress;

    if (source === 'started') {
      return;
    }

    if (job.status !== previousStatus) {
      this.appendLog(`Device job ${job.jobId} status -> ${job.status}`);
    }

    if (Math.floor(job.progress) !== Math.floor(previousProgress)) {
      this.appendLog(`Device job ${job.jobId} progress -> ${Math.round(job.progress)}%`);
    }

    if (!this.isActiveStatus(job.status)) {
      if (job.error) {
        this.appendLog(`Device job ${job.jobId} ended with error: ${job.error}`);
      } else {
        this.appendLog(`Device job ${job.jobId} finished: ${job.status}`);
      }
      this.stopDeviceStatusPolling();
    }

    this.persistUiState();
  }

  private isActiveStatus(status: string): boolean {
    const normalized = status.toUpperCase();
    return normalized !== 'COMPLETED' && normalized !== 'FAILED';
  }

  private appendLog(message: string): void {
    const timestamp = new Date().toLocaleTimeString();
    this.executionLogs.push(`[${timestamp}] ${message}`);
    if (this.executionLogs.length > this.maxLogLines) {
      this.executionLogs.splice(0, this.executionLogs.length - this.maxLogLines);
    }
    this.persistUiState();
  }

  private async delay(ms: number): Promise<void> {
    await new Promise<void>((resolve) => {
      window.setTimeout(resolve, ms);
    });
  }

  private joinPath(parent: string, name: string): string {
    const normalizedParent = parent.replace(/[\\/]+$/, '');
    return `${normalizedParent}\\${name}`;
  }

  private toDriveRoot(drive: string): string {
    const normalized = drive.trim().replace(/[\\/]+$/, '');
    if (!normalized) {
      return '';
    }

    return normalized.endsWith(':') ? `${normalized}\\` : normalized;
  }

  private isDriveRootPath(path: string): boolean {
    const normalized = path.trim().replace(/\//g, '\\').replace(/\\+$/, '');
    return /^[A-Za-z]:$/.test(normalized);
  }

  private persistUiState(): void {
    try {
      const state: PersistedWipeControlState = {
        mode: this.form.controls.mode.value,
        device: this.form.controls.device.value,
        method: this.form.controls.method.value,
        drive: this.form.controls.drive.value,
        shredMethod: this.form.controls.shredMethod.value,
        selectedFolderPath: this.selectedFolderNode?.path ?? null,
        selectedFolderPaths: [...this.selectedFolderPaths],
        selectedFilePaths: [...this.selectedFilePaths]
      };
      localStorage.setItem(WipeControlPageComponent.stateStorageKey, JSON.stringify(state));
    } catch {
      // Ignore storage failures (private mode/quota).
    }
  }

  private restoreUiState(): void {
    try {
      const raw = localStorage.getItem(WipeControlPageComponent.stateStorageKey);
      if (!raw) {
        return;
      }

      const parsed = JSON.parse(raw) as Partial<PersistedWipeControlState>;
      const mode = parsed.mode === 'FILE_SHREDDER' ? 'FILE_SHREDDER' : 'DEVICE_WIPE';

      this.form.patchValue(
        {
          mode,
          device: typeof parsed.device === 'string' ? parsed.device : '',
          method: typeof parsed.method === 'string' ? parsed.method : '',
          drive: typeof parsed.drive === 'string' ? parsed.drive : '',
          shredMethod: typeof parsed.shredMethod === 'string' ? parsed.shredMethod : ''
        },
        { emitEvent: false }
      );

      // Runtime logs are intentionally not restored across sessions.
      this.executionLogs.splice(0, this.executionLogs.length);

      this.pendingRestoreFolderPaths.clear();
      this.pendingRestoreFilePaths.clear();

      if (Array.isArray(parsed.selectedFolderPaths)) {
        for (const path of parsed.selectedFolderPaths) {
          if (typeof path === 'string' && path.trim()) {
            this.pendingRestoreFolderPaths.add(path);
          }
        }
      }

      if (Array.isArray(parsed.selectedFilePaths)) {
        for (const path of parsed.selectedFilePaths) {
          if (typeof path === 'string' && path.trim()) {
            this.pendingRestoreFilePaths.add(path);
          }
        }
      }

      this.pendingSelectedFolderPath = typeof parsed.selectedFolderPath === 'string'
        ? parsed.selectedFolderPath
        : null;
      this.hasPendingSelectionRestore = this.pendingRestoreFolderPaths.size > 0
        || this.pendingRestoreFilePaths.size > 0
        || Boolean(this.pendingSelectedFolderPath);
    } catch {
      // Ignore malformed persisted state.
    }
  }

  private restorePendingSelections(): void {
    if (!this.hasPendingSelectionRestore) {
      return;
    }

    this.selectedFolderPaths.clear();
    this.selectedFilePaths.clear();

    for (const path of this.pendingRestoreFolderPaths) {
      this.selectedFolderPaths.add(path);
    }

    for (const path of this.pendingRestoreFilePaths) {
      this.selectedFilePaths.add(path);
    }

    this.pendingRestoreFolderPaths.clear();
    this.pendingRestoreFilePaths.clear();
    this.hasPendingSelectionRestore = Boolean(this.pendingSelectedFolderPath);
  }

  private tryRestoreSelectedFolderNode(node: FolderTreeNode): void {
    const targetPath = this.pendingSelectedFolderPath;
    if (!targetPath) {
      this.hasPendingSelectionRestore = false;
      return;
    }

    if (this.pathsEqual(node.path, targetPath)) {
      this.selectedFolderNode = node;
      this.currentFiles = [...node.files];
      this.clearPendingFolderPathRestore();
      this.persistUiState();
      return;
    }

    const exactChild = node.children.find((child) => this.pathsEqual(child.path, targetPath));
    if (exactChild) {
      this.treeControl.expand(node);
      this.selectedFolderNode = exactChild;
      this.currentFiles = [...exactChild.files];
      if (!exactChild.loaded) {
        this.loadFolderNode(exactChild);
      }
      this.clearPendingFolderPathRestore();
      this.persistUiState();
      return;
    }

    const ancestorChild = node.children.find((child) => this.isPathAncestor(child.path, targetPath));
    if (ancestorChild && !ancestorChild.loaded) {
      this.treeControl.expand(node);
      this.loadFolderNode(ancestorChild);
    }
  }

  private clearPendingFolderPathRestore(): void {
    this.pendingSelectedFolderPath = null;
    this.hasPendingSelectionRestore = this.pendingRestoreFolderPaths.size > 0 || this.pendingRestoreFilePaths.size > 0;
  }

  private pathsEqual(left: string, right: string): boolean {
    return this.normalizePath(left) === this.normalizePath(right);
  }

  private isPathAncestor(candidateAncestor: string, target: string): boolean {
    const ancestor = this.normalizePath(candidateAncestor);
    const fullTarget = this.normalizePath(target);
    return fullTarget.startsWith(`${ancestor}\\`);
  }

  private normalizePath(path: string): string {
    return path.trim().replace(/\//g, '\\').replace(/\\+$/, '').toLowerCase();
  }

  getDriveDisplayLabel(drive: LogicalDriveInfo): string {
    const label = (drive.label ?? '').trim();
    if (label) {
      return label;
    }

    const type = (drive.type ?? '').trim();
    if (type.toLowerCase().includes('removable')) {
      return 'USB Drive';
    }

    return type || 'Drive';
  }
}
