package com.cipherforge.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record AuthRegisterRequest(
        @NotBlank @Size(min = 3, max = 100) String username,
        @NotBlank @Email @Size(max = 200) String email,
        @NotBlank @Size(min = 8, max = 200) String password
) {
}


