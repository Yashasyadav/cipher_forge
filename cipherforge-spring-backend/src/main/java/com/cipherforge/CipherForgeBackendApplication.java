package com.cipherforge;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class CipherForgeBackendApplication {

    public static void main(String[] args) {
        SpringApplication.run(CipherForgeBackendApplication.class, args);
    }
}


