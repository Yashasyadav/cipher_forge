package com.cipherforge;

import com.cipherforge.client.WipeEngineClient;
import com.cipherforge.dto.AuthResponse;
import com.cipherforge.dto.WipeJobStatusResponse;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class CipherForgeWorkflowIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private WipeEngineClient wipeEngineClient;

    private Path tempPdfPath;

    @BeforeEach
    void setupEngineMocks() throws Exception {
        tempPdfPath = Files.createTempFile("cipherforge-cert-", ".pdf");
        Files.writeString(tempPdfPath, "%PDF-1.4\n% CipherForge test PDF\n");

        when(wipeEngineClient.getDevices()).thenReturn(List.of(
                new WipeEngineClient.EngineDeviceDto("sda", "SSD", "512GB", "SSD123"),
                new WipeEngineClient.EngineDeviceDto("sdb", "HDD", "1TB", "HDD456")
        ));

        // Keep backward-compatible alias safe for older call sites.
        when(wipeEngineClient.fetchDevices()).thenReturn(List.of(
                new WipeEngineClient.EngineDeviceDto("sda", "SSD", "512GB", "SSD123"),
                new WipeEngineClient.EngineDeviceDto("sdb", "HDD", "1TB", "HDD456")
        ));

        String now = OffsetDateTime.now().toString();
        when(wipeEngineClient.startWipe("sda", "DoD")).thenReturn(
                new WipeEngineClient.EngineWipeStartDto(
                        "engine-job-001", "sda", "DoD", "DoD", "RUNNING", 10.0,
                        now, null, null, "started", null
                )
        );

        when(wipeEngineClient.getWipeStatus("engine-job-001")).thenReturn(
                new WipeEngineClient.EngineWipeStatusDto(
                        "engine-job-001", "sda", "DoD", "DoD", "COMPLETED", 100.0,
                        now, now, "cert-001", "done", null
                )
        );

        when(wipeEngineClient.fetchCertificateByJobId("engine-job-001")).thenReturn(
                new WipeEngineClient.EngineCertificateDto(
                        "cert-001",
                        "engine-job-001",
                        "sda",
                        "SSD123",
                        "SSD",
                        "DoD",
                        3,
                        now,
                        "PASSED",
                        0,
                        "abc123hash",
                        "certificates/cert-001.json",
                        tempPdfPath.toString()
                )
        );

        // Keep legacy certificate lookup safe if invoked by other paths.
        when(wipeEngineClient.fetchCertificate(anyString())).thenReturn(
                new WipeEngineClient.EngineCertificateDto(
                        "cert-001",
                        "engine-job-001",
                        "sda",
                        "SSD123",
                        "SSD",
                        "DoD",
                        3,
                        now,
                        "PASSED",
                        0,
                        "abc123hash",
                        "certificates/cert-001.json",
                        tempPdfPath.toString()
                )
        );
    }

    @Test
    void should_execute_full_wipe_to_certificate_workflow() throws Exception {
        String token = loginAndGetToken("admin", "admin12345");

        mockMvc.perform(get("/devices")
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].deviceName").value("sda"))
                .andExpect(jsonPath("$[1].deviceName").value("sdb"));

        String startResponseJson = mockMvc.perform(post("/wipe/start")
                        .header(HttpHeaders.AUTHORIZATION, bearer(token))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"device\":\"sda\",\"method\":\"DoD\"}"))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.jobId").isString())
                .andExpect(jsonPath("$.engineJobId").value("engine-job-001"))
                .andReturn()
                .getResponse()
                .getContentAsString();

        WipeJobStatusResponse startedJob = objectMapper.readValue(startResponseJson, WipeJobStatusResponse.class);

        mockMvc.perform(get("/wipe/status/{jobId}", startedJob.jobId())
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("COMPLETED"));

        String certsJson = mockMvc.perform(get("/certificates")
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].jobId").value(startedJob.jobId()))
                .andExpect(jsonPath("$[0].method").value("DOD"))
                .andExpect(jsonPath("$[0].verificationStatus").value("PASSED"))
                .andReturn()
                .getResponse()
                .getContentAsString();

        List<Map<String, Object>> certificates = objectMapper.readValue(certsJson, new TypeReference<>() {});
        assertThat(certificates).isNotEmpty();

        mockMvc.perform(get("/certificate/download/{jobId}", startedJob.jobId())
                        .header(HttpHeaders.AUTHORIZATION, bearer(token)))
                .andExpect(status().isOk())
                .andExpect(content().contentType(MediaType.APPLICATION_PDF));
    }

    private String loginAndGetToken(String username, String password) throws Exception {
        String loginJson = objectMapper.writeValueAsString(Map.of(
                "username", username,
                "password", password
        ));

        String response = mockMvc.perform(post("/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginJson))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.token").isString())
                .andReturn()
                .getResponse()
                .getContentAsString();

        AuthResponse authResponse = objectMapper.readValue(response, AuthResponse.class);
        return authResponse.token();
    }

    private String bearer(String token) {
        return "Bearer " + token;
    }
}
