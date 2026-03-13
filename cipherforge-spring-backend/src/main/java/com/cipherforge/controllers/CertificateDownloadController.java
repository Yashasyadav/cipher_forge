package com.cipherforge.controllers;

import com.cipherforge.services.CertificateService;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/certificate")
public class CertificateDownloadController {

    private final CertificateService certificateService;

    public CertificateDownloadController(CertificateService certificateService) {
        this.certificateService = certificateService;
    }

    @GetMapping("/download/{jobId}")
    public ResponseEntity<ByteArrayResource> download(@PathVariable String jobId) {
        CertificateService.CertificatePdfResult pdf = certificateService.loadCertificatePdfByJobId(jobId);
        ByteArrayResource resource = new ByteArrayResource(pdf.content());

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_PDF)
                .contentLength(pdf.content().length)
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"" + pdf.fileName() + "\"")
                .body(resource);
    }

    @GetMapping("/download-json/{jobId}")
    public ResponseEntity<ByteArrayResource> downloadJson(@PathVariable String jobId) {
        CertificateService.CertificateJsonResult json = certificateService.loadCertificateJsonByJobId(jobId);
        ByteArrayResource resource = new ByteArrayResource(json.content());

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .contentLength(json.content().length)
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"" + json.fileName() + "\"")
                .body(resource);
    }
}
