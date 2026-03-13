package com.cipherforge.services;

import com.cipherforge.dto.AuthLoginRequest;
import com.cipherforge.dto.AuthRegisterRequest;
import com.cipherforge.dto.AuthResponse;
import com.cipherforge.entities.Role;
import com.cipherforge.entities.User;
import com.cipherforge.exception.BadRequestException;
import com.cipherforge.exception.UnauthorizedException;
import com.cipherforge.repositories.UserRepository;
import com.cipherforge.security.JwtService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthService {

    private static final Logger log = LoggerFactory.getLogger(AuthService.class);
    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final AuthenticationManager authenticationManager;
    private final JwtService jwtService;

    public AuthService(
            UserRepository userRepository,
            PasswordEncoder passwordEncoder,
            AuthenticationManager authenticationManager,
            JwtService jwtService
    ) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.authenticationManager = authenticationManager;
        this.jwtService = jwtService;
    }

    @Transactional
    public AuthResponse register(AuthRegisterRequest request) {
        if (userRepository.existsByUsername(request.username())) {
            throw new BadRequestException("Username is already taken");
        }
        if (userRepository.existsByEmail(request.email())) {
            throw new BadRequestException("Email is already registered");
        }

        User user = new User();
        user.setUsername(request.username().trim());
        user.setEmail(request.email().trim().toLowerCase());
        user.setPasswordHash(passwordEncoder.encode(request.password()));
        user.setRole(Role.OPERATOR);
        User saved = userRepository.save(user);

        String token = jwtService.generateToken(saved);
        log.info("User registered: {}", saved.getUsername());
        return new AuthResponse(token, saved.getUsername(), saved.getRole().name());
    }

    public AuthResponse login(AuthLoginRequest request) {
        String username = request.username() == null ? "" : request.username().trim();

        if (username.isEmpty() || request.password() == null) {
            throw new UnauthorizedException("Invalid username or password");
        }

        try {
            authenticationManager.authenticate(
                    new UsernamePasswordAuthenticationToken(username, request.password())
            );
        } catch (AuthenticationException ex) {
            throw new UnauthorizedException("Invalid username or password");
        }

        User user = userRepository.findByUsername(username)
                .orElseThrow(() -> new UnauthorizedException("Invalid username or password"));
        String token = jwtService.generateToken(user);
        return new AuthResponse(token, user.getUsername(), user.getRole().name());
    }
}


