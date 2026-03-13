package com.cipherforge.dto;

import java.time.OffsetDateTime;

public record CertificateResponse(
        String id,
        String jobId,
        String engineCertificateId,
        String deviceSerialNumber,
        String deviceType,
        String wipeMethod,
        int overwritePasses,
        OffsetDateTime timestamp,
        String verificationStatus,
        int recoveredFiles,
        String sha256Hash,
        String jsonPath,
        String pdfPath,
        OffsetDateTime createdAt
) {
}


