package com.cipherforge.controllers;

import com.cipherforge.dto.WipeJobStatusResponse;
import com.cipherforge.dto.WipeStartRequest;
import com.cipherforge.services.WipeService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/wipe")
public class WipeController {

    private final WipeService wipeService;

    public WipeController(WipeService wipeService) {
        this.wipeService = wipeService;
    }

    @PostMapping("/start")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public WipeJobStatusResponse start(@Valid @RequestBody WipeStartRequest request) {
        return wipeService.startWipe(request);
    }

    @GetMapping("/status/{jobId}")
    public WipeJobStatusResponse status(@PathVariable String jobId) {
        return wipeService.getStatus(jobId);
    }

    @GetMapping("/jobs")
    public List<WipeJobStatusResponse> jobs() {
        return wipeService.listJobs();
    }

    @GetMapping("/methods")
    public List<String> methods() {
        return wipeService.listSupportedMethods();
    }
}


