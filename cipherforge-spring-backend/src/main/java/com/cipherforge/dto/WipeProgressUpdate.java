package com.cipherforge.dto;

import java.time.OffsetDateTime;

public record WipeProgressUpdate(
        String jobId,
        String engineJobId,
        String device,
        String wipeMethod,
        String status,
        double progress,
        OffsetDateTime startTime,
        OffsetDateTime endTime,
        String certificateId,
        String error,
        OffsetDateTime updatedAt
) {
}

