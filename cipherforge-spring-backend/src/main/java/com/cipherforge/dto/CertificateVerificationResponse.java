package com.cipherforge.dto;

import java.time.OffsetDateTime;

public record CertificateVerificationResponse(
        String device,
        String wipeMethod,
        OffsetDateTime timestamp,
        String verificationStatus
) {
}
