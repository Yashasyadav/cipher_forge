package com.cipherforge.dto;

import jakarta.validation.constraints.NotBlank;

public record WipeStartRequest(
        @NotBlank String device,
        @NotBlank String method
) {
}


