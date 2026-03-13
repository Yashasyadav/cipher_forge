package com.cipherforge.controllers;

import com.cipherforge.dto.CertificateListItemResponse;
import com.cipherforge.services.CertificateService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/certificates")
public class CertificateController {

    private final CertificateService certificateService;

    public CertificateController(CertificateService certificateService) {
        this.certificateService = certificateService;
    }

    @GetMapping
    public List<CertificateListItemResponse> list() {
        return certificateService.listCertificates();
    }
}

