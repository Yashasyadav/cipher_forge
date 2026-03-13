package com.cipherforge.services;

import com.cipherforge.dto.CertificateListItemResponse;
import com.cipherforge.dto.CertificateVerificationResponse;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.cipherforge.entities.Certificate;
import com.cipherforge.exception.ResourceNotFoundException;
import com.cipherforge.repositories.CertificateRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;

@Service
public class CertificateService {

    private final CertificateRepository certificateRepository;
    private final ObjectMapper objectMapper;

    public CertificateService(CertificateRepository certificateRepository, ObjectMapper objectMapper) {
        this.certificateRepository = certificateRepository;
        this.objectMapper = objectMapper;
    }

    @Transactional(readOnly = true)
    public List<CertificateListItemResponse> listCertificates() {
        return certificateRepository.findAll().stream()
                .map(this::toResponse)
                .toList();
    }

    @Transactional(readOnly = true)
    public CertificatePdfResult loadCertificatePdfByJobId(String jobId) {
        Certificate certificate = findCertificateByJobId(jobId);

        Path filePath = resolvePdfPath(certificate.getPdfPath());
        try {
            byte[] content = Files.readAllBytes(filePath);
            return new CertificatePdfResult(filePath.getFileName().toString(), content);
        } catch (IOException ex) {
            throw new ResourceNotFoundException("Certificate PDF is unavailable for job: " + jobId);
        }
    }

    @Transactional(readOnly = true)
    public CertificateJsonResult loadCertificateJsonByJobId(String jobId) {
        Certificate certificate = findCertificateByJobId(jobId);

        String rawJsonPayload = readRawJsonPayload(certificate, jobId);
        byte[] normalized = buildJsonWithQrPayload(certificate, rawJsonPayload);
        String fileName = resolveJsonFileName(certificate, jobId);
        return new CertificateJsonResult(fileName, normalized);
    }

    @Transactional(readOnly = true)
    public CertificateVerificationResponse getVerification(String certificateId) {
        Certificate certificate = certificateRepository.findByEngineCertificateId(certificateId)
                .or(() -> certificateRepository.findById(certificateId))
                .orElseThrow(() -> new ResourceNotFoundException("Certificate not found: " + certificateId));

        String deviceName = certificate.getWipeJob() != null
                && certificate.getWipeJob().getDevice() != null
                ? certificate.getWipeJob().getDevice().getEngineDeviceName()
                : certificate.getDeviceSerialNumber();

        return new CertificateVerificationResponse(
                deviceName,
                certificate.getWipeMethod().name(),
                certificate.getCertificateTimestamp(),
                certificate.getVerificationStatus()
        );
    }

    private CertificateListItemResponse toResponse(Certificate c) {
        return new CertificateListItemResponse(
                c.getId(),
                c.getWipeJob().getId(),
                c.getWipeMethod().name(),
                c.getVerificationStatus(),
                c.getRecoveredFiles(),
                c.getCertificateTimestamp()
        );
    }

    private Certificate findCertificateByJobId(String jobId) {
        return certificateRepository.findByWipeJob_Id(jobId)
                .or(() -> certificateRepository.findById(jobId))
                .orElseThrow(() -> new ResourceNotFoundException("Certificate not found for job: " + jobId));
    }

    private String readRawJsonPayload(Certificate certificate, String jobId) {
        if (certificate.getJsonPath() != null && !certificate.getJsonPath().isBlank()) {
            try {
                Path jsonPath = resolveJsonPath(certificate.getJsonPath());
                return Files.readString(jsonPath);
            } catch (IOException ignored) {
                // Fall back to raw payload when json file is unavailable.
            }
        }

        if (certificate.getRawPayload() != null && !certificate.getRawPayload().isBlank()) {
            return certificate.getRawPayload();
        }

        throw new ResourceNotFoundException("Certificate JSON is unavailable for job: " + jobId);
    }

    private String resolveJsonFileName(Certificate certificate, String jobId) {
        if (certificate.getJsonPath() != null && !certificate.getJsonPath().isBlank()) {
            try {
                Path jsonPath = resolveJsonPath(certificate.getJsonPath());
                return jsonPath.getFileName().toString();
            } catch (ResourceNotFoundException ignored) {
                // Fall back to deterministic name when path does not resolve.
            }
        }
        return "certificate-" + jobId + ".json";
    }

    private byte[] buildJsonWithQrPayload(Certificate certificate, String rawJsonPayload) {
        try {
            JsonNode payloadNode;
            try {
                payloadNode = objectMapper.readTree(rawJsonPayload);
            } catch (IOException ex) {
                payloadNode = objectMapper.getNodeFactory().textNode(rawJsonPayload);
            }

            ObjectNode root = objectMapper.createObjectNode();
            root.put("certificateId", certificate.getId());
            root.put("engineCertificateId", certificate.getEngineCertificateId());
            root.put("jobId", certificate.getWipeJob() != null ? certificate.getWipeJob().getId() : "");
            root.put("verificationStatus", certificate.getVerificationStatus());
            root.put("wipeMethod", certificate.getWipeMethod().name());
            root.put("timestamp", certificate.getCertificateTimestamp().toString());
            root.set("payload", payloadNode);

            ObjectNode qrCode = root.putObject("qrCode");
            qrCode.put("verificationUrl", "/verify/" + certificate.getEngineCertificateId());
            qrCode.put("certificateId", certificate.getEngineCertificateId());
            qrCode.put("verificationStatus", certificate.getVerificationStatus());

            return objectMapper.writerWithDefaultPrettyPrinter().writeValueAsBytes(root);
        } catch (IOException ex) {
            throw new ResourceNotFoundException("Certificate JSON payload could not be prepared");
        }
    }

    private Path resolvePdfPath(String pdfPath) {
        if (pdfPath == null || pdfPath.isBlank()) {
            throw new ResourceNotFoundException("Certificate PDF path is missing");
        }

        Path rawPath = Paths.get(pdfPath).normalize();
        if (rawPath.isAbsolute() && Files.exists(rawPath) && Files.isRegularFile(rawPath)) {
            return rawPath;
        }

        Path cwd = Paths.get(System.getProperty("user.dir")).toAbsolutePath().normalize();
        Path candidateInCwd = cwd.resolve(rawPath).normalize();
        if (Files.exists(candidateInCwd) && Files.isRegularFile(candidateInCwd)) {
            return candidateInCwd;
        }

        Path parent = cwd.getParent();
        if (parent != null) {
            Path candidateInParent = parent.resolve(rawPath).normalize();
            if (Files.exists(candidateInParent) && Files.isRegularFile(candidateInParent)) {
                return candidateInParent;
            }
        }

        throw new ResourceNotFoundException("Certificate PDF file not found");
    }

    private Path resolveJsonPath(String jsonPath) {
        if (jsonPath == null || jsonPath.isBlank()) {
            throw new ResourceNotFoundException("Certificate JSON path is missing");
        }

        Path rawPath = Paths.get(jsonPath).normalize();
        if (rawPath.isAbsolute() && Files.exists(rawPath) && Files.isRegularFile(rawPath)) {
            return rawPath;
        }

        Path cwd = Paths.get(System.getProperty("user.dir")).toAbsolutePath().normalize();
        Path candidateInCwd = cwd.resolve(rawPath).normalize();
        if (Files.exists(candidateInCwd) && Files.isRegularFile(candidateInCwd)) {
            return candidateInCwd;
        }

        Path parent = cwd.getParent();
        if (parent != null) {
            Path candidateInParent = parent.resolve(rawPath).normalize();
            if (Files.exists(candidateInParent) && Files.isRegularFile(candidateInParent)) {
                return candidateInParent;
            }
        }

        throw new ResourceNotFoundException("Certificate JSON file not found");
    }

    public record CertificatePdfResult(String fileName, byte[] content) {
    }

    public record CertificateJsonResult(String fileName, byte[] content) {
    }
}
