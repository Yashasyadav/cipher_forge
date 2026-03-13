package com.cipherforge.dto;

import java.time.OffsetDateTime;

public record DeviceResponse(
        Long id,
        String deviceName,
        String deviceType,
        String size,
        String serialNumber,
        OffsetDateTime lastSeenAt
) {
}


