package com.cipherforge.controllers;

import com.cipherforge.dto.CertificateVerificationResponse;
import com.cipherforge.services.CertificateService;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.HtmlUtils;

@RestController
public class VerificationController {

    private final CertificateService certificateService;

    public VerificationController(CertificateService certificateService) {
        this.certificateService = certificateService;
    }

    @GetMapping("/verify/{certificateId}")
    public ResponseEntity<?> verifyCertificate(
            @PathVariable String certificateId,
            @RequestParam(value = "view", required = false) String view,
            @RequestHeader(value = "Accept", required = false, defaultValue = "") String accept
    ) {
        CertificateVerificationResponse response = certificateService.getVerification(certificateId);

        boolean wantsHtml = "html".equalsIgnoreCase(view) || accept.toLowerCase().contains(MediaType.TEXT_HTML_VALUE);
        if (wantsHtml) {
            return ResponseEntity.ok()
                    .contentType(MediaType.TEXT_HTML)
                    .body(renderHtml(certificateId, response));
        }
        return ResponseEntity.ok(response);
    }

    private String renderHtml(String certificateId, CertificateVerificationResponse response) {
        boolean isAuthentic = "PASSED".equalsIgnoreCase(response.verificationStatus());
        String statusClass = isAuthentic ? "ok" : "bad";
        String authenticity = isAuthentic ? "Certificate is authentic" : "Certificate failed verification";

        return """
                <!doctype html>
                <html lang="en">
                <head>
                  <meta charset="utf-8" />
                  <meta name="viewport" content="width=device-width, initial-scale=1" />
                  <title>CipherForge Verification</title>
                  <style>
                    body {
                      margin: 0;
                      font-family: 'Segoe UI', Tahoma, sans-serif;
                      background: linear-gradient(135deg, #e6f4f7 0%, #f7fbfc 100%);
                      color: #1c2f3f;
                      min-height: 100vh;
                      display: grid;
                      place-items: center;
                      padding: 24px;
                    }
                    .card {
                      width: min(720px, 100%);
                      background: #ffffff;
                      border: 1px solid #dbe5ed;
                      border-radius: 16px;
                      box-shadow: 0 10px 30px rgba(15, 40, 64, 0.12);
                      padding: 24px;
                    }
                    h1 {
                      margin: 0 0 8px;
                      font-size: 1.5rem;
                    }
                    .meta {
                      color: #607387;
                      margin-bottom: 20px;
                      font-size: 0.92rem;
                    }
                    .banner {
                      margin: 0 0 18px;
                      padding: 10px 12px;
                      border-radius: 10px;
                      font-weight: 600;
                      border: 1px solid #e3eaf1;
                      background: #f8fbff;
                    }
                    .grid {
                      display: grid;
                      gap: 12px;
                      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                    }
                    .item {
                      border: 1px solid #e3eaf1;
                      border-radius: 10px;
                      padding: 12px;
                      background: #fbfdff;
                    }
                    .label {
                      font-size: 0.82rem;
                      color: #607387;
                    }
                    .value {
                      margin-top: 4px;
                      font-size: 1rem;
                      font-weight: 600;
                    }
                    .ok {
                      color: #0a7f37;
                    }
                    .bad {
                      color: #b42318;
                    }
                  </style>
                </head>
                <body>
                  <section class="card">
                    <h1>Certificate Verification</h1>
                    <p class="meta">Certificate ID: %s</p>
                    <p class="banner %s">%s</p>
                    <div class="grid">
                      <div class="item">
                        <div class="label">Device</div>
                        <div class="value">%s</div>
                      </div>
                      <div class="item">
                        <div class="label">Wipe Method</div>
                        <div class="value">%s</div>
                      </div>
                      <div class="item">
                        <div class="label">Timestamp</div>
                        <div class="value">%s</div>
                      </div>
                      <div class="item">
                        <div class="label">Verification Status</div>
                        <div class="value %s">%s</div>
                      </div>
                    </div>
                  </section>
                </body>
                </html>
                """.formatted(
                HtmlUtils.htmlEscape(certificateId),
                statusClass,
                HtmlUtils.htmlEscape(authenticity),
                HtmlUtils.htmlEscape(response.device()),
                HtmlUtils.htmlEscape(response.wipeMethod()),
                HtmlUtils.htmlEscape(String.valueOf(response.timestamp())),
                statusClass,
                HtmlUtils.htmlEscape(response.verificationStatus())
        );
    }
}
