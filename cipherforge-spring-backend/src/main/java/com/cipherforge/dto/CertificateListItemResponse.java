package com.cipherforge.dto;

import java.time.OffsetDateTime;

public record CertificateListItemResponse(
        String id,
        String jobId,
        String method,
        String verificationStatus,
        int recoveredFiles,
        OffsetDateTime timestamp
) {
}

