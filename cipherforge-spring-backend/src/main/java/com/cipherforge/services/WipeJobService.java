package com.cipherforge.services;

import com.cipherforge.client.WipeEngineClient;
import com.cipherforge.dto.WipeJobStatusResponse;
import com.cipherforge.dto.WipeStartRequest;
import com.cipherforge.entities.Certificate;
import com.cipherforge.entities.Device;
import com.cipherforge.entities.WipeJob;
import com.cipherforge.entities.WipeJobStatus;
import com.cipherforge.entities.WipeMethodType;
import com.cipherforge.exception.BadRequestException;
import com.cipherforge.exception.ExternalServiceException;
import com.cipherforge.exception.ResourceNotFoundException;
import com.cipherforge.repositories.CertificateRepository;
import com.cipherforge.repositories.WipeJobRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.EnumSet;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class WipeJobService {

    private static final Logger log = LoggerFactory.getLogger(WipeJobService.class);
    private final WipeJobRepository wipeJobRepository;
    private final CertificateRepository certificateRepository;
    private final DeviceService deviceService;
    private final WipeEngineClient engineClient;
    private final ProgressBroadcastService progressBroadcastService;
    private final ObjectMapper objectMapper;

    public WipeJobService(
            WipeJobRepository wipeJobRepository,
            CertificateRepository certificateRepository,
            DeviceService deviceService,
            WipeEngineClient engineClient,
            ProgressBroadcastService progressBroadcastService,
            ObjectMapper objectMapper
    ) {
        this.wipeJobRepository = wipeJobRepository;
        this.certificateRepository = certificateRepository;
        this.deviceService = deviceService;
        this.engineClient = engineClient;
        this.progressBroadcastService = progressBroadcastService;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public WipeJobStatusResponse startWipe(WipeStartRequest request) {
        String normalizedDevice = request.device().trim();
        MethodMapping methodMapping = mapMethod(request.method());

        Device device = deviceService.getOrSyncByEngineName(normalizedDevice);
        WipeEngineClient.EngineWipeStartDto engineJob = engineClient.startWipe(normalizedDevice, methodMapping.engineValue());
        if (engineJob.job_id() == null || engineJob.job_id().isBlank()) {
            throw new BadRequestException("Wipe engine did not return a valid job id");
        }

        WipeJob job = new WipeJob();
        job.setDevice(device);
        job.setWipeMethod(methodMapping.localType());
        job.setStatus(mapStatus(engineJob.status()));
        job.setProgress(engineJob.progress());
        job.setEngineJobId(engineJob.job_id());
        job.setStartTime(parseDateTime(engineJob.start_time()));
        job.setEndTime(parseDateTime(engineJob.end_time()));
        job.setErrorMessage(engineJob.error());

        wipeJobRepository.save(job);
        progressBroadcastService.broadcast(job, findCertificateId(job.getId()));
        log.info("Started wipe job localId={} engineId={} device={}", job.getId(), job.getEngineJobId(), normalizedDevice);
        return toResponse(job);
    }

    @Transactional
    public WipeJobStatusResponse getStatus(String jobId) {
        WipeJob job = wipeJobRepository.findById(jobId)
                .orElseThrow(() -> new ResourceNotFoundException("Wipe job not found: " + jobId));

        try {
            WipeEngineClient.EngineWipeStatusDto engineStatus = engineClient.getWipeStatus(job.getEngineJobId());
            applyEngineStatus(job, engineStatus);

            wipeJobRepository.save(job);
            progressBroadcastService.broadcast(job, findCertificateId(job.getId()));
        } catch (ExternalServiceException ex) {
            if (isEngineJobMissing(ex)) {
                markAsFailedMissingEngineJob(job, ex);
                return toResponse(job);
            }
            log.warn("Wipe engine status sync failed for localId={} engineId={}. Returning last known DB state.",
                    job.getId(), job.getEngineJobId(), ex);
        }

        return toResponse(job);
    }

    @Transactional(readOnly = true)
    public List<WipeJobStatusResponse> listJobs() {
        return wipeJobRepository.findAll().stream()
                .sorted(
                        Comparator
                                .comparing(WipeJob::getStartTime, Comparator.nullsLast(Comparator.reverseOrder()))
                                .thenComparing(WipeJob::getId, Comparator.reverseOrder())
                )
                .map(this::toResponse)
                .toList();
    }

    public List<String> listSupportedMethods() {
        return List.of("DoD", "NIST", "Gutmann");
    }

    @Scheduled(fixedDelayString = "${cipherforge.wipe-sync.fixed-delay-ms:5000}")
    @Transactional
    public void syncRunningJobProgress() {
        List<WipeJob> activeJobs = wipeJobRepository.findByStatusIn(EnumSet.of(WipeJobStatus.QUEUED, WipeJobStatus.RUNNING));
        for (WipeJob job : activeJobs) {
            if (isSeedEngineJob(job.getEngineJobId())) {
                markAsFailedSeedEngineJob(job);
                continue;
            }
            try {
                WipeEngineClient.EngineWipeStatusDto engineStatus = engineClient.getWipeStatus(job.getEngineJobId());
                applyEngineStatus(job, engineStatus);
                wipeJobRepository.save(job);
                progressBroadcastService.broadcast(job, findCertificateId(job.getId()));
            } catch (ExternalServiceException ex) {
                if (isEngineJobMissing(ex)) {
                    markAsFailedMissingEngineJob(job, ex);
                    continue;
                }
                log.debug("Background sync skipped for localId={} engineId={}: {}", job.getId(), job.getEngineJobId(), ex.getMessage());
            } catch (Exception ex) {
                log.warn("Unexpected failure while syncing job localId={} engineId={}", job.getId(), job.getEngineJobId(), ex);
            }
        }
    }

    @Scheduled(fixedDelayString = "${cipherforge.certificate-sync.fixed-delay-ms:7000}")
    @Transactional
    public void syncCompletedJobsMissingCertificates() {
        List<WipeJob> completedJobs = wipeJobRepository.findByStatusIn(EnumSet.of(WipeJobStatus.COMPLETED));
        for (WipeJob job : completedJobs) {
            if (certificateRepository.findByWipeJob_Id(job.getId()).isPresent()) {
                continue;
            }
            try {
                syncCertificate(job, null);
                progressBroadcastService.broadcast(job, findCertificateId(job.getId()));
            } catch (ExternalServiceException ex) {
                log.debug(
                        "Certificate still unavailable for localId={} engineId={}: {}",
                        job.getId(),
                        job.getEngineJobId(),
                        ex.getMessage()
                );
            } catch (Exception ex) {
                log.warn(
                        "Unexpected certificate backfill error for localId={} engineId={}",
                        job.getId(),
                        job.getEngineJobId(),
                        ex
                );
            }
        }
    }

    private void applyEngineStatus(WipeJob job, WipeEngineClient.EngineWipeStatusDto engineStatus) {
        job.setStatus(mapStatus(engineStatus.status()));
        job.setProgress(engineStatus.progress());
        job.setStartTime(parseDateTime(engineStatus.start_time()));
        job.setEndTime(parseDateTime(engineStatus.end_time()));
        job.setErrorMessage(engineStatus.error());

        if (job.getStatus() == WipeJobStatus.COMPLETED) {
            syncCertificateSafely(job, engineStatus.certificate_id());
        }
    }

    private void syncCertificateSafely(WipeJob job, String engineCertificateId) {
        try {
            syncCertificate(job, engineCertificateId);
        } catch (ExternalServiceException ex) {
            // Keep completed status; certificate may become available shortly after completion.
            log.warn(
                    "Certificate sync deferred for localId={} engineId={}: {}",
                    job.getId(),
                    job.getEngineJobId(),
                    ex.getMessage()
            );
        }
    }

    private void syncCertificate(WipeJob job, String engineCertificateId) {
        if (certificateRepository.findByWipeJob_Id(job.getId()).isPresent()) {
            return;
        }

        WipeEngineClient.EngineCertificateDto certDto = engineClient.fetchCertificateByJobId(job.getEngineJobId());
        String resolvedEngineCertificateId = orDefault(certDto.id(), engineCertificateId);
        if (resolvedEngineCertificateId != null && certificateRepository.findByEngineCertificateId(resolvedEngineCertificateId).isPresent()) {
            return;
        }

        Certificate cert = new Certificate();
        cert.setWipeJob(job);
        cert.setEngineCertificateId(orDefault(resolvedEngineCertificateId, job.getEngineJobId()));
        cert.setDeviceSerialNumber(orDefault(certDto.device_serial_number(), job.getDevice().getSerialNumber()));
        cert.setDeviceType(orDefault(certDto.device_type(), job.getDevice().getDeviceType()));
        cert.setWipeMethod(certDto.wipe_method() == null ? job.getWipeMethod() : mapMethod(certDto.wipe_method()).localType());
        cert.setOverwritePasses(certDto.overwrite_passes() == null ? 0 : certDto.overwrite_passes());
        cert.setCertificateTimestamp(parseDateTime(certDto.timestamp()));
        cert.setVerificationStatus(orDefault(certDto.verification_status(), "UNKNOWN"));
        cert.setRecoveredFiles(certDto.recovered_files() == null ? 0 : certDto.recovered_files());
        cert.setSha256Hash(orDefault(certDto.sha256_hash(), ""));
        cert.setJsonPath(orDefault(certDto.json_path(), ""));
        cert.setPdfPath(orDefault(certDto.pdf_path(), ""));
        cert.setRawPayload(serializeCertificatePayload(certDto));
        certificateRepository.save(cert);
        log.info("Synced certificate engineJobId={} for localJob={}", job.getEngineJobId(), job.getId());
    }

    private String serializeCertificatePayload(WipeEngineClient.EngineCertificateDto certDto) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("id", certDto.id());
        payload.put("job_id", certDto.job_id());
        payload.put("device", certDto.device());
        payload.put("device_serial_number", certDto.device_serial_number());
        payload.put("device_type", certDto.device_type());
        payload.put("wipe_method", certDto.wipe_method());
        payload.put("overwrite_passes", certDto.overwrite_passes());
        payload.put("timestamp", certDto.timestamp());
        payload.put("verification_status", certDto.verification_status());
        payload.put("recovered_files", certDto.recovered_files());
        payload.put("sha256_hash", certDto.sha256_hash());
        payload.put("json_path", certDto.json_path());
        payload.put("pdf_path", certDto.pdf_path());
        try {
            return objectMapper.writeValueAsString(payload);
        } catch (JsonProcessingException e) {
            return payload.toString();
        }
    }

    private WipeJobStatusResponse toResponse(WipeJob job) {
        String certId = findCertificateId(job.getId());

        return new WipeJobStatusResponse(
                job.getId(),
                job.getEngineJobId(),
                job.getDevice().getEngineDeviceName(),
                job.getWipeMethod().name(),
                job.getStatus().name(),
                job.getProgress(),
                job.getStartTime(),
                job.getEndTime(),
                certId,
                job.getErrorMessage()
        );
    }

    private String findCertificateId(String jobId) {
        return certificateRepository.findByWipeJob_Id(jobId)
                .map(Certificate::getId)
                .orElse(null);
    }

    private MethodMapping mapMethod(String input) {
        String normalized = input == null ? "" : input.trim().toUpperCase();
        return switch (normalized) {
            case "NIST", "NIST CLEAR" -> new MethodMapping(WipeMethodType.NIST, "NIST");
            case "DOD", "DOD 5220.22-M" -> new MethodMapping(WipeMethodType.DOD, "DoD");
            case "GUTMANN", "GUTMANN METHOD" -> new MethodMapping(WipeMethodType.GUTMANN, "Gutmann");
            default -> throw new BadRequestException("Unsupported wipe method: " + input);
        };
    }

    private WipeJobStatus mapStatus(String status) {
        String normalized = status == null ? "" : status.trim().toUpperCase();
        return switch (normalized) {
            case "QUEUED" -> WipeJobStatus.QUEUED;
            case "RUNNING" -> WipeJobStatus.RUNNING;
            case "COMPLETED" -> WipeJobStatus.COMPLETED;
            case "FAILED" -> WipeJobStatus.FAILED;
            default -> WipeJobStatus.QUEUED;
        };
    }

    private OffsetDateTime parseDateTime(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return OffsetDateTime.parse(value);
        } catch (DateTimeParseException ex) {
            return null;
        }
    }

    private String orDefault(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value;
    }

    private boolean isEngineJobMissing(ExternalServiceException ex) {
        String message = ex.getMessage();
        return message != null && message.startsWith("Wipe engine status lookup failed: HTTP 404");
    }

    private void markAsFailedMissingEngineJob(WipeJob job, ExternalServiceException ex) {
        job.setStatus(WipeJobStatus.FAILED);
        job.setEndTime(OffsetDateTime.now());
        job.setErrorMessage("Engine job not found: " + job.getEngineJobId());
        wipeJobRepository.save(job);
        progressBroadcastService.broadcast(job, findCertificateId(job.getId()));
        log.warn(
                "Marked local job {} as FAILED because wipe engine job {} was not found (404): {}",
                job.getId(),
                job.getEngineJobId(),
                ex.getMessage()
        );
    }

    private boolean isSeedEngineJob(String engineJobId) {
        return engineJobId != null && engineJobId.startsWith("seed-engine-job-");
    }

    private void markAsFailedSeedEngineJob(WipeJob job) {
        job.setStatus(WipeJobStatus.FAILED);
        job.setEndTime(OffsetDateTime.now());
        job.setErrorMessage("Seed engine job is not available in live wipe engine");
        wipeJobRepository.save(job);
        progressBroadcastService.broadcast(job, findCertificateId(job.getId()));
        log.info("Auto-closed stale seed engine job localId={} engineId={}", job.getId(), job.getEngineJobId());
    }

    private record MethodMapping(WipeMethodType localType, String engineValue) {
    }
}
