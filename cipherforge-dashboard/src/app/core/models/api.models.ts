export interface LogicalDriveInfo {
  drive: string;
  type: string;
  size: string;
  label?: string | null;
}

export interface FileMetadata {
  name: string;
  size: string;
  size_bytes: number;
}

export interface FilesystemBrowseResponse {
  path: string;
  folders: string[];
  files: FileMetadata[];
}
export interface FileWipeRequest {
  path: string;
  method: string;
}

export interface FolderWipeRequest {
  path: string;
  method?: string;
}

export interface FolderWipeJobStatus {
  job_id: string;
  path: string;
  method: string;
  status: string;
  progress: number;
  total_files: number;
  processed_files: number;
  deleted_files: number;
  failed_files: number;
  current_file?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  last_message?: string | null;
  error?: string | null;
}

export interface DeleteResult {
  status: string;
  deleted_files?: number;
  passes?: number;
  verified?: boolean;
  last_message?: string;
  stage_logs?: string[];
  free_space_cleanup?: string;
}
export interface Device {
  id: number;
  deviceName: string;
  deviceType: string;
  size: string;
  serialNumber: string;
  lastSeenAt: string;
}

export interface WipeStartRequest {
  mode?: WipeMode;
  device: string;
  method: string;
}

export interface FileShredStartRequest {
  mode: 'FILE_SHREDDER';
  drive: string;
  targetPath: string;
  method: string;
}

export type WipeMode = 'DEVICE_WIPE' | 'FILE_SHREDDER';

export type UserRole = 'ADMIN' | 'OPERATOR' | 'USER';

export interface AuthLoginRequest {
  username: string;
  password: string;
}

export interface AuthResponse {
  token: string;
  username: string;
  role: UserRole;
}

export interface WipeJobStatus {
  jobId: string;
  engineJobId: string;
  jobType?: 'DEVICE' | 'FILE';
  target?: string;
  device: string;
  wipeMethod: string;
  status: string;
  progress: number;
  startTime?: string | null;
  endTime?: string | null;
  certificateId?: string | null;
  error?: string | null;
}

export interface Certificate {
  id: string;
  jobId: string;
  method: string;
  verificationStatus: string;
  recoveredFiles: number;
  timestamp: string;
}

export interface Stats {
  totalUsers?: number;
  totalDevices?: number;
  totalWipeJobs?: number;
  completedWipeJobs?: number;
  failedWipeJobs?: number;
  totalCertificates?: number;
  devices_wiped?: number;
  successful_wipes?: number;
  failed_jobs?: number;
  certificates?: number;
  certificates_generated?: number;
  active_jobs?: number;
}
