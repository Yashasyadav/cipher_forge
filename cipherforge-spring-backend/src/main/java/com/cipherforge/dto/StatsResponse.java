package com.cipherforge.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public record StatsResponse(
        @JsonProperty("devices_wiped") long devicesWiped,
        @JsonProperty("certificates_generated") long certificatesGenerated,
        @JsonProperty("failed_jobs") long failedJobs,
        @JsonProperty("active_jobs") long activeJobs
) {
}


