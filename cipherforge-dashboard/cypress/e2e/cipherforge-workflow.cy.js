describe('CipherForge end-to-end workflow', () => {
  const username = 'admin';
  const password = 'admin12345';

  it('runs detect -> wipe -> progress -> certificate flow', () => {
    cy.intercept('GET', '**/devices').as('getDevices');
    cy.intercept('GET', '**/wipe/methods').as('getWipeMethods');
    cy.intercept('POST', '**/wipe/start').as('startWipe');
    cy.intercept('GET', '**/wipe/jobs').as('getWipeJobs');
    cy.intercept('GET', '**/certificates').as('getCertificates');

    cy.visit('/login');
    cy.contains('h1', 'CipherForge Login').should('be.visible');
    cy.get('input[formControlName="username"]').type(username);
    cy.get('input[formControlName="password"]').type(password);
    cy.contains('button', 'Sign in').click();

    cy.location('pathname', { timeout: 20000 }).should('match', /^\/(dashboard|admin)$/);

    cy.visit('/dashboard');
    cy.wait('@getDevices').its('response.statusCode').should('eq', 200);
    cy.contains('h3', 'Connected Devices').should('be.visible');

    cy.visit('/wipe-control');
    cy.wait('@getDevices').its('response.statusCode').should('eq', 200);
    cy.wait('@getWipeMethods').its('response.statusCode').should('eq', 200);

    cy.get('mat-select[formControlName="device"]').click();
    cy.get('mat-option').first().click();

    cy.get('mat-select[formControlName="method"]').click();
    cy.get('mat-option').first().click();

    cy.contains('button', 'Start Wipe Job').click();
    cy.wait('@startWipe').its('response.statusCode').should('be.oneOf', [200, 202]);

    cy.location('pathname', { timeout: 20000 }).should('eq', '/progress-monitor');
    cy.wait('@getWipeJobs').its('response.statusCode').should('eq', 200);

    cy.get('table tbody tr', { timeout: 20000 }).first().find('td').first().invoke('text').then((jobIdText) => {
      const jobId = jobIdText.trim();
      expect(jobId).to.not.equal('');

      cy.visit('/certificates');

      const assertCertificateAppears = (attempt) => {
        cy.wait('@getCertificates').its('response.statusCode').should('eq', 200);
        cy.get('body').then(($body) => {
          if ($body.text().includes(jobId)) {
            cy.contains('td', jobId).should('be.visible');
            return;
          }

          if (attempt >= 10) {
            throw new Error(`Certificate for job ${jobId} did not appear in time`);
          }

          cy.wait(5000);
          cy.contains('button', 'Refresh').click();
          assertCertificateAppears(attempt + 1);
        });
      };

      assertCertificateAppears(1);
    });
  });
});
