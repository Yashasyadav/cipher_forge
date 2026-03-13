# Cypress E2E Workflow

This suite validates the high-level CipherForge flow:

1. Login as admin
2. Detect devices on Dashboard
3. Start wipe job in Wipe Control
4. Validate progress page receives active jobs
5. Verify certificate appears in Certificates page

## Prerequisites

- Angular app running at `http://localhost:4200`
- Spring backend running at `http://localhost:8080`
- Python wipe engine running and integrated with backend
- Seeded admin user (`admin` / `admin12345`) or update test credentials

## Run

```bash
npm install
npm run e2e
```

To run interactively:

```bash
npm run e2e:open
```
