package com.cipherforge.dto;

public record AuthResponse(
        String token,
        String username,
        String role
) {
}


